from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


# --- Candle ---

class CandleResponse(BaseModel):
    instrument: str
    source: str
    granularity: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    complete: bool

    class Config:
        from_attributes = True


# --- Indicators ---

class IndicatorResponse(BaseModel):
    rsi_14: Optional[float] = None
    macd_line: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    ema_20: Optional[float] = None
    ema_50: Optional[float] = None
    ema_200: Optional[float] = None
    bb_upper: Optional[float] = None
    bb_middle: Optional[float] = None
    bb_lower: Optional[float] = None
    atr_14: Optional[float] = None
    vwap: Optional[float] = None
    ichimoku_tenkan: Optional[float] = None
    ichimoku_kijun: Optional[float] = None
    ichimoku_senkou_a: Optional[float] = None
    ichimoku_senkou_b: Optional[float] = None

    class Config:
        from_attributes = True


class CandleWithIndicators(BaseModel):
    candle: CandleResponse
    indicators: Optional[IndicatorResponse] = None


# --- Analysis ---

class AnalysisResponse(BaseModel):
    instrument: str
    timeframe: str
    bias: Optional[str] = None
    confidence: Optional[int] = None
    key_levels: Optional[dict] = None
    entry_suggestion: Optional[dict] = None
    stop_loss_suggestion: Optional[float] = None
    take_profit_suggestion: Optional[float] = None
    reasoning: Optional[str] = None
    risk_warning: str = "This is educational analysis, not financial advice."
    raw_response: Optional[str] = None


# --- Risk ---

class RiskValidationRequest(BaseModel):
    instrument: str
    entry_price: float
    stop_loss: float
    take_profit: float
    account_balance: float
    starting_balance: Optional[float] = None  # defaults to account_balance


class RiskValidationResponse(BaseModel):
    approved: bool
    position_size: float
    risk_amount: float
    risk_reward_ratio: float
    rejection_reasons: List[str]


# --- Phase 3: Signals ---

class SignalResponse(BaseModel):
    id: int
    instrument: str
    direction: Optional[str] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit_1: Optional[float] = None
    take_profit_2: Optional[float] = None
    confidence: int
    session: Optional[str] = None
    position_size: Optional[float] = None
    risk_amount: Optional[float] = None
    risk_reward_ratio: Optional[float] = None
    risk_approved: bool
    rejection_reasons: List[str] = []
    status: str
    is_news_blackout: bool
    reasoning: Optional[str] = None
    screener_reason: Optional[str] = None
    created_at: Optional[datetime] = None

    execution_status: Optional[str] = None
    trade_id: Optional[int] = None

    class Config:
        from_attributes = True


# --- Phase 5: Trades ---

class TradeResponse(BaseModel):
    id: int
    signal_id: Optional[int] = None
    oanda_trade_id: Optional[str] = None
    instrument: str
    direction: Optional[str] = None
    entry_price: Optional[float] = None
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None
    units: Optional[float] = None
    position_size: Optional[float] = None
    risk_amount: Optional[float] = None
    status: str
    exit_reason: Optional[str] = None
    actual_exit_price: Optional[float] = None
    actual_pnl: Optional[float] = None
    slippage: Optional[float] = None
    breakeven_applied: bool = False
    trailing_stop_applied: bool = False
    partial_close_done: bool = False
    opened_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# --- Phase 3: Token Usage ---

class AgentUsage(BaseModel):
    cost_usd: float


class TokenUsageResponse(BaseModel):
    daily_cost_usd: float
    weekly_cost_usd: float
    monthly_cost_usd: float
    by_agent_today: dict
    total_calls_today: int
    total_calls_month: int
    budget: dict


# --- Phase 3: News Events ---

class NewsEventResponse(BaseModel):
    id: int
    event: str
    currency: str
    impact: str
    event_datetime: Optional[datetime] = None
    blackout_start: Optional[datetime] = None
    blackout_end: Optional[datetime] = None
    source: Optional[str] = None
    fetched_at: Optional[datetime] = None

    class Config:
        from_attributes = True
