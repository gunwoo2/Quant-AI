"""
services/layer2_service.py — Layer 2 NLP 시그널 데이터 조회 (v3.4)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GET /api/stock/layer2/{ticker}
+ 신뢰도 등급 + 스코어링 모드 (FIXED / ADAPTIVE)
+ DB 스키마 자동 감지 (컬럼명 불일치 대응)
"""
import traceback
from datetime import date, datetime, timezone
from db_pool import get_cursor

CALIBRATION_MIN_DAYS = 90

def _utcnow():
    return datetime.now(timezone.utc)

def _safe(val, default=0):
    if val is None: return default
    try:
        v = float(val)
        return default if v != v else v
    except (TypeError, ValueError): return default

def _safe_int(val, default=0):
    return int(_safe(val, default))


# ═══════════════════════════════════════════
#  DB 스키마 자동 감지 (캐시)
# ═══════════════════════════════════════════
_analyst_cols_cache = None

def _get_analyst_cols():
    global _analyst_cols_cache
    if _analyst_cols_cache: return _analyst_cols_cache
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT column_name FROM information_schema.columns
                WHERE table_name = 'analyst_rating_aggregates'
            """)
            _analyst_cols_cache = {r["column_name"] for r in cur.fetchall()}
    except: _analyst_cols_cache = set()
    return _analyst_cols_cache

def _col(preferred, fallback, cols):
    if preferred in cols: return preferred
    if fallback in cols: return fallback
    return None


def get_layer2_data(ticker: str) -> dict | None:
    try:
        with get_cursor() as cur:
            cur.execute(
                "SELECT stock_id, company_name FROM stocks WHERE ticker = %s LIMIT 1",
                (ticker.upper(),))
            row = cur.fetchone()
            if not row: return None
            stock_id = row["stock_id"]
            company_name = row["company_name"] or ticker.upper()

        today = date.today()
        return {
            "ticker": ticker.upper(),
            "companyName": company_name,
            "overview":    _get_overview(stock_id, today),
            "confidence":  _get_confidence(stock_id, today),
            "news":        _get_news_data(stock_id, today),
            "analyst":     _get_analyst_data(stock_id, today),
            "insider":     _get_insider_data(stock_id, today),
        }
    except Exception as e:
        print(f"[L2-SVC] get_layer2_data({ticker}) 에러: {e}")
        traceback.print_exc()
        raise


# ═══════════════════════════════════════════
#  0. Confidence + Scoring Mode
# ═══════════════════════════════════════════
def _get_confidence(stock_id: int, today: date) -> dict:
    cols = _get_analyst_cols()
    ta_col = _col("total_analysts", "total_analyst_count", cols)

    with get_cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) AS cnt FROM news_articles
            WHERE stock_id = %s AND COALESCE(published_at, created_at) >= %s::date - 7
        """, (stock_id, today))
        news_cnt = _safe_int((cur.fetchone() or {}).get("cnt"))

        analyst_cnt = 0
        if ta_col:
            try:
                cur.execute(f"""
                    SELECT {ta_col} FROM analyst_rating_aggregates
                    WHERE stock_id = %s ORDER BY calc_date DESC LIMIT 1
                """, (stock_id,))
                analyst_cnt = _safe_int((cur.fetchone() or {}).get(ta_col))
            except: pass

        cur.execute("""
            SELECT COUNT(*) AS cnt FROM insider_transactions
            WHERE stock_id = %s AND transaction_date >= %s::date - 90
        """, (stock_id, today))
        insider_cnt = _safe_int((cur.fetchone() or {}).get("cnt"))

        cal_days, is_cal = 0, False
        try:
            cur.execute("""
                SELECT calibration_days, is_calibrated FROM l2_calibration_stats
                WHERE stock_id = %s ORDER BY calc_date DESC LIMIT 1
            """, (stock_id,))
            cal = cur.fetchone()
            if cal:
                cal_days = _safe_int(cal.get("calibration_days"))
                is_cal = bool(cal.get("is_calibrated"))
        except: pass

    n = min(news_cnt / 10, 1.0)
    a = min(analyst_cnt / 10, 1.0)
    i = min(insider_cnt / 3, 1.0)
    total = n * 0.4 + a * 0.35 + i * 0.25

    if total >= 0.7:   grade = "HIGH"
    elif total >= 0.4: grade = "MED"
    elif total >= 0.1: grade = "LOW"
    else:              grade = "NO_DATA"

    scoring_mode = "ADAPTIVE" if is_cal else "FIXED"
    remaining = max(0, CALIBRATION_MIN_DAYS - cal_days)
    if is_cal:
        msg = f"{cal_days}일 데이터 기반 적응형 스코어링 활성"
    else:
        msg = f"데이터 축적 {cal_days}/{CALIBRATION_MIN_DAYS}일 — {remaining}일 후 적응형 전환"

    return {
        "grade": grade,
        "scoringMode": scoring_mode,
        "calibrationDays": cal_days,
        "calibrationTarget": CALIBRATION_MIN_DAYS,
        "daysRemaining": remaining,
        "newsCount": news_cnt,
        "analystCount": analyst_cnt,
        "insiderCount": insider_cnt,
        "message": msg,
    }


