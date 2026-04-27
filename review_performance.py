#!/usr/bin/env python3
"""
TradeSight — Weekly Performance Review

Run this on the trading Mac whenever you want me (Claude) to review and
tune the strategy. It exports a comprehensive JSON report covering every
signal, trade, and API call. Paste the entire output into our chat.

Usage:
    python review_performance.py            # last 7 days (default)
    python review_performance.py --days 30  # last 30 days
    python review_performance.py --all      # everything

The script makes ZERO API calls (no token cost) — it just reads the local
SQLite database.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone

# Auto-detect and relaunch with venv Python if running under system Python
venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
if os.path.exists(venv_python) and os.path.realpath(sys.executable) != os.path.realpath(venv_python):
    os.execv(venv_python, [venv_python] + sys.argv)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for key in ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"]:
    os.environ.pop(key, None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7, help="Lookback window (default 7)")
    parser.add_argument("--all", action="store_true", help="Include all history")
    args = parser.parse_args()

    from backend.app.config import get_settings
    from backend.app.database import SessionLocal
    from backend.app.models.signal import Signal
    from backend.app.models.trade import Trade
    from backend.app.models.api_call import ApiCall

    get_settings.cache_clear()
    settings = get_settings()
    cutoff = None if args.all else datetime.now(timezone.utc) - timedelta(days=args.days)

    db = SessionLocal()
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "lookback": "all_time" if args.all else f"last_{args.days}_days",
        "config": {
            "execution_mode": settings.execution_mode,
            "analyst_min_confidence": settings.analyst_min_confidence,
            "max_risk_per_trade": settings.max_risk_per_trade,
            "daily_loss_limit": settings.daily_loss_limit,
            "max_open_positions": settings.max_open_positions,
            "min_risk_reward_ratio": settings.min_risk_reward_ratio,
        },
        "signals": [],
        "trades": [],
        "api_costs": {},
        "summary": {},
    }

    # ── Signals ────────────────────────────────────────────────────────────────
    sq = db.query(Signal)
    if cutoff:
        sq = sq.filter(Signal.created_at >= cutoff)
    signals = sq.order_by(Signal.created_at.desc()).all()

    for s in signals:
        report["signals"].append({
            "id": s.id,
            "instrument": s.instrument,
            "direction": s.direction,
            "confidence": s.confidence,
            "entry_price": s.entry_price,
            "stop_loss": s.stop_loss,
            "take_profit_1": s.take_profit_1,
            "take_profit_2": s.take_profit_2,
            "risk_reward_ratio": s.risk_reward_ratio,
            "position_size": s.position_size,
            "risk_amount": s.risk_amount,
            "risk_approved": s.risk_approved,
            "risk_rejection_reasons": s.risk_rejection_reasons,
            "status": s.status,
            "execution_status": s.execution_status,
            "session": s.session,
            "is_news_blackout": s.is_news_blackout,
            "screener_reason": s.screener_reason,
            "reasoning": (s.reasoning[:500] + "...") if s.reasoning and len(s.reasoning) > 500 else s.reasoning,
            "created_at": s.created_at.isoformat() if s.created_at else None,
        })

    # ── Trades ─────────────────────────────────────────────────────────────────
    tq = db.query(Trade)
    if cutoff:
        tq = tq.filter(Trade.created_at >= cutoff)
    trades = tq.order_by(Trade.created_at.desc()).all()

    for t in trades:
        report["trades"].append({
            "id": t.id,
            "signal_id": t.signal_id,
            "instrument": t.instrument,
            "direction": t.direction,
            "recommended_entry": t.recommended_entry,
            "actual_entry": t.entry_price,
            "stop_loss": t.stop_loss,
            "take_profit": t.take_profit,
            "recommended_tp1": t.recommended_tp1,
            "recommended_tp2": t.recommended_tp2,
            "position_size_lots": t.position_size,
            "risk_amount": t.risk_amount,
            "risk_reward_ratio": t.risk_reward_ratio,
            "slippage": t.slippage,
            "status": t.status,
            "exit_reason": t.exit_reason,
            "actual_exit_price": t.actual_exit_price,
            "actual_pnl": t.actual_pnl,
            "breakeven_applied": t.breakeven_applied,
            "trailing_stop_applied": t.trailing_stop_applied,
            "partial_close_done": t.partial_close_done,
            "account_balance_at_open": t.account_balance_at_open,
            "opened_at": t.opened_at.isoformat() if t.opened_at else None,
            "closed_at": t.closed_at.isoformat() if t.closed_at else None,
            "duration_hours": (
                (t.closed_at - t.opened_at).total_seconds() / 3600
                if t.opened_at and t.closed_at else None
            ),
        })

    # ── API costs ──────────────────────────────────────────────────────────────
    aq = db.query(ApiCall)
    if cutoff:
        aq = aq.filter(ApiCall.timestamp >= cutoff)
    calls = aq.all()

    by_agent = {}
    total_cost = 0.0
    for c in calls:
        a = c.agent or "unknown"
        if a not in by_agent:
            by_agent[a] = {"calls": 0, "input_tokens": 0, "output_tokens": 0,
                           "cache_read": 0, "cache_write": 0, "cost_usd": 0.0}
        by_agent[a]["calls"] += 1
        by_agent[a]["input_tokens"] += c.input_tokens or 0
        by_agent[a]["output_tokens"] += c.output_tokens or 0
        by_agent[a]["cache_read"] += c.cache_read_tokens or 0
        by_agent[a]["cache_write"] += c.cache_write_tokens or 0
        by_agent[a]["cost_usd"] += c.cost_usd or 0
        total_cost += c.cost_usd or 0

    report["api_costs"] = {"by_agent": by_agent, "total_usd": round(total_cost, 4)}

    # ── Aggregate summary ──────────────────────────────────────────────────────
    closed_trades = [t for t in trades if t.status == "closed"]
    wins = [t for t in closed_trades if (t.actual_pnl or 0) > 0]
    losses = [t for t in closed_trades if (t.actual_pnl or 0) <= 0]

    by_pair = {}
    for t in closed_trades:
        p = t.instrument
        if p not in by_pair:
            by_pair[p] = {"count": 0, "wins": 0, "losses": 0, "pnl": 0.0}
        by_pair[p]["count"] += 1
        by_pair[p]["pnl"] += (t.actual_pnl or 0)
        if (t.actual_pnl or 0) > 0:
            by_pair[p]["wins"] += 1
        else:
            by_pair[p]["losses"] += 1

    by_exit_reason = {}
    for t in closed_trades:
        r = t.exit_reason or "unknown"
        by_exit_reason[r] = by_exit_reason.get(r, 0) + 1

    by_confidence = {}
    for s in signals:
        if s.risk_approved:
            c = s.confidence
            if c not in by_confidence:
                by_confidence[c] = {"signals": 0, "trades": 0, "wins": 0, "pnl": 0.0}
            by_confidence[c]["signals"] += 1

    # Match trades to signal confidence
    sig_by_id = {s.id: s for s in signals}
    for t in closed_trades:
        sig = sig_by_id.get(t.signal_id)
        if sig and sig.confidence in by_confidence:
            by_confidence[sig.confidence]["trades"] += 1
            by_confidence[sig.confidence]["pnl"] += (t.actual_pnl or 0)
            if (t.actual_pnl or 0) > 0:
                by_confidence[sig.confidence]["wins"] = by_confidence[sig.confidence].get("wins", 0) + 1

    win_rate = (len(wins) / len(closed_trades) * 100) if closed_trades else 0
    avg_win = sum((t.actual_pnl or 0) for t in wins) / len(wins) if wins else 0
    avg_loss = sum((t.actual_pnl or 0) for t in losses) / len(losses) if losses else 0
    profit_factor = (
        sum((t.actual_pnl or 0) for t in wins) / abs(sum((t.actual_pnl or 0) for t in losses))
        if losses and sum((t.actual_pnl or 0) for t in losses) != 0 else None
    )
    total_pnl = sum((t.actual_pnl or 0) for t in closed_trades)

    open_trades = [t for t in trades if t.status in ("open", "partial_close")]

    report["summary"] = {
        "total_signals": len(signals),
        "approved_signals": sum(1 for s in signals if s.risk_approved),
        "rejected_signals": sum(1 for s in signals if not s.risk_approved),
        "total_trades": len(trades),
        "open_trades": len(open_trades),
        "closed_trades": len(closed_trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate_pct": round(win_rate, 1),
        "total_pnl_usd": round(total_pnl, 2),
        "avg_win_usd": round(avg_win, 2),
        "avg_loss_usd": round(avg_loss, 2),
        "profit_factor": round(profit_factor, 2) if profit_factor else None,
        "by_pair": {k: {**v, "win_rate": round(v["wins"]/v["count"]*100, 1) if v["count"] else 0,
                        "pnl": round(v["pnl"], 2)} for k, v in by_pair.items()},
        "by_exit_reason": by_exit_reason,
        "by_confidence_bucket": {str(k): v for k, v in by_confidence.items()},
    }

    db.close()

    # Print one big JSON blob the user can copy/paste to me
    print("=" * 78)
    print("  TradeSight Performance Report — paste everything below to Claude")
    print("=" * 78)
    print()
    print(json.dumps(report, indent=2, default=str))
    print()
    print("=" * 78)
    print(f"  {len(signals)} signals  |  {len(trades)} trades  |  {len(closed_trades)} closed")
    print(f"  Win rate: {win_rate:.1f}%  |  Total P&L: ${total_pnl:+.2f}  |  AI cost: ${total_cost:.4f}")
    print("=" * 78)


if __name__ == "__main__":
    main()
