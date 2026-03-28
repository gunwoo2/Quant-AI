"""
services/layer3_service.py — Layer 3 Market Signal 데이터 조회
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GET /api/stock/layer3/{ticker} 에서 호출
MarketSignalTab.jsx의 Overview / Technical / Flow / Macro 탭에 실데이터 공급

v2: totalScore 폴백 로직 + section_b/c 실시간 계산
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

    overview = _get_overview(stock_id, today, sector_code)
    technical = _get_technical(stock_id, today)
    flow = _get_flow(stock_id, today)
    macro = _get_macro(today, sector_code)

    return {
        "ticker": ticker.upper(),
        "companyName": company_name,
        "overview": overview,
        "technical": technical,
        "flow": flow,
        "macro": macro,
        "patterns": _get_patterns(stock_id, today),
        "fearGreed": _get_fear_greed(today),
    }


# ═══════════════════════════════════════════════════════════════
#  1. Overview (요약 카드 + 레이더)
# ═══════════════════════════════════════════════════════════════
def _get_overview(stock_id: int, today: date, sector_code: str = "") -> dict:
    with get_cursor() as cur:
        cur.execute("""
            SELECT
                section_a_technical, section_b_flow, section_c_macro,
                layer3_total_score, layer3_technical_score,
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
        return {"totalScore": None, "calcDate": None, "sections": [], "radar": [], "indicators": []}

    sa = _f(row["section_a_technical"])
    sb = _f(row["section_b_flow"])
    sc = _f(row["section_c_macro"])

    # ── section_b 실시간 폴백: DB에 0이면 관련 테이블에서 직접 계산 ──
    if not sb or sb == 0:
        sb = _calc_section_b_realtime(stock_id, row)

    # ── section_c 실시간 폴백: DB에 0이면 관련 테이블에서 직접 계산 ──
    if not sc or sc == 0:
        sc = _calc_section_c_realtime(sector_code, row)

    # ── totalScore 폴백 ──
    total = _f(row["layer3_total_score"])
    if not total or total == 0:
        # layer3_technical_score 시도
        total = _f(row.get("layer3_technical_score"))
    if not total or total == 0:
        # section 합산으로 계산
        total = round((sa or 0) + (sb or 0) + (sc or 0), 2)
    if not total or total == 0:
        total = sa  # 최소한 section_a라도

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


