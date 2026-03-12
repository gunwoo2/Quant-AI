from fastapi import APIRouter, HTTPException
from schemas.stock import StockDetailResponse
from services.stock_service import get_stock_detail

router = APIRouter()


@router.get(
    "/stock/detail/{ticker}",
    response_model=StockDetailResponse,
    summary="종목 상세 헤더 + 실시간 가격",
)
def api_stock_detail(ticker: str):
    result = get_stock_detail(ticker)
    if result is None:
        raise HTTPException(status_code=404, detail=f"{ticker} 종목을 찾을 수 없습니다.")
    return result