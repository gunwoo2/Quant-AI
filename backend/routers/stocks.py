from fastapi import APIRouter, Query
from typing import Optional
from schemas.stock import StockListItem
from services.stock_service import get_stock_list

router = APIRouter()


@router.get(
    "/stocks",
    response_model=list[StockListItem],
    summary="메인 종목 목록",
    description="StockTable.jsx 에서 호출. KIS API 없이 DB close_price 직접 반환. TTL 5분 캐시.",
)
def api_get_stocks(
    sector:  Optional[str] = Query(None, description="섹터 코드 (예: 45)"),
    country: Optional[str] = Query(None, description="시장 코드 (예: US)"),
    grade:   Optional[str] = Query(None, description="등급 필터 (예: A+)"),
):
    """
    데이터 없으면 [] 반환 → 프론트에서 '등록된 종목이 없습니다' 표시.
    """
    return get_stock_list(sector=sector, country=country, grade=grade)