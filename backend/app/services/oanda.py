from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import httpx
from dateutil.parser import isoparse

from backend.app.config import get_settings


class OandaAPIError(Exception):
    pass


def _parse_candle(raw: dict) -> dict:
    """Parse an OANDA candle into a flat OHLCV dict."""
    mid = raw["mid"]
    # OANDA timestamps have nanosecond precision — isoparse handles them
    ts = isoparse(raw["time"])
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return {
        "timestamp": ts,
        "open": float(mid["o"]),
        "high": float(mid["h"]),
        "low": float(mid["l"]),
        "close": float(mid["c"]),
        "volume": float(raw["volume"]),
        "complete": raw["complete"],
    }


class OandaClient:
    def __init__(self, settings=None):
        s = settings or get_settings()
        self._base_url = s.oanda_api_url
        self._account_id = s.oanda_account_id
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {s.oanda_api_token}"},
            timeout=30.0,
        )

    async def get_candles(
        self,
        instrument: str,
        granularity: str = "H4",
        count: int = 500,
        from_time: Optional[str] = None,
        to_time: Optional[str] = None,
    ) -> list[dict]:
        params: dict = {
            "granularity": granularity,
            "price": "M",
        }
        if from_time and to_time:
            params["from"] = from_time
            params["to"] = to_time
        else:
            params["count"] = min(count, 5000)

        resp = await self._client.get(
            f"/v3/instruments/{instrument}/candles",
            params=params,
        )
        if resp.status_code != 200:
            raise OandaAPIError(f"OANDA {resp.status_code}: {resp.text}")

        data = resp.json()
        return [_parse_candle(c) for c in data.get("candles", [])]

    async def get_account_summary(self) -> dict:
        resp = await self._client.get(f"/v3/accounts/{self._account_id}/summary")
        if resp.status_code != 200:
            raise OandaAPIError(f"OANDA {resp.status_code}: {resp.text}")
        return resp.json().get("account", {})

    async def get_open_positions(self) -> list[dict]:
        resp = await self._client.get(f"/v3/accounts/{self._account_id}/openPositions")
        if resp.status_code != 200:
            raise OandaAPIError(f"OANDA {resp.status_code}: {resp.text}")
        positions = resp.json().get("positions", [])
        result = []
        for p in positions:
            long_units = float(p.get("long", {}).get("units", 0))
            short_units = float(p.get("short", {}).get("units", 0))
            units = long_units if long_units != 0 else short_units
            side = "long" if long_units != 0 else "short"
            pl = float(p.get("unrealizedPL", 0))
            result.append({
                "instrument": p.get("instrument"),
                "side": side,
                "units": abs(units),
                "unrealized_pl": pl,
                "avg_price": float(p.get(side, {}).get("averagePrice", 0)),
            })
        return result

    async def close(self):
        await self._client.aclose()

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        await self.close()
