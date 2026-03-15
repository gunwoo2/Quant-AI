"""
rating_history_service.py — AI Rating History 조회
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
SummaryTab의 AI Rating History 섹션에 사용.
batch_final_score.py가 매일 stock_rating_history에 적재한 데이터를 조회한다.
"""

from db_pool import get_cursor


def get_rating_history(ticker: str, limit: int = 20) -> list[dict]:
    """
    종목의 최근 등급 변동 이력을 조회한다.

    Returns:
        [{ date, grade, signal, score, l1, l2, l3 }, ...]
    """
    sql = """
        SELECT
            rh.rating_date   AS date,
            rh.grade,
            rh.signal,
            rh.weighted_score AS score,
            rh.layer1_score   AS l1,
            rh.layer2_score   AS l2,
            rh.layer3_score   AS l3
        FROM stock_rating_history rh
        JOIN stocks s ON rh.stock_id = s.stock_id
        WHERE s.ticker = %s
          AND s.is_active = TRUE
        ORDER BY rh.rating_date DESC
        LIMIT %s
    """

    with get_cursor() as cur:
        cur.execute(sql, (ticker.upper(), limit))
        rows = cur.fetchall()

    result = []
    for row in rows:
        item = dict(row)
        # date를 문자열로
        if item.get("date"):
            item["date"] = str(item["date"])
        # 숫자 변환
        for k in ("score", "l1", "l2", "l3"):
            if item.get(k) is not None:
                item[k] = float(item[k])
        result.append(item)

    return result