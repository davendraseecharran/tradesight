from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env from project root (two levels up from this file)
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_ENV_FILE),
        env_file_encoding="utf-8",
    )

    # OANDA
    oanda_api_token: str
    oanda_account_id: str
    oanda_api_url: str = "https://api-fxpractice.oanda.com"

    # Binance (optional for Phase 1)
    binance_api_key: str = ""
    binance_api_secret: str = ""
    binance_base_url: str = "https://api.binance.us"

    # Anthropic
    anthropic_api_key: str

    # Database
    database_url: str = "sqlite:///./tradesight.db"

    # Risk management — calibrated for both $1K real and $100K paper accounts.
    # Position size is computed dynamically as: balance × max_risk_per_trade ÷
    # stop distance, then clamped to a per-account lot ceiling in
    # risk_manager_agent.py. R:R 2.5 and confidence 7 keep quality high.
    max_risk_per_trade: float = 0.02       # 2% of balance per trade
    daily_loss_limit: float = 0.03         # tightened from 5% — circuit breaker
    max_open_positions: int = 2            # quality over quantity
    min_risk_reward_ratio: float = 2.5     # raised from 2.0
    news_blackout_minutes: int = 30

    # Email / SMTP
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    alert_email_to: str = ""

    # Execution mode
    execution_mode: str = "ALERT_ONLY"  # ALERT_ONLY | SEMI_AUTO | FULL_AUTO

    # Token budgets
    daily_token_budget_usd: float = 2.0
    monthly_token_budget_usd: float = 20.0

    # Agent thresholds — confidence 7+ only ("Weekly + Daily aligned, good
    # SMC confluence, clean entry"). Lower than 7 = "mixed signals" per the
    # analyst's own scoring rubric and is rejected.
    analyst_min_confidence: int = 7

    # Validator mode: "required" = no Claude validation, no trade (safest);
    # "optional" = trade mechanically if the validator is unavailable;
    # "off" = pure mechanical engine, zero AI calls in the trade path.
    validator_mode: str = "required"


@lru_cache
def get_settings() -> Settings:
    return Settings()


# --- Constants ---

FOREX_PAIRS = ["EUR_USD", "GBP_USD", "USD_JPY", "GBP_JPY", "AUD_USD", "USD_CAD", "XAU_USD"]
CRYPTO_PAIRS = ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"]

OANDA_GRANULARITIES = {"1H": "H1", "4H": "H4", "D": "D", "W": "W"}
BINANCE_INTERVALS = {"1H": "1h", "4H": "4h", "D": "1d", "W": "1w"}

TIMEFRAMES = ["1H", "4H", "D", "W"]
