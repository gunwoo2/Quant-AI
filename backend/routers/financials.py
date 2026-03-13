from fastapi import APIRouter, HTTPException
from services.financials_service import get_financials

router = APIRouter()


@router.get(
    "/stock/financials/{ticker}",
    summary="재무제표 연간/분기",
)
def api_financials(ticker: str):
    result = get_financials(ticker)
    if result is None:
        raise HTTPException(status_code=404, detail=f"{ticker} 종목을 찾을 수 없습니다.")
    return result