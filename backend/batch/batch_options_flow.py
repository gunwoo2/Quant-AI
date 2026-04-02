"""
batch/batch_options_flow.py — Options Flow Intelligence v1.0
=============================================================
Day 3 신규 | 선행지표 #2: 옵션 시장은 주식보다 1~4주 먼저 움직인다

yfinance options chain(무료)에서 수집:
  1. IV Rank: 30일 내재변동성의 1년 내 순위 (0~100)
  2. IV Percentile: IV가 1년 중 몇 %에 위치하는가
  3. Put/Call Ratio: 실제 풋/콜 거래량 비율 (기존 3.5 하드코딩 대체!)
  4. IV Skew: OTM Put / ATM Put IV 비율 → 하방 리스크 선행

저장: options_flow_daily 테이블
연동: batch_layer3_flow_macro.py의 put_call_score에서 실데이터 사용
      batch_xgboost.py Feature v2에서 활용

실행: scheduler.py Step 5.3 | 소요: ~30초 (종목당 0.5초) | 비용: $0
제한: yfinance 옵션 = 미국 주식만, 장 마감 후 수집
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import patch_numpy_adapter
except ImportError:
    pass

import numpy as np
import json
import logging
from datetime import datetime, date, timedelta
from db_pool import get_cursor

logger = logging.getLogger("batch_options_flow")

try:
    import yfinance as yf
    _HAS_YF = True
except ImportError:
    _HAS_YF = False
    logger.warning("[OPTIONS] yfinance 미설치")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 상수
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

MAX_STOCKS = 60          # 상위 N 종목만 수집 (API 부하 관리)
IV_HISTORY_DAYS = 252    # IV Rank 계산 기준 (1년)
RETRY_COUNT = 2          # API 재시도


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 테이블 생성
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _ensure_table():
    with get_cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS options_flow_daily (
                id              SERIAL PRIMARY KEY,
                stock_id        INT NOT NULL,
                calc_date       DATE NOT NULL,
                ticker          VARCHAR(10),
                -- IV 지표
                iv_current      NUMERIC(8,4),
                iv_rank         NUMERIC(6,2),
                iv_percentile   NUMERIC(6,2),
                -- Put/Call
                put_volume      INT,
                call_volume     INT,
                put_call_ratio  NUMERIC(6,3),
                -- IV Skew
                atm_iv          NUMERIC(8,4),
                otm_put_iv      NUMERIC(8,4),
                iv_skew         NUMERIC(6,3),
                -- 점수화
                options_score   NUMERIC(6,2),
                data_quality    VARCHAR(10) DEFAULT 'FULL',
                detail          JSONB,
                created_at      TIMESTAMPTZ DEFAULT NOW(),
                UNIQUE(stock_id, calc_date)
            )
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_options_stock_date
            ON options_flow_daily(stock_id, calc_date DESC)
        """)
    print("[OPTIONS] ✅ options_flow_daily 테이블 확인")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 종목별 옵션 데이터 수집
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _fetch_options_data(ticker_symbol):
    """
    yfinance에서 옵션 체인 수집 → IV/Put-Call/Skew 계산.

    Returns:
        dict or None (수집 실패시)
    """
    if not _HAS_YF:
        return None

    try:
        tk = yf.Ticker(ticker_symbol)

        # 옵션 만기일 목록
        expirations = tk.options
        if not expirations:
            return None

        # 가장 가까운 만기 (30일 이내) 선택
        today = date.today()
        target_exp = None
        for exp_str in expirations:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").date()
            days_to_exp = (exp_date - today).days
            if 7 <= days_to_exp <= 45:
                target_exp = exp_str
                break

        if target_exp is None and expirations:
            target_exp = expirations[0]  # 가장 가까운 만기

        if target_exp is None:
            return None

        chain = tk.option_chain(target_exp)
        calls = chain.calls
        puts = chain.puts

        if calls.empty or puts.empty:
            return None

        # 현재 주가
        hist = tk.history(period="1d")
        if hist.empty:
            return None
        current_price = float(hist['Close'].iloc[-1])

        # ── 1. Put/Call Ratio ──
        total_call_vol = int(calls['volume'].sum()) if 'volume' in calls.columns else 0
        total_put_vol = int(puts['volume'].sum()) if 'volume' in puts.columns else 0
        pc_ratio = total_put_vol / max(total_call_vol, 1)

        # ── 2. ATM IV (현재가 가장 가까운 행사가의 IV) ──
        atm_iv = None
        otm_put_iv = None

        if 'impliedVolatility' in calls.columns and 'strike' in calls.columns:
            calls_valid = calls[calls['impliedVolatility'] > 0].copy()
            if not calls_valid.empty:
                calls_valid['dist'] = abs(calls_valid['strike'] - current_price)
                atm_call = calls_valid.loc[calls_valid['dist'].idxmin()]
                atm_iv = float(atm_call['impliedVolatility'])

        if 'impliedVolatility' in puts.columns and 'strike' in puts.columns:
            puts_valid = puts[puts['impliedVolatility'] > 0].copy()
            if not puts_valid.empty:
                # ATM Put
                puts_valid['dist'] = abs(puts_valid['strike'] - current_price)

                # OTM Put (현재가의 90~95% 행사가)
                otm_target = current_price * 0.925
                puts_valid['otm_dist'] = abs(puts_valid['strike'] - otm_target)
                otm_row = puts_valid.loc[puts_valid['otm_dist'].idxmin()]
                otm_put_iv = float(otm_row['impliedVolatility'])

        # ── 3. IV Skew (OTM Put IV / ATM IV) ──
        iv_skew = None
        if atm_iv and otm_put_iv and atm_iv > 0:
            iv_skew = round(otm_put_iv / atm_iv, 3)

        # ── 4. IV Current (ATM 평균) ──
        iv_current = atm_iv

        return {
            "iv_current": round(iv_current, 4) if iv_current else None,
            "put_volume": total_put_vol,
            "call_volume": total_call_vol,
            "put_call_ratio": round(pc_ratio, 3),
            "atm_iv": round(atm_iv, 4) if atm_iv else None,
            "otm_put_iv": round(otm_put_iv, 4) if otm_put_iv else None,
            "iv_skew": iv_skew,
            "current_price": current_price,
        }

    except Exception as e:
        logger.debug(f"[OPTIONS] {ticker_symbol} 수집 실패: {e}")
        return None


