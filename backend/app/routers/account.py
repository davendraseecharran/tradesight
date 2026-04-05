from __future__ import annotations

from fastapi import APIRouter, HTTPException

from backend.app.services.oanda import OandaClient, OandaAPIError

router = APIRouter(prefix="/api/v1/account", tags=["account"])


@router.get("/summary")
async def get_account_summary():
    """Fetch live OANDA account summary (balance, equity, margin, unrealized P&L)."""
    try:
        async with OandaClient() as client:
            data = await client.get_account_summary()
        return {
            "balance": float(data.get("balance", 0)),
            "equity": float(data.get("NAV", data.get("balance", 0))),
            "unrealized_pl": float(data.get("unrealizedPL", 0)),
            "margin_used": float(data.get("marginUsed", 0)),
            "margin_available": float(data.get("marginAvailable", 0)),
            "open_trade_count": int(data.get("openTradeCount", 0)),
            "currency": data.get("currency", "USD"),
        }
    except OandaAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))


@router.get("/positions")
async def get_open_positions():
    """Fetch open positions from OANDA."""
    try:
        async with OandaClient() as client:
            data = await client.get_open_positions()
        return data
    except OandaAPIError as exc:
        raise HTTPException(status_code=502, detail=str(exc))
