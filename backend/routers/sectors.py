from fastapi import APIRouter
from schemas.stock import SectorItem
from services.stock_service import get_sector_list

router = APIRouter()


@router.get(
    "/sectors",
    response_model=list[SectorItem],
    summary="섹터 목록",
    description="Sidebar.jsx 에서 호출. 종목 수·평균 점수 포함. TTL 1시간 캐시.",
)
def api_get_sectors():
    return get_sector_list()