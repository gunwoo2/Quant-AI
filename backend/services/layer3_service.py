"""
services/layer3_service.py — Layer 3 Market Signal 데이터 조회
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GET /api/stock/layer3/{ticker} 에서 호출
MarketSignalTab.jsx의 Overview / Technical / Flow / Macro 탭에 실데이터 공급
"""
from db_pool import get_cursor
from datetime import date, timedelta


def _f(v, digits=2):
    if v is None:
        return None
    try:
        return round(float(v), digits)
    except Exception:
        return None


def get_layer3_data(ticker: str) -> dict | None:
    """Layer 3 전체 데이터 조회 — MarketSignalTab에 1:1 매핑"""

    with get_cursor() as cur:
        cur.execute(
            "SELECT stock_id, company_name, sector_id FROM stocks WHERE ticker = %s AND is_active = TRUE LIMIT 1",
            (ticker.upper(),)
        )
        row = cur.fetchone()
        if not row:
            return None
        stock_id = row["stock_id"]
        company_name = row["company_name"]
        sector_id = row["sector_id"]

    # sector_code 조회
    sector_code = ""
    if sector_id:
        with get_cursor() as cur:
            cur.execute("SELECT sector_code FROM sectors WHERE sector_id = %s", (sector_id,))
            sr = cur.fetchone()
            if sr:
                sector_code = sr["sector_code"]

    today = date.today()

    overview = _get_overview(stock_id, today)
    technical = _get_technical(stock_id, today)
    flow = _get_flow(stock_id, today)
    macro = _get_macro(today, sector_code)

    # Phase 2: Chart Patterns + Fear & Greed
    patterns = _get_patterns(stock_id, today)
    fear_greed = _get_fear_greed(today)

    return {
        "ticker": ticker.upper(),
        "companyName": company_name,
        "overview": overview,
        "technical": technical,
        "flow": flow,
        "macro": macro,
        "patterns": patterns,
        "fearGreed": fear_greed,
    }


# ═══════════════════════════════════════════════════════════════
#  1. Overview (요약 카드 + 레이더)
# ═══════════════════════════════════════════════════════════════
def _get_overview(stock_id: int, today: date) -> dict:
    with get_cursor() as cur:
        cur.execute("""
            SELECT
                section_a_technical, section_b_flow, section_c_macro,
                layer3_total_score,
                relative_momentum_score, high_52w_score,
                trend_stability_score, rsi_score, macd_score,
                obv_score, volume_surge_score,
                structural_signal_score,
                short_volume_score, put_call_score,
                vix_score, sector_etf_score,
                calc_date
            FROM technical_indicators
            WHERE stock_id = %s AND calc_date >= %s - INTERVAL '7 days'
            ORDER BY calc_date DESC LIMIT 1
        """, (stock_id, today))
        row = cur.fetchone()

    if not row:
        return {"totalScore": None, "sections": [], "radar": [], "indicators": []}

    total = _f(row["layer3_total_score"])
    sa = _f(row["section_a_technical"])
    sb = _f(row["section_b_flow"])
    sc = _f(row["section_c_macro"])

    radar = [
        {"subject": "모멘텀 (Momentum)",     "score": _f(row["relative_momentum_score"]), "max": 15},
        {"subject": "52주고가 (52W High)",    "score": _f(row["high_52w_score"]),         "max": 10},
        {"subject": "추세안정 (Trend R²)",    "score": _f(row["trend_stability_score"]),  "max": 8},
        {"subject": "RSI",                    "score": _f(row["rsi_score"]),              "max": 7},
        {"subject": "MACD",                   "score": _f(row["macd_score"]),             "max": 5},
        {"subject": "OBV (거래량흐름)",        "score": _f(row["obv_score"]),             "max": 5},
        {"subject": "거래량급증 (VolSurge)",   "score": _f(row["volume_surge_score"]),    "max": 5},
    ]

    # 레이더차트용 정규화 (0~100)
    for r in radar:
        r["pct"] = round(r["score"] / r["max"] * 100, 1) if r["score"] is not None and r["max"] > 0 else 0

    indicators = [
        {"name": "구조적 시그널 (Structural)", "score": _f(row["structural_signal_score"]), "max": 8},
        {"name": "공매도 (Short Volume)",      "score": _f(row["short_volume_score"]),      "max": 10},
        {"name": "풋콜비율 (Put/Call)",         "score": _f(row["put_call_score"]),         "max": 7},
        {"name": "VIX (공포지수)",              "score": _f(row["vix_score"]),              "max": 10},
        {"name": "섹터 ETF",                   "score": _f(row["sector_etf_score"]),       "max": 10},
    ]

    return {
        "totalScore": total,
        "calcDate": str(row["calc_date"]),
        "sections": [
            {"name": "A. 기술지표 (Technical)",  "score": sa, "max": 55},
            {"name": "B. 수급·구조 (Flow)",       "score": sb, "max": 25},
            {"name": "C. 시장환경 (Macro)",       "score": sc, "max": 20},
        ],
        "radar": radar,
        "indicators": indicators,
    }


