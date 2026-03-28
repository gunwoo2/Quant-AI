"""
stock_service_patch.py — stock_service.py 수정 가이드
=====================================================
get_stock_list()의 SELECT에 conviction_score, layer_agreement 추가.

적용 방법:
1. services/stock_service.py의 get_stock_list() 내 SQL을 아래로 교체
2. 또는 아래 diff를 참고하여 수동 적용
"""

# ── 기존 (line 60~66 부근) ──
# fs.layer1_score                     AS l1,
# fs.layer2_score                     AS l2,
# fs.layer3_score                     AS l3,
# fs.weighted_score                   AS score,
# fs.grade,
# fs.investment_opinion               AS signal,
# COALESCE(lc.like_count, 0)          AS like_count

# ── 변경 후 ──
# fs.layer1_score                     AS l1,
# fs.layer2_score                     AS l2,
# fs.layer3_score                     AS l3,
# fs.weighted_score                   AS score,
# fs.grade,
# fs.investment_opinion               AS signal,
# COALESCE(lc.like_count, 0)          AS like_count,
# dss.conviction_score,
# dss.layer_agreement,
# dss.data_completeness

# ── 서브쿼리 추가 (fs JOIN 다음에) ──
# LEFT JOIN (
#     SELECT DISTINCT ON (stock_id)
#         stock_id, conviction_score, layer_agreement, data_completeness
#     FROM daily_stock_score
#     ORDER BY stock_id, calc_date DESC
# ) dss ON s.stock_id = dss.stock_id

# ── result 처리 루프에 추가 ──
# for key in ("conviction_score", "layer_agreement", "data_completeness"):
#     if item.get(key) is not None:
#         item[key] = float(item[key])
