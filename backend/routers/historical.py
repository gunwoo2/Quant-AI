from fastapi import APIRouter, HTTPException
from services.historical_service import get_historical

router = APIRouter()


@router.get(
    "/stock/historical/{ticker}",
    summary="주가 OHLCV 이력 + 재무 차트",
)
def api_historical(ticker: str):
    result = get_historical(ticker)
    if result is None:
        raise HTTPException(status_code=404, detail=f"{ticker} 종목을 찾을 수 없습니다.")
    return result