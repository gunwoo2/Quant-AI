"""
stock_service.py — 종목 서비스 v5.0
====================================
v5.0:
  - AI: xgboost_predictions → ai_scores_daily
  - AI 등급: 횡단면 백분위(Cross-Sectional Percentile)
  - L3: technical_indicators에서 직접 보정
  - 에러 로깅 (except pass 제거)
"""
from typing import Optional
from db_pool import get_cursor
import traceback


SECTOR_KO_MAP = {
    "10": "에너지", "15": "소재", "20": "산업재", "25": "경기소비재",
    "30": "필수소비재", "35": "헬스케어", "40": "금융", "45": "IT",
    "50": "커뮤니케이션", "55": "유틸리티", "60": "부동산",
}


# ═══════════════════════════════════════════════════════
#  횡단면 백분위 등급 (batch_final_score 동일 방법론)
# ═══════════════════════════════════════════════════════
_GRADE_PCT_CUTS = [
    (97, "S"), (92, "A+"), (82, "A"), (65, "B+"),
    (40, "B"), (15, "C"), (0, "D"),
]
_ABSOLUTE_FLOOR = [(25, "D"), (30, "C"), (35, "B"), (40, "B+")]
_GRADE_ORDER = {"S": 7, "A+": 6, "A": 5, "B+": 4, "B": 3, "C": 2, "D": 1}
_GRADE_TO_SIGNAL = {
    "S": "STRONG_BUY", "A+": "STRONG_BUY",
    "A": "BUY", "B+": "BUY", "B": "HOLD",
    "C": "SELL", "D": "STRONG_SELL",
}

def _pct_to_grade(pct):
    if pct is None: return None
    for cutoff, g in _GRADE_PCT_CUTS:
        if pct >= cutoff: return g
    return "D"

def _apply_floor(grade, raw):
    if grade is None or raw is None: return grade
    for th, cap in _ABSOLUTE_FLOOR:
        if raw < th:
            if _GRADE_ORDER.get(grade, 0) > _GRADE_ORDER.get(cap, 0): return cap
            return grade
    return grade

def _cross_sectional_grades(ai_map):
    """전 종목 ensemble에 횡단면 백분위 등급/시그널 부여."""
    import numpy as np
    from scipy import stats as sp_stats
    tickers, scores = [], []
    for tk, d in ai_map.items():
        if d.get("ensemble") is not None:
            tickers.append(tk); scores.append(d["ensemble"])
    if len(tickers) < 5: return
    arr = np.array(scores, dtype=float)
    median = np.median(arr); mad = np.median(np.abs(arr - median))
    if mad < 1e-8:
        std = np.std(arr)
        if std < 1e-8:
            from scipy.stats import rankdata
            ranks = rankdata(arr, method="average")
            pcts = (ranks - 1) / max(len(ranks) - 1, 1) * 100.0
        else:
            z = np.clip((arr - np.mean(arr)) / std, -3.0, 3.0)
            pcts = sp_stats.norm.cdf(z) * 100.0
    else:
        z = np.clip((arr - median) / (1.4826 * mad), -3.0, 3.0)
        pcts = sp_stats.norm.cdf(z) * 100.0
    for i, tk in enumerate(tickers):
        grade = _pct_to_grade(float(pcts[i]))
        grade = _apply_floor(grade, scores[i])
        ai_map[tk]["ai_grade"] = grade
        ai_map[tk]["ai_signal"] = _GRADE_TO_SIGNAL.get(grade, "HOLD")

# legacy
_SIGNAL_THRESHOLDS = [
    (80, "STRONG_BUY"), (65, "BUY"), (50, "OUTPERFORM"),
    (40, "HOLD"), (30, "UNDERPERFORM"), (20, "SELL"), (0, "STRONG_SELL"),
]
def _score_to_signal(score):
    if score is None: return None
    for th, label in _SIGNAL_THRESHOLDS:
        if score >= th: return label
    return "STRONG_SELL"

