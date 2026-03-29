"""
rating_history_service.py — Rating History 조회 (Quant + AI)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
v2.0:
  - Quant 이력: stock_rating_history 테이블
  - AI 이력: ai_scores_daily 테이블 (ensemble 기반 등급 계산)
  - type 필드로 "quant" / "ai" 구분
"""

from db_pool import get_cursor


# ensemble 점수 → 등급
_GRADE_THRESHOLDS = [
    (90, "S"), (80, "A+"), (70, "A"), (60, "B+"),
    (50, "B"), (40, "C"), (0, "D"),
]

def _score_to_grade(score):
    if score is None:
        return None
    s = float(score)
    for threshold, label in _GRADE_THRESHOLDS:
        if s >= threshold:
            return label
    return "D"


def get_rating_history(ticker: str, limit: int = 20) -> list[dict]:
    """
    종목의 최근 등급 변동 이력을 조회한다. (Quant + AI)

    Returns:
        [{ date, grade, signal, score, l1, l2, l3, type }, ...]
    """
    result = []

    # ── 1. Quant 이력 (stock_rating_history) ──
    try:
        sql_quant = """
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
            cur.execute(sql_quant, (ticker.upper(), limit))
            rows = cur.fetchall()

        for row in rows:
            item = dict(row)
            if item.get("date"):
                item["date"] = str(item["date"])
            for k in ("score", "l1", "l2", "l3"):
                if item.get(k) is not None:
                    item[k] = float(item[k])
            item["type"] = "quant"
            result.append(item)
    except Exception as e:
        print(f"[rating_history] ⚠️ Quant 이력 조회 실패: {e}")

    # ── 2. AI 이력 (ai_scores_daily) ──
    try:
        sql_ai = """
            SELECT
                ad.calc_date       AS date,
                ad.ensemble_score  AS score,
                ad.ai_score,
                ad.stat_score
            FROM ai_scores_daily ad
            JOIN stocks s ON ad.stock_id = s.stock_id
            WHERE s.ticker = %s
              AND s.is_active = TRUE
            ORDER BY ad.calc_date DESC
            LIMIT %s
        """
        with get_cursor() as cur:
            cur.execute(sql_ai, (ticker.upper(), limit))
            rows = cur.fetchall()

        for row in rows:
            item = dict(row)
            if item.get("date"):
                item["date"] = str(item["date"])
            ens = float(item["score"]) if item.get("score") is not None else None
            item["score"] = ens
            item["grade"] = _score_to_grade(ens)
            item["ai_score"] = float(item["ai_score"]) if item.get("ai_score") is not None else None
            item["stat_score"] = float(item["stat_score"]) if item.get("stat_score") is not None else None
            item["type"] = "ai"
            result.append(item)
    except Exception as e:
        print(f"[rating_history] ⚠️ AI 이력 조회 실패: {e}")

    return result
