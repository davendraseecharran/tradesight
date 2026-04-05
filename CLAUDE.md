# TradeSight — Pre-Build Setup Checklist (Mac)

Complete these steps in order before opening Claude Code to start Phase 1.

---

## Step 1: Create OANDA Practice Account

This gives you a $100,000 virtual forex account with full API access — perfect for paper trading.

1. Go to **https://www.oanda.com** and click **"Try free demo"** or **"Practice Trading"**
2. Select **fxTrade Practice** (not fxTrade Live)
3. Fill in your details and create the account
4. Once logged in, go to the **HUB** dashboard
5. Click **Tools → API** in the top navigation
6. Click **"Generate"** to create your API access token
7. **Copy and save** the token somewhere secure — it's a long string of letters and numbers (this is your password for the API)
8. Note your **Account ID** — it's in the format `xxx-xxx-xxxxxxx-xxx` and visible on your account page

**Save these two values — you'll need them for Claude Code:**
- `OANDA_API_TOKEN`: your generated access token
- `OANDA_ACCOUNT_ID`: your account ID (xxx-xxx-xxxxxxx-xxx format)

**Important:** The practice API endpoint is `https://api-fxpractice.oanda.com` (not the live endpoint). Claude Code will use this automatically.

---

## Step 2: Create Binance Account (for Crypto Data)

We only need Binance's **public API** for price data — no trading, no deposits needed.

1. Go to **https://www.binance.com** and create a free account
2. Complete basic verification
3. Go to **Account → API Management**
4. Create a new API key with **read-only** permissions (no trading, no withdrawals)
5. Save both the **API Key** and **Secret Key**

**Note:** For initial development, Binance's public endpoints don't even require an API key. We'll use the key later for rate limit increases.

---

## Step 3: Get Your Anthropic API Key

You need this so TradeSight can call Claude's API for chart analysis.

1. Go to **https://console.anthropic.com**
2. Click **API Keys** in the left sidebar
3. Click **Create Key** and name it "TradeSight"
4. Copy and save the key (starts with `sk-ant-`)

**Save this value:**
- `ANTHROPIC_API_KEY`: your Claude API key

---

## Step 4: Install TradingView Desktop (for MCP Integration)

1. Go to **https://www.tradingview.com/desktop/** and download the Mac version
2. Install and sign in with a TradingView account (free tier works)
3. **Do NOT open it yet** — we'll launch it with a special debug flag later

**To launch TradingView with MCP debug port (you'll do this later):**
```bash
/Applications/TradingView.app/Contents/MacOS/TradingView --remote-debugging-port=9222
```

---

## Step 5: Verify Claude Code is Ready

Open your terminal and run:
```bash
claude --version
```

You should see a version number. If not, install Claude Code:
```bash
npm install -g @anthropic-ai/claude-code
```

---

## Step 6: Create Your Project Folder

```bash
mkdir ~/tradesight
cd ~/tradesight
```

---

## Step 7: Create Your Environment File

Create a `.env` file in your project folder with your API keys:

```bash
cat > ~/tradesight/.env << 'EOF'
# OANDA Practice Account
OANDA_API_TOKEN=your_oanda_token_here
OANDA_ACCOUNT_ID=your_account_id_here
OANDA_API_URL=https://api-fxpractice.oanda.com

# Binance (optional for Phase 1 — public endpoints work without keys)
BINANCE_API_KEY=your_binance_key_here
BINANCE_API_SECRET=your_binance_secret_here

# Anthropic
ANTHROPIC_API_KEY=your_anthropic_key_here
EOF
```

**Replace the placeholder values with your actual keys.**

---

## Step 8: Start Building with Claude Code

Open Claude Code in your project folder:

```bash
cd ~/tradesight
claude
```

Then paste this prompt to kick off Phase 1:

> I'm building TradeSight, an AI-powered trading analysis assistant. Here's the project plan: [paste the project plan or key details]. Start Phase 1: create a Python FastAPI backend that connects to OANDA's v20 API and Binance's public API to fetch OHLCV candle data for forex and crypto pairs across 1H, 4H, Daily, and Weekly timeframes. Compute RSI, MACD, EMA (20/50/200), Bollinger Bands, and ATR for each pair. Store results in SQLite. Use the 'ta' library for indicators. Read my .env file for API credentials. Also set up the TradingView MCP server (tradingview-mcp by atilaahmettaner) for backtesting and multi-indicator analysis.

---

## Quick Reference: API Endpoints

| Service | Practice/Demo Endpoint | Live Endpoint |
|---------|----------------------|---------------|
| OANDA | `https://api-fxpractice.oanda.com` | `https://api-fxtrade.oanda.com` |
| Binance | `https://api.binance.com` | Same |
| Anthropic | `https://api.anthropic.com` | Same |

---

## Checklist Summary

- [ ] OANDA practice account created
- [ ] OANDA API token generated and saved
- [ ] OANDA Account ID noted
- [ ] Binance account created (optional for Phase 1)
- [ ] Anthropic API key generated and saved
- [ ] TradingView Desktop installed (not launched yet)
- [ ] Claude Code verified (`claude --version`)
- [ ] Project folder created (`~/tradesight`)
- [ ] `.env` file created with all keys
- [ ] Ready to launch Claude Code and start Phase 1!

---

*This checklist accompanies the TradeSight Project Plan v1.0 — April 2026*
