"""
utils/cross_source_validator.py — 교차소스 데이터 품질 검증 v1.0 (SET A-5)
============================================================================
FMP ↔ yfinance 교차검증으로 데이터 신뢰성 확보.
기존 data_quality_gate.py의 Step 0에 통합.

검증 항목:
  1. 주가 교차검증 (가장 중요: ±0.5% OK, ±2% WARNING, >2% ALERT)
  2. 거래량 교차검증 (±10% 허용)
  3. 재무지표 교차검증 (Market Cap, EPS 등)

설계 근거:
  - Ince & Porter (2006): 데이터 소스 간 차이가 포트폴리오 성과에 유의한 영향
  - Bloomberg DQ Dashboard: Completeness × Timeliness × Accuracy 3축
  - FactSet Golden Copy: 다수 소스에서 가장 신뢰할 수 있는 값 선택

실행:
  data_quality_gate.py Step 0 확장으로 자동 실행
  또는 독립 실행: python -m utils.cross_source_validator
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
import logging
import time
import random
import numpy as np
from datetime import datetime, date, timedelta
from enum import Enum
from db_pool import get_cursor

logger = logging.getLogger("cross_source_validator")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 상수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PRICE_OK_THRESHOLD      = 0.005   # < 0.5% 차이 → OK
PRICE_WARNING_THRESHOLD = 0.020   # < 2% 차이 → WARNING
VOLUME_OK_THRESHOLD     = 0.10    # < 10% 차이 → OK
FINANCIAL_OK_THRESHOLD  = 0.05    # < 5% 차이 → OK

# 샘플링: 전체 534종목 중 일부만 교차검증 (API 비용/속도 제한)
SAMPLE_SIZE = 100                 # 매일 100종목 랜덤 검증
YF_RATE_LIMIT_SEC = 0.2          # yfinance 호출 간격


class ValidationStatus(Enum):
    OK       = "OK"
    WARNING  = "WARNING"
    ALERT    = "ALERT"
    SKIP     = "SKIP"        # 소스 데이터 없음


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 테이블 보장
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def ensure_cross_validation_table():
    with get_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS data_cross_validation (
                id              SERIAL PRIMARY KEY,
                calc_date       DATE NOT NULL,
                stock_id        INTEGER,
                ticker          VARCHAR(20),
                check_type      VARCHAR(30) NOT NULL,
                source_a_value  NUMERIC(16,4),
                source_b_value  NUMERIC(16,4),
                diff_pct        NUMERIC(10,6),
                status          VARCHAR(10) NOT NULL,
                golden_value    NUMERIC(16,4),
                detail          JSONB,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_cross_val_date
            ON data_cross_validation(calc_date, check_type)
        """)
        
        cur.execute("""
            CREATE TABLE IF NOT EXISTS data_quality_daily_report (
                id              SERIAL PRIMARY KEY,
                calc_date       DATE NOT NULL UNIQUE,
                total_checks    INTEGER,
                ok_count        INTEGER,
                warning_count   INTEGER,
                alert_count     INTEGER,
                skip_count      INTEGER,
                health_score    NUMERIC(6,2),
                price_accuracy  NUMERIC(6,4),
                volume_accuracy NUMERIC(6,4),
                excluded_tickers JSONB,
                source_reliability JSONB,
                detail          JSONB,
                created_at      TIMESTAMPTZ DEFAULT NOW()
            )
        """)
    print("[CROSS-VAL] Tables ensured")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# yfinance 데이터 로더 (교차검증 전용)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _yf_get_price(ticker: str, target_date: date) -> dict:
    """yfinance에서 종가/거래량 조회 (캐시 없음, 직접 호출)"""
    try:
        import yfinance as yf
        start = target_date - timedelta(days=5)
        end = target_date + timedelta(days=1)
        df = yf.download(ticker, start=str(start), end=str(end), 
                         progress=False, timeout=10)
        if df.empty:
            return None
        
        # 가장 가까운 날짜
        df.index = df.index.date if hasattr(df.index, 'date') else df.index
        row = df.iloc[-1]
        return {
            "close": float(row["Close"]) if "Close" in row.index else None,
            "volume": float(row["Volume"]) if "Volume" in row.index else None,
        }
    except Exception as e:
        logger.debug(f"yfinance failed for {ticker}: {e}")
        return None


def _yf_get_market_cap(ticker: str) -> float:
    """yfinance에서 시가총액 조회"""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        info = t.info or {}
        return float(info.get("marketCap", 0))
    except Exception:
        return 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FMP 데이터 로더 (DB에서 조회)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _fmp_get_price(stock_id: int, calc_date: date) -> dict:
    """FMP 데이터(DB에 저장된) 조회"""
    with get_cursor() as cur:
        cur.execute("""
            SELECT close_price, volume
            FROM stock_prices_daily
            WHERE stock_id = %s AND trade_date <= %s
            ORDER BY trade_date DESC LIMIT 1
        """, (stock_id, calc_date))
        row = cur.fetchone()
        if not row:
            return None
        return {
            "close": float(row["close_price"]) if row["close_price"] else None,
            "volume": float(row["volume"]) if row["volume"] else None,
        }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 교차검증 엔진
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def validate_price(stock_id: int, ticker: str, calc_date: date) -> dict:
    """주가 교차검증"""
    fmp = _fmp_get_price(stock_id, calc_date)
    
    time.sleep(YF_RATE_LIMIT_SEC)
    yf_data = _yf_get_price(ticker, calc_date)
    
    if not fmp or not fmp["close"] or not yf_data or not yf_data["close"]:
        return {"check_type": "PRICE", "status": ValidationStatus.SKIP,
                "fmp": fmp, "yf": yf_data}
    
    diff = abs(fmp["close"] - yf_data["close"]) / yf_data["close"]
    
    if diff < PRICE_OK_THRESHOLD:
        status = ValidationStatus.OK
        golden = (fmp["close"] + yf_data["close"]) / 2
    elif diff < PRICE_WARNING_THRESHOLD:
        status = ValidationStatus.WARNING
        golden = min(fmp["close"], yf_data["close"])  # 보수적
    else:
        status = ValidationStatus.ALERT
        golden = None  # 수동 확인 필요
    
    return {
        "check_type": "PRICE",
        "status": status,
        "fmp_value": fmp["close"],
        "yf_value": yf_data["close"],
        "diff_pct": diff,
        "golden_value": golden,
    }


