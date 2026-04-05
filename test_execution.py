"""
TradeSight Phase 5 — Execution Test Script

Tests execution engine, OANDA connectivity, order placement, trade lifecycle,
and deployment readiness. Does NOT call any AI/Anthropic endpoints.

Usage:
    python test_execution.py
"""

import asyncio
import sys
import os

# Ensure project root is in path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"

results = {"passed": 0, "failed": 0, "warnings": 0}


def check(name, condition, msg=""):
    if condition:
        print(f"  {PASS} {name}")
        results["passed"] += 1
    else:
        print(f"  {FAIL} {name} — {msg}")
        results["failed"] += 1


def warn(name, msg):
    print(f"  {WARN} {name} — {msg}")
    results["warnings"] += 1


# ── 1. Config & Environment ─────────────────────────────────────────────────

def test_config():
    print("\n[1] Configuration & Environment")
    try:
        from backend.app.config import get_settings, FOREX_PAIRS
        settings = get_settings()

        check("OANDA token loaded", len(settings.oanda_api_token) > 10)
        check("OANDA account ID loaded", "-" in settings.oanda_account_id)
        check("OANDA practice URL", "fxpractice" in settings.oanda_api_url)
        if len(settings.anthropic_api_key) > 10:
            check("Anthropic key loaded", True)
        else:
            warn("Anthropic key", "not set (needed for AI pipeline, not for execution tests)")
        check("Execution mode valid", settings.execution_mode in ("ALERT_ONLY", "SEMI_AUTO", "FULL_AUTO"))
        check("Forex pairs defined", len(FOREX_PAIRS) >= 6)
        check("Risk per trade <= 5%", settings.max_risk_per_trade <= 0.05)
        check("Max positions > 0", settings.max_open_positions > 0)
    except Exception as e:
        check("Config loads without error", False, str(e))


# ── 2. Database & Models ────────────────────────────────────────────────────

def test_database():
    print("\n[2] Database & Models")
    try:
        from backend.app.database import init_db, SessionLocal
        init_db()
        check("Database initialized", True)

        db = SessionLocal()
        check("Session created", db is not None)

        from backend.app.models.trade import Trade
        from backend.app.models.signal import Signal

        # Verify trade model has Phase 5 columns
        trade_cols = [c.name for c in Trade.__table__.columns]
        check("Trade.oanda_trade_id exists", "oanda_trade_id" in trade_cols)
        check("Trade.breakeven_applied exists", "breakeven_applied" in trade_cols)
        check("Trade.trailing_stop_applied exists", "trailing_stop_applied" in trade_cols)
        check("Trade.partial_close_done exists", "partial_close_done" in trade_cols)
        check("Trade.exit_reason exists", "exit_reason" in trade_cols)
        check("Trade.slippage exists", "slippage" in trade_cols)
        check("Trade.account_balance_at_open exists", "account_balance_at_open" in trade_cols)

        # Verify signal model has execution columns
        signal_cols = [c.name for c in Signal.__table__.columns]
        check("Signal.execution_status exists", "execution_status" in signal_cols)
        check("Signal.trade_id exists", "trade_id" in signal_cols)
        check("Signal.approved_at exists", "approved_at" in signal_cols)

        db.close()
    except Exception as e:
        check("Database test", False, str(e))


# ── 3. Order Manager (unit conversion & init) ───────────────────────────────

def test_order_manager_units():
    print("\n[3] Order Manager — Unit Conversion")
    try:
        from backend.app.services.order_manager import lots_to_units, units_to_lots, OrderManager

        check("0.01 lots = 1,000 units", lots_to_units(0.01) == 1000)
        check("0.1 lots = 10,000 units", lots_to_units(0.1) == 10000)
        check("1.0 lot = 100,000 units", lots_to_units(1.0) == 100000)
        check("1,000 units = 0.01 lots", abs(units_to_lots(1000) - 0.01) < 0.0001)

        mgr = OrderManager()
        check("OrderManager instantiates", mgr is not None)
    except Exception as e:
        check("Order Manager test", False, str(e))


# ── 4. OANDA API Connectivity ───────────────────────────────────────────────

async def test_oanda_connectivity():
    print("\n[4] OANDA API Connectivity")
    try:
        from backend.app.services.order_manager import OrderManager
        mgr = OrderManager()

        # Account summary
        acct = await mgr.get_account_summary()
        check("Account summary fetched", acct is not None)
        check("Balance > 0", float(acct.get("balance", 0)) > 0)
        check("Currency is USD", acct.get("currency") == "USD")
        print(f"      Balance: ${acct.get('balance', '?')}")
        print(f"      Open trades: {acct.get('open_trade_count', '?')}")

        # Open trades
        trades = await mgr.get_open_trades()
        check("Open trades fetched", isinstance(trades, list))
        print(f"      Currently open: {len(trades)}")

        # Trade history
        history = await mgr.get_trade_history(5)
        check("Trade history fetched", isinstance(history, list))
        print(f"      Recent trades: {len(history)}")

    except Exception as e:
        check("OANDA connectivity", False, str(e))


# ── 5. Trade Lifecycle Manager ───────────────────────────────────────────────

async def test_trade_manager():
    print("\n[5] Trade Lifecycle Manager")
    try:
        from backend.app.services.trade_manager import TradeManager
        from backend.app.database import SessionLocal

        db = SessionLocal()
        mgr = TradeManager(db)
        check("TradeManager instantiates", mgr is not None)

        # Run lifecycle check (should work even with 0 trades)
        result = await mgr.check_and_manage_trades()
        check("Lifecycle check runs", isinstance(result, dict))
        check("Result has expected keys",
              all(k in result for k in ["checked", "breakeven_applied", "trailing_applied", "partial_closes", "closed"]))
        print(f"      Checked: {result['checked']} trades")

        db.close()
    except Exception as e:
        check("Trade Manager test", False, str(e))