def _calc_section_b_realtime(stock_id: int, ti_row: dict) -> float:
    """section_b_flow 실시간 계산 — short_volume_daily + put_call + structural"""
    score = 0.0

    # 1. 공매도 점수 (max 10) — short_volume_daily에서
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT short_volume_score FROM short_volume_daily
                WHERE stock_id = %s
                ORDER BY trade_date DESC LIMIT 1
            """, (stock_id,))
            sv_row = cur.fetchone()
        if sv_row and sv_row["short_volume_score"] is not None:
            score += min(float(sv_row["short_volume_score"]), 10.0)
    except Exception:
        pass

    # 2. 풋콜 점수 (max 7) — technical_indicators에서
    pc = _f(ti_row.get("put_call_score"))
    if pc:
        score += min(pc, 7.0)

    # 3. 구조적 시그널 (max 8) — technical_indicators에서
    struct = _f(ti_row.get("structural_signal_score"))
    if struct:
        score += min(struct, 8.0)

    return round(min(score, 25.0), 2)


def _calc_section_c_realtime(sector_code: str, ti_row: dict) -> float:
    """section_c_macro 실시간 계산 — VIX + 섹터 ETF"""
    score = 0.0

    # 1. VIX 점수 (max 10)
    vix_s = _f(ti_row.get("vix_score"))
    if vix_s:
        score += min(vix_s, 10.0)
    else:
        # macro_indicators에서 VIX 가져와서 직접 계산
        try:
            with get_cursor() as cur:
                cur.execute("""
                    SELECT value FROM macro_indicators
                    WHERE indicator_name = 'VIX'
                    ORDER BY recorded_date DESC LIMIT 1
                """)
                vix_row = cur.fetchone()
            if vix_row and vix_row["value"] is not None:
                vix_val = float(vix_row["value"])
                # VIX 점수: 낮을수록 좋음 (시장 안정)
                if vix_val <= 12:
                    score += 10.0
                elif vix_val <= 15:
                    score += 8.0
                elif vix_val <= 20:
                    score += 6.0
                elif vix_val <= 25:
                    score += 4.0
                elif vix_val <= 30:
                    score += 2.0
                else:
                    score += 0.5
        except Exception:
            pass

    # 2. 섹터 ETF 점수 (max 10)
    etf_s = _f(ti_row.get("sector_etf_score"))
    if etf_s:
        score += min(etf_s, 10.0)
    elif sector_code:
        # sector_etf_daily에서 직접 조회
        try:
            with get_cursor() as cur:
                cur.execute("""
                    SELECT sector_etf_score FROM sector_etf_daily
                    WHERE sector_code = %s
                    ORDER BY calc_date DESC LIMIT 1
                """, (sector_code,))
                etf_row = cur.fetchone()
            if etf_row and etf_row["sector_etf_score"] is not None:
                score += min(float(etf_row["sector_etf_score"]), 10.0)
        except Exception:
            pass

    return round(min(score, 20.0), 2)


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
        return {"indicators": [], "structural": {}}

    def _ind(name, val, score, max_s, unit=""):
        return {
            "name": name, "value": _f(val, 4), "score": _f(score), "max": max_s,
            "unit": unit, "pct": round(_f(score, 4) / max_s * 100, 1) if _f(score) and max_s else 0,
        }

    indicators = [
        _ind("상대 모멘텀 (12-1M)", row["relative_momentum_12_1"], row["relative_momentum_score"], 15, "%"),
        _ind("52주 고가 근접도",     row["high_52w_position_ratio"], row["high_52w_score"], 10, "%"),
        _ind("추세 안정성 (R²)",     row["trend_r2_90d"],  row["trend_stability_score"], 8),
        _ind("RSI (14일)",          row["rsi_14"],         row["rsi_score"], 7),
        _ind("MACD 히스토그램",      row["macd_histogram"], row["macd_score"], 5),
        _ind("OBV 추세",            None,                  row["obv_score"], 5, row.get("obv_trend") or ""),
        _ind("거래량 급증 비율",     row["volume_surge_ratio"], row["volume_surge_score"], 5, "x"),
    ]

    structural = {
        "goldenCross": bool(row.get("golden_cross")),
        "deathCross": bool(row.get("death_cross")),
        "bbSqueeze": bool(row.get("bb_squeeze")),
        "ma20Streak": row.get("ma20_streak_days") or 0,
        "breakout52w": bool(row.get("breakout_52w")),
        "structuralScore": _f(row.get("structural_signal_score")),
        "ma50": _f(row.get("ma_50")),
        "ma200": _f(row.get("ma_200")),
        "bbUpper": _f(row.get("bb_upper")),
        "bbLower": _f(row.get("bb_lower")),
        "bbWidth": _f(row.get("bb_width"), 4),
    }

    return {
        "indicators": indicators,
        "structural": structural,
        "calcDate": str(row["calc_date"]),
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
    # VIX + SPY — market_signal_daily 또는 macro_indicators에서
    vix = {}
    spy = {}

    # 먼저 market_signal_daily 시도
    with get_cursor() as cur:
        cur.execute("""
            SELECT calc_date, vix_close, vix_score,
                   spy_close, spy_ma50, spy_ma200
            FROM market_signal_daily
            ORDER BY calc_date DESC LIMIT 1
        """)
        mrow = cur.fetchone()

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
    else:
        # market_signal_daily 없으면 macro_indicators에서 폴백
        try:
            with get_cursor() as cur:
                cur.execute("""
                    SELECT value, recorded_date FROM macro_indicators
                    WHERE indicator_name = 'VIX'
                    ORDER BY recorded_date DESC LIMIT 1
                """)
                vix_row = cur.fetchone()
            if vix_row:
                vix_val = float(vix_row["value"])
                # VIX → 점수 변환
                if vix_val <= 12: vs = 10.0
                elif vix_val <= 15: vs = 8.0
                elif vix_val <= 20: vs = 6.0
                elif vix_val <= 25: vs = 4.0
                elif vix_val <= 30: vs = 2.0
                else: vs = 0.5
                vix = {"close": _f(vix_val), "score": _f(vs), "date": str(vix_row["recorded_date"])}
        except Exception:
            pass

        try:
            with get_cursor() as cur:
                cur.execute("""
                    SELECT value, recorded_date FROM macro_indicators
                    WHERE indicator_name = 'SP500'
                    ORDER BY recorded_date DESC LIMIT 1
                """)
                spy_row = cur.fetchone()
            if spy_row:
                spy = {"close": _f(float(spy_row["value"])), "ma50": None, "ma200": None}
        except Exception:
            pass

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
#  5. Chart Patterns (batch_chart_patterns → chart_patterns 테이블)
# ═══════════════════════════════════════════════════════════════
def _get_patterns(stock_id: int, today) -> list:
    """chart_patterns 테이블에서 종목별 패턴 조회 (최근 3일)"""
    try:
        from db_pool import get_cursor
        with get_cursor() as cur:
            cur.execute("""
                SELECT pattern_type, pattern_name, direction, strength, description
                FROM chart_patterns
                WHERE stock_id = %s AND calc_date >= %s::date - INTERVAL '3 days'
                ORDER BY strength DESC NULLS LAST
            """, (stock_id, today))
            rows = cur.fetchall()
        return [
            {
                "type": r["pattern_type"],
                "name": r["pattern_name"],
                "direction": r["direction"],
                "confidence": float(r["strength"]) if r["strength"] else 0,
                "desc": r["description"] or "",
            }
            for r in rows
        ]
    except Exception as e:
        print(f"[L3-SVC] _get_patterns 에러: {e}")
        return []


# ═══════════════════════════════════════════════════════════════
#  6. Fear & Greed Index (batch_fear_greed → market_fear_greed 테이블)
# ═══════════════════════════════════════════════════════════════
def _classify_fg(score):
    """점수 → 레이팅 자동 분류 (DB에 rating 없을 때 fallback)"""
    if score is None:
        return "N/A"
    if score <= 25:
        return "Extreme Fear"
    elif score <= 45:
        return "Fear"
    elif score <= 55:
        return "Neutral"
    elif score <= 75:
        return "Greed"
    else:
        return "Extreme Greed"


def _get_fear_greed(today) -> dict:
    """
    market_fear_greed 테이블에서 최신 F&G 조회.
    반환: { value, label, prev, oneWeek, oneMonth, oneYear, date }
    """
    try:
        from db_pool import get_cursor
        with get_cursor() as cur:
            cur.execute("""
                SELECT score, rating, calc_date,
                       previous_close, one_week_ago, one_month_ago, one_year_ago
                FROM market_fear_greed
                ORDER BY calc_date DESC LIMIT 2
            """)
            rows = cur.fetchall()
        if not rows:
            return {"value": None, "label": "N/A", "prev": None}

        current = rows[0]
        prev_row = rows[1] if len(rows) > 1 else None

        score_val = float(current["score"]) if current["score"] is not None else None
        label = current.get("rating") or _classify_fg(score_val)

        return {
            "value": score_val,
            "label": label,
            "prev": float(current["previous_close"]) if current.get("previous_close") else (
                     float(prev_row["score"]) if prev_row and prev_row["score"] else None),
            "oneWeek": float(current["one_week_ago"]) if current.get("one_week_ago") else None,
            "oneMonth": float(current["one_month_ago"]) if current.get("one_month_ago") else None,
            "oneYear": float(current["one_year_ago"]) if current.get("one_year_ago") else None,
            "date": str(current["calc_date"]),
        }
    except Exception as e:
        print(f"[L3-SVC] _get_fear_greed 에러: {e}")
        return {"value": None, "label": "N/A", "prev": None}
