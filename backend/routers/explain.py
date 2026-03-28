"""
routers/explain.py — XGBoost + SHAP Explainability API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GET /api/stock/explain/{ticker}
  → SummaryTab.jsx에 "왜 이 등급인가?" SHAP 시각화 데이터 공급
"""
from fastapi import APIRouter, HTTPException
from services.explain_service import get_explanation

router = APIRouter()


@router.get(
    "/stock/explain/{ticker}",
    summary="XGBoost + SHAP 설명 데이터",
    description="종목별 AI Score + SHAP 기여도 Top 5 (상승/하락 요인)",
)
def api_explain(ticker: str):
    result = get_explanation(ticker)
    if result is None:
        raise HTTPException(status_code=404, detail=f"{ticker} 종목을 찾을 수 없습니다.")
    return result
