from __future__ import annotations

import json
import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy.orm import Session

from backend.app.agents.analyst import run_analyst
from backend.app.agents.risk_manager_agent import run_risk_manager
from backend.app.agents.screener import run_screener
from backend.app.config import get_settings
from backend.app.models.signal import Signal

logger = logging.getLogger(__name__)


# ── Email alert ───────────────────────────────────────────────────────────────

def _send_email_alert(settings, signal: Signal, risk_result: dict, executed: bool = False) -> bool:
    """Send SMTP email alert for a trade signal. Returns True on success."""
    if not settings.smtp_username or not settings.alert_email_to:
        logger.info("Orchestrator: email not configured, skipping alert")
        return False

    direction_emoji = "BUY" if signal.direction == "long" else "SELL"
    mode_label = settings.execution_mode
    subject = f"[TradeSight] {direction_emoji} {signal.instrument} — Confidence {signal.confidence}/10"

    body_lines = [
        f"TradeSight Trade Alert — {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}",
        f"Mode: {mode_label}",
        "",
        f"Instrument:   {signal.instrument}",
        f"Direction:    {signal.direction.upper()}",
        f"Entry Price:  {signal.entry_price}",
        f"Stop Loss:    {signal.stop_loss}",
        f"Take Profit 1:{signal.take_profit_1}",
    ]
    if signal.take_profit_2:
        body_lines.append(f"Take Profit 2:{signal.take_profit_2}")

    body_lines += [
        "",
        f"Position Size:{risk_result['position_size_lots']:.2f} lots",
        f"Risk Amount:  ${risk_result['risk_amount_usd']:.2f}",
        f"Risk/Reward:  1:{risk_result['risk_reward_ratio']:.1f}",
        f"Confidence:   {signal.confidence}/10",
        "",
        "=== ANALYST REASONING ===",
        signal.reasoning or "N/A",
        "",
    ]

    if executed:
        body_lines += [
            "=== TRADE EXECUTED ===",
            f"A trade has been AUTOMATICALLY placed on your OANDA practice account.",
            f"Trade ID: {signal.trade_id or 'N/A'}",
            "",
        ]
    elif mode_label == "SEMI_AUTO":
        body_lines += [
            "=== AWAITING YOUR APPROVAL ===",
            f"To approve this trade, visit the TradeSight dashboard and click 'Approve'",
            f"on Signal #{signal.id}.",
            "",
        ]
    else:
        body_lines += [
            "=== ALERT ONLY ===",
            "No trade has been executed automatically.",
            "Review the setup before placing any order.",
            "",
        ]

    if signal.risk_rejection_reasons:
        body_lines.append("=== RISK FLAGS ===")
        try:
            reasons = json.loads(signal.risk_rejection_reasons)
            for r in reasons:
                body_lines.append(f"  • {r}")
        except Exception:
            body_lines.append(signal.risk_rejection_reasons)

    body = "\n".join(body_lines)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = settings.smtp_username
    msg["To"] = settings.alert_email_to
    msg.attach(MIMEText(body, "plain"))

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.sendmail(settings.smtp_username, settings.alert_email_to, msg.as_string())
        logger.info("Orchestrator: email alert sent for %s", signal.instrument)
        return True
    except Exception as exc:
        logger.error("Orchestrator: email send failed: %s", exc)
        return False


# ── Signal persistence ────────────────────────────────────────────────────────

def _persist_signal(db: Session, analyst_result: dict, risk_result: dict, execution_mode: str) -> Signal:
    """Save a completed signal (approved or not) to the database."""
    rejection_reasons = risk_result.get("rejection_reasons", [])

    # Determine execution_status based on mode
    approved = risk_result.get("approved", False)
    if not approved:
        exec_status = None
    elif execution_mode == "SEMI_AUTO":
        exec_status = "pending_approval"
    elif execution_mode == "FULL_AUTO":
        exec_status = "pending_execution"
    else:
        exec_status = None  # ALERT_ONLY

    signal = Signal(
        instrument=analyst_result["instrument"],
        direction=analyst_result.get("direction"),
        entry_price=analyst_result.get("entry_price"),
        stop_loss=analyst_result.get("stop_loss"),
        take_profit_1=analyst_result.get("take_profit_1"),
        take_profit_2=analyst_result.get("take_profit_2"),
        confidence=analyst_result.get("confidence", 0),
        session=analyst_result.get("session"),
        reasoning=analyst_result.get("reasoning"),
        screener_reason=analyst_result.get("screener_reason"),
        position_size=risk_result.get("position_size_lots"),
        risk_amount=risk_result.get("risk_amount_usd"),
        risk_reward_ratio=risk_result.get("risk_reward_ratio"),
        risk_approved=approved,
        risk_rejection_reasons=json.dumps(rejection_reasons) if rejection_reasons else None,
        status="active" if approved else "cancelled",
        is_news_blackout=risk_result.get("news_blackout", False),
        execution_status=exec_status,
    )
    db.add(signal)
    db.commit()
    db.refresh(signal)
    return signal


