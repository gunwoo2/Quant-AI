"""
main.py — QUANT AI Backend v3.8
=================================
v3.8: API 서버 전용 — 스케줄러 완전 분리
  - main.py: FastAPI 서버 + 라우터만
  - batch/scheduler.py: 일일 배치 + 알림 + 주간/월간 (standalone)

  ★ 모든 스케줄(배치/모닝브리핑/주간/월간)은 scheduler에서 처리
  ★ main.py에는 스케줄러 없음 (중복 방지)
"""
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from datetime import datetime, date
import logging, os
import db_pool

from routers import stocks, sectors, tickers, market, stock_detail, quant, historical, financials, news

_optional_routers = {}
try:
    from routers import layer2
    _optional_routers["layer2"] = layer2
except ImportError:
    pass
try:
    from routers import layer3
    _optional_routers["layer3"] = layer3
except ImportError:
    pass
try:
    from routers import rating_history
    _optional_routers["rating_history"] = rating_history
except ImportError:
    pass

load_dotenv()
logger = logging.getLogger("quant_ai")


# ══════════════════════════════════════════════
#  수동 배치 실행 (POST /api/batch/run)
# ══════════════════════════════════════════════

def _run_daily_batch():
    """수동 배치 실행용 (POST /api/batch/run)"""
    try:
        from batch.scheduler import run_all
        print(f"\n[BATCH] ▶ 수동 실행 시작: {datetime.now()}")
        run_all(date.today())
        print(f"[BATCH] ✅ 수동 실행 완료: {datetime.now()}")
    except Exception as e:
        print(f"[BATCH] ❌ 실패: {e}")
        try:
            from notifier import notify_emergency
            notify_emergency(calc_date=date.today(), message=f"수동 배치 실패: {e}")
        except Exception:
            pass


# ══════════════════════════════════════════════
#  Lifespan — DB 풀만
# ══════════════════════════════════════════════

@asynccontextmanager
async def lifespan(app: FastAPI):
    db_pool.init_pool()
    print("[MAIN] ✅ DB 풀 초기화 완료")
    print("[MAIN] ℹ️  배치/알림 스케줄 → standalone batch/scheduler.py (ET 20:30)")
    yield
    db_pool.close_pool()
    print("[MAIN] 🛑 DB 풀 종료")


# ══════════════════════════════════════════════
#  FastAPI 앱
# ══════════════════════════════════════════════

app = FastAPI(
    title="QUANT AI API",
    version="3.8",
    description="S&P500 퀀트+NLP+기술지표+트레이딩 시그널 v3.8",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://*.cloudshell.dev",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://34.29.129.236:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 라우터 등록 ──
app.include_router(stocks.router, prefix="/api")
app.include_router(sectors.router, prefix="/api")
app.include_router(tickers.router, prefix="/api")
app.include_router(market.router, prefix="/api")
app.include_router(stock_detail.router, prefix="/api")
app.include_router(quant.router, prefix="/api")
app.include_router(historical.router, prefix="/api")
app.include_router(financials.router, prefix="/api")
app.include_router(news.router, prefix="/api")

if "layer2" in _optional_routers:
    app.include_router(_optional_routers["layer2"].router, prefix="/api", tags=["Layer 2"])
    print("[ROUTER] ✅ Layer 2 라우터 등록")
if "layer3" in _optional_routers:
    app.include_router(_optional_routers["layer3"].router, prefix="/api", tags=["Layer 3"])
    print("[ROUTER] ✅ Layer 3 라우터 등록")
if "rating_history" in _optional_routers:
    app.include_router(_optional_routers["rating_history"].router, prefix="/api", tags=["Rating History"])
    print("[ROUTER] ✅ Rating History 라우터 등록")


# ══════════════════════════════════════════════
#  엔드포인트
# ══════════════════════════════════════════════

@app.get("/health")
def health_check():
    try:
        with db_pool.get_cursor() as cur:
            cur.execute("SELECT 1")
        return {"status": "ok", "version": "3.8"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/api/system/info")
def system_info():
    return {
        "version": "3.8",
        "features": [
            "DynamicConfig 국면별 파라미터",
            "Drawdown 5단계 방어",
            "CircuitBreaker 연패 감지",
            "8중 안전장치",
            "상관 필터",
            "Kelly+DD 사이징",
            "8채널 Discord 알림",
            "배치완료 후 일괄 알림",
            "주간/월간 리포트",
            "DecisionAudit 의사결정 기록",
            "Layer 3 Flow/Macro (B+C)",
            "가격 안전장치 (stale 검증)",
        ],
        "scheduler": "OFF (main.py는 API 전용)",
        "batch_scheduler": "standalone batch/scheduler.py (평일 ET 20:30 = KST 09:30)",
        "routers": 9 + len(_optional_routers),
        "trading_mode": "LIVE" if os.environ.get("TRADING_LIVE", "0") == "1" else "DRY_RUN",
    }


@app.post("/api/batch/run")
async def manual_batch_run(background_tasks: BackgroundTasks):
    """수동 배치 실행 (백그라운드)"""
    background_tasks.add_task(_run_daily_batch)
    return {"status": "started", "message": "배치가 백그라운드에서 실행됩니다."}
