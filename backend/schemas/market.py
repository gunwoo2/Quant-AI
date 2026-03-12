from pydantic import BaseModel
from typing import Optional


class MarketIndexItem(BaseModel):
    label: str          # S&P 500, NASDAQ, VIX 등
    val:   float        # 현재값
    chg:   float        # 등락률 %
    up:    bool         # 상승 여부


class MarketStatusResponse(BaseModel):
    isOpen:   bool
    session:  str       # OPEN, CLOSED, PRE_MARKET, AFTER_HOURS
    nextOpen: Optional[str] = None