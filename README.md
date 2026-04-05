# TradeSight

AI-powered forex trading analysis assistant. Runs on a dedicated MacBook with OANDA practice account.

## Architecture

- **Backend**: Python FastAPI + SQLAlchemy + SQLite
- **Frontend**: React 18 + Vite + Tailwind CSS (dark theme)
- **Data**: OANDA v20 API (forex), Binance public API (crypto)
- **AI**: Anthropic Claude for chart analysis and signal generation
- **Execution**: OANDA practice account with 3 modes (Alert Only / Semi-Auto / Full Auto)

## Features

- Multi-timeframe OHLCV data (1H, 4H, D, W) with technical indicators (RSI, MACD, EMA, BB, ATR)
- 4-agent AI pipeline: Screener → Analyst → Risk Manager → Orchestrator
- Signal generation with confidence scoring and risk validation
- Trade execution via OANDA with lifecycle management (breakeven, trailing stop, partial close)
- Economic calendar from ForexFactory with news blackout zones
- Backtesting engine with walk-forward analysis
- Real-time dashboard with charts, signals, portfolio, and trade history

## Quick Start

```bash
# 1. Clone and enter project
cd ~/tradesight

# 2. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env with your OANDA, Binance, and Anthropic API keys

# 5. Install frontend dependencies
cd frontend && npm install && cd ..

# 6. Start everything
./scripts/start.sh
```

Backend: http://localhost:8000
Frontend: http://localhost:5173
Health check: http://localhost:8000/health

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/start.sh` | Start backend + frontend |
| `scripts/stop.sh` | Stop all services |
| `scripts/watchdog.sh` | Auto-restart crashed services |

## Auto-Start on Login (macOS)

```bash
cp scripts/com.tradesight.watchdog.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.tradesight.watchdog.plist
```

## Execution Modes

Set `EXECUTION_MODE` in `.env`:

| Mode | Behavior |
|------|----------|
| `ALERT_ONLY` | Email alerts only, no trades placed |
| `SEMI_AUTO` | Signals require manual approval in UI before execution |
| `FULL_AUTO` | Auto-execute signals with confidence >= 7 |

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | System health + market status |
| `/api/v1/market/{pair}` | GET | OHLCV candle data |
| `/api/v1/signals/` | GET | Active signals |
| `/api/v1/signals/{id}/approve` | POST | Approve & execute signal |
| `/api/v1/trade/execute` | POST | Manual trade execution |
| `/api/v1/trade/open` | GET | Live open trades from OANDA |
| `/api/v1/trade/history` | GET | Closed trade history |
| `/api/v1/trade/{id}/close` | POST | Close a trade |
| `/api/v1/account/summary` | GET | OANDA account summary |
| `/api/v1/news/calendar` | GET | Economic calendar events |

## Forex Pairs

EUR/USD, GBP/USD, USD/JPY, GBP/JPY, AUD/USD, USD/CAD

## Market Hours

Forex market: Sunday 5 PM ET → Friday 5 PM ET. The scheduler automatically skips pipeline runs when markets are closed.
