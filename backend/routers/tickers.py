from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List
from services.ticker_service import add_ticker, deactivate_tickers

router = APIRouter()


class AddTickerRequest(BaseModel):
    ticker: str


class DeleteTickerRequest(BaseModel):
    tickers: List[str]


@router.post(
    "/ticker",
    summary="종목 추가",
)
def api_add_ticker(body: AddTickerRequest):
    result = add_ticker(body.ticker.upper())
    if not result["success"]:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.delete(
    "/ticker",
    summary="종목 삭제 (비활성화)",
)
def api_delete_ticker(body: DeleteTickerRequest):
    result = deactivate_tickers([t.upper() for t in body.tickers])
    return result