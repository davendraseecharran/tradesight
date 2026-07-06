from __future__ import annotations

import json
import logging
import smtplib
from datetime import datetime, timezone
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from sqlalchemy.orm import Session

from backend.app.agents.risk_manager_agent import run_risk_manager
from backend.app.agents.validator import run_validator
from backend.app.config import FOREX_PAIRS, get_settings
from backend.app.models.signal import Signal
from backend.app.services.historical import load_candles_as_dataframe
from backend.app.services.indicators import compute_indicators
from backend.app.services.strategy import evaluate_setup
from backend.app.services.system_status import record_failure, record_success

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
        record_success("email", f"trade alert for {signal.instrument}")
        return True
    except Exception as exc:
        # Track SMTP breakage in /health — the failure-alert email obviously
        # can't announce that email itself is broken.
        logger.error("Orchestrator: email send failed: %s", exc)
        record_failure("email", str(exc))
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
        db.commit()
        return False


# ── Engine scan (pure Python, zero AI cost) ───────────────────────────────────

def _current_session() -> str:
    hour = datetime.now(timezone.utc).hour
    if 7 <= hour < 12:
        return "London"
    if 12 <= hour < 16:
        return "London/NY overlap"
    if 16 <= hour < 21:
        return "New York"
    return "Asia"


def _load_frames(db: Session, instrument: str) -> dict:
    """Load the timeframes the engine needs from the local candle store."""
    frames = {}
    for gran in ("W", "D", "H4"):
        df = load_candles_as_dataframe(db, instrument, gran)
        if df is not None and len(df):
            frames[gran] = df
    return frames


def scan_setups(db: Session) -> list[dict]:
    """Run the mechanical 3-step engine over all pairs. Free, deterministic."""
    candidates = []
    for pair in FOREX_PAIRS:
        try:
            frames = _load_frames(db, pair)
            setup = evaluate_setup(frames, pair)
            if setup:
                candidates.append(setup)
                logger.info("Engine: candidate %s %s — %s",
                            pair, setup["direction"], setup["reason"])
        except Exception as exc:
            logger.error("Engine: scan failed for %s: %s", pair, exc)
    return candidates


def _indicator_frames(db: Session, instrument: str) -> dict:
    """Small indicator context for the validator (D + H4)."""
    frames = {}
    for tf, gran in (("D", "D"), ("H4", "4H")):
        try:
            df = load_candles_as_dataframe(db, instrument, gran)
            if df is not None and len(df) >= 50:
                frames[tf] = compute_indicators(df, tf)
        except Exception as exc:
            logger.warning("Orchestrator: indicators failed %s %s: %s", instrument, tf, exc)
    return frames


# ── Main pipeline ─────────────────────────────────────────────────────────────

async def run_pipeline(db: Session) -> dict:
    """
    Engine-first pipeline:
      1. Engine scan — mechanical 3-step strategy over all pairs (free)
      2. Validator — one Claude call per candidate (usually 0-1 per run)
      3. Risk Manager — pure Python validation
      4. Orchestrator — persist Signal, handle execution mode, send email
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

    # ── Step 1: Engine scan ────────────────────────────────────────────────────
    candidates = scan_setups(db)
    summary["pairs_screened"] = len(FOREX_PAIRS)
    summary["pairs_flagged"] = len(candidates)

    if not candidates:
        logger.info("Orchestrator: engine found no setups — pipeline complete")
        return summary

    # ── Steps 2-4 per candidate ────────────────────────────────────────────────
    for setup in candidates:
        instrument = setup["instrument"]
        try:
            # Step 2: Claude validator (per validator_mode)
            mode = settings.validator_mode
            if mode == "off":
                analyst_result = dict(setup)
                analyst_result["confidence"] = 7
                analyst_result["reasoning"] = "Mechanical mode: engine rules passed; validator disabled."
            else:
                try:
                    analyst_result = await run_validator(
                        db, setup, indicator_frames=_indicator_frames(db, instrument)
                    )
                    # The API call worked — reset the failure counter
                    record_success("validator", f"validated {instrument}")
                    if not analyst_result.get("validator_approve"):
                        logger.info("Orchestrator: validator vetoed %s (confidence %d)",
                                    instrument, analyst_result.get("confidence", 0))
                        summary["errors"].append(
                            f"Validator ({instrument}): vetoed — {analyst_result.get('reasoning', '')[:200]}"
                        )
                        continue
                except Exception as exc:
                    # A validator failure with a live candidate means a missed
                    # trade — track it so repeated failures (e.g. unfunded API
                    # key) trigger the alert email instead of failing silently.
                    record_failure("validator", f"{instrument}: {exc}")
                    if mode == "optional":
                        logger.warning("Orchestrator: validator unavailable (%s), proceeding mechanically", exc)
                        analyst_result = dict(setup)
                        analyst_result["confidence"] = 7
                        analyst_result["reasoning"] = f"Validator unavailable ({exc}); engine rules passed."
                    else:
                        # required: no validation = no trade
                        logger.error("Orchestrator: validator failed for %s: %s", instrument, exc)
                        summary["errors"].append(f"Validator ({instrument}): {exc}")
                        continue

            analyst_result["screener_reason"] = setup["reason"]
            analyst_result["session"] = _current_session()
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
    Run the engine + validator + risk pipeline for a single pair (manual
    trigger via the Analyze button).
    """
    settings = get_settings()
    logger.info("Orchestrator: manual analysis triggered for %s (mode=%s)", instrument, settings.execution_mode)

    try:
        frames = _load_frames(db, instrument)
        setup = evaluate_setup(frames, instrument)
    except Exception as exc:
        logger.error("Orchestrator: engine failed for %s: %s", instrument, exc)
        return {"status": "error", "instrument": instrument, "error": str(exc)}

    if setup is None:
        return {
            "status": "no_setup",
            "instrument": instrument,
            "confidence": 0,
            "reasoning": (
                "No valid 3-step setup right now. All of the following must hold: "
                "Weekly and Daily structure agree on direction; price is at a "
                "support/resistance zone with 3+ touches inside the structure range; "
                "the last closed 4H candle is a confirmation pattern in that direction; "
                "and the nearest structure target gives at least 1:2 risk/reward."
            ),
        }

    mode = settings.validator_mode
    if mode == "off":
        analyst_result = dict(setup)
        analyst_result["confidence"] = 7
        analyst_result["reasoning"] = "Mechanical mode: engine rules passed; validator disabled."
    else:
        try:
            analyst_result = await run_validator(
                db, setup, indicator_frames=_indicator_frames(db, instrument)
            )
        except Exception as exc:
            if mode == "optional":
                analyst_result = dict(setup)
                analyst_result["confidence"] = 7
                analyst_result["reasoning"] = f"Validator unavailable ({exc}); engine rules passed."
            else:
                logger.error("Orchestrator: validator failed for %s: %s", instrument, exc)
                return {"status": "error", "instrument": instrument,
                        "error": f"Engine found a setup but the validator is unavailable: {exc}"}
        if not analyst_result.get("validator_approve", True):
            return {
                "status": "no_setup",
                "instrument": instrument,
                "confidence": analyst_result.get("confidence", 0),
                "reasoning": "Validator vetoed the engine candidate: "
                             + str(analyst_result.get("reasoning", "")),
            }

    analyst_result["screener_reason"] = setup["reason"] + " (manual trigger)"
    analyst_result["session"] = _current_session()

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