# ── Auto-execute for FULL_AUTO mode ──────────────────────────────────────────

async def _auto_execute(db: Session, signal: Signal, settings) -> bool:
    """Execute a trade automatically in FULL_AUTO mode. Returns True on success."""
    from backend.app.services.trade_manager import execute_signal_trade

    # Defense-in-depth: even if the analyst min confidence is dropped, never
    # auto-execute below 7. Risk filters (R:R, daily loss, max positions) are
    # applied separately by the risk manager.
    if signal.confidence < 7:
        logger.info("Orchestrator: FULL_AUTO skipped — confidence %d < 7", signal.confidence)
        signal.execution_status = None
        db.commit()
        return False

    try:
        trade = await execute_signal_trade(db, signal.id)
        logger.info("Orchestrator: FULL_AUTO executed trade %s for signal %d", trade.oanda_trade_id, signal.id)
        return True
    except Exception as exc:
        logger.error("Orchestrator: FULL_AUTO execution failed for signal %d: %s", signal.id, exc)
        signal.execution_status = "execution_failed"
        signal.notes = str(exc) if hasattr(signal, "notes") else None
        db.commit()
        return False


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def run_pipeline(db: Session) -> dict:
    """
    Full 4-agent pipeline:
      1. Screener — batch screen all 6 pairs (1 Haiku call)
      2. Analyst — deep MTF analysis per flagged pair (1 Sonnet call each)
      3. Risk Manager — pure Python validation
      4. Orchestrator — persist Signal, handle execution mode, send email

    Returns pipeline summary.
    """
    settings = get_settings()
    logger.info("=== Orchestrator: starting pipeline run (mode=%s) ===", settings.execution_mode)

    summary = {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "execution_mode": settings.execution_mode,
        "pairs_screened": 0,
        "pairs_flagged": 0,
        "signals_generated": 0,
        "signals_approved": 0,
        "trades_executed": 0,
        "emails_sent": 0,
        "signals": [],
        "errors": [],
    }

    # ── Step 1: Screener ───────────────────────────────────────────────────────
    try:
        screener_result = await run_screener(db)
    except Exception as exc:
        logger.error("Orchestrator: Screener failed: %s", exc)
        summary["errors"].append(f"Screener: {exc}")
        return summary

    summary["pairs_screened"] = screener_result.get("pairs_screened", 0)
    flagged = screener_result.get("flagged", [])
    summary["pairs_flagged"] = len(flagged)

    if not flagged:
        logger.info("Orchestrator: Screener found no setups — pipeline complete")
        return summary

    logger.info("Orchestrator: %d pair(s) flagged for deep analysis: %s",
                len(flagged), [f["pair"] for f in flagged])

    # ── Steps 2–4: Analyst + Risk Manager + persist + execute per flagged pair
    for flagged_pair in flagged:
        instrument = flagged_pair["pair"]
        screener_direction = flagged_pair.get("direction", "")
        screener_reason = flagged_pair.get("reason", "")

        try:
            # Step 2: Analyst
            analyst_result = await run_analyst(
                db=db,
                instrument=instrument,
                screener_reason=screener_reason,
                screener_direction=screener_direction,
            )

            if not analyst_result.get("direction"):
                logger.info("Orchestrator: Analyst found no valid setup for %s", instrument)
                summary["errors"].append(f"Analyst ({instrument}): no setup above confidence threshold")
                continue

            summary["signals_generated"] += 1

            # Step 3: Risk Manager
            risk_result = await run_risk_manager(db=db, analyst_result=analyst_result)

            # Step 4: Persist signal
            signal = _persist_signal(db, analyst_result, risk_result, settings.execution_mode)

            signal_summary = {
                "id": signal.id,
                "instrument": instrument,
                "direction": signal.direction,
                "entry_price": signal.entry_price,
                "stop_loss": signal.stop_loss,
                "take_profit_1": signal.take_profit_1,
                "confidence": signal.confidence,
                "risk_approved": signal.risk_approved,
                "status": signal.status,
                "execution_status": signal.execution_status,
            }
            summary["signals"].append(signal_summary)

            if risk_result.get("approved"):
                summary["signals_approved"] += 1

                # Handle execution based on mode
                if settings.execution_mode == "FULL_AUTO":
                    executed = await _auto_execute(db, signal, settings)
                    if executed:
                        summary["trades_executed"] += 1
                    # Send email notification either way
                    email_sent = _send_email_alert(settings, signal, risk_result, executed=executed)
                    if email_sent:
                        summary["emails_sent"] += 1

                elif settings.execution_mode == "SEMI_AUTO":
                    # Signal stays as pending_approval — user must approve via API
                    email_sent = _send_email_alert(settings, signal, risk_result, executed=False)
                    if email_sent:
                        summary["emails_sent"] += 1

                else:
                    # ALERT_ONLY
                    email_sent = _send_email_alert(settings, signal, risk_result, executed=False)
                    if email_sent:
                        summary["emails_sent"] += 1

            else:
                logger.info(
                    "Orchestrator: %s signal NOT approved — reasons: %s",
                    instrument,
                    risk_result.get("rejection_reasons"),
                )

        except Exception as exc:
            logger.error("Orchestrator: error processing %s: %s", instrument, exc)
            summary["errors"].append(f"{instrument}: {exc}")

    summary["completed_at"] = datetime.now(timezone.utc).isoformat()
    logger.info(
        "=== Orchestrator: pipeline complete — %d signals, %d approved, %d executed, %d emails ===",
        summary["signals_generated"],
        summary["signals_approved"],
        summary["trades_executed"],
        summary["emails_sent"],
    )

    return summary


