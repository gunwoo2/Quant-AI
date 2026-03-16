from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from datetime import datetime, date
import threading

import db_pool

# ── 기본 라우터 ──
from routers import stocks, sectors, tickers, market, stock_detail, quant, historical, financials, news

# ── 선택적 라우터 (없으면 무시) ──
_optional_routers = []
try:
    from routers import layer2
    _optional_routers.append(("layer2", layer2))
    print("  ✅ routers/layer2.py 등록됨")
except ImportError:
    pass
try:
    from routers import layer3
    _optional_routers.append(("layer3", layer3))
    print("  ✅ routers/layer3.py 등록됨")
except ImportError:
    pass
try:
    from routers import rating_history
    _optional_routers.append(("rating_history", rating_history))
    print("  ✅ routers/rating_history.py 등록됨")
except ImportError:
    pass

# .env 파일에서 환경변수 로드 (NEWS_API_KEY 등)
load_dotenv()

# ── APScheduler ──
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

ET = pytz.timezone("America/New_York")
_scheduler = BackgroundScheduler(timezone=ET)


def _run_daily_batch():
    """APScheduler가 매일 ET 02:00에 호출하는 함수"""
    calc_date = datetime.now(ET).date()
    print(f"\n🚀 [APScheduler] 일일 배치 시작 — {calc_date}")
    try:
        from batch.scheduler import run_all
        run_all(calc_date)
        print(f"✅ [APScheduler] 일일 배치 완료 — {calc_date}")
    except Exception as e:
        print(f"❌ [APScheduler] 배치 실패: {e}")
        import traceback
        traceback.print_exc()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 앱 시작 ──
    db_pool.init_pool()

    # ★ 마켓 캐시 워밍업 (백그라운드)
    try:
        from services.market_service import _refresh_cache_background
        threading.Thread(target=_refresh_cache_background, daemon=True).start()
        print("🔄 [MarketIndices] 백그라운드 캐시 워밍업 시작")
    except Exception as e:
        print(f"⚠️  마켓 캐시 워밍업 실패 (무시): {e}")

    # ★ APScheduler 시작
    _scheduler.add_job(
        _run_daily_batch,
        trigger=CronTrigger(
            day_of_week="tue-sat",   # 화~토 (= 미국 월~금 장 마감 후)
            hour=2, minute=0,
            timezone=ET,
        ),
        id="daily_batch",
        name="일일 전체 배치",
        replace_existing=True,
    )
    _scheduler.start()
    print("🕐 [APScheduler] 스케줄러 시작 — 매일 ET 02:00 배치 실행")

    jobs = _scheduler.get_jobs()
    for job in jobs:
        print(f"   📅 {job.name}: 다음 실행 → {job.next_run_time}")

    yield

    # ── 앱 종료 ──
    _scheduler.shutdown(wait=False)
    db_pool.close_pool()


app = FastAPI(
    title="QUANT AI API",
    version="2.0",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://*.cloudshell.dev",
        "http://localhost:5173",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 기본 라우터 등록 ──
app.include_router(stocks.router,       prefix="/api")
app.include_router(sectors.router,      prefix="/api")
app.include_router(tickers.router,      prefix="/api")
app.include_router(market.router,       prefix="/api")
app.include_router(stock_detail.router, prefix="/api")
app.include_router(quant.router,        prefix="/api")
app.include_router(historical.router,   prefix="/api")
app.include_router(financials.router,   prefix="/api")
app.include_router(news.router,         prefix="/api")

# ── 선택적 라우터 등록 ──
for name, mod in _optional_routers:
    app.include_router(mod.router, prefix="/api")


# ──────────────────────────────────────────────────────────
#  배치 관리 API
# ──────────────────────────────────────────────────────────
@app.get("/api/batch/status")
def batch_status():
    """스케줄러 상태 확인"""
    jobs = _scheduler.get_jobs()
    return {
        "scheduler_running": _scheduler.running,
        "jobs": [
            {
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time),
                "trigger": str(job.trigger),
            }
            for job in jobs
        ],
    }


@app.post("/api/batch/run")
def batch_run_manual(date: str = None):
    """수동 배치 실행 (백그라운드)"""
    if date:
        calc_date = datetime.strptime(date, "%Y-%m-%d").date()
    else:
        calc_date = datetime.now(ET).date()

    thread = threading.Thread(
        target=_run_daily_batch_with_date,
        args=(calc_date,),
        daemon=True,
    )
    thread.start()

    return {
        "status": "started",
        "calc_date": str(calc_date),
        "message": "배치가 백그라운드에서 실행 중입니다.",
    }


def _run_daily_batch_with_date(calc_date):
    print(f"\n🚀 [수동배치] 시작 — {calc_date}")
    try:
        from batch.scheduler import run_all
        run_all(calc_date)
        print(f"✅ [수동배치] 완료 — {calc_date}")
    except Exception as e:
        print(f"❌ [수동배치] 실패: {e}")
        import traceback
        traceback.print_exc()


# ──────────────────────────────────────────────────────────
#  헬스체크
# ──────────────────────────────────────────────────────────
@app.get("/health")
def health_check():
    try:
        with db_pool.get_cursor() as cur:
            cur.execute("SELECT 1")
        jobs = _scheduler.get_jobs()
        return {
            "status": "ok",
            "db": "connected",
            "scheduled_jobs": [
                {
                    "name": job.name,
                    "next_run": str(job.next_run_time),
                }
                for job in jobs
            ],
        }
    except Exception as e:
        return {"status": "error", "db": str(e)}

