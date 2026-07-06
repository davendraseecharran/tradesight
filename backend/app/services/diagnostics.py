"""Full diagnostic report builder — analytics + bug evidence in one JSON.

Used by the dashboard's "Download Report" button and review_performance.py.
The output is designed to be uploaded to Claude for a weekly performance
review: it contains everything needed to analyze strategy performance AND
diagnose failures (job health, error log tail, candle freshness) without
access to the machine.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.models.api_call import ApiCall
from backend.app.models.signal import Signal
from backend.app.models.trade import Trade
from backend.app.services.system_status import health_snapshot, load_status

BACKEND_LOG = Path("/tmp/tradesight-backend.log")
WATCHDOG_LOG = Path("/tmp/tradesight-watchdog.log")


def build_daily_status(db: Session) -> str:
    """Plain-text daily heartbeat email body: last 24h of activity + health.

    Sent every day so the user can distinguish 'no setups found' (email
    arrives, says so) from 'app is down' (no email at all).
    """
    from backend.app.models.api_call import ApiCall as _ApiCall  # local alias

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=24)

    signals = db.query(Signal).filter(Signal.created_at >= cutoff).all()
    trades = db.query(Trade).filter(Trade.created_at >= cutoff).all()
    open_trades = db.query(Trade).filter(Trade.status.in_(["open", "partial_close"])).all()
    ai_calls = db.query(_ApiCall).filter(_ApiCall.timestamp >= cutoff).all()
    ai_cost = sum((c.cost_usd or 0) for c in ai_calls)

    snapshot = health_snapshot()
    jobs = snapshot.get("jobs", {})

    def _job_line(name: str, label: str) -> str:
        j = jobs.get(name)
        if not j:
            return f"  {label}: no runs recorded yet"
        age = j.get("last_success_age_hours")
        fails = j.get("consecutive_failures", 0)
        age_str = f"last success {age}h ago" if age is not None else "no success recorded"
        fail_str = f", {fails} consecutive failures" if fails else ""
        return f"  {label}: {age_str}{fail_str}"

    lines = [
        f"TradeSight Daily Status — {now.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
        "If you're reading this, the app is alive. No daily email = app is down.",
        "",
        f"System health: {'OK' if snapshot['ok'] else 'DEGRADED'}",
    ]
    for p in snapshot.get("problems", []):
        lines.append(f"  PROBLEM: {p}")
    lines += [
        _job_line("pipeline", "Pipeline (4h scans)"),
        _job_line("candle_refresh", "Candle refresh (hourly)"),
        _job_line("trade_lifecycle", "Trade lifecycle (5min)"),
        _job_line("validator", "AI validator"),
        _job_line("news_sentinel", "News sentinel"),
        _job_line("email", "Email delivery"),
        "",
        "Last 24 hours:",
        f"  Setups found by engine: {len(signals)}",
    ]
    for s in signals:
        verdict = "risk-approved" if s.risk_approved else "rejected"
        lines.append(
            f"    - {s.instrument} {s.direction} conf={s.confidence} → {verdict}"
            f" ({s.status}/{s.execution_status or 'no exec'})"
        )
    lines += [
        f"  Trades opened: {len(trades)}",
        f"  Open positions now: {len(open_trades)}",
    ]
    for t in open_trades:
        lines.append(
            f"    - {t.instrument} {t.direction} @ {t.entry_price}"
            f" (SL {t.stop_loss}, TP {t.take_profit})"
        )
    lines += [
        f"  AI cost: ${ai_cost:.4f} ({len(ai_calls)} calls)",
        "",
        "Engine snapshot (what each market is doing / waiting for):",
    ]
    try:
        # Lazy import avoids a circular dependency at module load time
        from backend.app.agents.orchestrator import explain_pair_gates
        for line in explain_pair_gates(db):
            lines.append(f"  {line}")
    except Exception as exc:
        lines.append(f"  (snapshot unavailable: {exc})")
    lines += [
        "",
        "Zero setups is normal — the 48-month backtest averaged ~1 trade every 6-8 weeks",
        "across all markets. Quiet weeks are the strategy working, not failing.",
        "Dashboard: http://localhost:8000  |  Weekly review: click Download Report.",
    ]
    return "\n".join(lines)


def _log_tail(path: Path, interesting_only: bool = True, max_lines: int = 300) -> list[str]:
    """Last error/warning lines from a log file (bounded read: only the final
    512KB, so a weeks-old unrotated log can't blow up report generation)."""
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - 512 * 1024))
            lines = f.read().decode(errors="ignore").splitlines()
            if size > 512 * 1024 and lines:
                lines = lines[1:]  # drop the partial first line
    except Exception:
        return []
    if interesting_only:
        lines = [l for l in lines if "ERROR" in l or "WARNING" in l or "Traceback" in l]
    return lines[-max_lines:]