def _calc_iv_rank(stock_id, ticker, iv_current, calc_date):
    """
    IV Rank: 현재 IV가 1년 내 최소~최대 중 어디인가 (0~100).
    IV Percentile: 현재 IV보다 낮았던 날의 비율 (0~100).
    """
    if iv_current is None:
        return None, None

    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT iv_current FROM options_flow_daily
                WHERE stock_id = %s
                  AND calc_date >= %s - INTERVAL '252 days'
                  AND iv_current IS NOT NULL
                ORDER BY calc_date ASC
            """, (stock_id, calc_date))
            rows = cur.fetchall()

        if len(rows) < 20:
            return None, None

        iv_history = [float(r["iv_current"]) for r in rows]
        iv_min = min(iv_history)
        iv_max = max(iv_history)

        # IV Rank
        if iv_max > iv_min:
            iv_rank = round((iv_current - iv_min) / (iv_max - iv_min) * 100, 2)
        else:
            iv_rank = 50.0

        # IV Percentile
        below_count = sum(1 for v in iv_history if v <= iv_current)
        iv_pctile = round(below_count / len(iv_history) * 100, 2)

        return iv_rank, iv_pctile

    except Exception as e:
        logger.debug(f"[OPTIONS] IV Rank 계산 실패: {e}")
        return None, None


def _calc_options_score(pc_ratio, iv_rank, iv_skew):
    """
    옵션 종합 점수 (0~10).
    Put/Call이 극단적이면 반전 가능, IV Skew 높으면 하방 위험.
    """
    score = 5.0  # 중립

    # Put/Call Ratio: 0.7 이하(콜 우세=낙관) → +, 1.3 이상(풋 우세=비관) → -
    if pc_ratio is not None:
        if pc_ratio < 0.5:
            score += 1.5    # 극단적 낙관 → 과열? 역방향도 가능
        elif pc_ratio < 0.7:
            score += 1.0    # 적당한 낙관
        elif pc_ratio > 1.5:
            score -= 1.5    # 극단적 비관 → 반전 가능성
        elif pc_ratio > 1.0:
            score -= 0.5    # 약간 비관

    # IV Rank: 높으면 변동성 확대 예상 → 부정적
    if iv_rank is not None:
        if iv_rank > 80:
            score -= 1.0
        elif iv_rank > 60:
            score -= 0.5
        elif iv_rank < 20:
            score += 0.5

    # IV Skew: 1.2 이상이면 하방 리스크 프리미엄 높음
    if iv_skew is not None:
        if iv_skew > 1.3:
            score -= 1.0
        elif iv_skew > 1.15:
            score -= 0.5

    return round(max(0, min(10, score)), 2)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 공개 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def get_put_call_score(stock_id, calc_date=None):
    """
    batch_layer3_flow_macro.py에서 호출.
    기존 3.5 하드코딩 대체 → 실제 옵션 데이터 기반 점수 (0~7).
    """
    if calc_date is None:
        calc_date = date.today()
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT options_score, put_call_ratio, iv_rank
                FROM options_flow_daily
                WHERE stock_id = %s AND calc_date <= %s
                ORDER BY calc_date DESC LIMIT 1
            """, (stock_id, calc_date))
            row = cur.fetchone()
            if row and row["options_score"] is not None:
                # 0~10 → 0~7로 스케일 (기존 put_call_score 범위와 맞춤)
                return round(float(row["options_score"]) * 0.7, 2)
    except Exception as e:
        logger.debug(f"[OPTIONS] put_call_score 조회 실패: {e}")
    return 3.5  # Fallback: 기존 중립값


