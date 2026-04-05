"""
TradeSight — Historical Data Refresh
Clears old candle data and re-fetches from OANDA for all pairs x timeframes.
Uses OANDA API directly (no AI calls, free to run).
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for key in ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"]:
    os.environ.pop(key, None)

from backend.app.config import get_settings, FOREX_PAIRS, TIMEFRAMES
get_settings.cache_clear()


async def main():
    print("=" * 55)
    print("  TradeSight — Historical Data Refresh")
    print("=" * 55)

    from backend.app.database import init_db, SessionLocal, engine
    from backend.app.models.candle import Candle
    from sqlalchemy import text

    init_db()

    # Step 1: Clear existing candle data
    print("\n[1] Clearing existing candle data...")
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM candles"))
        old_count = result.scalar()
        conn.execute(text("DELETE FROM candles"))
        conn.commit()
    print(f"  Deleted {old_count} old candles")

    # Step 2: Re-fetch all pairs x timeframes
    print(f"\n[2] Fetching historical data...")
    print(f"  Pairs: {', '.join(FOREX_PAIRS)}")
    print(f"  Timeframes: {', '.join(TIMEFRAMES)}")
    print(f"  Total combinations: {len(FOREX_PAIRS) * len(TIMEFRAMES)}")
    print()

    from backend.app.services.historical import fetch_all_historical

    try:
        results = await fetch_all_historical(
            pairs=FOREX_PAIRS,
            timeframes=TIMEFRAMES,
            months=6,
        )
    except Exception as e:
        print(f"\n✗ Fetch failed: {e}")
        sys.exit(1)

    # Step 3: Summary
    total = sum(results.values())
    print(f"\n{'─' * 40}")
    print(f"  Total candles loaded: {total:,}")
    print(f"  Breakdown:")
    for key, count in sorted(results.items()):
        print(f"    {key}: {count:,}")

    # Verify in DB
    with engine.connect() as conn:
        result = conn.execute(text("SELECT COUNT(*) FROM candles"))
        db_count = result.scalar()
    print(f"\n  Verified in database: {db_count:,} candles")

    print(f"\n{'=' * 55}")
    print(f"  ✓ Historical data refresh complete")
    print(f"{'=' * 55}")


if __name__ == "__main__":
    asyncio.run(main())
