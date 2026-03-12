from pydantic import BaseModel
from typing import Optional


class StockListItem(BaseModel):
    """
    /api/stocks 응답 단건. 프론트 StockTable.jsx 기준.
    """
    ticker:  str
    name:    str
    sector:  Optional[str] = None       # 섹터명 (sector_name)
    country: Optional[str] = "US"       # 시장 코드 (market_code)

    # 가격 (stock_prices_realtime)
    price:   Optional[float] = None
    chg:     Optional[float] = None     # 등락률 %

    # 레이어 점수 (stock_final_scores)
    l1:      Optional[float] = None     # Layer 1 점수
    l2:      Optional[float] = None     # Layer 2 점수
    l3:      Optional[float] = None     # Layer 3 점수
    score:   Optional[float] = None     # 최종 가중 합산 점수
    grade:   Optional[str]  = None      # S, A+, A, B+, B, C, D
    signal:  Optional[str]  = None      # STRONG_BUY 등

    # 좋아요
    like_count: Optional[int] = 0

    class Config:
        from_attributes = True


class SectorItem(BaseModel):
    """
    /api/sectors 응답 단건. 프론트 Sidebar.jsx 기준.
    """
    key:        str             # sector_code  (ex: '45')
    en:         str             # sector_name  (ex: 'Information Technology')
    ko:         Optional[str]   # 한글명 (없으면 en 그대로)
    stock_count: int = 0
    avg_score:  Optional[float] = None
    top_grade:  Optional[str]  = None