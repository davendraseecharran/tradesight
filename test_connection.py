#!/usr/bin/env python3
"""TradeSight Phase 1 Checkpoint — Verify OANDA + Binance connectivity and indicator computation."""

import asyncio
import sys
from pathlib import Path

# Ensure project root is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from backend.app.services.binance import BinanceClient
from backend.app.services.indicators import compute_indicators, compute_fibonacci_levels
from backend.app.services.oanda import OandaClient


async def test_oanda():
    print("=" * 60)
    print("TEST 1: OANDA API — Fetching 10 EUR_USD H4 candles")
    print("=" * 60)

    async with OandaClient() as client:
        candles = await client.get_candles("EUR_USD", "H4", count=10)

    print(f"Received {len(candles)} candles\n")
    for c in candles:
        print(f"  {c['timestamp']}  O={c['open']:.5f}  H={c['high']:.5f}  L={c['low']:.5f}  C={c['close']:.5f}  V={c['volume']}")

    # Compute indicators (need more data for meaningful values)
    print("\n--- Fetching 200 candles for indicator computation ---")
    async with OandaClient() as client:
        candles_200 = await client.get_candles("EUR_USD", "H4", count=200)

    df = pd.DataFrame(candles_200)
    df = compute_indicators(df, timeframe="4H")
    last = df.iloc[-1]

    print(f"\nLatest indicators for EUR_USD (H4):")
    print(f"  RSI(14):       {last.get('rsi_14', 'N/A'):.2f}" if pd.notna(last.get("rsi_14")) else "  RSI(14):       N/A")
    print(f"  MACD line:     {last.get('macd_line', 'N/A'):.6f}" if pd.notna(last.get("macd_line")) else "  MACD line:     N/A")
    print(f"  MACD signal:   {last.get('macd_signal', 'N/A'):.6f}" if pd.notna(last.get("macd_signal")) else "  MACD signal:   N/A")
    print(f"  MACD hist:     {last.get('macd_histogram', 'N/A'):.6f}" if pd.notna(last.get("macd_histogram")) else "  MACD hist:     N/A")
    print(f"  EMA(20):       {last.get('ema_20', 'N/A'):.5f}" if pd.notna(last.get("ema_20")) else "  EMA(20):       N/A")
    print(f"  EMA(50):       {last.get('ema_50', 'N/A'):.5f}" if pd.notna(last.get("ema_50")) else "  EMA(50):       N/A")
    print(f"  EMA(200):      {last.get('ema_200', 'N/A'):.5f}" if pd.notna(last.get("ema_200")) else "  EMA(200):      N/A")
    print(f"  BB Upper:      {last.get('bb_upper', 'N/A'):.5f}" if pd.notna(last.get("bb_upper")) else "  BB Upper:      N/A")
    print(f"  BB Lower:      {last.get('bb_lower', 'N/A'):.5f}" if pd.notna(last.get("bb_lower")) else "  BB Lower:      N/A")
    print(f"  ATR(14):       {last.get('atr_14', 'N/A'):.5f}" if pd.notna(last.get("atr_14")) else "  ATR(14):       N/A")

    # Fibonacci
    fib = compute_fibonacci_levels(df, lookback=100)
    print(f"\nFibonacci Retracement Levels:")
    for k, v in fib.items():
        print(f"  {k}: {v:.5f}")

    # Account summary
    print("\n--- Account Summary ---")
    async with OandaClient() as client:
        account = await client.get_account_summary()
    print(f"  Balance:    {account.get('balance', 'N/A')}")
    print(f"  Unrealized: {account.get('unrealizedPL', 'N/A')}")
    print(f"  NAV:        {account.get('NAV', 'N/A')}")

    print("\nOANDA test PASSED")


async def test_binance():
    print("\n" + "=" * 60)
    print("TEST 2: Binance API — Fetching 10 BTCUSDT 4h candles")
    print("=" * 60)

    async with BinanceClient() as client:
        candles = await client.get_klines("BTCUSDT", "4h", limit=10)

    print(f"Received {len(candles)} candles\n")
    for c in candles:
        print(f"  {c['timestamp']}  O={c['open']:.2f}  H={c['high']:.2f}  L={c['low']:.2f}  C={c['close']:.2f}  V={c['volume']:.2f}")

    # Compute indicators
    print("\n--- Fetching 200 candles for indicator computation ---")
    async with BinanceClient() as client:
        candles_200 = await client.get_klines("BTCUSDT", "4h", limit=200)

    df = pd.DataFrame(candles_200)
    df = compute_indicators(df, timeframe="4H")
    last = df.iloc[-1]

    print(f"\nLatest indicators for BTCUSDT (4H):")
    print(f"  RSI(14):       {last.get('rsi_14', 'N/A'):.2f}" if pd.notna(last.get("rsi_14")) else "  RSI(14):       N/A")
    print(f"  MACD line:     {last.get('macd_line', 'N/A'):.2f}" if pd.notna(last.get("macd_line")) else "  MACD line:     N/A")
    print(f"  MACD signal:   {last.get('macd_signal', 'N/A'):.2f}" if pd.notna(last.get("macd_signal")) else "  MACD signal:   N/A")
    print(f"  EMA(20):       {last.get('ema_20', 'N/A'):.2f}" if pd.notna(last.get("ema_20")) else "  EMA(20):       N/A")
    print(f"  ATR(14):       {last.get('atr_14', 'N/A'):.2f}" if pd.notna(last.get("atr_14")) else "  ATR(14):       N/A")

    print("\nBinance test PASSED")


async def main():
    print("TradeSight Phase 1 — Connection & Indicator Test")
    print("=" * 60)

    try:
        await test_oanda()
    except Exception as e:
        print(f"\nOANDA test FAILED: {e}")

    try:
        await test_binance()
    except Exception as e:
        print(f"\nBinance test FAILED: {e}")

    print("\n" + "=" * 60)
    print("All tests complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
