from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

import db_pool
from routers import (
    stocks, sectors, tickers, market, stock_detail,
    quant, historical, financials, news,
)

# .env 파일에서 환경변수 로드 (NEWS_API_KEY 등)
load_dotenv()

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Layer2 / Layer3 / Rating History 라우터 (있으면 등록)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
_optional_routers = {}
try:
    from routers import layer2
    _optional_routers["layer2"] = layer2.router
except ImportError:
    print("[WARN] routers/layer2.py 없음 — 스킵")

try:
    from routers import layer3
    _optional_routers["layer3"] = layer3.router
except ImportError:
    print("[WARN] routers/layer3.py 없음 — 스킵")

try:
    from routers import rating_history
    _optional_routers["rating_history"] = rating_history.router
except ImportError:
    print("[WARN] routers/rating_history.py 없음 — 스킵")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# APScheduler 설정
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
import pytz

scheduler = BackgroundScheduler(timezone=pytz.timezone("US/Eastern"))


def _run_daily_batch():
    """매일 자동 실행되는 전체 배치"""
    from datetime import datetime
    from batch.scheduler import run_all
    calc_date = datetime.now(pytz.timezone("US/Eastern")).date()
    print(f"\n🤖 [APScheduler] 일일 배치 시작: {calc_date}")
    try:
        run_all(calc_date)
        print(f"🤖 [APScheduler] 일일 배치 완료: {calc_date}")
    except Exception as e:
        print(f"🤖 [APScheduler] 배치 오류: {e}")
        import traceback
        traceback.print_exc()


# 스케줄 등록: 화~토 새벽 ET 02:00 (월요장→화요새벽, 금요장→토요새벽)
scheduler.add_job(
    _run_daily_batch,
    CronTrigger(
        hour=2, minute=0,
        day_of_week="tue-sat",
        timezone="US/Eastern",
    ),
    id="daily_batch",
    name="일일 전체 배치",
    replace_existing=True,
    misfire_grace_time=3600,
)


def _print_next_run():
    for job in scheduler.get_jobs():
        print(f"   📅 {job.name}: 다음 실행 → {job.next_run_time}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FastAPI Lifespan
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── 앱 시작 ──
    db_pool.init_pool()
    scheduler.start()
    print("🕐 [APScheduler] 스케줄러 시작 — 매일 ET 02:00 배치 실행")
    _print_next_run()
    yield
    # ── 앱 종료 ──
    scheduler.shutdown(wait=False)
    print("🕐 [APScheduler] 스케줄러 종료")
    db_pool.close_pool()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# FastAPI 앱
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
app = FastAPI(
    title="QUANT AI API",
    version="2.0",
    lifespan=lifespan,
)

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

# ── 기본 라우터 ──
app.include_router(stocks.router,       prefix="/api")
app.include_router(sectors.router,      prefix="/api")
app.include_router(tickers.router,      prefix="/api")
app.include_router(market.router,       prefix="/api")
app.include_router(stock_detail.router, prefix="/api")
app.include_router(quant.router,        prefix="/api")
app.include_router(historical.router,   prefix="/api")
app.include_router(financials.router,   prefix="/api")
app.include_router(news.router,         prefix="/api")

# ── 선택적 라우터 (있으면 등록) ──
for name, router in _optional_routers.items():
    app.include_router(router, prefix="/api")
    print(f"  ✅ routers/{name}.py 등록됨")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 헬스체크
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.get("/health")
def health_check():
    try:
        with db_pool.get_cursor() as cur:
            cur.execute("SELECT 1")
        jobs = []
        for job in scheduler.get_jobs():
            jobs.append({
                "name": job.name,
                "next_run": str(job.next_run_time),
            })
        return {"status": "ok", "db": "connected", "scheduled_jobs": jobs}
    except Exception as e:
        return {"status": "error", "db": str(e)}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 배치 수동 실행 / 상태 조회 API
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
@app.post("/api/batch/run", summary="배치 수동 실행 (백그라운드)")
def api_run_batch(background_tasks: BackgroundTasks, date: str = None):
    """
    수동으로 배치를 트리거합니다.
    - date 생략: 오늘 날짜로 실행
    - date 지정: "2026-03-14" 형식
    """
    from datetime import datetime as dt

    if date:
        try:
            calc_date = dt.strptime(date, "%Y-%m-%d").date()
        except ValueError:
            return {"error": "날짜 형식: YYYY-MM-DD"}
    else:
        calc_date = dt.now(pytz.timezone("US/Eastern")).date()

    def _task():
        from batch.scheduler import run_all
        run_all(calc_date)

    background_tasks.add_task(_task)
    return {
        "status": "started",
        "calc_date": str(calc_date),
        "message": f"{calc_date} 배치가 백그라운드에서 실행 중입니다. 서버 로그를 확인하세요.",
    }


@app.get("/api/batch/status", summary="스케줄러 상태 조회")
def api_batch_status():
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "name": job.name,
            "next_run": str(job.next_run_time),
            "trigger": str(job.trigger),
        })
    return {"scheduler_running": scheduler.running, "jobs": jobs}