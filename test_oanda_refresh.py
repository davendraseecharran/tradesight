#!/usr/bin/env python3
"""
TradeSight — OANDA Credential Verification
Verifies new OANDA credentials from .env and scans for hardcoded tokens.
"""
import asyncio
import sys
import os
import re

# Auto-detect and relaunch with venv Python if running under system Python
venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
if os.path.exists(venv_python) and sys.executable != os.path.realpath(venv_python):
    os.execv(venv_python, [venv_python] + sys.argv)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for key in ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"]:
    os.environ.pop(key, None)

from backend.app.config import get_settings
get_settings.cache_clear()

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"


async def main():
    print("=" * 55)
    print("  TradeSight — OANDA Credential Verification")
    print("=" * 55)

    settings = get_settings()
    failed = False

    # 1. Show credentials from .env
    print("\n[1] Credentials from .env")
    print(f"  Account ID:  {settings.oanda_account_id}")
    print(f"  API Token:   ***{settings.oanda_api_token[-8:]}")
    print(f"  API URL:     {settings.oanda_api_url}")

    # 2. Connect and fetch account summary
    print("\n[2] OANDA API Connection")
    from backend.app.services.oanda import OandaClient
    try:
        async with OandaClient() as client:
            acct = await client.get_account_summary()
            print(f"  {PASS} Connection successful")
            print(f"  Account ID:   {acct.get('id', '?')}")
            print(f"  Balance:      ${float(acct.get('balance', 0)):,.2f}")
            print(f"  Currency:     {acct.get('currency', '?')}")
            print(f"  Open Trades:  {acct.get('openTradeCount', 0)}")
            print(f"  Margin Rate:  {acct.get('marginRate', '?')}")

            # Verify account ID matches
            if acct.get("id") != settings.oanda_account_id:
                print(f"  {FAIL} Account ID mismatch! API returned {acct.get('id')} but .env has {settings.oanda_account_id}")
                failed = True
            else:
                print(f"  {PASS} Account ID matches .env")

            # 3. Fetch 5 recent EUR/USD candles
            print("\n[3] Data Access — EUR/USD candles")
            candles = await client.get_candles("EUR_USD", "H1", count=5)
            if candles:
                print(f"  {PASS} Fetched {len(candles)} EUR/USD H1 candles")
                for c in candles[-3:]:
                    ts = c["timestamp"].strftime("%Y-%m-%d %H:%M")
                    print(f"      {ts}  O:{c['open']:.5f}  H:{c['high']:.5f}  L:{c['low']:.5f}  C:{c['close']:.5f}")
            else:
                print(f"  {FAIL} No candles returned")
                failed = True

    except Exception as e:
        print(f"  {FAIL} Connection failed: {e}")
        failed = True

    # 4. Scan codebase for hardcoded credentials
    print("\n[4] Codebase Credential Scan")
    project_root = os.path.dirname(os.path.abspath(__file__))

    # Patterns to look for: OANDA account IDs and token-like strings
    patterns = [
        (r"101-001-\d{8}-\d{3}", "OANDA account ID"),
        (r"[0-9a-f]{32}-[0-9a-f]{32}", "OANDA API token pattern"),
    ]

    skip_dirs = {".venv", "venv", "node_modules", ".git", "__pycache__", ".claude"}
    skip_files = {".env", ".env.example", "test_oanda_refresh.py", "test_connection.py"}
    found_issues = []

    for root, dirs, files in os.walk(project_root):
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        for fname in files:
            if fname in skip_files:
                continue
            if not fname.endswith((".py", ".js", ".jsx", ".json", ".sh", ".md", ".txt", ".plist")):
                continue
            fpath = os.path.join(root, fname)
            try:
                with open(fpath, "r", errors="ignore") as f:
                    content = f.read()
                for pat, desc in patterns:
                    matches = re.findall(pat, content)
                    for m in matches:
                        rel = os.path.relpath(fpath, project_root)
                        found_issues.append((rel, desc, m))
            except Exception:
                pass

    if found_issues:
        print(f"  {FAIL} Found {len(found_issues)} potential hardcoded credential(s):")
        for path, desc, val in found_issues:
            print(f"      {path}: {desc} → {val[:12]}...{val[-4:]}")
        failed = True
    else:
        print(f"  {PASS} No hardcoded credentials found in codebase")

    # Summary
    print("\n" + "=" * 55)
    if failed:
        print(f"  {FAIL} Issues found — see above")
    else:
        print(f"  {PASS} All OANDA credential checks passed")
    print("=" * 55)

    return not failed


if __name__ == "__main__":
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