# ═══════════════════════════════════════════
#  1. Overview
# ═══════════════════════════════════════════
def _get_overview(stock_id: int, today: date) -> dict:
    with get_cursor() as cur:
        cur.execute("""
            SELECT news_sentiment_score, earnings_call_score,
                   analyst_rating_score, insider_signal_score,
                   layer2_total_score
            FROM layer2_scores
            WHERE stock_id = %s AND calc_date >= %s - 7
            ORDER BY calc_date DESC LIMIT 1
        """, (stock_id, today))
        row = cur.fetchone()

    if not row:
        return {"totalScore": 50, "radar": [], "signals": [], "conviction": "NO DATA"}

    total = _safe(row["layer2_total_score"], 50)
    ns  = _safe(row["news_sentiment_score"], 50)
    es  = _safe(row["earnings_call_score"], 50)
    as_ = _safe(row["analyst_rating_score"], 50)
    is_ = _safe(row["insider_signal_score"], 50)

    radar = [
        {"axis": "News", "score": round(ns)},
        {"axis": "Analyst", "score": round(as_)},
        {"axis": "Insider", "score": round(is_)},
        {"axis": "Earnings", "score": round(es)},
    ]

    def _sig(score):
        if score >= 75: return ("BULLISH", "#22c55e")
        if score >= 60: return ("POSITIVE", "#86efac")
        if score >= 40: return ("NEUTRAL", "#9ca3af")
        if score >= 25: return ("NEGATIVE", "#fbbf24")
        return ("BEARISH", "#ef4444")

    signals = []
    for label, sc, phase in [
        ("FinBERT News Sentiment", ns, 2),
        ("Analyst Revision", as_, 2),
        ("SEC Insider Flow", is_, 2),
        ("Earnings Call Tone", es, 3),
    ]:
        sig, color = _sig(sc)
        signals.append({"label": label, "score": round(sc), "sig": sig, "color": color, "phase": phase})

    if total >= 75:   conv = "BULLISH CONVICTION"
    elif total >= 60: conv = "POSITIVE BIAS"
    elif total >= 40: conv = "NEUTRAL"
    elif total >= 25: conv = "NEGATIVE BIAS"
    else:             conv = "BEARISH CONVICTION"

    return {"totalScore": round(total), "radar": radar, "signals": signals, "conviction": conv}