def build_report(db: Session, days: Optional[int] = 7) -> dict:
    """Assemble the full diagnostic report. `days=None` = all history."""
    settings = get_settings()
    cutoff = None if days is None else datetime.now(timezone.utc) - timedelta(days=days)

    report: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback": "all_time" if days is None else f"last_{days}_days",
        "config": {
            "execution_mode": settings.execution_mode,
            "validator_mode": settings.validator_mode,
            "max_risk_per_trade": settings.max_risk_per_trade,
            "daily_loss_limit": settings.daily_loss_limit,
            "max_open_positions": settings.max_open_positions,
            "min_risk_reward_ratio": settings.min_risk_reward_ratio,
        },
    }

    # ── Signals ────────────────────────────────────────────────────────────────
    sq = db.query(Signal)
    if cutoff:
        sq = sq.filter(Signal.created_at >= cutoff)
    signals = sq.order_by(Signal.created_at.desc()).all()
    report["signals"] = [
        {
            "id": s.id, "instrument": s.instrument, "direction": s.direction,
            "confidence": s.confidence, "entry_price": s.entry_price,
            "stop_loss": s.stop_loss, "take_profit_1": s.take_profit_1,
            "risk_reward_ratio": s.risk_reward_ratio,
            "position_size": s.position_size, "risk_amount": s.risk_amount,
            "risk_approved": s.risk_approved,
            "risk_rejection_reasons": s.risk_rejection_reasons,
            "status": s.status, "execution_status": s.execution_status,
            "session": s.session, "screener_reason": s.screener_reason,
            "reasoning": (s.reasoning[:400] + "...") if s.reasoning and len(s.reasoning) > 400 else s.reasoning,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        }
        for s in signals
    ]

    # ── Trades ─────────────────────────────────────────────────────────────────
    tq = db.query(Trade)
    if cutoff:
        tq = tq.filter(Trade.created_at >= cutoff)
    trades = tq.order_by(Trade.created_at.desc()).all()
    report["trades"] = [
        {
            "id": t.id, "signal_id": t.signal_id, "instrument": t.instrument,
            "direction": t.direction,
            "recommended_entry": t.recommended_entry, "actual_entry": t.entry_price,
            "stop_loss": t.stop_loss, "take_profit": t.take_profit,
            "position_size_lots": t.position_size, "risk_amount": t.risk_amount,
            "slippage": t.slippage, "status": t.status,
            "exit_reason": t.exit_reason, "actual_exit_price": t.actual_exit_price,
            "actual_pnl": t.actual_pnl,
            "breakeven_applied": t.breakeven_applied,
            "trailing_stop_applied": t.trailing_stop_applied,
            "partial_close_done": t.partial_close_done,
            "account_balance_at_open": t.account_balance_at_open,
            "opened_at": t.opened_at.isoformat() if t.opened_at else None,
            "closed_at": t.closed_at.isoformat() if t.closed_at else None,
        }
        for t in trades
    ]

    # ── Performance summary ────────────────────────────────────────────────────
    closed = [t for t in trades if t.status == "closed"]
    wins = [t for t in closed if (t.actual_pnl or 0) > 0]
    losses = [t for t in closed if (t.actual_pnl or 0) <= 0]
    gross_win = sum((t.actual_pnl or 0) for t in wins)
    gross_loss = abs(sum((t.actual_pnl or 0) for t in losses))

    by_pair: dict = {}
    for t in closed:
        d = by_pair.setdefault(t.instrument, {"count": 0, "wins": 0, "pnl": 0.0})
        d["count"] += 1
        d["pnl"] = round(d["pnl"] + (t.actual_pnl or 0), 2)
        if (t.actual_pnl or 0) > 0:
            d["wins"] += 1

    by_exit: dict = {}
    for t in closed:
        by_exit[t.exit_reason or "unknown"] = by_exit.get(t.exit_reason or "unknown", 0) + 1

    report["summary"] = {
        "total_signals": len(signals),
        "approved_signals": sum(1 for s in signals if s.risk_approved),
        "total_trades": len(trades),
        "open_trades": sum(1 for t in trades if t.status in ("open", "partial_close")),
        "closed_trades": len(closed),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(len(wins) / len(closed) * 100, 1) if closed else None,
        "net_pnl_usd": round(sum((t.actual_pnl or 0) for t in closed), 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        "by_pair": by_pair,
        "by_exit_reason": by_exit,
    }

    # ── AI costs ───────────────────────────────────────────────────────────────
    aq = db.query(ApiCall)
    if cutoff:
        aq = aq.filter(ApiCall.timestamp >= cutoff)
    by_agent: dict = {}
    total_cost = 0.0
    for c in aq.all():
        d = by_agent.setdefault(c.agent or "unknown", {"calls": 0, "cost_usd": 0.0})
        d["calls"] += 1
        d["cost_usd"] = round(d["cost_usd"] + (c.cost_usd or 0), 4)
        total_cost += c.cost_usd or 0
    report["api_costs"] = {"by_agent": by_agent, "total_usd": round(total_cost, 4)}

    # ── System health / bug evidence ───────────────────────────────────────────
    report["health"] = health_snapshot()
    report["job_status_raw"] = load_status()

    freshness = []
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    for row in db.execute(text(
        "SELECT instrument, granularity, MAX(timestamp) FROM candles "
        "GROUP BY instrument, granularity ORDER BY instrument, granularity"
    )):
        latest = row[2]
        if isinstance(latest, str):
            latest = datetime.fromisoformat(latest.split(".")[0])
        freshness.append({
            "instrument": row[0], "granularity": row[1],
            "latest": str(latest),
            "age_hours": round((now - latest).total_seconds() / 3600, 1),
        })
    report["candle_freshness"] = freshness

    report["error_log_tail"] = _log_tail(BACKEND_LOG)
    report["watchdog_log_tail"] = _log_tail(WATCHDOG_LOG, interesting_only=False, max_lines=50)

    return report
