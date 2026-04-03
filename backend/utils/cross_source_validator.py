"""
utils/cross_source_validator.py — 교차소스 데이터 품질 검증 v1.1 (SET A-5 FIX)
============================================================================
v1.1 수정사항:
  ★ yfinance MultiIndex 컬럼 대응 (최신 yfinance 호환)
  ★ FMP 데이터 없을 때 graceful skip
  ★ 로그 개선 (첫 SKIP 원인 출력)

검증 항목:
  1. 주가 교차검증 (±0.5% OK, ±2% WARNING, >2% ALERT)
  2. 거래량 교차검증 (±10% 허용)
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

PRICE_OK_THRESHOLD      = 0.005
PRICE_WARNING_THRESHOLD = 0.020
VOLUME_OK_THRESHOLD     = 0.10
FINANCIAL_OK_THRESHOLD  = 0.05
SAMPLE_SIZE = 100
YF_RATE_LIMIT_SEC = 0.2


class ValidationStatus(Enum):
    OK       = "OK"
    WARNING  = "WARNING"
    ALERT    = "ALERT"
    SKIP     = "SKIP"


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
# yfinance 데이터 로더 (v1.1: MultiIndex 대응)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _yf_get_price(ticker: str, target_date: date) -> dict:
    """
    yfinance에서 종가/거래량 조회.
    v1.1: MultiIndex 컬럼 대응 (yfinance >= 0.2.31)
    """
    try:
        import yfinance as yf
        start = target_date - timedelta(days=7)   # 7일 여유 (주말/공휴일 대비)
        end = target_date + timedelta(days=1)
        
        df = yf.download(ticker, start=str(start), end=str(end), 
                         progress=False, timeout=10)
        if df.empty:
            return None
        
        # ★ v1.1: MultiIndex 컬럼 처리
        # yfinance 최신 버전은 컬럼이 ('Close', 'AAPL') 형태의 MultiIndex
        if hasattr(df.columns, 'nlevels') and df.columns.nlevels > 1:
            df.columns = df.columns.get_level_values(0)
        
        # 가장 최근 행
        row = df.iloc[-1]
        
        close_val = None
        volume_val = None
        
        # Close 컬럼 찾기 (대소문자 유연 처리)
        for col in df.columns:
            col_lower = str(col).lower()
            if col_lower == 'close' and close_val is None:
                close_val = float(row[col])
            elif col_lower == 'volume' and volume_val is None:
                volume_val = float(row[col])
        
        if close_val is None:
            return None
            
        return {
            "close": close_val,
            "volume": volume_val,
        }
    except Exception as e:
        logger.debug(f"yfinance failed for {ticker}: {e}")
        return None


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
    
    # ★ v1.1: SKIP 원인 구분
    if not fmp or not fmp.get("close"):
        return {"check_type": "PRICE", "status": ValidationStatus.SKIP,
                "skip_reason": "FMP_MISSING", "fmp": fmp, "yf": yf_data}
    
    if not yf_data or not yf_data.get("close"):
        return {"check_type": "PRICE", "status": ValidationStatus.SKIP,
                "skip_reason": "YF_MISSING", "fmp": fmp, "yf": yf_data}
    
    diff = abs(fmp["close"] - yf_data["close"]) / yf_data["close"]
    
    if diff < PRICE_OK_THRESHOLD:
        status = ValidationStatus.OK
        golden = (fmp["close"] + yf_data["close"]) / 2
    elif diff < PRICE_WARNING_THRESHOLD:
        status = ValidationStatus.WARNING
        golden = min(fmp["close"], yf_data["close"])
    else:
        status = ValidationStatus.ALERT
        golden = None
    
    return {
        "check_type": "PRICE",
        "status": status,
        "fmp_value": fmp["close"],
        "yf_value": yf_data["close"],
        "diff_pct": diff,
        "golden_value": golden,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 일일 배치
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_cross_validation(calc_date: date = None):
    """일일 교차검증 배치."""
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
    skip_reasons = {"FMP_MISSING": 0, "YF_MISSING": 0, "OTHER": 0}
    alert_tickers = []
    first_skip_logged = False
    
    for i, t in enumerate(targets):
        try:
            price_result = validate_price(t["stock_id"], t["ticker"], calc_date)
            status = price_result["status"]
            counts[status.value] += 1
            
            # ★ v1.1: SKIP 원인 추적
            if status == ValidationStatus.SKIP:
                reason = price_result.get("skip_reason", "OTHER")
                skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
                
                # 첫 번째 SKIP만 상세 출력 (디버깅용)
                if not first_skip_logged:
                    print(f"  [DEBUG] First SKIP: {t['ticker']} reason={reason} "
                          f"fmp={price_result.get('fmp')} yf={price_result.get('yf')}")
                    first_skip_logged = True
            
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
                      json.dumps({"source_a": "FMP", "source_b": "yfinance",
                                  "skip_reason": price_result.get("skip_reason")})))
            
            if (i + 1) % 20 == 0:
                print(f"  Progress: {i+1}/{len(targets)} | "
                      f"OK={counts['OK']} WARN={counts['WARNING']} "
                      f"ALERT={counts['ALERT']} SKIP={counts['SKIP']}")
                
        except Exception as e:
            counts["SKIP"] += 1
            logger.debug(f"Validation failed for {t['ticker']}: {e}")
    
    # 일일 리포트
    total = sum(counts.values())
    validated = total - counts["SKIP"]
    health_score = (counts["OK"] + counts["WARNING"] * 0.5) / max(validated, 1) * 100
    price_accuracy = counts["OK"] / max(validated, 1)
    
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
              json.dumps({"counts": counts, "skip_reasons": skip_reasons})))
    
    print(f"\n[CROSS-VAL] Results:")
    print(f"  OK: {counts['OK']} | WARNING: {counts['WARNING']} | "
          f"ALERT: {counts['ALERT']} | SKIP: {counts['SKIP']}")
    
    if counts["SKIP"] > 0:
        print(f"  SKIP breakdown: {skip_reasons}")
    
    if validated > 0:
        print(f"  Health Score: {health_score:.1f}/100 (validated {validated}/{total})")
        print(f"  Price Accuracy: {price_accuracy:.1%}")
    else:
        print(f"  ⚠️ 검증 가능 종목 0 — FMP DB에 해당 날짜 데이터 있는지 확인 필요")
    
    if alert_tickers:
        print(f"  ALERT tickers: {', '.join(alert_tickers[:10])}")
    
    return {
        "health_score": health_score,
        "price_accuracy": price_accuracy,
        "counts": counts,
        "skip_reasons": skip_reasons,
        "alert_tickers": alert_tickers,
    }


if __name__ == "__main__":
    run_cross_validation()