async def run_single_pair(db: Session, instrument: str) -> dict:
    """
    Run the analyst + risk pipeline for a single pair (manual trigger).
    Skips the screener — goes directly to deep analysis.
    """
    settings = get_settings()
    logger.info("Orchestrator: manual analysis triggered for %s (mode=%s)", instrument, settings.execution_mode)

    try:
        analyst_result = await run_analyst(
            db=db,
            instrument=instrument,
            screener_reason="Manual trigger via API",
            screener_direction="",
        )
    except Exception as exc:
        logger.error("Orchestrator: Analyst failed for %s: %s", instrument, exc)
        return {"status": "error", "instrument": instrument, "error": str(exc)}

    if not analyst_result.get("direction"):
        return {
            "status": "no_setup",
            "instrument": instrument,
            "confidence": analyst_result.get("confidence", 0),
            "reasoning": analyst_result.get("reasoning"),
        }

    try:
        risk_result = await run_risk_manager(db=db, analyst_result=analyst_result)
    except Exception as exc:
        logger.error("Orchestrator: Risk Manager failed for %s: %s", instrument, exc)
        return {"status": "error", "instrument": instrument, "error": str(exc)}

    signal = _persist_signal(db, analyst_result, risk_result, settings.execution_mode)

    executed = False
    if risk_result.get("approved"):
        if settings.execution_mode == "FULL_AUTO" and signal.confidence >= 7:
            executed = await _auto_execute(db, signal, settings)

        _send_email_alert(settings, signal, risk_result, executed=executed)

    return {
        "status": "ok",
        "signal_id": signal.id,
        "instrument": signal.instrument,
        "direction": signal.direction,
        "entry_price": signal.entry_price,
        "stop_loss": signal.stop_loss,
        "take_profit_1": signal.take_profit_1,
        "take_profit_2": signal.take_profit_2,
        "confidence": signal.confidence,
        "risk_approved": signal.risk_approved,
        "execution_status": signal.execution_status,
        "position_size_lots": risk_result.get("position_size_lots"),
        "risk_amount_usd": risk_result.get("risk_amount_usd"),
        "rejection_reasons": risk_result.get("rejection_reasons", []),
        "reasoning": signal.reasoning,
        "executed": executed,
    }