# ═══════════════════════════════════════════════════════════════
#  2. Technical (상세 지표값)
# ═══════════════════════════════════════════════════════════════
def _get_technical(stock_id: int, today: date) -> dict:
    with get_cursor() as cur:
        cur.execute("""
            SELECT
                relative_momentum_12_1, relative_momentum_score,
                high_52w, high_52w_position_ratio, high_52w_score,
                trend_r2_90d, trend_slope_90d, trend_stability_score,
                rsi_14, rsi_score,
                macd_line, macd_signal, macd_histogram, macd_score,
                obv_current, obv_ma20, obv_trend, obv_score,
                volume_20d_avg, volume_surge_ratio, volume_surge_score,
                golden_cross, death_cross, ma_50, ma_200,
                bb_upper, bb_lower, bb_width, bb_squeeze,
                golden_cross_score, bb_squeeze_score,
                ma20_streak_days, ma20_streak_score,
                breakout_52w, breakout_52w_score,
                structural_signal_score,
                calc_date
            FROM technical_indicators
            WHERE stock_id = %s AND calc_date >= %s - INTERVAL '7 days'
            ORDER BY calc_date DESC LIMIT 1
        """, (stock_id, today))
        row = cur.fetchone()

    if not row:
        return {}

    return {
        "calcDate": str(row["calc_date"]),
        # ① 상대 모멘텀
        "relativeMomentum": _f(row["relative_momentum_12_1"], 4),
        "relativeMomentumScore": _f(row["relative_momentum_score"]),
        # ② 52주 고가
        "high52w": _f(row["high_52w"]),
        "high52wRatio": _f(row["high_52w_position_ratio"], 4),
        "high52wScore": _f(row["high_52w_score"]),
        # ③ 추세 안정성
        "trendR2": _f(row["trend_r2_90d"], 4),
        "trendSlope": _f(row["trend_slope_90d"], 6),
        "trendScore": _f(row["trend_stability_score"]),
        # ④ RSI
        "rsi14": _f(row["rsi_14"]),
        "rsiScore": _f(row["rsi_score"]),
        # ⑤ MACD
        "macdLine": _f(row["macd_line"], 4),
        "macdSignal": _f(row["macd_signal"], 4),
        "macdHistogram": _f(row["macd_histogram"], 4),
        "macdScore": _f(row["macd_score"]),
        # ⑥ OBV
        "obvCurrent": _f(row["obv_current"], 0),
        "obvMa20": _f(row["obv_ma20"], 0),
        "obvTrend": row["obv_trend"],
        "obvScore": _f(row["obv_score"]),
        # ⑦ 거래량
        "volume20dAvg": _f(row["volume_20d_avg"], 0),
        "volumeSurgeRatio": _f(row["volume_surge_ratio"]),
        "volumeSurgeScore": _f(row["volume_surge_score"]),
        # 구조적 시그널
        "goldenCross": row["golden_cross"],
        "deathCross": row["death_cross"],
        "ma50": _f(row["ma_50"]),
        "ma200": _f(row["ma_200"]),
        "bbUpper": _f(row["bb_upper"]),
        "bbLower": _f(row["bb_lower"]),
        "bbWidth": _f(row["bb_width"], 4),
        "bbSqueeze": row["bb_squeeze"],
        "goldenCrossScore": _f(row["golden_cross_score"]),
        "bbSqueezeScore": _f(row["bb_squeeze_score"]),
        "ma20StreakDays": row["ma20_streak_days"],
        "ma20StreakScore": _f(row["ma20_streak_score"]),
        "breakout52w": row["breakout_52w"],
        "breakout52wScore": _f(row["breakout_52w_score"]),
        "structuralScore": _f(row["structural_signal_score"]),
    }


