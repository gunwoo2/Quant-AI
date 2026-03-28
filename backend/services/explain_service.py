"""
explain_service.py — XGBoost + SHAP 설명 서비스
================================================
GET /api/stock/explain/{ticker} 엔드포인트에 데이터를 공급.
batch_xgboost.py가 ai_scores_daily 테이블에 저장한 데이터를 조회.
"""
from datetime import date, datetime
from db_pool import get_cursor

# SHAP feature → 한글 라벨 매핑
FEATURE_LABELS = {
    "moat_total":       "경쟁우위 (ROIC/GPA/FCF)",
    "value_total":      "가치 (EV/EBIT, PBR)",
    "momentum_total":   "모멘텀 (실적 추세)",
    "stability_total":  "안정성 (부채/변동성)",
    "news_sentiment":   "뉴스 감성",
    "analyst_total":    "애널리스트 의견",
    "insider_total":    "내부자 거래",
    "section_a_tech":   "기술지표 (RSI/MACD)",
    "section_b_flow":   "수급·구조 (공매도/P·C)",
    "section_c_macro":  "시장환경 (VIX/섹터)",
    "cross_asset":      "글로벌 자산 시그널",
    "market_cap_log":   "시가총액 규모",
    "sector_code":      "섹터 특성",
    "regime":           "시장 국면",
    "vix_level":        "VIX 수준",
    "log_price":        "주가 수준",
    "stat_score":       "기존 퀀트 점수",
    "data_completeness":"데이터 완성도",
}


def _label(raw_name: str) -> str:
    return FEATURE_LABELS.get(raw_name, raw_name)


def get_explanation(ticker: str) -> dict | None:
    """
    종목별 SHAP 설명 조회.
    Returns:
        {
            "ticker": "NVDA",
            "calcDate": "2026-03-28",
            "aiScore": 82.5,
            "ensembleScore": 78.2,
            "statScore": 74.5,
            "aiWeight": 0.35,
            "baseValue": 45.2,
            "topPositive": [{"feature":"경쟁우위","shap":15.2,"raw":"moat_total"}, ...],
            "topNegative": [{"feature":"가치","shap":-4.2,"raw":"value_total"}, ...],
        }
    """
    try:
        with get_cursor() as cur:
            # stock_id 조회
            cur.execute("SELECT stock_id FROM stocks WHERE UPPER(ticker) = %s AND is_active = TRUE",
                        (ticker.upper(),))
            row = cur.fetchone()
            if not row:
                return None
            stock_id = row["stock_id"]

            # ai_scores_daily에서 최신 데이터
            cur.execute("""
                SELECT ai_score, shap_base, shap_top5_pos, shap_top5_neg, shap_all,
                       ensemble_score, stat_score, ai_weight, calc_date
                FROM ai_scores_daily
                WHERE stock_id = %s
                ORDER BY calc_date DESC LIMIT 1
            """, (stock_id,))
            row = cur.fetchone()

        if not row:
            return {
                "ticker": ticker.upper(),
                "calcDate": None,
                "aiScore": None,
                "status": "NO_DATA",
                "message": "XGBoost 분석 데이터가 아직 없습니다. 배치 실행 후 조회 가능합니다.",
                "topPositive": [],
                "topNegative": [],
            }

        # top5 positive/negative에 한글 라벨 추가
        top_pos = row["shap_top5_pos"] or []
        top_neg = row["shap_top5_neg"] or []

        for item in top_pos:
            if "raw" in item and "feature" not in item:
                item["feature"] = _label(item["raw"])
            elif "feature" not in item:
                item["feature"] = item.get("raw", "unknown")

        for item in top_neg:
            if "raw" in item and "feature" not in item:
                item["feature"] = _label(item["raw"])
            elif "feature" not in item:
                item["feature"] = item.get("raw", "unknown")

        return {
            "ticker": ticker.upper(),
            "calcDate": str(row["calc_date"]),
            "aiScore": float(row["ai_score"]) if row["ai_score"] else None,
            "ensembleScore": float(row["ensemble_score"]) if row["ensemble_score"] else None,
            "statScore": float(row["stat_score"]) if row["stat_score"] else None,
            "aiWeight": float(row["ai_weight"]) if row["ai_weight"] else None,
            "baseValue": float(row["shap_base"]) if row["shap_base"] else None,
            "topPositive": top_pos,
            "topNegative": top_neg,
        }

    except Exception as e:
        print(f"[EXPLAIN-SVC] 에러: {e}")
        return None
