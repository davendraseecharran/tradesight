from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.agents.news_sentinel import get_active_blackouts
from backend.app.config import get_settings
from backend.app.models.news_event import NewsEvent
from backend.app.services.oanda import OandaClient
from backend.app.services.risk import RiskManager

logger = logging.getLogger(__name__)

# Position size clamp for ~$500 demo account
LOT_MIN = 0.01
LOT_MAX = 0.05
UNITS_PER_LOT = 100_000


def _units_to_lots(raw_units: float) -> float:
    """Convert raw position units to clamped lot size for $500 account."""
    lots = raw_units / UNITS_PER_LOT
    return round(max(LOT_MIN, min(LOT_MAX, lots)), 2)


async def run_risk_manager(
    db: Session,
    analyst_result: dict,
) -> dict:
    """
    Pure-Python risk gate. No API calls to Claude — zero token cost.

    Steps:
    1. Fetch live OANDA account balance
    2. Check news blackout for instrument currencies
    3. Validate trade via existing RiskManager rules
    4. Clamp position size for $500 account
    5. Return approval dict with full breakdown
    """
    settings = get_settings()
    instrument = analyst_result.get("instrument", "")
    direction = analyst_result.get("direction")
    entry = analyst_result.get("entry_price")
    stop_loss = analyst_result.get("stop_loss")
    take_profit_1 = analyst_result.get("take_profit_1")

    # Bail early if analyst found no setup
    if not direction or entry is None or stop_loss is None or take_profit_1 is None:
        return {
            "approved": False,
            "rejection_reasons": ["Analyst did not produce a valid trade setup"],
            "instrument": instrument,
        }

    # ── 1. Fetch live account balance ──────────────────────────────────────────
    account_balance = 500.0  # safe fallback
    try:
        oanda = OandaClient(settings)
        summary = await oanda.get_account_summary()
        await oanda.close()
        account_balance = float(summary.get("balance", 500.0))
        logger.info("Risk Manager: live OANDA balance $%.2f", account_balance)
    except Exception as exc:
        logger.warning("Risk Manager: OANDA balance fetch failed (%s), using $500 fallback", exc)

    # ── 2. News blackout check ─────────────────────────────────────────────────
    active_blackouts = get_active_blackouts(db, instrument)
    in_blackout = len(active_blackouts) > 0
    blackout_detail = []
    if in_blackout:
        for ev in active_blackouts:
            blackout_detail.append(
                f"{ev.event} ({ev.currency}) — blackout until {ev.blackout_end.strftime('%H:%M UTC')}"
            )
        logger.info("Risk Manager: news blackout active for %s: %s", instrument, blackout_detail)

    # ── 3. Standard risk validation ───────────────────────────────────────────
    rm = RiskManager(db, settings)
    validation = rm.validate_trade(
        account_balance=account_balance,
        starting_balance=account_balance,  # daily loss vs current balance for demo
        entry=entry,
        stop_loss=stop_loss,
        take_profit=take_profit_1,
        instrument=instrument,
    )

    rejection_reasons = list(validation["rejection_reasons"])

    if in_blackout:
        rejection_reasons.append(
            "News blackout active: " + "; ".join(blackout_detail)
        )

    # ── 4. Clamp position size ─────────────────────────────────────────────────
    raw_units = validation["position_size"]
    clamped_lots = _units_to_lots(raw_units)
    risk_amount = round(account_balance * settings.max_risk_per_trade, 2)

    approved = len(rejection_reasons) == 0

    logger.info(
        "Risk Manager: %s %s — approved=%s lots=%.2f risk=$%.2f",
        instrument, direction, approved, clamped_lots, risk_amount,
    )

    return {
        "approved": approved,
        "instrument": instrument,
        "direction": direction,
        "entry_price": entry,
        "stop_loss": stop_loss,
        "take_profit_1": take_profit_1,
        "take_profit_2": analyst_result.get("take_profit_2"),
        "position_size_lots": clamped_lots,
        "risk_amount_usd": risk_amount,
        "risk_reward_ratio": validation["risk_reward_ratio"],
        "account_balance": round(account_balance, 2),
        "rejection_reasons": rejection_reasons,
        "news_blackout": in_blackout,
        "blackout_details": blackout_detail,
    }
