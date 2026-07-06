from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from backend.app.database import init_db
from backend.app.routers import analysis, backtest, market_data, risk
from backend.app.routers import signals, tokens, news, account, chart_data, trades
from backend.app.routers import report_export
from backend.app.routers import settings as settings_router
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

# Remote devices on the LAN may VIEW everything but change nothing: any
# non-GET request must originate from this machine. This closes off the
# unauthenticated attack surface (placing OANDA orders, flipping execution
# mode, rewriting .env via the settings endpoint) that binding 0.0.0.0
# would otherwise expose to every device — or compromised webpage — on the
# home network. Full control stays available in the dashboard opened on
# the Mac itself.
@app.middleware("http")
async def _localhost_only_mutations(request, call_next):
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        client_host = request.client.host if request.client else ""
        if client_host not in ("127.0.0.1", "::1", "localhost"):
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=403,
                content={"detail": "State-changing requests are only allowed from the "
                                   "trading Mac itself. Remote devices are view-only."},
            )
    return await call_next(request)


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
app.include_router(settings_router.router)
app.include_router(report_export.router)


@app.get("/health")
def health():
    from backend.app.scheduler import get_market_status
    from backend.app.services.system_status import health_snapshot
    market = get_market_status()
    snapshot = health_snapshot()
    return {
        "status": "ok" if snapshot["ok"] else "degraded",
        "version": "0.6.0",
        "market_open": market["is_open"],
        "market_time_et": market["current_time_et"],
        "scheduler_running": _scheduler.running if _scheduler else False,
        "problems": snapshot["problems"],
        "jobs": snapshot["jobs"],
    }


# ── Serve the built frontend (production) ─────────────────────────────────────
# When frontend/dist exists (created by `npm run build`), the backend serves
# the UI directly on port 8000. This removes the vite dev server from the
# deployment entirely and makes the dashboard reachable from any device on
# the network at http://<mac-ip>:8000.
#
# MUST be registered last: Starlette matches routes in registration order,
# and this catch-all mount at "/" would otherwise swallow /health and any
# route defined after it.

class _SPAStaticFiles(StaticFiles):
    """Static files with SPA fallback: unknown paths serve index.html so
    React Router routes like /signals work on direct load/refresh."""

    async def get_response(self, path: str, scope):
        try:
            response = await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code == 404:
                return await super().get_response("index.html", scope)
            raise
        if response.status_code == 404:
            response = await super().get_response("index.html", scope)
        return response


_FRONTEND_DIST = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    app.mount("/", _SPAStaticFiles(directory=str(_FRONTEND_DIST), html=True), name="frontend")
    logger.info("TradeSight: serving built frontend from %s", _FRONTEND_DIST)
