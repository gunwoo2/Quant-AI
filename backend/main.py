"""
main.py — QUANT AI Backend v3.7
=================================
v3.7: standalone scheduler(21:00 ET)와 역할 분리
  - main.py: API 서버 + 모닝 브리핑만
  - batch.scheduler: 일일 배치 + 주간/월간 리포트
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
except ImportError: pass
try:
    from routers import layer3
    _optional_routers["layer3"] = layer3
except ImportError: pass
try:
    from routers import rating_history
    _optional_routers["rating_history"] = rating_history
except ImportError: pass

load_dotenv()
logger = logging.getLogger("quant_ai")
_scheduler = None


# ══════════════════════════════════════════════
#  스케줄러 (모닝 브리핑 전용)
#  ★ 일일 배치는 standalone batch.scheduler에서 처리
# ══════════════════════════════════════════════

def _init_scheduler():
    global _scheduler
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.cron import CronTrigger
        import pytz
        et = pytz.timezone("US/Eastern")
        _scheduler = BackgroundScheduler(timezone=et)

        # ★ daily_batch 제거 — standalone batch.scheduler (21:00 ET)에서 처리
        # ★ earnings_call 제거 — standalone scheduler Step 5.5에서 처리

        # 모닝 브리핑: 월~금 ET 08:30 (KST 21:30)
        _scheduler.add_job(
            _run_morning_briefing,
            trigger=CronTrigger(day_of_week="mon-fri", hour=8, minute=30, timezone=et),
            id="morning_briefing",
            name="Morning Briefing",
            replace_existing=True,
            misfire_grace_time=1800,
        )

        _scheduler.start()
        print("[SCHEDULER] ✅ 모닝 브리핑 스케줄러 시작 (평일 08:30 ET)")

    except ImportError:
        print("[SCHEDULER] ⚠️  APScheduler 미설치 — pip install apscheduler")
    except Exception as e:
        print(f"[SCHEDULER] ❌ 초기화 실패: {e}")


def _shutdown_scheduler():
    global _scheduler
    if _scheduler:
        _scheduler.shutdown(wait=False)
        print("[SCHEDULER] 🛑 종료")


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
            notify_emergency("수동 배치 실패", str(e))
        except Exception:
            pass


def _run_morning_briefing():
    """모닝 브리핑: 시장 국면 + 워치리스트 + 보유현황"""
    try:
        from db_pool import get_cursor
        today = date.today()

        # 최근 국면
        with get_cursor() as cur:
            cur.execute("SELECT regime, spy_price, spy_ma50, spy_ma200, vix_close FROM market_regime ORDER BY regime_date DESC LIMIT 1")
            row = cur.fetchone()
        if not row:
            return

        regime = row["regime"]
        regime_detail = {
            "spy_price": float(row["spy_price"] or 0),
            "spy_ma50": float(row["spy_ma50"] or 0),
            "spy_ma200": float(row["spy_ma200"] or 0),
            "vix_close": float(row["vix_close"] or 0),
        }

        # 보유 현황
        with get_cursor() as cur:
            cur.execute("SELECT COUNT(*) as cnt FROM portfolio_positions WHERE status = 'OPEN' AND portfolio_id = 1")
            pos_count = cur.fetchone()["cnt"]

            cur.execute("SELECT total_value, cash_balance FROM portfolio_daily_snapshot WHERE portfolio_id = 1 ORDER BY snapshot_date DESC LIMIT 1")
            snap = cur.fetchone()

        cash_pct = 100
        if snap and snap["total_value"] and float(snap["total_value"]) > 0:
            cash_pct = float(snap["cash_balance"] or 0) / float(snap["total_value"]) * 100

        # 고점수 워치리스트
        watchlist = []
        with get_cursor() as cur:
            cur.execute("""
                SELECT s.ticker, f.weighted_score as score, f.grade
                FROM stock_final_scores f
                JOIN stocks s ON f.stock_id = s.stock_id
                WHERE f.calc_date = (SELECT MAX(calc_date) FROM stock_final_scores)
                  AND f.weighted_score >= 70
                  AND s.stock_id NOT IN (SELECT stock_id FROM portfolio_positions WHERE status = 'OPEN')
                ORDER BY f.weighted_score DESC LIMIT 5
            """)
            for r in cur.fetchall():
                watchlist.append({
                    "ticker": r["ticker"],
                    "score": float(r["score"]),
                    "reason": f"{r['grade']} 등급",
                })

        from notifier import notify_morning_briefing
        notify_morning_briefing(
            calc_date=today,
            regime=regime,
            regime_detail=regime_detail,
            watchlist=watchlist,
            positions_count=pos_count,
            cash_pct=cash_pct,
        )
    except Exception as e:
        print(f"[MORNING] ⚠️ 모닝 브리핑 실패: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db_pool.init_pool()
    _init_scheduler()
    yield
    _shutdown_scheduler()
    db_pool.close_pool()


app = FastAPI(
    title="QUANT AI API",
    version="3.7",
    description="S&P500 퀀트+NLP+기술지표+트레이딩 시그널 v3.7",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://*.cloudshell.dev", "http://localhost:5173", "http://localhost:3000", "http://34.29.129.236:3000"],
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


@app.get("/health")
def health_check():
    try:
        with db_pool.get_cursor() as cur:
            cur.execute("SELECT 1")
        return {"status": "ok", "version": "3.7"}
    except Exception as e:
        return {"status": "error", "detail": str(e)}


@app.get("/api/system/info")
def system_info():
    sched_info = "OFF"
    if _scheduler and _scheduler.running:
        jobs = _scheduler.get_jobs()
        sched_info = f"ON ({len(jobs)} jobs: morning briefing)"
    return {
        "version": "3.7",
        "features": [
            "DynamicConfig 국면별 파라미터",
            "Drawdown 5단계 방어",
            "CircuitBreaker 연패 감지",
            "8중 안전장치",
            "상관 필터",
            "Kelly+DD 사이징",
            "8채널 Discord 알림",
            "모닝 브리핑",
            "주간/월간 리포트",
            "DecisionAudit 의사결정 기록",
            "Layer 3 Flow/Macro (B+C)",
            "가격 안전장치 (stale 검증)",
        ],
        "scheduler": sched_info,
        "batch_scheduler": "standalone (21:00 ET)",
        "routers": 9 + len(_optional_routers),
        "trading_mode": "LIVE" if os.environ.get("TRADING_LIVE", "0") == "1" else "DRY_RUN",
    }


@app.post("/api/batch/run")
async def manual_batch_run(background_tasks: BackgroundTasks):
    """수동 배치 실행 (백그라운드)"""
    background_tasks.add_task(_run_daily_batch)
    return {"status": "started", "message": "배치가 백그라운드에서 실행됩니다."}