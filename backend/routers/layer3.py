"""
routers/layer3.py — Layer 3 Market Signal API
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

GET /api/stock/layer3/{ticker}
  → MarketSignalTab.jsx에 기술지표 / 수급 / 시장환경 데이터 공급
"""
from fastapi import APIRouter, HTTPException
from services.layer3_service import get_layer3_data

router = APIRouter()


@router.get(
    "/stock/layer3/{ticker}",
    summary="Layer 3 Market Signal 전체 데이터",
    description="기술지표(RSI/MACD/OBV 등) + 공매도 + VIX/섹터ETF 통합 반환",
)
def api_layer3_data(ticker: str):
    result = get_layer3_data(ticker)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"{ticker} 종목을 찾을 수 없습니다."
        )
    return result