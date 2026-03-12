from fastapi import APIRouter, HTTPException
from services.quant_service import get_quant_detail

router = APIRouter()


@router.get(
    "/stock/detail/{ticker}/quant",
    summary="Layer 1 퀀트 상세 점수",
    description="재계산 없이 DB 직접 조회. Phase 1 작업#3.",
)
def api_quant_detail(ticker: str):
    result = get_quant_detail(ticker)
    if result is None:
        raise HTTPException(status_code=404, detail=f"{ticker} 종목을 찾을 수 없습니다.")
    return result