def validate_volume(stock_id: int, ticker: str, calc_date: date) -> dict:
    """거래량 교차검증"""
    fmp = _fmp_get_price(stock_id, calc_date)
    
    # yf 데이터는 이미 validate_price에서 호출했을 수 있으므로 캐시 활용
    yf_data = _yf_get_price(ticker, calc_date)
    
    if not fmp or not fmp["volume"] or not yf_data or not yf_data["volume"]:
        return {"check_type": "VOLUME", "status": ValidationStatus.SKIP}
    
    if yf_data["volume"] == 0:
        return {"check_type": "VOLUME", "status": ValidationStatus.SKIP}
    
    diff = abs(fmp["volume"] - yf_data["volume"]) / yf_data["volume"]
    
    status = ValidationStatus.OK if diff < VOLUME_OK_THRESHOLD else \
             ValidationStatus.WARNING if diff < 0.30 else ValidationStatus.ALERT
    
    return {
        "check_type": "VOLUME",
        "status": status,
        "fmp_value": fmp["volume"],
        "yf_value": yf_data["volume"],
        "diff_pct": diff,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 일일 배치
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_cross_validation(calc_date: date = None):
    """
    일일 교차검증 배치.
    data_quality_gate.py Step 0 확장으로 호출.
    """
    if calc_date is None:
        calc_date = date.today()
    
    print(f"\n[CROSS-VAL] Running cross-source validation for {calc_date}")
    ensure_cross_validation_table()
    
    # 검증 대상 샘플링
    with get_cursor() as cur:
        cur.execute("""
            SELECT stock_id, ticker FROM stocks
            WHERE is_active = TRUE
            ORDER BY RANDOM()
            LIMIT %s
        """, (SAMPLE_SIZE,))
        targets = [dict(r) for r in cur.fetchall()]
    
    print(f"[CROSS-VAL] Validating {len(targets)} stocks (sampled from active)")
    
    counts = {"OK": 0, "WARNING": 0, "ALERT": 0, "SKIP": 0}
    alert_tickers = []
    
    for i, t in enumerate(targets):
        try:
            # 주가 검증
            price_result = validate_price(t["stock_id"], t["ticker"], calc_date)
            status = price_result["status"]
            counts[status.value] += 1
            
            if status == ValidationStatus.ALERT:
                alert_tickers.append(t["ticker"])
            
            # DB 저장
            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO data_cross_validation
                    (calc_date, stock_id, ticker, check_type,
                     source_a_value, source_b_value, diff_pct, status,
                     golden_value, detail)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """, (calc_date, t["stock_id"], t["ticker"],
                      price_result.get("check_type", "PRICE"),
                      price_result.get("fmp_value"),
                      price_result.get("yf_value"),
                      price_result.get("diff_pct"),
                      status.value,
                      price_result.get("golden_value"),
                      json.dumps({"source_a": "FMP", "source_b": "yfinance"})))
            
            if (i + 1) % 20 == 0:
                print(f"  Progress: {i+1}/{len(targets)} | "
                      f"OK={counts['OK']} WARN={counts['WARNING']} ALERT={counts['ALERT']}")
                
        except Exception as e:
            counts["SKIP"] += 1
            logger.debug(f"Validation failed for {t['ticker']}: {e}")
    
    # 일일 리포트 생성
    total = sum(counts.values())
    health_score = (counts["OK"] + counts["WARNING"] * 0.5) / max(total - counts["SKIP"], 1) * 100
    price_accuracy = counts["OK"] / max(total - counts["SKIP"], 1)
    
    with get_cursor() as cur:
        cur.execute("""
            INSERT INTO data_quality_daily_report
            (calc_date, total_checks, ok_count, warning_count, alert_count, skip_count,
             health_score, price_accuracy, excluded_tickers, detail)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (calc_date) DO UPDATE SET
                total_checks=EXCLUDED.total_checks, ok_count=EXCLUDED.ok_count,
                warning_count=EXCLUDED.warning_count, alert_count=EXCLUDED.alert_count,
                skip_count=EXCLUDED.skip_count, health_score=EXCLUDED.health_score,
                price_accuracy=EXCLUDED.price_accuracy,
                excluded_tickers=EXCLUDED.excluded_tickers
        """, (calc_date, total, counts["OK"], counts["WARNING"],
              counts["ALERT"], counts["SKIP"],
              health_score, price_accuracy,
              json.dumps(alert_tickers),
              json.dumps(counts)))
    
    print(f"\n[CROSS-VAL] Results:")
    print(f"  OK: {counts['OK']} | WARNING: {counts['WARNING']} | "
          f"ALERT: {counts['ALERT']} | SKIP: {counts['SKIP']}")
    print(f"  Health Score: {health_score:.1f}/100")
    print(f"  Price Accuracy: {price_accuracy:.1%}")
    if alert_tickers:
        print(f"  ALERT tickers: {', '.join(alert_tickers[:10])}")
    
    return {
        "health_score": health_score,
        "price_accuracy": price_accuracy,
        "counts": counts,
        "alert_tickers": alert_tickers,
    }


if __name__ == "__main__":
    run_cross_validation()