# ── 6. API Routes ───────────────────────────────────────────────────────────

async def test_api_routes():
    print("\n[6] API Routes")
    try:
        import httpx
        base = "http://localhost:8000"

        async with httpx.AsyncClient(timeout=10) as client:
            # Health
            r = await client.get(f"{base}/health")
            check("GET /health → 200", r.status_code == 200)
            health = r.json()
            check("Health has version", "version" in health)
            print(f"      Version: {health.get('version')}")
            print(f"      Market: {'OPEN' if health.get('market_open') else 'CLOSED'}")

            # Open trades
            r = await client.get(f"{base}/api/v1/trade/open")
            check("GET /api/v1/trade/open → 200", r.status_code == 200)

            # Trade history
            r = await client.get(f"{base}/api/v1/trade/history")
            check("GET /api/v1/trade/history → 200", r.status_code == 200)

            # Signals
            r = await client.get(f"{base}/api/v1/signals/")
            check("GET /api/v1/signals/ → 200", r.status_code == 200)

            # Account summary
            r = await client.get(f"{base}/api/v1/account/summary")
            check("GET /api/v1/account/summary → 200", r.status_code == 200)

            # News calendar
            r = await client.get(f"{base}/api/v1/news/calendar")
            check("GET /api/v1/news/calendar → 200", r.status_code == 200)

    except httpx.ConnectError:
        warn("API routes", "Backend not running on localhost:8000. Start with ./scripts/start.sh")
    except Exception as e:
        check("API routes test", False, str(e))


# ── 7. Scheduler ────────────────────────────────────────────────────────────

def test_scheduler():
    print("\n[7] Scheduler")
    try:
        from backend.app.scheduler import create_scheduler, is_market_open, get_market_status

        status = get_market_status()
        check("Market status works", "is_open" in status)
        print(f"      Market: {'OPEN' if status['is_open'] else 'CLOSED'}")
        print(f"      Time (ET): {status['current_time_et']}")

        sched = create_scheduler()
        jobs = sched.get_jobs()
        job_ids = [j.id for j in jobs]
        check("Pipeline job registered", "pipeline" in job_ids)
        check("News sentinel (AM) registered", "news_sentinel_morning" in job_ids)
        check("News sentinel (PM) registered", "news_sentinel_afternoon" in job_ids)
        check("Trade lifecycle job registered", "trade_lifecycle" in job_ids)
        print(f"      Total jobs: {len(jobs)}")

    except Exception as e:
        check("Scheduler test", False, str(e))


# ── 8. Deployment Files ─────────────────────────────────────────────────────

def test_deployment_files():
    print("\n[8] Deployment Files")
    project_root = os.path.dirname(os.path.abspath(__file__))

    files = {
        "scripts/start.sh": True,
        "scripts/stop.sh": True,
        "scripts/watchdog.sh": True,
        "scripts/com.tradesight.watchdog.plist": False,
        ".env.example": False,
        "requirements.txt": False,
        "README.md": False,
    }

    for f, executable in files.items():
        path = os.path.join(project_root, f)
        exists = os.path.exists(path)
        check(f"{f} exists", exists)
        if executable and exists:
            is_exec = os.access(path, os.X_OK)
            check(f"{f} is executable", is_exec)


# ── 9. Frontend Build Check ─────────────────────────────────────────────────

def test_frontend():
    print("\n[9] Frontend")
    project_root = os.path.dirname(os.path.abspath(__file__))
    fe_dir = os.path.join(project_root, "frontend")

    check("frontend/package.json exists", os.path.exists(os.path.join(fe_dir, "package.json")))
    check("frontend/node_modules exists", os.path.isdir(os.path.join(fe_dir, "node_modules")))

    # Check key files were updated
    api_js = os.path.join(fe_dir, "src", "utils", "api.js")
    if os.path.exists(api_js):
        with open(api_js) as f:
            content = f.read()
        check("api.js has openTrades endpoint", "openTrades" in content)
        check("api.js has approveSignal endpoint", "approveSignal" in content)
        check("api.js has closeTrade endpoint", "closeTrade" in content)

    signal_card = os.path.join(fe_dir, "src", "components", "SignalCard.jsx")
    if os.path.exists(signal_card):
        with open(signal_card) as f:
            content = f.read()
        check("SignalCard has approve button", "Approve" in content)
        check("SignalCard has ConfirmModal", "ConfirmModal" in content)

    portfolio = os.path.join(fe_dir, "src", "pages", "Portfolio.jsx")
    if os.path.exists(portfolio):
        with open(portfolio) as f:
            content = f.read()
        check("Portfolio has trade history", "tradeHistory" in content or "Trade History" in content)
        check("Portfolio has equity curve", "Equity Curve" in content)
        check("Portfolio has close button", "CloseTradeBadge" in content or "Close" in content)


# ── Run All ──────────────────────────────────────────────────────────────────

async def main():
    print("=" * 60)
    print("  TradeSight Phase 5 — Execution Test Suite")
    print("  (No AI/Anthropic calls — safe for offline testing)")
    print("=" * 60)

    test_config()
    test_database()
    test_order_manager_units()
    await test_oanda_connectivity()
    await test_trade_manager()
    await test_api_routes()
    test_scheduler()
    test_deployment_files()
    test_frontend()

    print("\n" + "=" * 60)
    total = results["passed"] + results["failed"]
    print(f"  Results: {results['passed']}/{total} passed, "
          f"{results['failed']} failed, {results['warnings']} warnings")
    print("=" * 60)

    if results["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