# ═══════════════════════════════════════════
#  2. News
# ═══════════════════════════════════════════
def _get_news_data(stock_id: int, today: date) -> dict:
    result = {
        "trend": [], "distribution": {"positive": 0, "negative": 0, "neutral": 0, "total": 0},
        "articles": [], "avgSentiment": 0.0, "newsScore": 50,
    }
    with get_cursor() as cur:
        cur.execute("""
            SELECT sentiment_date AS d, avg_sentiment_score AS s,
                   layer2_news_score AS score, total_articles AS cnt
            FROM news_sentiment_daily
            WHERE stock_id = %s AND sentiment_date >= %s - 30
            ORDER BY sentiment_date
        """, (stock_id, today))
        for r in cur.fetchall():
            result["trend"].append({
                "d": r["d"].strftime("%m/%d") if r["d"] else "",
                "s": round(_safe(r["s"]), 4), "score": round(_safe(r["score"], 50)),
            })

        cur.execute("""
            SELECT
                COUNT(*) FILTER (WHERE s.sentiment_score > 0.15) AS pos,
                COUNT(*) FILTER (WHERE s.sentiment_score < -0.15) AS neg,
                COUNT(*) FILTER (WHERE s.sentiment_score BETWEEN -0.15 AND 0.15) AS neu,
                COUNT(*) AS total, ROUND(AVG(s.sentiment_score), 4) AS avg
            FROM news_articles a
            JOIN news_sentiment_scores s ON a.news_id = s.news_id
            WHERE a.stock_id = %s AND COALESCE(a.published_at, a.created_at) >= NOW() - INTERVAL '7 days'
        """, (stock_id,))
        d = cur.fetchone()
        if d:
            result["distribution"] = {
                "positive": _safe_int(d["pos"]), "negative": _safe_int(d["neg"]),
                "neutral": _safe_int(d["neu"]), "total": _safe_int(d["total"]),
            }
            result["avgSentiment"] = round(_safe(d["avg"]), 4)

        cur.execute("""
            SELECT a.title, a.source_name AS src, a.url, a.published_at,
                   s.sentiment_score, s.sentiment_label, s.confidence, s.model_version
            FROM news_articles a
            JOIN news_sentiment_scores s ON a.news_id = s.news_id
            WHERE a.stock_id = %s
            ORDER BY COALESCE(a.published_at, a.created_at) DESC LIMIT 20
        """, (stock_id,))
        for r in cur.fetchall():
            elapsed = ""
            if r["published_at"]:
                try:
                    diff = _utcnow() - r["published_at"]
                    hrs = diff.total_seconds() / 3600
                    if hrs < 1: elapsed = f"{max(1, int(diff.total_seconds()/60))}m"
                    elif hrs < 24: elapsed = f"{int(hrs)}h"
                    else: elapsed = f"{int(hrs/24)}d"
                except: elapsed = ""
            result["articles"].append({
                "title": r["title"] or "", "src": r["src"] or "", "url": r["url"] or "",
                "time": elapsed, "score": round(_safe(r["sentiment_score"]), 4),
                "label": r["sentiment_label"] or "NEUTRAL",
                "confidence": round(_safe(r["confidence"]), 2), "model": r["model_version"] or "",
            })

        cur.execute("""
            SELECT layer2_news_score FROM news_sentiment_daily
            WHERE stock_id = %s ORDER BY sentiment_date DESC LIMIT 1
        """, (stock_id,))
        ns = cur.fetchone()
        if ns: result["newsScore"] = round(_safe(ns["layer2_news_score"], 50))
    return result


# ═══════════════════════════════════════════
#  3. Analyst
# ═══════════════════════════════════════════
def _get_analyst_data(stock_id: int, today: date) -> dict:
    result = {
        "consensus": {"buy": 0, "hold": 0, "sell": 0, "total": 0, "buyPct": 0},
        "score": 50, "netUpgrade": 0, "upgradeCount": 0, "downgradeCount": 0,
    }
    cols = _get_analyst_cols()
    ta  = _col("total_analysts", "total_analyst_count", cols)
    bc  = _col("buy_count", "buy_count", cols)
    hc  = _col("hold_count", "hold_count", cols)
    sc_ = _col("sell_count", "sell_count", cols)
    bp  = _col("buy_pct", "buy_percentage", cols)
    sp  = _col("sell_pct", "sell_percentage", cols)
    u90 = _col("upgrade_count_90d", "upgrade_count", cols)
    d90 = _col("downgrade_count_90d", "downgrade_count", cols)
    n90 = _col("net_upgrade_90d", "net_upgrade", cols)
    asc = _col("layer2_analyst_score", "analyst_score", cols)

    if not (ta and asc):
        return result

    with get_cursor() as cur:
        try:
            cur.execute(f"""
                SELECT {ta}, {bc}, {hc}, {sc_},
                       {bp}, {sp}, {u90}, {d90},
                       {n90}, {asc}
                FROM analyst_rating_aggregates
                WHERE stock_id = %s AND calc_date >= %s - 7
                ORDER BY calc_date DESC LIMIT 1
            """, (stock_id, today))
            r = cur.fetchone()
        except:
            r = None

    if r:
        result["consensus"] = {
            "buy": _safe_int(r.get(bc)), "hold": _safe_int(r.get(hc)),
            "sell": _safe_int(r.get(sc_)), "total": _safe_int(r.get(ta)),
            "buyPct": round(_safe(r.get(bp))),
        }
        result["score"] = round(_safe(r.get(asc), 50))
        result["netUpgrade"] = _safe_int(r.get(n90))
        result["upgradeCount"] = _safe_int(r.get(u90))
        result["downgradeCount"] = _safe_int(r.get(d90))
    return result


