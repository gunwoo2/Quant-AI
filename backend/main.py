from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from dotenv import load_dotenv

import db_pool
from routers import (
    stocks, sectors, tickers, market,
    stock_detail, quant, historical, financials, news,
)

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작 시 DB 풀 초기화, 종료 시 정리."""
    db_pool.init_pool()
    yield
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

# ── 라우터 등록 ──
app.include_router(stocks.router,       prefix="/api")
app.include_router(sectors.router,      prefix="/api")
app.include_router(tickers.router,      prefix="/api")
app.include_router(market.router,       prefix="/api")
app.include_router(stock_detail.router, prefix="/api")
app.include_router(quant.router,        prefix="/api")
app.include_router(historical.router,   prefix="/api")
app.include_router(financials.router,   prefix="/api")
app.include_router(news.router,         prefix="/api")


@app.get("/health")
def health_check():
    try:
        with db_pool.get_cursor() as cur:
            cur.execute("SELECT 1")
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return {"status": "error", "db": str(e)}