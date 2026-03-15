from pydantic import BaseModel
from typing import Optional


class MarketIndexItem(BaseModel):
    label: str          # S&P 500, NASDAQ, VIX 등
    val:   float        # 현재값
    chg:   float        # 등락률 %
    up:    bool         # 상승 여부


class MarketStatusResponse(BaseModel):
    # 미국 시장 (NYSE)
    isOpen:     bool
    session:    str             # OPEN, CLOSED, PRE_MARKET, AFTER_HOURS
    etStr:      Optional[str] = None    # "21:30" (뉴욕 현지시간)
    nextOpen:   Optional[str] = None

    # 한국 시장 (KRX)
    krIsOpen:   bool = False
    krSession:  str = "CLOSED"  # OPEN, CLOSED, PRE_MARKET, AFTER_HOURS
    kstStr:     Optional[str] = None    # "10:30" (한국시간)
    krNextOpen: Optional[str] = None

