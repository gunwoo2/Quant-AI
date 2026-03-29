from pydantic import BaseModel
from typing import Optional
from datetime import date


class StockListItem(BaseModel):
    ticker:     str
    name:       str
    sector:     Optional[str]   = None
    sector_code: Optional[str]  = None
    country:    Optional[str]   = "US"
    price:      Optional[float] = None
    chg:        Optional[float] = None
    l1:         Optional[float] = None
    l2:         Optional[float] = None
    l3:         Optional[float] = None
    score:      Optional[float] = None
    grade:      Optional[str]   = None
    signal:     Optional[str]   = None
    ai_score:   Optional[float] = None
    ensemble:   Optional[float] = None
    ai_grade:   Optional[str]   = None
    ai_signal:  Optional[str]   = None
    like_count: Optional[int]   = 0

    class Config:
        from_attributes = True


class SectorItem(BaseModel):
    key:         str
    en:          str
    ko:          Optional[str]   = None
    stock_count: int             = 0
    avg_score:   Optional[float] = None
    top_grade:   Optional[str]   = None
    top_ticker:  Optional[str]   = None


class StockHeader(BaseModel):
    ticker:      str
    name:        str
    description: Optional[str]  = None
    exchange:    Optional[str]  = None
    sector:      Optional[str]  = None
    market:      Optional[str]  = None
    listingDate: Optional[date] = None


class RealtimeData(BaseModel):
    price:             Optional[float] = None
    change:            Optional[float] = None
    amount_change:     Optional[float] = None
    changesPercentage: Optional[float] = None
    grade:             Optional[str]   = None
    score:             Optional[float] = None
    l1:                Optional[float] = None
    l2:                Optional[float] = None
    l3:                Optional[float] = None
    eps:               Optional[float] = None
    per:               Optional[float] = None
    forwardPer:        Optional[float] = None
    pbr:               Optional[float] = None
    roe:               Optional[float] = None
    roa:               Optional[float] = None
    roic:              Optional[float] = None
    strong_buy_signal:  Optional[bool] = False
    strong_sell_signal: Optional[bool] = False


class StockDetailResponse(BaseModel):
    header:   StockHeader
    realtime: RealtimeData