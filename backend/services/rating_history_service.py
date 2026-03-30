"""
rating_history_service.py — Rating History (Quant + AI) v2.1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
v2.1:
  - AI 등급: 횡단면 백분위 기반 (절대값 → 상대평가)
  - 같은 날짜의 전 종목 ensemble 분포에서 백분위 계산
"""
from db_pool import get_cursor

# 백분위 → 등급 (adaptive_scoring 동일)
_GRADE_PCT_CUTS = [
    (97, "S"), (92, "A+"), (82, "A"), (65, "B+"),
    (40, "B"), (15, "C"), (0, "D"),
]
_ABSOLUTE_FLOOR = [(25, "D"), (30, "C"), (35, "B"), (40, "B+")]
_GRADE_ORDER = {"S": 7, "A+": 6, "A": 5, "B+": 4, "B": 3, "C": 2, "D": 1}

def _pct_to_grade(pct):
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


def get_rating_history(ticker: str, limit: int = 20) -> list[dict]:
    result = []

    # ── 1. Quant 이력 (stock_rating_history) ──
    try:
        with get_cursor() as cur:
            cur.execute("""
                SELECT rh.rating_date AS date, rh.grade, rh.signal,
                       rh.weighted_score AS score,
                       rh.layer1_score AS l1, rh.layer2_score AS l2, rh.layer3_score AS l3
                FROM stock_rating_history rh
                JOIN stocks s ON rh.stock_id = s.stock_id
                WHERE s.ticker = %s AND s.is_active = TRUE
                ORDER BY rh.rating_date DESC LIMIT %s
            """, (ticker.upper(), limit))
            for row in cur.fetchall():
                item = dict(row)
                if item.get("date"): item["date"] = str(item["date"])
                for k in ("score", "l1", "l2", "l3"):
                    if item.get(k) is not None: item[k] = float(item[k])
                item["type"] = "quant"
                result.append(item)
    except Exception as e:
        print(f"[rating_history] ⚠️ Quant 이력 실패: {e}")

    # ── 2. AI 이력 (ai_scores_daily + 횡단면 백분위) ──
    try:
        import numpy as np
        from scipy import stats as sp_stats

        with get_cursor() as cur:
            # 해당 종목의 stock_id
            cur.execute("SELECT stock_id FROM stocks WHERE UPPER(ticker) = %s AND is_active = TRUE",
                        (ticker.upper(),))
            srow = cur.fetchone()
            if not srow:
                return result
            target_id = srow["stock_id"]

            # 해당 종목의 AI 이력
            cur.execute("""
                SELECT calc_date, ensemble_score, ai_score, stat_score
                FROM ai_scores_daily WHERE stock_id = %s
                ORDER BY calc_date DESC LIMIT %s
            """, (target_id, limit))
            target_rows = [dict(r) for r in cur.fetchall()]

            if not target_rows:
                return result

            # 각 날짜별로 전 종목 ensemble 분포에서 백분위 계산
            dates = list(set(str(r["calc_date"]) for r in target_rows))

            for calc_date_str in dates:
                cur.execute("""
                    SELECT stock_id, ensemble_score
                    FROM ai_scores_daily WHERE calc_date = %s AND ensemble_score IS NOT NULL
                """, (calc_date_str,))
                all_ens = {r["stock_id"]: float(r["ensemble_score"]) for r in cur.fetchall()}

                if len(all_ens) < 5:
                    continue

                # 전 종목 ensemble → percentile
                ids = list(all_ens.keys())
                scores_arr = np.array([all_ens[sid] for sid in ids], dtype=float)
                median = np.median(scores_arr)
                mad = np.median(np.abs(scores_arr - median))
                if mad < 1e-8:
                    std = np.std(scores_arr)
                    if std < 1e-8:
                        from scipy.stats import rankdata
                        ranks = rankdata(scores_arr, method="average")
                        pcts = (ranks - 1) / max(len(ranks) - 1, 1) * 100.0
                    else:
                        z = np.clip((scores_arr - np.mean(scores_arr)) / std, -3.0, 3.0)
                        pcts = sp_stats.norm.cdf(z) * 100.0
                else:
                    z = np.clip((scores_arr - median) / (1.4826 * mad), -3.0, 3.0)
                    pcts = sp_stats.norm.cdf(z) * 100.0

                pct_map = {ids[i]: float(pcts[i]) for i in range(len(ids))}

                # target 종목의 해당 날짜 행에 등급 할당
                target_pct = pct_map.get(target_id)
                if target_pct is None:
                    continue

                for trow in target_rows:
                    if str(trow["calc_date"]) == calc_date_str:
                        ens = float(trow["ensemble_score"]) if trow["ensemble_score"] else None
                        grade = _pct_to_grade(target_pct)
                        grade = _apply_floor(grade, ens)
                        result.append({
                            "date": calc_date_str,
                            "score": ens,
                            "grade": grade,
                            "ai_score": float(trow["ai_score"]) if trow.get("ai_score") else None,
                            "stat_score": float(trow["stat_score"]) if trow.get("stat_score") else None,
                            "type": "ai",
                        })
    except Exception as e:
        print(f"[rating_history] ⚠️ AI 이력 실패: {e}")
        import traceback; traceback.print_exc()

    return result