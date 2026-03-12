from fastapi import APIRouter
from schemas.market import MarketIndexItem, MarketStatusResponse
from services.market_service import get_market_indices, get_market_status
from pydantic import BaseModel
from typing import Optional

router = APIRouter()


@router.get(
    "/market/indices",
    response_model=list[MarketIndexItem],
    summary="글로벌 지수 (S&P, NASDAQ, DOW, VIX)",
)
def api_market_indices():
    return get_market_indices()


@router.get(
    "/market/status",
    response_model=MarketStatusResponse,
    summary="미국 시장 개장/마감 상태",
)
def api_market_status():
    return get_market_status()

class MarketIndexItem(BaseModel):
    symbol:   str
    label:    str
    category: str       # US_INDEX, KR_INDEX, GLOBAL_INDEX, FX, BOND, COMMODITY, CRYPTO
    val:      float
    chg:      float
    up:       bool


class MarketStatusResponse(BaseModel):
    isOpen:   bool
    session:  str
    nextOpen: Optional[str] = None    