# ═══════════════════════════════════════════════════════════════
#  3. Flow (공매도 + P/C)
# ═══════════════════════════════════════════════════════════════
def _get_flow(stock_id: int, today: date) -> dict:
    # 최근 10일 short volume 트렌드
    with get_cursor() as cur:
        cur.execute("""
            SELECT trade_date, short_volume, total_volume,
                   short_volume_ratio, svr_5d_avg, short_volume_score
            FROM short_volume_daily
            WHERE stock_id = %s
            ORDER BY trade_date DESC LIMIT 10
        """, (stock_id,))
        sv_rows = [dict(r) for r in cur.fetchall()]

    sv_trend = []
    latest_sv = {}
    for r in reversed(sv_rows):
        sv_trend.append({
            "date": str(r["trade_date"]),
            "svr": _f(r["short_volume_ratio"], 4),
            "svr5d": _f(r["svr_5d_avg"], 4),
        })
    if sv_rows:
        latest = sv_rows[0]
        latest_sv = {
            "shortVolume": _f(latest["short_volume"], 0),
            "totalVolume": _f(latest["total_volume"], 0),
            "svr": _f(latest["short_volume_ratio"], 4),
            "svr5d": _f(latest["svr_5d_avg"], 4),
            "score": _f(latest["short_volume_score"]),
        }

    # P/C 점수 (technical_indicators에 저장됨)
    with get_cursor() as cur:
        cur.execute("""
            SELECT put_call_score FROM technical_indicators
            WHERE stock_id = %s
            ORDER BY calc_date DESC LIMIT 1
        """, (stock_id,))
        pc_row = cur.fetchone()
    pc_score = _f(pc_row["put_call_score"]) if pc_row else None

    return {
        "shortVolume": latest_sv,
        "svTrend": sv_trend,
        "putCallScore": pc_score,
    }


# ═══════════════════════════════════════════════════════════════
#  4. Macro (VIX + SPY + 섹터 ETF)
# ═══════════════════════════════════════════════════════════════
def _get_macro(today: date, sector_code: str) -> dict:
    # VIX + SPY
    with get_cursor() as cur:
        cur.execute("""
            SELECT calc_date, vix_close, vix_score,
                   spy_close, spy_ma50, spy_ma200
            FROM market_signal_daily
            ORDER BY calc_date DESC LIMIT 1
        """)
        mrow = cur.fetchone()

    vix = {}
    spy = {}
    if mrow:
        vix = {
            "close": _f(mrow["vix_close"]),
            "score": _f(mrow["vix_score"]),
            "date": str(mrow["calc_date"]),
        }
        spy = {
            "close": _f(mrow["spy_close"]),
            "ma50": _f(mrow["spy_ma50"]),
            "ma200": _f(mrow["spy_ma200"]),
        }

    # 전체 섹터 ETF
    etf_list = []
    with get_cursor() as cur:
        cur.execute("""
            SELECT sector_code, etf_symbol, etf_close, etf_ma20, etf_ma50, sector_etf_score
            FROM sector_etf_daily
            ORDER BY calc_date DESC, sector_code
            LIMIT 11
        """)
        for r in cur.fetchall():
            etf_list.append({
                "sectorCode": r["sector_code"],
                "symbol": r["etf_symbol"],
                "close": _f(r["etf_close"]),
                "ma20": _f(r["etf_ma20"]),
                "ma50": _f(r["etf_ma50"]),
                "score": _f(r["sector_etf_score"]),
            })

    # 현재 종목의 섹터 ETF 점수
    my_etf_score = None
    for e in etf_list:
        if e["sectorCode"] == sector_code:
            my_etf_score = e["score"]
            break

    return {
        "vix": vix,
        "spy": spy,
        "sectorEtfs": etf_list,
        "mySectorScore": my_etf_score,
    }

# ═══════════════════════════════════════════════════════════════
#  5. Chart Patterns (차트 패턴)
# ═══════════════════════════════════════════════════════════════
def _get_patterns(stock_id: int, today: date) -> list:
    """chart_patterns 테이블에서 종목별 패턴 조회."""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT pattern_type, pattern_name, direction,
                       strength, description
                FROM chart_patterns
                WHERE stock_id = %s
                  AND calc_date >= %s::date - INTERVAL '3 days'
                ORDER BY strength DESC NULLS LAST
            """, (stock_id, today))
            rows = cur.fetchall()
        return [
            {
                "type": r["pattern_type"],
                "name": r["pattern_name"],
                "direction": r["direction"] or "NEUTRAL",
                "confidence": float(r["strength"]) if r["strength"] else 0,
                "desc": r["description"] or "",
            }
            for r in rows
        ]
    except Exception as e:
        print(f"[L3-SVC] _get_patterns 에러: {e}")
        return []


# ═══════════════════════════════════════════════════════════════
#  6. Fear & Greed Index
# ═══════════════════════════════════════════════════════════════
def _get_fear_greed(today: date) -> dict:
    """market_fear_greed 테이블에서 최신 공포/탐욕 지수 조회."""
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT calc_date, score, rating, previous_close
                FROM market_fear_greed
                WHERE calc_date <= %s
                ORDER BY calc_date DESC
                LIMIT 1
            """, (today,))
            row = cur.fetchone()

        if not row:
            return {"value": None, "label": "N/A", "prev": None}

        return {
            "value": float(row["score"]) if row["score"] is not None else None,
            "label": row["rating"] or "N/A",
            "prev": float(row["previous_close"]) if row["previous_close"] is not None else None,
            "date": str(row["calc_date"]),
        }
    except Exception as e:
        print(f"[L3-SVC] _get_fear_greed 에러: {e}")
        return {"value": None, "label": "N/A", "prev": None}