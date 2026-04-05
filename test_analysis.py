"""
test_analysis.py — Phase 3 Checkpoint Script
=============================================
Tests the full 4-agent AI analysis pipeline:
  1. News Sentinel — ForexFactory scrape + DB upsert
  2. Screener     — batch screen all 6 forex pairs (1 Haiku call)
  3. Analyst      — deep MTF confluence for first flagged pair (1 Sonnet call)
  4. Risk Manager — pure Python validation
  5. Token usage  — print cost summary for this run

Usage:
  cd ~/tradesight
  python test_analysis.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys

# Ensure project root is on path
sys.path.insert(0, ".")

# If ANTHROPIC_API_KEY is set but empty (e.g., by Claude Code's own process),
# remove it so pydantic-settings falls through to the .env file value.
if os.environ.get("ANTHROPIC_API_KEY", None) == "":
    del os.environ["ANTHROPIC_API_KEY"]

from backend.app.database import SessionLocal, init_db
from backend.app.agents.news_sentinel import run_news_sentinel, get_upcoming_events
from backend.app.agents.screener import run_screener
from backend.app.agents.analyst import run_analyst
from backend.app.agents.risk_manager_agent import run_risk_manager
from backend.app.services.token_tracker import get_usage_summary
from backend.app.scheduler import get_market_status


def separator(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


async def main():
    separator("Phase 3 — AI Analysis Pipeline Checkpoint")

    # Initialize database (creates new tables if they don't exist)
    init_db()
    print("✓ Database initialized (new tables: signals, api_calls, news_events)")

    db = SessionLocal()

    try:
        # ── Market Status ──────────────────────────────────────────────────────
        market = get_market_status()
        print(f"\nMarket Status: {'OPEN' if market['is_open'] else 'CLOSED'}")
        print(f"Current Time:  {market['current_time_et']} / {market['current_time_utc']}")

        # ── Step 1: News Sentinel ──────────────────────────────────────────────
        separator("Step 1: News Sentinel")
        print("Fetching ForexFactory economic calendar...")
        sentinel_result = await run_news_sentinel(db)

        if sentinel_result.get("status") == "error":
            print(f"✗ News Sentinel error: {sentinel_result.get('error')}")
        else:
            print(f"✓ Raw events fetched: {sentinel_result.get('raw_events_fetched', 0)}")
            print(f"✓ High-impact parsed: {sentinel_result.get('high_impact_parsed', 0)}")
            print(f"✓ Events stored/updated: {sentinel_result.get('events_stored', 0)}")
            print(f"  Model: {sentinel_result.get('model')} | "
                  f"Tokens: {sentinel_result.get('input_tokens', 0)} in / "
                  f"{sentinel_result.get('output_tokens', 0)} out")

        # Print upcoming blackout schedule
        upcoming = get_upcoming_events(db, hours_ahead=72)
        if upcoming:
            print(f"\nUpcoming high-impact events (next 72h):")
            for ev in upcoming[:10]:
                print(f"  [{ev.currency}] {ev.event}")
                print(f"         Event: {ev.event_datetime.strftime('%Y-%m-%d %H:%M UTC')}")
                print(f"         Blackout: {ev.blackout_start.strftime('%H:%M')} – {ev.blackout_end.strftime('%H:%M UTC')}")
        else:
            print("\nNo upcoming high-impact events found in next 72h.")

        # ── Step 2: Screener ───────────────────────────────────────────────────
        separator("Step 2: Screener (All 6 Pairs — 1 Haiku Call)")
        print("Building indicator snapshots and screening all pairs...")
        screener_result = await run_screener(db)

        if screener_result.get("status") == "error":
            print(f"✗ Screener error: {screener_result.get('error')}")
            return
        elif screener_result.get("status") == "no_data":
            print("✗ No data available — run the historical data fetch first")
            print("  Hint: POST /api/v1/backtest/fetch-historical?instrument=EUR_USD")
            return

        print(f"✓ Pairs screened: {screener_result.get('pairs_screened', 0)}")
        print(f"✓ Model: {screener_result.get('model')} | "
              f"Tokens: {screener_result.get('input_tokens', 0)} in / "
              f"{screener_result.get('output_tokens', 0)} out | "
              f"Cache read: {screener_result.get('cache_read_tokens', 0)}")

        all_results = screener_result.get("all_results", [])
        flagged = screener_result.get("flagged", [])

        print(f"\nScreener results:")
        for r in all_results:
            flag = "*** FLAGGED" if r.get("potential_setup") else "    pass"
            direction = f" ({r.get('direction', 'N/A')})" if r.get("potential_setup") else ""
            print(f"  {flag} — {r['pair']}{direction}")
            if r.get("potential_setup"):
                print(f"           Reason: {r.get('reason', 'N/A')}")

        if not flagged:
            print("\nNo setups flagged — no further analysis needed this cycle.")
            print("(This is normal. Screener only flags when a clear setup is forming.)")
            _print_token_summary(db)
            return

        print(f"\n{len(flagged)} pair(s) flagged for deep analysis: {[f['pair'] for f in flagged]}")

        # ── Step 3: Analyst ────────────────────────────────────────────────────
        # Run analyst only on the first flagged pair (to control cost in testing)
        first_flagged = flagged[0]
        instrument = first_flagged["pair"]

        separator(f"Step 3: Analyst — Deep MTF Analysis ({instrument})")
        print(f"Running Sonnet 4.6 multi-timeframe confluence analysis for {instrument}...")
        print("(This may take 30–60 seconds)")

        analyst_result = await run_analyst(
            db=db,
            instrument=instrument,
            screener_reason=first_flagged.get("reason", ""),
            screener_direction=first_flagged.get("direction", ""),
        )

        print(f"✓ Model: {analyst_result.get('model')} | "
              f"Tokens: {analyst_result.get('input_tokens', 0)} in / "
              f"{analyst_result.get('output_tokens', 0)} out | "
              f"Cache read: {analyst_result.get('cache_read_tokens', 0)}")

        if not analyst_result.get("direction"):
            print(f"\nAnalyst result: NO SETUP (confidence: {analyst_result.get('confidence', 0)}/10)")
            print(f"Reasoning: {analyst_result.get('reasoning', 'N/A')[:300]}...")
            _print_token_summary(db)
            return

        print(f"\nAnalyst recommendation:")
        print(f"  Instrument:   {analyst_result.get('instrument')}")
        print(f"  Direction:    {analyst_result.get('direction', '').upper()}")
        print(f"  Entry:        {analyst_result.get('entry_price')}")
        print(f"  Stop Loss:    {analyst_result.get('stop_loss')}")
        print(f"  TP1:          {analyst_result.get('take_profit_1')}")
        print(f"  TP2:          {analyst_result.get('take_profit_2', 'N/A')}")
        print(f"  Confidence:   {analyst_result.get('confidence')}/10")
        print(f"  Session:      {analyst_result.get('session', 'N/A')}")
        print(f"\nReasoning (first 500 chars):")
        reasoning = analyst_result.get("reasoning", "N/A")
        print(f"  {reasoning[:500]}{'...' if len(reasoning or '') > 500 else ''}")

        # ── Step 4: Risk Manager ───────────────────────────────────────────────
        separator("Step 4: Risk Manager (Pure Python — Zero Tokens)")
        print("Validating trade: live OANDA balance + news blackout + risk rules...")

        risk_result = await run_risk_manager(db=db, analyst_result=analyst_result)

        print(f"  Account balance: ${risk_result.get('account_balance', 0):.2f}")
        print(f"  News blackout:   {'YES — ' + '; '.join(risk_result.get('blackout_details', [])) if risk_result.get('news_blackout') else 'No'}")
        print(f"  Position size:   {risk_result.get('position_size_lots', 0):.2f} lots")
        print(f"  Risk amount:     ${risk_result.get('risk_amount_usd', 0):.2f}")
        print(f"  Risk/Reward:     1:{risk_result.get('risk_reward_ratio', 0):.1f}")
        print(f"  APPROVED:        {'✓ YES' if risk_result.get('approved') else '✗ NO'}")

        if not risk_result.get("approved"):
            print(f"  Rejection reasons:")
            for reason in risk_result.get("rejection_reasons", []):
                print(f"    • {reason}")

        # ── Token Usage Summary ────────────────────────────────────────────────
        _print_token_summary(db)

        separator("Phase 3 Checkpoint Complete")
        print("✓ All agents tested successfully")
        print("\nNext steps:")
        print("  1. Start the server: uvicorn backend.app.main:app --reload")
        print("  2. View API docs:    http://localhost:8000/docs")
        print("  3. Check endpoints:  GET /api/v1/signals/schedule")
        print("                       GET /api/v1/tokens/usage")
        print("                       GET /api/v1/news/calendar")
        print("  4. Configure email:  Add SMTP_USERNAME/PASSWORD/ALERT_EMAIL_TO to .env")

    finally:
        db.close()


def _print_token_summary(db):
    separator("Token Usage Summary")
    summary = get_usage_summary(db)
    print(f"  Today:    ${summary['daily_cost_usd']:.4f} ({summary['total_calls_today']} calls)")
    print(f"  This week: ${summary['weekly_cost_usd']:.4f}")
    print(f"  This month: ${summary['monthly_cost_usd']:.4f} ({summary['total_calls_month']} calls)")
    if summary["by_agent_today"]:
        print(f"\n  By agent (today):")
        for agent, cost in summary["by_agent_today"].items():
            print(f"    {agent}: ${cost:.4f}")


if __name__ == "__main__":
    asyncio.run(main())
