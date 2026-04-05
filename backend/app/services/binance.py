from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import httpx

from backend.app.config import get_settings


class BinanceAPIError(Exception):
    pass


def _parse_kline(raw: list) -> dict:
    """Parse a Binance kline array into a flat OHLCV dict."""
    return {
        "timestamp": datetime.fromtimestamp(raw[0] / 1000, tz=timezone.utc),
        "open": float(raw[1]),
        "high": float(raw[2]),
        "low": float(raw[3]),
        "close": float(raw[4]),
        "volume": float(raw[5]),
        "complete": True,  # Binance only returns complete klines by default
    }


class BinanceClient:
    def __init__(self, settings=None):
        s = settings or get_settings()
        self._client = httpx.AsyncClient(
            base_url=s.binance_base_url,
            timeout=30.0,
        )

    async def get_klines(
        self,
        symbol: str,
        interval: str = "4h",
        limit: int = 500,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> list[dict]:
        params: dict = {
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, 1000),
        }
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        resp = await self._client.get("/api/v3/klines", params=params)
        if resp.status_code != 200:
            raise BinanceAPIError(f"Binance {resp.status_code}: {resp.text}")

        return [_parse_kline(k) for k in resp.json()]

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
