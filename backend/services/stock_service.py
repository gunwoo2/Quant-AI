from typing import Optional
from db_pool import get_cursor


# ──────────────────────────────────────────────────────────
#  섹터 코드 → 한글명 매핑 (GICS 기준)
# ──────────────────────────────────────────────────────────
SECTOR_KO_MAP = {
    "10": "에너지",
    "15": "소재",
    "20": "산업재",
    "25": "경기소비재",
    "30": "필수소비재",
    "35": "헬스케어",
    "40": "금융",
    "45": "IT",
    "50": "커뮤니케이션",
    "55": "유틸리티",
    "60": "부동산",
}


# ──────────────────────────────────────────────────────────
#  GET /api/stocks
# ──────────────────────────────────────────────────────────
def get_stock_list(
    sector:  Optional[str] = None,
    country: Optional[str] = None,
    grade:   Optional[str] = None,
) -> list[dict]:
    """
    메인 종목 목록 조회.
    - v_latest_stock_scores 뷰 사용 (stocks + final_scores + realtime + likes JOIN)
    - KIS API 호출 없음. DB close_price 직접 반환.
    - 데이터 없으면 빈 배열 반환 (프론트는 빈 테이블 렌더링).
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
            fs.investment_opinion               AS signal,
            COALESCE(lc.like_count, 0)          AS like_count
        FROM stocks s
        JOIN markets m
            ON s.market_id = m.market_id
        LEFT JOIN sectors sec
            ON s.sector_id = sec.sector_id
        LEFT JOIN (
            -- 종목별 최신 calc_date 기준 점수 1행만 가져오기
            SELECT DISTINCT ON (stock_id)
                stock_id,
                layer1_score,
                layer2_score,
                layer3_score,
                weighted_score,
                grade,
                investment_opinion
            FROM stock_final_scores
            ORDER BY stock_id, calc_date DESC
        ) fs ON s.stock_id = fs.stock_id
        LEFT JOIN stock_prices_realtime rt
            ON s.stock_id = rt.stock_id
        LEFT JOIN stock_like_counts lc
            ON s.stock_id = lc.stock_id
        WHERE s.is_active = TRUE
          AND {where_clause}
        ORDER BY
            fs.weighted_score DESC NULLS LAST,
            s.ticker ASC
    """

    with get_cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()

    # RealDictCursor → 일반 dict 변환 후 반환
    result = []
    for row in rows:
        item = dict(row)

        # Decimal → float 변환 (JSON 직렬화 대비)
        for key in ("price", "chg", "l1", "l2", "l3", "score"):
            if item.get(key) is not None:
                item[key] = float(item[key])

        result.append(item)

    return result


# ──────────────────────────────────────────────────────────
#  GET /api/sectors
# ──────────────────────────────────────────────────────────
def get_sector_list() -> list[dict]:
    """
    사이드바용 섹터 목록.
    - 종목 수, 평균 점수, 최고 등급 포함.
    - 데이터 없으면 섹터 마스터만 반환 (종목 수 0).
    """
    sql = """
        SELECT
            sec.sector_code                         AS key,
            sec.sector_name                         AS en,
            COUNT(s.stock_id)                       AS stock_count,
            ROUND(AVG(fs.weighted_score)::NUMERIC, 1) AS avg_score,
            MAX(fs.grade)                           AS top_grade
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
        GROUP BY sec.sector_id, sec.sector_code, sec.sector_name
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
        result.append(item)

    return result

def get_stock_detail(ticker: str) -> dict | None:
    """
    종목 상세 헤더 + 실시간 데이터.
    없는 ticker면 None 반환 → 404 처리.
    """
    sql = """
        SELECT
            -- header
            s.ticker,
            s.company_name                      AS name,
            s.description                       AS description,
            s.listing_date                      AS listing_date,
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

            -- 재무 지표 (최신 연간)
            fin.eps_actual                      AS eps,
            fin.roic,
            fin.pb_ratio                        AS pbr,
            fin.peg_ratio                       AS per

        FROM stocks s
        JOIN exchanges e
            ON s.exchange_id = e.exchange_id
        JOIN markets m
            ON s.market_id = m.market_id
        LEFT JOIN sectors sec
            ON s.sector_id = sec.sector_id
        LEFT JOIN stock_prices_realtime rt
            ON s.stock_id = rt.stock_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id)
                stock_id, grade, weighted_score,
                layer1_score, layer2_score, layer3_score,
                strong_buy_signal, strong_sell_signal
            FROM stock_final_scores
            ORDER BY stock_id, calc_date DESC
        ) fs ON s.stock_id = fs.stock_id
        LEFT JOIN (
            SELECT DISTINCT ON (stock_id)
                stock_id, eps_actual, roic,
                pb_ratio, peg_ratio
            FROM stock_financials
            WHERE report_type = 'ANNUAL'
            ORDER BY stock_id, fiscal_year DESC
        ) fin ON s.stock_id = fin.stock_id
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

    # float 변환
    float_fields = (
        "price", "amount_change", "changes_percentage",
        "score", "l1", "l2", "l3",
        "eps", "roic", "pbr", "per"
    )
    for f in float_fields:
        if row.get(f) is not None:
            row[f] = float(row[f])

    return {
        "header": {
            "ticker":      row["ticker"],
            "name":        row["name"],
            "description": row["description"],      # 배치잡에서 추후 업데이트
            "exchange":    row["exchange"],
            "sector":      row["sector"],
            "market":      row["market"],
            "listingDate": row["listing_date"],
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
            "eps":               row.get("eps"),
            "per":               row.get("per"),
            "forwardPer":        None,   # 배치잡에서 추후 업데이트
            "pbr":               row.get("pbr"),
            "roe":               None,   # 배치잡에서 추후 업데이트
            "roa":               None,
            "roic":              row.get("roic"),
            "strong_buy_signal":  row.get("strong_buy_signal", False),
            "strong_sell_signal": row.get("strong_sell_signal", False),
        }
    }    