def run_options_flow(calc_date=None):
    """
    scheduler.py Step 5.3에서 호출.

    1. 상위 N 종목 선정
    2. 종목별 옵션 데이터 수집
    3. IV Rank/Percentile 계산
    4. 옵션 점수 산출 + DB 저장
    """
    if calc_date is None:
        calc_date = date.today()

    print(f"\n[OPTIONS] === Options Flow Intelligence — {calc_date} ===")
    _ensure_table()

    if not _HAS_YF:
        print("[OPTIONS] ⚠️ yfinance 미설치 → 건너뜀")
        return {"error": "yfinance not installed"}

    # 상위 종목 선정 (최종 점수 높은 순)
    with get_cursor() as cur:
        cur.execute("""
            SELECT s.stock_id, s.ticker
            FROM stocks s
            JOIN LATERAL (
                SELECT weighted_score FROM stock_final_scores
                WHERE stock_id = s.stock_id
                ORDER BY calc_date DESC LIMIT 1
            ) sfs ON TRUE
            WHERE s.is_active = TRUE AND s.ticker IS NOT NULL
            ORDER BY sfs.weighted_score DESC
            LIMIT %s
        """, (MAX_STOCKS,))
        targets = cur.fetchall()

    print(f"  대상 종목: {len(targets)}개")

    saved = 0
    skipped = 0
    for t in targets:
        stock_id = t["stock_id"]
        ticker = t["ticker"]

        # 옵션 수집
        data = _fetch_options_data(ticker)
        if data is None:
            skipped += 1
            continue

        # IV Rank/Percentile
        iv_rank, iv_pctile = _calc_iv_rank(stock_id, ticker, data.get("iv_current"), calc_date)

        # 점수
        score = _calc_options_score(data.get("put_call_ratio"), iv_rank, data.get("iv_skew"))

        # DB 저장
        try:
            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO options_flow_daily
                        (stock_id, calc_date, ticker, iv_current, iv_rank, iv_percentile,
                         put_volume, call_volume, put_call_ratio,
                         atm_iv, otm_put_iv, iv_skew, options_score, data_quality, detail)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (stock_id, calc_date) DO UPDATE SET
                        iv_current=EXCLUDED.iv_current, iv_rank=EXCLUDED.iv_rank,
                        iv_percentile=EXCLUDED.iv_percentile,
                        put_volume=EXCLUDED.put_volume, call_volume=EXCLUDED.call_volume,
                        put_call_ratio=EXCLUDED.put_call_ratio,
                        atm_iv=EXCLUDED.atm_iv, otm_put_iv=EXCLUDED.otm_put_iv,
                        iv_skew=EXCLUDED.iv_skew, options_score=EXCLUDED.options_score,
                        data_quality=EXCLUDED.data_quality, detail=EXCLUDED.detail,
                        created_at=NOW()
                """, (
                    stock_id, calc_date, ticker,
                    data.get("iv_current"), iv_rank, iv_pctile,
                    data.get("put_volume"), data.get("call_volume"),
                    data.get("put_call_ratio"),
                    data.get("atm_iv"), data.get("otm_put_iv"),
                    data.get("iv_skew"), score,
                    "FULL" if iv_rank is not None else "PARTIAL",
                    json.dumps(data, default=str),
                ))
            saved += 1
        except Exception as e:
            logger.warning(f"[OPTIONS] {ticker} 저장 실패: {e}")

    # Telemetry
    try:
        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO system_telemetry (calc_date, category, metric_name, metric_value, detail)
                VALUES (%s, 'OPTIONS', 'daily_collection', %s, %s)
            """, (calc_date, saved,
                  json.dumps({"saved": saved, "skipped": skipped, "total": len(targets)})))
    except Exception as e:
        logger.debug(f"[TELEMETRY] 기록 실패: {e}")

    print(f"[OPTIONS] ✅ 저장: {saved}/{len(targets)}종목 (skip={skipped})")
    return {"saved": saved, "skipped": skipped, "total": len(targets)}


# 하위 호환
run_all = run_options_flow
