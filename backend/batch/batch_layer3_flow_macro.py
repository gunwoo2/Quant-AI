"""
batch/batch_layer3_flow_macro.py — Layer 3 Section B (Flow) + C (Macro) 배치
=============================================================================
v1.0: 2026-03-23

기존 batch_layer3_v2.py가 Section A (기술지표 55점)만 계산하므로,
이 배치가 Section B (수급 25점) + Section C (시장환경 20점)을 계산하고
technical_indicators 테이블을 UPDATE합니다.

실행 순서:
  1. batch_layer3_v2.py (Section A) → INSERT/UPDATE section_a_technical
  2. 이 배치 (Section B + C) → UPDATE section_b_flow, section_c_macro, layer3_total_score

배점:
  [Section B - 수급·구조 (25점)]
    공매도 비율 (Short Volume)  : 10점  ← FINRA short_volume_daily
    풋콜 비율 (Put/Call Ratio)  :  7점  ← 추후 데이터소스 추가 시
    구조적 시그널 (Structural)  :  8점  ← golden_cross, bb_squeeze 등 (이미 section_a에서 계산)

  [Section C - 시장환경 (20점)]
    VIX 점수                    : 10점  ← macro_indicators (batch_macro.py가 수집)
    섹터 ETF 점수               : 10점  ← FinanceDataReader 섹터 ETF

스케줄: batch_layer3_v2 완료 후 실행 (03:45 ET)
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import patch_numpy_adapter
except ImportError:
    pass

import numpy as np
import FinanceDataReader as fdr
from datetime import datetime, date, timedelta
from db_pool import get_cursor, get_pool


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# 섹터 코드 → ETF 심볼 매핑
SECTOR_ETF_MAP = {
    "10": "XLE",   # Energy
    "15": "XLB",   # Materials
    "20": "XLI",   # Industrials
    "25": "XLY",   # Consumer Discretionary
    "30": "XLP",   # Consumer Staples
    "35": "XLV",   # Healthcare
    "40": "XLF",   # Financials
    "45": "XLK",   # Technology
    "50": "XLC",   # Communication Services
    "55": "XLU",   # Utilities
    "60": "XLRE",  # Real Estate
}


def _safe(v):
    """NaN/Inf → None"""
    if v is None:
        return None
    try:
        fv = float(v)
        if np.isnan(fv) or np.isinf(fv):
            return None
        return fv
    except (TypeError, ValueError):
        return None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Section B: 수급·구조 (25점)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def score_short_volume(svr: float) -> float:
    """
    공매도 비율(SVR) → 점수 (0~10)
    SVR < 0.20 : 10 (매우 강세)
    SVR 0.20~0.35 : 8~10 (강세)
    SVR 0.35~0.45 : 4~8 (중립)
    SVR 0.45~0.55 : 2~4 (약세)
    SVR > 0.55 : 0~2 (매우 약세)
    """
    if svr is None:
        return 5.0  # 데이터 없으면 중립
    svr = float(svr)
    if svr <= 0.20:
        return 10.0
    elif svr <= 0.35:
        return round(10.0 - (svr - 0.20) / 0.15 * 2.0, 2)
    elif svr <= 0.45:
        return round(8.0 - (svr - 0.35) / 0.10 * 4.0, 2)
    elif svr <= 0.55:
        return round(4.0 - (svr - 0.45) / 0.10 * 2.0, 2)
    else:
        return round(max(0.0, 2.0 - (svr - 0.55) / 0.15 * 2.0), 2)


def calc_section_b(stock_id: int, calc_date: date) -> dict:
    """Section B 계산: 공매도(10) + 풋콜(7) + 구조적시그널(8) = 25점"""

    # 1. 공매도 점수 (10점)
    short_score = 5.0  # 기본 중립
    svr = None
    svr_5d = None

    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT short_volume, total_volume, short_volume_ratio, svr_5d_avg
                FROM short_volume_daily
                WHERE stock_id = %s
                ORDER BY trade_date DESC LIMIT 1
            """, (stock_id,))
            sv_row = cur.fetchone()

        if sv_row and sv_row["short_volume_ratio"] is not None:
            svr = float(sv_row["short_volume_ratio"])
            svr_5d = float(sv_row["svr_5d_avg"]) if sv_row["svr_5d_avg"] else svr
            # 5일 평균 기반으로 스코어 (노이즈 감소)
            short_score = score_short_volume(svr_5d)
        else:
            short_score = 5.0  # 데이터 없으면 중립 (5/10)
    except Exception as e:
        print(f"  [WARN] 공매도 조회 실패 (stock_id={stock_id}): {e}")
        short_score = 5.0

    # 2. 풋콜 비율 점수 (7점) — put_call_daily 테이블에서 조회
    put_call_score = 3.5  # 기본값 (데이터 없을 때)
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT pc_score, pc_ratio_oi, source
                FROM put_call_daily
                WHERE stock_id = %s
                ORDER BY calc_date DESC LIMIT 1
            """, (stock_id,))
            pc_row = cur.fetchone()
        if pc_row and pc_row["pc_score"] is not None:
            put_call_score = min(float(pc_row["pc_score"]), 7.0)
    except Exception as e:
        print(f"  [WARN] P/C 조회 실패 (stock_id={stock_id}): {e}")
        put_call_score = 3.5  # fallback

    # 3. 구조적 시그널 점수 (8점) — technical_indicators에서 이미 계산됨
    struct_score = 0.0
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT structural_signal_score
                FROM technical_indicators
                WHERE stock_id = %s AND calc_date = %s
                LIMIT 1
            """, (stock_id, calc_date))
            row = cur.fetchone()
        if row and row["structural_signal_score"] is not None:
            struct_score = min(float(row["structural_signal_score"]), 8.0)
    except Exception:
        pass

    section_b = round(min(short_score + put_call_score + struct_score, 25.0), 2)

    return {
        "short_volume_score": round(short_score, 2),
        "put_call_score": round(put_call_score, 2),
        "structural_signal_score": round(struct_score, 2),
        "section_b_flow": section_b,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Section C: 시장환경 (20점)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def score_vix(vix_close: float) -> float:
    """
    VIX → 점수 (0~10)
    VIX <= 12 : 10 (극도 안정 — 주의: 과열 가능성)
    VIX 12~15 : 9
    VIX 15~20 : 6~8 (정상)
    VIX 20~25 : 3~6 (불안)
    VIX 25~30 : 1~3 (공포)
    VIX > 30  : 0~1 (극단 공포 — 역발상 가능)
    """
    if vix_close is None:
        return 5.0
    v = float(vix_close)
    if v <= 12:
        return 9.0  # 과열 경계로 10이 아닌 9
    elif v <= 15:
        return round(9.0 - (v - 12) / 3 * 1.0, 2)
    elif v <= 20:
        return round(8.0 - (v - 15) / 5 * 2.0, 2)
    elif v <= 25:
        return round(6.0 - (v - 20) / 5 * 3.0, 2)
    elif v <= 30:
        return round(3.0 - (v - 25) / 5 * 2.0, 2)
    elif v <= 40:
        return round(max(0.5, 1.0 - (v - 30) / 10 * 0.5), 2)
    else:
        return 0.5  # 극단 공포 (역발상 시 가산점은 별도)


def score_sector_etf(close: float, ma20: float, ma50: float) -> float:
    """
    섹터 ETF 추세 → 점수 (0~10)
    정배열 (close > ma20 > ma50) : 8~10
    close > ma20               : 5~8
    close < ma20 < ma50 (역배열): 0~3
    """
    if close is None or ma20 is None:
        return 5.0

    score = 5.0  # 기본 중립

    # close vs ma20
    ratio_20 = close / ma20 if ma20 > 0 else 1.0
    if ratio_20 > 1.02:
        score += 2.0
    elif ratio_20 > 1.0:
        score += 1.0
    elif ratio_20 < 0.98:
        score -= 2.0
    elif ratio_20 < 1.0:
        score -= 1.0

    # 정배열/역배열
    if ma50 and ma50 > 0:
        if close > ma20 > ma50:
            score += 2.0  # 정배열 보너스
        elif close < ma20 < ma50:
            score -= 2.0  # 역배열 페널티

    return round(max(0.0, min(10.0, score)), 2)


def calc_section_c(sector_code: str, calc_date: date) -> dict:
    """Section C 계산: VIX(10) + 섹터ETF(10) = 20점"""

    # 1. VIX 점수 (10점)
    vix_close = None
    vix_s = 5.0

    try:
        with get_cursor() as cur:
            # macro_indicators에서 최신 VIX
            cur.execute("""
                SELECT value FROM macro_indicators
                WHERE indicator_name = 'VIX'
                ORDER BY recorded_date DESC LIMIT 1
            """)
            vix_row = cur.fetchone()
        if vix_row and vix_row["value"] is not None:
            vix_close = float(vix_row["value"])
            vix_s = score_vix(vix_close)
    except Exception as e:
        print(f"  [WARN] VIX 조회 실패: {e}")

    # 2. 섹터 ETF 점수 (10점)
    etf_s = 5.0
    etf_symbol = SECTOR_ETF_MAP.get(sector_code, "SPY")

    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT etf_close, etf_ma20, etf_ma50, sector_etf_score
                FROM sector_etf_daily
                WHERE sector_code = %s
                ORDER BY calc_date DESC LIMIT 1
            """, (sector_code,))
            etf_row = cur.fetchone()

        if etf_row and etf_row["sector_etf_score"] is not None:
            etf_s = min(float(etf_row["sector_etf_score"]), 10.0)
        elif etf_row and etf_row["etf_close"] is not None:
            etf_s = score_sector_etf(
                float(etf_row["etf_close"]),
                float(etf_row["etf_ma20"]) if etf_row["etf_ma20"] else None,
                float(etf_row["etf_ma50"]) if etf_row["etf_ma50"] else None,
            )
    except Exception:
        # sector_etf_daily에 데이터 없으면 직접 FDR에서 가져오기
        try:
            etf_s = _fetch_etf_score_fdr(etf_symbol)
        except Exception as e2:
            print(f"  [WARN] 섹터 ETF 조회 실패 ({etf_symbol}): {e2}")
            etf_s = 5.0

    section_c = round(min(vix_s + etf_s, 20.0), 2)

    return {
        "vix_close": vix_close,
        "vix_score": round(vix_s, 2),
        "sector_etf_score": round(etf_s, 2),
        "section_c_macro": section_c,
    }


def _fetch_etf_score_fdr(symbol: str) -> float:
    """FinanceDataReader에서 ETF 데이터 가져와서 점수 계산"""
    df = fdr.DataReader(symbol)
    if df is None or len(df) < 50:
        return 5.0

    close = float(df.iloc[-1]["Close"])
    ma20 = float(df["Close"].tail(20).mean())
    ma50 = float(df["Close"].tail(50).mean())

    return score_sector_etf(close, ma20, ma50)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 섹터 ETF 일별 수집 + 저장 (sector_etf_daily)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def collect_sector_etf_daily(calc_date: date):
    """모든 섹터 ETF 가격 + MA + 점수를 sector_etf_daily에 저장"""
    print(f"\n── 섹터 ETF 수집 ──")
    ok, fail = 0, 0

    for sector_code, symbol in SECTOR_ETF_MAP.items():
        try:
            df = fdr.DataReader(symbol)
            if df is None or len(df) < 50:
                print(f"  [SKIP] {symbol}: 데이터 부족")
                fail += 1
                continue

            close = float(df.iloc[-1]["Close"])
            ma20 = float(df["Close"].tail(20).mean())
            ma50 = float(df["Close"].tail(50).mean())
            score = score_sector_etf(close, ma20, ma50)

            with get_cursor() as cur:
                cur.execute("""
                    INSERT INTO sector_etf_daily (
                        sector_code, etf_symbol, etf_close, etf_ma20, etf_ma50,
                        sector_etf_score, calc_date
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (sector_code, calc_date) DO UPDATE SET
                        etf_close = EXCLUDED.etf_close,
                        etf_ma20 = EXCLUDED.etf_ma20,
                        etf_ma50 = EXCLUDED.etf_ma50,
                        sector_etf_score = EXCLUDED.sector_etf_score
                """, (sector_code, symbol, close, ma20, ma50, score, calc_date))

            ok += 1
            trend = "정배열↑" if close > ma20 > ma50 else ("역배열↓" if ma50 and close < ma20 < ma50 else "혼조")
            print(f"  {symbol}({sector_code}): ${close:.2f} MA20=${ma20:.2f} MA50=${ma50:.2f} → {score:.1f}/10 [{trend}]")

        except Exception as e:
            fail += 1
            print(f"  [ERR] {symbol}: {e}")

    print(f"  → 섹터 ETF: {ok}성공 / {fail}실패")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# VIX/SPY → market_signal_daily 저장
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def collect_market_signal_daily(calc_date: date):
    """VIX + SPY 가격/MA/점수를 market_signal_daily에 저장"""
    print(f"\n── 시장 시그널 수집 ──")

    try:
        # VIX
        vix_df = fdr.DataReader("^VIX")
        vix_close = float(vix_df.iloc[-1]["Close"]) if vix_df is not None and len(vix_df) > 0 else None
        vix_s = score_vix(vix_close) if vix_close else 5.0

        # SPY
        spy_df = fdr.DataReader("SPY")
        spy_close = None
        spy_ma50 = None
        spy_ma200 = None
        if spy_df is not None and len(spy_df) >= 200:
            spy_close = float(spy_df.iloc[-1]["Close"])
            spy_ma50 = float(spy_df["Close"].tail(50).mean())
            spy_ma200 = float(spy_df["Close"].tail(200).mean())
        elif spy_df is not None and len(spy_df) >= 50:
            spy_close = float(spy_df.iloc[-1]["Close"])
            spy_ma50 = float(spy_df["Close"].tail(50).mean())

        with get_cursor() as cur:
            cur.execute("""
                INSERT INTO market_signal_daily (
                    calc_date, vix_close, vix_score,
                    spy_close, spy_ma50, spy_ma200
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (calc_date) DO UPDATE SET
                    vix_close = EXCLUDED.vix_close,
                    vix_score = EXCLUDED.vix_score,
                    spy_close = EXCLUDED.spy_close,
                    spy_ma50 = EXCLUDED.spy_ma50,
                    spy_ma200 = EXCLUDED.spy_ma200
            """, (calc_date, vix_close, vix_s, spy_close, spy_ma50, spy_ma200))

        spy_trend = "N/A"
        if spy_close and spy_ma50:
            if spy_ma200 and spy_close > spy_ma50 > spy_ma200:
                spy_trend = "정배열↑"
            elif spy_close > spy_ma50:
                spy_trend = "강세↑"
            elif spy_ma200 and spy_close < spy_ma50 < spy_ma200:
                spy_trend = "역배열↓"
            else:
                spy_trend = "혼조"

        print(f"  VIX: {vix_close:.1f} → {vix_s:.1f}/10")
        print(f"  SPY: ${spy_close:.2f} MA50=${spy_ma50:.2f} MA200={spy_ma200 or 'N/A'} [{spy_trend}]")

    except Exception as e:
        print(f"  [ERR] 시장 시그널 수집 실패: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 메인: technical_indicators UPDATE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def run_flow_macro(calc_date: date = None):
    """Section B + C 계산 후 technical_indicators UPDATE"""
    if calc_date is None:
        calc_date = datetime.now().date()

    print(f"\n{'='*60}")
    print(f"  Layer 3 — Section B (Flow) + C (Macro)")
    print(f"  Date: {calc_date}")
    print(f"{'='*60}")

    # Step 1: 시장 데이터 수집 (VIX/SPY + 섹터 ETF)
    collect_market_signal_daily(calc_date)
    collect_sector_etf_daily(calc_date)

    # Step 2: 종목별 Section B + C 계산 → UPDATE
    with get_cursor() as cur:
        cur.execute("""
            SELECT s.stock_id, s.ticker, sec.sector_code
            FROM stocks s
            LEFT JOIN sectors sec ON s.sector_id = sec.sector_id
            WHERE s.is_active = TRUE
            ORDER BY s.ticker
        """)
        stocks = [dict(r) for r in cur.fetchall()]

    print(f"\n── 종목별 B+C 계산 ({len(stocks)}종목) ──")
    ok, skip, fail = 0, 0, 0

    for s in stocks:
        stock_id = s["stock_id"]
        ticker = s["ticker"]
        sector_code = s["sector_code"] or "45"  # 기본값: Technology

        try:
            # 해당 날짜에 Section A 데이터가 있는지 확인
            with get_cursor() as cur:
                cur.execute("""
                    SELECT section_a_technical, layer3_technical_score
                    FROM technical_indicators
                    WHERE stock_id = %s AND calc_date = %s
                    LIMIT 1
                """, (stock_id, calc_date))
                ti_row = cur.fetchone()

            if not ti_row:
                skip += 1
                continue  # Section A 데이터 없으면 스킵

            section_a = float(ti_row["section_a_technical"] or 0)

            # Section B 계산
            b_result = calc_section_b(stock_id, calc_date)
            section_b = b_result["section_b_flow"]

            # Section C 계산
            c_result = calc_section_c(sector_code, calc_date)
            section_c = c_result["section_c_macro"]

            # Layer 3 Total = A + B + C
            layer3_total = round(min(section_a + section_b + section_c, 100.0), 2)

            # UPDATE technical_indicators
            with get_cursor() as cur:
                cur.execute("""
                    UPDATE technical_indicators SET
                        section_b_flow = %s,
                        section_c_macro = %s,
                        short_volume_score = %s,
                        put_call_score = %s,
                        vix_score = %s,
                        sector_etf_score = %s,
                        layer3_total_score = %s
                    WHERE stock_id = %s AND calc_date = %s
                """, (
                    section_b, section_c,
                    b_result["short_volume_score"],
                    b_result["put_call_score"],
                    c_result["vix_score"],
                    c_result["sector_etf_score"],
                    layer3_total,
                    stock_id, calc_date,
                ))

            ok += 1
            if ok <= 10 or ok % 50 == 0:
                print(f"  {ticker}: A={section_a:.1f} B={section_b:.1f} C={section_c:.1f} → Total={layer3_total:.1f}")

        except Exception as e:
            fail += 1
            print(f"  [ERR] {ticker}: {e}")

    print(f"\n{'='*60}")
    print(f"  완료: {ok}성공 / {skip}스킵 / {fail}실패")
    print(f"{'='*60}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 하위호환 alias
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

run_all = run_flow_macro


if __name__ == "__main__":
    from db_pool import init_pool
    init_pool()
    run_flow_macro()