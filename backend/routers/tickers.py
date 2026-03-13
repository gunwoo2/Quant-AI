from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import List
from services.ticker_service import add_ticker, deactivate_tickers

router = APIRouter()


class TickerAddRequest(BaseModel):
    ticker: str


class TickerDeleteRequest(BaseModel):
    tickers: List[str]


@router.post("/ticker", summary="종목 추가")
def api_add_ticker(req: TickerAddRequest, background_tasks: BackgroundTasks):
    result = add_ticker(req.ticker.upper(), background_tasks)
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result


@router.delete("/ticker", summary="종목 비활성화")
def api_delete_ticker(req: TickerDeleteRequest):
    result = deactivate_tickers([t.upper() for t in req.tickers])
    if not result.get("success"):
        raise HTTPException(status_code=400, detail=result.get("error"))
    return result