from __future__ import annotations

import logging
from datetime import datetime, timezone

import pytz
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from backend.app.agents.news_sentinel import run_news_sentinel
from backend.app.agents.orchestrator import run_pipeline
from backend.app.database import SessionLocal
from backend.app.services.trade_manager import TradeManager

logger = logging.getLogger(__name__)

ET = pytz.timezone("America/New_York")

# ── Market hours detection ─────────────────────────────────────────────────────

def is_market_open() -> bool:
    """
    Forex market hours (UTC):
    - Opens: Sunday 5PM ET (22:00 UTC standard / 21:00 UTC DST)
    - Closes: Friday 5PM ET (22:00 UTC standard / 21:00 UTC DST)

    Returns True if market is currently open.
    """
    now_et = datetime.now(ET)
    weekday = now_et.weekday()  # Monday=0, Sunday=6
    hour = now_et.hour
    minute = now_et.minute

    # Saturday: always closed
    if weekday == 5:
        return False

    # Sunday: open from 5PM ET
    if weekday == 6:
        return hour >= 17

    # Monday–Thursday: always open
    if weekday in (0, 1, 2, 3):
        return True

    # Friday: closed from 5PM ET
    if weekday == 4:
        return hour < 17 or (hour == 17 and minute == 0)

    return False


def get_market_status() -> dict:
    """Return current market status with next state change info."""
    now_et = datetime.now(ET)
    open_now = is_market_open()

    return {
        "is_open": open_now,
        "current_time_et": now_et.strftime("%Y-%m-%d %H:%M %Z"),
        "current_time_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "weekday": now_et.strftime("%A"),
    }


# ── Scheduled jobs ─────────────────────────────────────────────────────────────

async def job_run_pipeline():
    """Main 4-agent pipeline job — runs every 4 hours during market hours."""
    if not is_market_open():
        logger.info("Scheduler: market closed, skipping pipeline run")
        return

    logger.info("Scheduler: starting scheduled pipeline run...")
    db = SessionLocal()
    try:
        result = await run_pipeline(db)
        logger.info(
            "Scheduler: pipeline complete — %d signals, %d approved",
            result.get("signals_generated", 0),
            result.get("signals_approved", 0),
        )
    except Exception as exc:
        logger.error("Scheduler: pipeline job failed: %s", exc)
    finally:
        db.close()


async def job_run_news_sentinel():
    """News sentinel job — runs at 6AM and 4PM ET daily."""
    logger.info("Scheduler: running News Sentinel...")
    db = SessionLocal()
    try:
        result = await run_news_sentinel(db)
        logger.info(
            "Scheduler: News Sentinel complete — %d events stored",
            result.get("events_stored", 0),
        )
    except Exception as exc:
        logger.error("Scheduler: News Sentinel job failed: %s", exc)
    finally:
        db.close()


async def job_manage_trades():
    """Trade lifecycle manager — runs every 5 minutes during market hours."""
    if not is_market_open():
        return

    logger.info("Scheduler: running trade lifecycle check...")
    db = SessionLocal()
    try:
        mgr = TradeManager(db)
        result = await mgr.check_and_manage_trades()
        logger.info(
            "Scheduler: trade lifecycle — checked=%d, breakeven=%d, trailing=%d, partial=%d, closed=%d",
            result["checked"], result["breakeven_applied"],
            result["trailing_applied"], result["partial_closes"], result["closed"],
        )
    except Exception as exc:
        logger.error("Scheduler: trade lifecycle job failed: %s", exc)
    finally:
        db.close()


# ── Scheduler factory ──────────────────────────────────────────────────────────

def create_scheduler() -> AsyncIOScheduler:
    """
    Build and return the configured AsyncIOScheduler.

    Jobs:
    - Pipeline: every 4H at :00 (00:00, 04:00, 08:00, 12:00, 16:00, 20:00 UTC)
    - News Sentinel: 6AM ET and 4PM ET daily (converts to UTC in cron)
      Standard time: 11:00 UTC and 21:00 UTC
      DST:           10:00 UTC and 20:00 UTC
      → Use ET timezone directly in APScheduler

    """
    scheduler = AsyncIOScheduler(timezone=pytz.utc)

    # Screener + analyst pipeline every 4 hours (on the hour, UTC)
    scheduler.add_job(
        job_run_pipeline,
        trigger="cron",
        hour="0,4,8,12,16,20",
        minute=0,
        id="pipeline",
        name="4-Agent Pipeline",
        replace_existing=True,
        misfire_grace_time=300,  # 5 minute grace period
    )

    # News Sentinel at 6AM ET (handles DST automatically via timezone arg)
    scheduler.add_job(
        job_run_news_sentinel,
        trigger="cron",
        hour=6,
        minute=0,
        timezone=ET,
        id="news_sentinel_morning",
        name="News Sentinel (Morning)",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # News Sentinel at 4PM ET
    scheduler.add_job(
        job_run_news_sentinel,
        trigger="cron",
        hour=16,
        minute=0,
        timezone=ET,
        id="news_sentinel_afternoon",
        name="News Sentinel (Afternoon)",
        replace_existing=True,
        misfire_grace_time=600,
    )

    # Trade lifecycle manager every 5 minutes
    scheduler.add_job(
        job_manage_trades,
        trigger="interval",
        minutes=5,
        id="trade_lifecycle",
        name="Trade Lifecycle Manager",
        replace_existing=True,
        misfire_grace_time=60,
    )

    return scheduler
