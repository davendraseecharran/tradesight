#!/usr/bin/env python3
"""
TradeSight — System Validation (Pre-Flight Check)
Runs all system checks without making AI calls.

Usage:  .venv/bin/python validate_system.py
   or:  source .venv/bin/activate && python validate_system.py
"""
import asyncio
import subprocess
import sys
import os

# Auto-detect and relaunch with venv Python if running under system Python
venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
if os.path.exists(venv_python) and os.path.realpath(sys.executable) != os.path.realpath(venv_python):
    os.execv(venv_python, [venv_python] + sys.argv)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for key in ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"]:
    os.environ.pop(key, None)

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"

results = {"passed": 0, "failed": 0}
PROJECT = os.path.dirname(os.path.abspath(__file__))


def check(name, ok, detail=""):
    if ok:
        print(f"  {PASS} {name}")
        results["passed"] += 1
    else:
        print(f"  {FAIL} {name}{' — ' + detail if detail else ''}")
        results["failed"] += 1


async def main():
    print("=" * 60)
    print("  TradeSight — Pre-Flight System Validation")
    print("=" * 60)

    # ── Check 1: .env file ──────────────────────────────────────
    print("\n[1] Environment Configuration")
    env_path = os.path.join(PROJECT, ".env")
    check(".env file exists", os.path.exists(env_path))

    from backend.app.config import get_settings
    get_settings.cache_clear()
    try:
        s = get_settings()
        check("OANDA_API_TOKEN set", len(s.oanda_api_token) > 10)
        check("OANDA_ACCOUNT_ID set", "-" in s.oanda_account_id)
        check("OANDA_API_URL set", "oanda.com" in s.oanda_api_url)
        check("ANTHROPIC_API_KEY set", len(s.anthropic_api_key) > 10)
        check("EXECUTION_MODE valid", s.execution_mode in ("ALERT_ONLY", "SEMI_AUTO", "FULL_AUTO"))
        print(f"      Mode: {s.execution_mode}")
    except Exception as e:
        check("Config loads", False, str(e))
        s = None

    # ── Check 2: OANDA API connection ───────────────────────────
    print("\n[2] OANDA API Connection")
    try:
        from backend.app.services.oanda import OandaClient
        async with OandaClient() as client:
            acct = await client.get_account_summary()
            balance = float(acct.get("balance", 0))
            check("OANDA API responds", True)
            check(f"Account balance > $0", balance > 0, f"Balance: ${balance:,.2f}")
            print(f"      Account: {acct.get('id')}")
            print(f"      Balance: ${balance:,.2f} {acct.get('currency', '')}")
    except Exception as e:
        check("OANDA API connection", False, str(e))

    # ── Check 3: SMTP Configuration ────────────────────────────
    print("\n[3] SMTP / Email Configuration")
    if s:
        check("SMTP host configured", bool(s.smtp_host))
        check("SMTP username set", bool(s.smtp_username))
        check("SMTP password set", bool(s.smtp_password))
        check("Alert email set", bool(s.alert_email_to))
        if s.smtp_username:
            print(f"      From: {s.smtp_username}")
            print(f"      To:   {s.alert_email_to}")
    else:
        check("SMTP config", False, "settings failed to load")

    # ── Check 4: Database ──────────────────────────────────────
    print("\n[4] Database")
    db_path = os.path.join(PROJECT, "tradesight.db")
    check("SQLite database exists", os.path.exists(db_path))

    try:
        from backend.app.database import engine
        from sqlalchemy import text, inspect
        insp = inspect(engine)
        tables = insp.get_table_names()
        required = ["candles", "signals", "trades", "news_events", "api_calls"]
        for t in required:
            check(f"Table '{t}' exists", t in tables)
    except Exception as e:
        check("Database tables", False, str(e))

    # ── Check 5: Historical candle data ─────────────────────────
    print("\n[5] Historical Candle Data")
    try:
        with engine.connect() as conn:
            result = conn.execute(text("SELECT COUNT(*) FROM candles"))
            total = result.scalar()
            check(f"Candle data exists ({total:,} rows)", total > 100)

            result = conn.execute(text(
                "SELECT instrument, COUNT(*) as cnt FROM candles GROUP BY instrument ORDER BY instrument"
            ))
            pairs_in_db = []
            for row in result:
                pairs_in_db.append(row[0])
                print(f"      {row[0]}: {row[1]:,} candles")

            check("At least 4 pairs have data", len(pairs_in_db) >= 4)
    except Exception as e:
        check("Candle data query", False, str(e))

    # ── Check 6: Frontend ──────────────────────────────────────
    print("\n[6] Frontend")
    fe = os.path.join(PROJECT, "frontend")
    check("frontend/package.json exists", os.path.exists(os.path.join(fe, "package.json")))
    check("frontend/node_modules exists", os.path.isdir(os.path.join(fe, "node_modules")))
    check("frontend/src/App.jsx exists", os.path.exists(os.path.join(fe, "src", "App.jsx")))

    # ── Check 7: Deployment Scripts ────────────────────────────
    print("\n[7] Deployment Scripts")
    scripts = ["scripts/start.sh", "scripts/stop.sh", "scripts/watchdog.sh"]
    for s_path in scripts:
        full = os.path.join(PROJECT, s_path)
        exists = os.path.exists(full)
        check(f"{s_path} exists", exists)
        if exists:
            check(f"{s_path} executable", os.access(full, os.X_OK))

    check("LaunchAgent plist exists",
          os.path.exists(os.path.join(PROJECT, "scripts", "com.tradesight.watchdog.plist")))

    # ── Verdict ────────────────────────────────────────────────
    total = results["passed"] + results["failed"]
    print("\n" + "=" * 60)
    print(f"  Results: {results['passed']}/{total} passed, {results['failed']} failed")
    if results["failed"] == 0:
        print(f"\n  {PASS} READY FOR LIVE TRADING")
    else:
        print(f"\n  {FAIL} NOT READY — fix the items above")
    print("=" * 60)

    return results["failed"] == 0


if __name__ == "__main__":
    ok = asyncio.run(main())
    sys.exit(0 if ok else 1)
