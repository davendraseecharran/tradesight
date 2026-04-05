from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

import httpx

from backend.app.config import get_settings

logger = logging.getLogger(__name__)


class OrderError(Exception):
    pass


def lots_to_units(lots: float) -> int:
    """Convert lots to OANDA units. 1 lot = 100,000 units."""
    return int(round(lots * 100_000))


def units_to_lots(units: float) -> float:
    """Convert OANDA units to lots."""
    return abs(units) / 100_000


class OrderManager:
    """OANDA v20 Order Manager for trade execution on the practice account."""

    def __init__(self, settings=None):
        s = settings or get_settings()
        self._base_url = s.oanda_api_url
        self._account_id = s.oanda_account_id
        self._headers = {"Authorization": f"Bearer {s.oanda_api_token}"}

    async def _request(self, method: str, path: str, json_body: dict | None = None) -> dict:
        async with httpx.AsyncClient(
            base_url=self._base_url, headers=self._headers, timeout=15.0
        ) as client:
            resp = await client.request(method, path, json=json_body)
            data = resp.json()
            if resp.status_code not in (200, 201):
                error_msg = data.get("errorMessage", resp.text)
                raise OrderError(f"OANDA {resp.status_code}: {error_msg}")
            return data

    # ── Place Orders ──────────────────────────────────────────────────────────

    async def place_market_order(
        self,
        instrument: str,
        units: int,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> dict:
        """
        Place a market order on OANDA.

        Args:
            instrument: e.g. "EUR_USD"
            units: positive for BUY, negative for SELL
            stop_loss: stop loss price
            take_profit: take profit price

        Returns:
            Dict with order details and fill info.
        """
        order_body: dict = {
            "type": "MARKET",
            "instrument": instrument,
            "units": str(units),
            "timeInForce": "FOK",  # Fill Or Kill
        }

        if stop_loss is not None:
            order_body["stopLossOnFill"] = {
                "price": f"{stop_loss:.5f}",
                "timeInForce": "GTC",
            }

        if take_profit is not None:
            order_body["takeProfitOnFill"] = {
                "price": f"{take_profit:.5f}",
                "timeInForce": "GTC",
            }

        data = await self._request(
            "POST",
            f"/v3/accounts/{self._account_id}/orders",
            {"order": order_body},
        )

        # Extract fill info
        fill = data.get("orderFillTransaction", {})
        if not fill:
            # Order might have been rejected
            reject = data.get("orderRejectTransaction", {})
            if reject:
                raise OrderError(f"Order rejected: {reject.get('rejectReason', 'unknown')}")
            raise OrderError(f"No fill transaction in response: {data}")

        trade_id = None
        trades_opened = fill.get("tradeOpened", {})
        if trades_opened:
            trade_id = trades_opened.get("tradeID")

        return {
            "order_id": fill.get("orderID"),
            "trade_id": trade_id,
            "instrument": fill.get("instrument", instrument),
            "units": int(float(fill.get("units", units))),
            "price": float(fill.get("price", 0)),
            "pl": float(fill.get("pl", 0)),
            "time": fill.get("time"),
        }

    async def place_trade_from_signal(
        self,
        instrument: str,
        direction: str,
        lots: float,
        stop_loss: float,
        take_profit: float,
    ) -> dict:
        """
        Place a trade based on a signal recommendation.

        Args:
            instrument: e.g. "EUR_USD"
            direction: "long" or "short"
            lots: position size in lots (0.01–0.05 for small account)
            stop_loss: stop loss price
            take_profit: take profit price (use TP1)
        """
        units = lots_to_units(lots)
        if direction == "short":
            units = -units

        logger.info(
            "OrderManager: placing %s %s %d units (%.2f lots), SL=%.5f, TP=%.5f",
            direction.upper(), instrument, abs(units), lots, stop_loss, take_profit,
        )

        result = await self.place_market_order(
            instrument=instrument,
            units=units,
            stop_loss=stop_loss,
            take_profit=take_profit,
        )

        logger.info(
            "OrderManager: filled %s @ %.5f, trade_id=%s",
            instrument, result["price"], result["trade_id"],
        )
        return result

    # ── Close Trades ──────────────────────────────────────────────────────────

    async def close_trade(self, trade_id: str, units: Optional[int] = None) -> dict:
        """
        Close a trade (fully or partially).

        Args:
            trade_id: OANDA trade ID
            units: if specified, close only this many units (partial close)
        """
        body = {}
        if units is not None:
            body["units"] = str(abs(units))

        data = await self._request(
            "PUT",
            f"/v3/accounts/{self._account_id}/trades/{trade_id}/close",
            body if body else None,
        )

        close_txn = data.get("orderFillTransaction", {})
        return {
            "trade_id": trade_id,
            "units_closed": int(float(close_txn.get("units", 0))),
            "price": float(close_txn.get("price", 0)),
            "realized_pl": float(close_txn.get("pl", 0)),
            "time": close_txn.get("time"),
        }

    async def close_trade_partial(self, trade_id: str, close_percent: float = 0.5) -> dict:
        """Close a percentage of an open trade (default 50% for TP1 partial)."""
        trade = await self.get_trade(trade_id)
        current_units = abs(int(float(trade.get("currentUnits", 0))))
        close_units = max(1, int(current_units * close_percent))
        return await self.close_trade(trade_id, units=close_units)

    # ── Modify Trades ─────────────────────────────────────────────────────────

    async def modify_trade(
        self,
        trade_id: str,
        stop_loss: Optional[float] = None,
        take_profit: Optional[float] = None,
    ) -> dict:
        """Modify the SL and/or TP of an open trade."""
        body: dict = {}
        if stop_loss is not None:
            body["stopLoss"] = {"price": f"{stop_loss:.5f}", "timeInForce": "GTC"}
        if take_profit is not None:
            body["takeProfit"] = {"price": f"{take_profit:.5f}", "timeInForce": "GTC"}

        if not body:
            raise OrderError("Must specify stop_loss or take_profit to modify")

        data = await self._request(
            "PUT",
            f"/v3/accounts/{self._account_id}/trades/{trade_id}/orders",
            body,
        )
        return {"trade_id": trade_id, "modified": True, "details": data}

    async def move_sl_to_breakeven(self, trade_id: str, entry_price: float) -> dict:
        """Move stop loss to entry price (breakeven)."""
        logger.info("OrderManager: moving SL to breakeven (%.5f) for trade %s", entry_price, trade_id)
        return await self.modify_trade(trade_id, stop_loss=entry_price)

    async def set_trailing_stop(self, trade_id: str, trailing_sl: float) -> dict:
        """Update the stop loss to trail at a specific price."""
        logger.info("OrderManager: trailing SL to %.5f for trade %s", trailing_sl, trade_id)
        return await self.modify_trade(trade_id, stop_loss=trailing_sl)

    # ── Query Trades ──────────────────────────────────────────────────────────

    async def get_trade(self, trade_id: str) -> dict:
        """Get details for a specific trade."""
        data = await self._request("GET", f"/v3/accounts/{self._account_id}/trades/{trade_id}")
        return data.get("trade", {})

    async def get_open_trades(self) -> list[dict]:
        """Get all open trades from OANDA."""
        data = await self._request("GET", f"/v3/accounts/{self._account_id}/openTrades")
        trades = data.get("trades", [])
        return [_parse_trade(t) for t in trades]

    async def get_trade_history(self, count: int = 50) -> list[dict]:
        """Get recently closed trades from OANDA transaction history."""
        data = await self._request(
            "GET",
            f"/v3/accounts/{self._account_id}/trades?state=CLOSED&count={count}",
        )
        trades = data.get("trades", [])
        return [_parse_trade(t) for t in trades]

    async def get_account_summary(self) -> dict:
        """Get account balance, equity, margin info."""
        data = await self._request("GET", f"/v3/accounts/{self._account_id}/summary")
        acct = data.get("account", {})
        return {
            "balance": float(acct.get("balance", 0)),
            "equity": float(acct.get("NAV", 0)),
            "unrealized_pl": float(acct.get("unrealizedPL", 0)),
            "margin_used": float(acct.get("marginUsed", 0)),
            "margin_available": float(acct.get("marginAvailable", 0)),
            "open_trade_count": int(acct.get("openTradeCount", 0)),
            "currency": acct.get("currency", "USD"),
        }


def _parse_trade(raw: dict) -> dict:
    """Parse an OANDA trade object into a clean dict."""
    units = float(raw.get("currentUnits", raw.get("initialUnits", 0)))
    return {
        "trade_id": raw.get("id"),
        "instrument": raw.get("instrument"),
        "direction": "long" if units > 0 else "short",
        "units": abs(int(units)),
        "initial_units": abs(int(float(raw.get("initialUnits", 0)))),
        "entry_price": float(raw.get("price", 0)),
        "unrealized_pl": float(raw.get("unrealizedPL", 0)),
        "realized_pl": float(raw.get("realizedPL", 0)),
        "stop_loss": float(raw.get("stopLossOrder", {}).get("price", 0)) if raw.get("stopLossOrder") else None,
        "take_profit": float(raw.get("takeProfitOrder", {}).get("price", 0)) if raw.get("takeProfitOrder") else None,
        "state": raw.get("state", "OPEN"),
        "open_time": raw.get("openTime"),
        "close_time": raw.get("closeTime"),
    }