# ═══════════════════════════════════════════
#  4. Insider
# ═══════════════════════════════════════════
def _get_insider_data(stock_id: int, today: date) -> dict:
    result = {
        "score": 50, "signal": "NEUTRAL", "largeSellAlert": False,
        "cLevelBuyCount": 0, "buyCount": 0, "sellCount": 0,
        "trades": [], "monthlyFlow": [],
    }
    with get_cursor() as cur:
        cur.execute("""
            SELECT layer2_insider_score, net_insider_signal,
                   large_sell_alert, c_level_net_buy_30d, insider_count_buying_30d
            FROM insider_signal_aggregates
            WHERE stock_id = %s AND calc_date >= %s - 7
            ORDER BY calc_date DESC LIMIT 1
        """, (stock_id, today))
        r = cur.fetchone()
        if r:
            result["score"] = round(_safe(r["layer2_insider_score"], 50))
            result["signal"] = r["net_insider_signal"] or "NEUTRAL"
            result["largeSellAlert"] = bool(r["large_sell_alert"])
            result["cLevelBuyCount"] = _safe_int(r["insider_count_buying_30d"])

        cur.execute("""
            SELECT insider_name, insider_title, is_c_level,
                   transaction_date, transaction_type,
                   shares_transacted, price_per_share, total_value
            FROM insider_transactions
            WHERE stock_id = %s ORDER BY transaction_date DESC LIMIT 20
        """, (stock_id,))
        b_cnt, s_cnt = 0, 0
        for r in cur.fetchall():
            val = _safe(r["total_value"])
            if r["transaction_type"] == "BUY": b_cnt += 1
            else: s_cnt += 1
            result["trades"].append({
                "name": r["insider_name"] or "",
                "role": r["insider_title"] or ("C-Level" if r["is_c_level"] else "Insider"),
                "type": r["transaction_type"],
                "shares": f"{r['shares_transacted']:,}" if r["shares_transacted"] else "-",
                "val": f"${val/1e6:.1f}M" if val >= 1e6 else (f"${val/1e3:.0f}K" if val >= 1e3 else f"${val:.0f}"),
                "date": str(r["transaction_date"]) if r["transaction_date"] else "",
                "isCLevel": bool(r["is_c_level"]),
            })
        result["buyCount"] = b_cnt
        result["sellCount"] = s_cnt

        cur.execute("""
            SELECT TO_CHAR(transaction_date, 'Mon') AS m,
                   EXTRACT(YEAR FROM transaction_date) AS y,
                   EXTRACT(MONTH FROM transaction_date) AS mn,
                   COALESCE(SUM(CASE WHEN transaction_type='BUY' THEN total_value END),0)/1e6 AS buy,
                   COALESCE(SUM(CASE WHEN transaction_type='SELL' THEN total_value END),0)/1e6 AS sell
            FROM insider_transactions
            WHERE stock_id = %s AND transaction_date >= %s - INTERVAL '6 months'
            GROUP BY m, y, mn ORDER BY y, mn
        """, (stock_id, today))
        for r in cur.fetchall():
            result["monthlyFlow"].append({
                "m": r["m"], "buy": round(_safe(r["buy"]),1), "sell": round(_safe(r["sell"]),1),
            })
    return result