def get_stock_list(
    sector:  Optional[str] = None,
    country: Optional[str] = None,
    grade:   Optional[str] = None,
) -> list[dict]:
    """
    메인 종목 목록 조회.
    v4.2: signal을 investment_opinion(한국어) 대신 signal(영문키)로 직접 반환
    """
    conditions = ["1=1"]
    params: list = []

    if sector:
        conditions.append("sec.sector_code = %s")
        params.append(sector)
    if country:
        conditions.append("m.market_code = %s")
        params.append(country.upper())
    if grade:
        conditions.append("fs.grade = %s")
        params.append(grade)

    where_clause = " AND ".join(conditions)

    sql = f"""
        SELECT
            s.ticker,
            s.company_name                      AS name,
            sec.sector_name                     AS sector,
            sec.sector_code,
            m.market_code                       AS country,
            rt.current_price                    AS price,
            rt.price_change_pct                 AS chg,
            fs.layer1_score                     AS l1,
            fs.layer2_score                     AS l2,
            fs.layer3_score                     AS l3,
            fs.weighted_score                   AS score,
            fs.grade,
            fs.signal,
            COALESCE(lc.like_count, 0)          AS like_count
        FROM stocks s
        JOIN markets m ON s.market_id = m.market_id
        LEFT JOIN sectors sec ON s.sector_id = sec.sector_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id)
                stock_id, layer1_score, layer2_score, layer3_score,
                weighted_score, grade, signal
            FROM stock_final_scores
            ORDER BY stock_id, calc_date DESC
        ) fs ON s.stock_id = fs.stock_id
        LEFT JOIN stock_prices_realtime rt ON s.stock_id = rt.stock_id
        LEFT JOIN stock_like_counts lc ON s.stock_id = lc.stock_id
        WHERE s.is_active = TRUE AND {where_clause}
        ORDER BY fs.weighted_score DESC NULLS LAST, s.ticker ASC
    """

    with get_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    result = []
    for row in rows:
        item = dict(row)
        for key in ("price", "chg", "l1", "l2", "l3", "score"):
            if item.get(key) is not None:
                item[key] = float(item[key])
        result.append(item)

    # ── L3 보정 (stock_final_scores가 0일 때 technical_indicators에서 직접) ──
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT s.ticker,
                       COALESCE(ti.layer3_total_score, ti.layer3_technical_score) AS l3_direct
                FROM (
                    SELECT DISTINCT ON (stock_id)
                        stock_id, layer3_total_score, layer3_technical_score
                    FROM technical_indicators
                    ORDER BY stock_id, calc_date DESC
                ) ti
                JOIN stocks s ON s.stock_id = ti.stock_id
            """)
            l3_map = {r["ticker"]: float(r["l3_direct"]) for r in cur.fetchall() if r["l3_direct"] is not None}
        for item in result:
            if (item.get("l3") is None or item.get("l3") == 0) and item.get("ticker") in l3_map:
                item["l3"] = l3_map[item["ticker"]]
    except Exception as e:
        print(f"[stock_service] ⚠️ L3 보정 실패: {e}")

    # ── AI 데이터 보충 (ai_scores_daily + 횡단면 백분위) ──
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT s.ticker, xp.ai_score, xp.ensemble_score
                FROM (
                    SELECT DISTINCT ON (stock_id) stock_id, ai_score, ensemble_score
                    FROM ai_scores_daily ORDER BY stock_id, calc_date DESC
                ) xp
                JOIN stocks s ON s.stock_id = xp.stock_id
            """)
            ai_map = {}
            for r in cur.fetchall():
                ai_s = float(r["ai_score"]) if r["ai_score"] is not None else None
                ens = float(r["ensemble_score"]) if r["ensemble_score"] is not None else None
                ai_map[r["ticker"]] = {"ai_score": ai_s, "ensemble": ens, "ai_grade": None, "ai_signal": None}
        _cross_sectional_grades(ai_map)
        for item in result:
            ai = ai_map.get(item.get("ticker"), {})
            item["ai_score"] = ai.get("ai_score")
            item["ensemble"] = ai.get("ensemble")
            item["ai_grade"] = ai.get("ai_grade")
            item["ai_signal"] = ai.get("ai_signal")
    except Exception as e:
        print(f"[stock_service] ⚠️ AI 데이터 실패: {e}")
        traceback.print_exc()


    # ── Conviction 보충 (daily_stock_score — 테이블 없으면 skip) ──
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT s.ticker,
                       dss.conviction_score,
                       dss.layer_agreement,
                       dss.data_completeness
                FROM (
                    SELECT DISTINCT ON (stock_id)
                        stock_id, conviction_score, layer_agreement, data_completeness
                    FROM daily_stock_score
                    ORDER BY stock_id, calc_date DESC
                ) dss
                JOIN stocks s ON s.stock_id = dss.stock_id
            """)
            conv_map = {
                r["ticker"]: {
                    "conviction_score": float(r["conviction_score"]) if r["conviction_score"] else None,
                    "layer_agreement": float(r["layer_agreement"]) if r["layer_agreement"] else None,
                    "data_completeness": float(r["data_completeness"]) if r["data_completeness"] else None,
                }
                for r in cur.fetchall()
            }
        for item in result:
            conv = conv_map.get(item.get("ticker"), {})
            item["conviction_score"] = conv.get("conviction_score")
            item["layer_agreement"] = conv.get("layer_agreement")
            item["data_completeness"] = conv.get("data_completeness")
    except Exception:
        pass

    return result



def get_sector_list() -> list[dict]:
    """
    사이드바용 섹터 목록.
    v4.2: top_ticker(섹터 내 최고 점수 종목 티커) 추가
    """
    sql = """
        SELECT
            sec.sector_code                             AS key,
            sec.sector_name                             AS en,
            COUNT(s.stock_id)                           AS stock_count,
            ROUND(AVG(fs.weighted_score)::NUMERIC, 1)   AS avg_score,
            top.top_grade,
            top.top_ticker
        FROM sectors sec
        LEFT JOIN stocks s
            ON sec.sector_id = s.sector_id
            AND s.is_active = TRUE
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id)
                stock_id, weighted_score, grade
            FROM stock_final_scores
            ORDER BY stock_id, calc_date DESC
        ) fs ON s.stock_id = fs.stock_id
        LEFT JOIN LATERAL (
            SELECT
                s2.ticker   AS top_ticker,
                fs2.grade   AS top_grade
            FROM stocks s2
            JOIN (
                SELECT DISTINCT ON (stock_id)
                    stock_id, weighted_score, grade
                FROM stock_final_scores
                ORDER BY stock_id, calc_date DESC
            ) fs2 ON s2.stock_id = fs2.stock_id
            WHERE s2.sector_id = sec.sector_id
              AND s2.is_active = TRUE
              AND fs2.weighted_score IS NOT NULL
            ORDER BY fs2.weighted_score DESC
            LIMIT 1
        ) top ON TRUE
        GROUP BY sec.sector_id, sec.sector_code, sec.sector_name,
                 top.top_grade, top.top_ticker
        ORDER BY sec.sector_code ASC
    """

    with get_cursor() as cur:
        cur.execute(sql)
        rows = cur.fetchall()

    result = []
    for row in rows:
        item = dict(row)
        item["ko"] = SECTOR_KO_MAP.get(item["key"], item["en"])
        if item.get("avg_score") is not None:
            item["avg_score"] = float(item["avg_score"])
        item["stock_count"] = item["stock_count"] or 0
        item["top_ticker"] = item.get("top_ticker") or "—"
        item["top_grade"] = item.get("top_grade") or "—"
        result.append(item)

    return result


# ──────────────────────────────────────────────────────────
#  GET /api/stock/detail/{ticker}  ★ TTM 기반
# ──────────────────────────────────────────────────────────
def get_stock_detail(ticker: str) -> dict | None:
    """
    종목 상세 헤더 + 실시간 데이터.
    ★ 재무지표를 TTM(Trailing Twelve Months) 기반으로 계산.
    """
    sql = """
        WITH ttm_flow AS (
            SELECT
                sf_sub.stock_id,
                SUM(sf_sub.revenue)             AS ttm_revenue,
                SUM(sf_sub.ebit)                AS ttm_ebit,
                SUM(sf_sub.net_income)          AS ttm_net_income,
                SUM(sf_sub.operating_cash_flow) AS ttm_ocf,
                SUM(sf_sub.free_cash_flow)      AS ttm_fcf,
                SUM(sf_sub.gross_profit)        AS ttm_gross_profit,
                SUM(sf_sub.ebitda)              AS ttm_ebitda,
                SUM(sf_sub.income_tax)          AS ttm_income_tax,
                SUM(sf_sub.pretax_income)       AS ttm_pretax_income,
                SUM(sf_sub.eps_actual)          AS ttm_eps
            FROM (
                SELECT stock_id, revenue, ebit, net_income,
                       operating_cash_flow, free_cash_flow,
                       gross_profit, ebitda, income_tax, pretax_income,
                       eps_actual,
                       ROW_NUMBER() OVER (
                           PARTITION BY stock_id
                           ORDER BY fiscal_year DESC, fiscal_quarter DESC
                       ) AS rn
                FROM stock_financials
                WHERE report_type = 'QUARTERLY'
            ) sf_sub
            WHERE sf_sub.rn <= 4
            GROUP BY sf_sub.stock_id
        ),
        eps_consensus AS (
            SELECT DISTINCT ON (stock_id)
                stock_id,
                eps_estimated AS consensus_eps
            FROM stock_financials
            WHERE report_type = 'ANNUAL'
              AND eps_estimated IS NOT NULL
            ORDER BY stock_id, fiscal_year DESC
        ),
        eps_annual_hist AS (
            SELECT
                stock_id,
                MAX(CASE WHEN rn = 1 THEN eps_actual END) AS eps_y1,
                MAX(CASE WHEN rn = 4 THEN eps_actual END) AS eps_y4
            FROM (
                SELECT stock_id, eps_actual,
                       ROW_NUMBER() OVER (
                           PARTITION BY stock_id
                           ORDER BY fiscal_year DESC
                       ) AS rn
                FROM stock_financials
                WHERE report_type = 'ANNUAL' AND eps_actual IS NOT NULL
            ) sub
            WHERE rn <= 5
            GROUP BY stock_id
        ),
        latest_balance AS (
            SELECT DISTINCT ON (stock_id)
                stock_id,
                total_assets         AS latest_ta,
                total_equity         AS latest_equity,
                total_debt           AS latest_debt,
                cash_and_equivalents AS latest_cash,
                invested_capital     AS latest_ic
            FROM stock_financials
            WHERE report_type = 'QUARTERLY'
            ORDER BY stock_id, fiscal_year DESC, fiscal_quarter DESC
        )
        SELECT
            -- header
            s.ticker,
            s.company_name                      AS name,
            s.description,
            s.listing_date,
            s.shares_outstanding,
            e.exchange_code                     AS exchange,
            sec.sector_name                     AS sector,
            m.market_code                       AS market,

            -- realtime
            rt.current_price                    AS price,
            rt.price_change                     AS amount_change,
            rt.price_change_pct                 AS changes_percentage,

            -- 등급/점수
            fs.grade,
            fs.weighted_score                   AS score,
            fs.layer1_score                     AS l1,
            fs.layer2_score                     AS l2,
            fs.layer3_score                     AS l3,
            fs.strong_buy_signal,
            fs.strong_sell_signal,

            -- TTM 손익
            tf.ttm_revenue,
            tf.ttm_ebit,
            tf.ttm_net_income,
            tf.ttm_ocf,
            tf.ttm_fcf,
            tf.ttm_gross_profit,
            tf.ttm_ebitda,
            tf.ttm_income_tax,
            tf.ttm_pretax_income,
            tf.ttm_eps,

            -- 최신 잔액
            lb.latest_ta,
            lb.latest_equity,
            lb.latest_debt,
            lb.latest_cash,
            lb.latest_ic,

            -- Forward PER용
            ec.consensus_eps,
            eah.eps_y1,
            eah.eps_y4

        FROM stocks s
        JOIN exchanges e ON s.exchange_id = e.exchange_id
        JOIN markets m   ON s.market_id   = m.market_id
        LEFT JOIN sectors sec ON s.sector_id = sec.sector_id
        LEFT JOIN stock_prices_realtime rt ON s.stock_id = rt.stock_id
        LEFT JOIN ttm_flow tf ON s.stock_id = tf.stock_id
        LEFT JOIN latest_balance lb ON s.stock_id = lb.stock_id
        LEFT JOIN eps_consensus ec ON s.stock_id = ec.stock_id
        LEFT JOIN eps_annual_hist eah ON s.stock_id = eah.stock_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id)
                stock_id, grade, weighted_score,
                layer1_score, layer2_score, layer3_score,
                strong_buy_signal, strong_sell_signal
            FROM stock_final_scores
            ORDER BY stock_id, calc_date DESC
        ) fs ON s.stock_id = fs.stock_id
        WHERE s.ticker = %s
          AND s.is_active = TRUE
        LIMIT 1
    """

    with get_cursor() as cur:
        cur.execute(sql, (ticker.upper(),))
        row = cur.fetchone()

    if not row:
        return None

    row = dict(row)

    def _f(key):
        v = row.get(key)
        return round(float(v), 4) if v is not None else None

    # ── TTM 파생지표 계산 ──
    ttm_ebit   = _f("ttm_ebit")
    ttm_ni     = _f("ttm_net_income")
    ttm_ocf    = _f("ttm_ocf")
    ttm_eps    = _f("ttm_eps")
    ttm_tax    = _f("ttm_income_tax")
    ttm_pretax = _f("ttm_pretax_income")

    ta     = _f("latest_ta")
    equity = _f("latest_equity")
    debt   = _f("latest_debt")
    cash   = _f("latest_cash")
    ic     = _f("latest_ic")
    shares = _f("shares_outstanding")
    price  = _f("price")

    market_cap = price * shares if (price and shares) else None

    # ROIC (TTM)
    roic = None
    if ttm_ebit is not None and ic and ic != 0:
        if ttm_tax is not None and ttm_pretax and ttm_pretax != 0:
            eff_tax = max(0.0, min(abs(ttm_tax / ttm_pretax), 0.50))
        else:
            eff_tax = 0.21
        nopat = ttm_ebit * (1 - eff_tax)
        roic = round(nopat / ic, 4)

    # PER (TTM) = 주가 / TTM EPS
    per = None
    if price and ttm_eps and ttm_eps != 0:
        per = round(price / ttm_eps, 2)

    # ── Forward PER (컨센서스 우선 → CAGR 폴백) ──
    forward_per = None
    forward_eps = None
    forward_method = None  # "consensus" | "cagr"

    # 1순위: 애널리스트 컨센서스 EPS
    consensus_eps = _f("consensus_eps")
    if consensus_eps and consensus_eps > 0 and price:
        fwd = round(price / consensus_eps, 2)
        if 0 < fwd <= 200:
            forward_per = fwd
            forward_eps = round(consensus_eps, 4)
            forward_method = "consensus"

    # 2순위: EPS 3년 CAGR 기반 자체 추정
    if forward_per is None and ttm_eps and ttm_eps > 0 and price:
        eps_y1 = _f("eps_y1")  # 최신 ANNUAL
        eps_y4 = _f("eps_y4")  # 3년 전
        if eps_y1 and eps_y1 > 0 and eps_y4 and eps_y4 > 0:
            cagr = (eps_y1 / eps_y4) ** (1.0 / 3.0) - 1.0
            if -0.30 <= cagr <= 0.80:
                est_eps = round(ttm_eps * (1 + cagr), 4)
                if est_eps > 0:
                    fwd = round(price / est_eps, 2)
                    if 0 < fwd <= 200:
                        forward_per = fwd
                        forward_eps = est_eps
                        forward_method = "cagr"

    # PBR (TTM) = 시총 / 자본
    pbr = None
    if market_cap and equity and equity != 0:
        pbr = round(market_cap / equity, 2)

    # ROE (TTM) = TTM 순이익 / 자본
    roe = None
    if ttm_ni and equity and equity != 0:
        roe = round(ttm_ni / equity, 4)

    # ROA (TTM) = TTM 순이익 / 총자산
    roa = None
    if ttm_ni and ta and ta != 0:
        roa = round(ttm_ni / ta, 4)

    # float 변환
    float_fields = ("price", "amount_change", "changes_percentage",
                    "score", "l1", "l2", "l3")
    for f in float_fields:
        if row.get(f) is not None:
            row[f] = float(row[f])


    # ── L3 보정 (get_stock_detail) ──
    if (row.get("l3") is None or row.get("l3") == 0):
        try:
            with get_cursor() as cur:
                cur.execute("""
                    SELECT COALESCE(layer3_total_score, layer3_technical_score) AS l3
                    FROM technical_indicators
                    WHERE stock_id = (SELECT stock_id FROM stocks WHERE UPPER(ticker) = %s)
                    ORDER BY calc_date DESC LIMIT 1
                """, (ticker.upper(),))
                l3r = cur.fetchone()
                if l3r and l3r["l3"] is not None:
                    row["l3"] = float(l3r["l3"])
        except Exception:
            pass


    return {
        "header": {
            "ticker":      row["ticker"],
            "name":        row["name"],
            "description": row.get("description"),
            "exchange":    row.get("exchange"),
            "sector":      row.get("sector"),
            "market":      row.get("market"),
            "listingDate": row.get("listing_date"),
        },
        "realtime": {
            "price":             row.get("price"),
            "change":            row.get("changes_percentage"),
            "amount_change":     row.get("amount_change"),
            "changesPercentage": row.get("changes_percentage"),
            "grade":             row.get("grade"),
            "score":             row.get("score"),
            "l1":                row.get("l1"),
            "l2":                row.get("l2"),
            "l3":                row.get("l3"),
            "eps":               ttm_eps,
            "per":               per,
            "forwardPer":        forward_per,
            "forwardEps":        forward_eps,
            "forwardMethod":     forward_method,
            "pbr":               pbr,
            "roe":               roe,
            "roa":               roa,
            "roic":              roic,
            "strong_buy_signal":  row.get("strong_buy_signal", False),
            "strong_sell_signal": row.get("strong_sell_signal", False),
        },
    }