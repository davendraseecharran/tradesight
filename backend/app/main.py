from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.database import init_db
from backend.app.routers import analysis, backtest, market_data, risk
from backend.app.routers import signals, tokens, news, account, chart_data, trades
from backend.app.scheduler import create_scheduler

logger = logging.getLogger(__name__)

_scheduler = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _scheduler
    init_db()

    _scheduler = create_scheduler()
    _scheduler.start()
    logger.info("TradeSight: scheduler started (%d jobs)", len(_scheduler.get_jobs()))

    print("TradeSight: database initialized, scheduler started, server ready")
    yield

    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("TradeSight: scheduler stopped")
    print("TradeSight: shutting down")


app = FastAPI(
    title="TradeSight",
    description="AI-powered trading analysis assistant",
    version="0.5.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*", "http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Phase 1 + 2 routers
app.include_router(market_data.router, prefix="/api/v1")
app.include_router(analysis.router, prefix="/api/v1")
app.include_router(risk.router, prefix="/api/v1")
app.include_router(backtest.router, prefix="/api/v1")

# Phase 3 routers
app.include_router(signals.router)
app.include_router(tokens.router)
app.include_router(news.router)

# Phase 4 routers
app.include_router(account.router)
app.include_router(chart_data.router)

# Phase 5 routers
app.include_router(trades.router)


@app.get("/health")
def health():
    from backend.app.scheduler import get_market_status
    market = get_market_status()
    return {
        "status": "ok",
        "version": "0.5.0",
        "market_open": market["is_open"],
        "market_time_et": market["current_time_et"],
        "scheduler_running": _scheduler.running if _scheduler else False,
    }
