from __future__ import annotations

import json

import anthropic

from backend.app.config import get_settings

SYSTEM_PROMPT = """You are a professional technical analyst for TradeSight, an AI-powered trading analysis platform. Your role is to analyze market data and technical indicators to provide structured trading insights.

Rules:
- Always respond with valid JSON matching the requested format
- Never provide financial advice — present analysis as educational information only
- Always include risk warnings
- Base analysis strictly on the data provided
- Consider multiple timeframes when available

Output JSON format:
{
  "bias": "bullish" | "bearish" | "neutral",
  "confidence": 0-100,
  "key_levels": {"support": [...], "resistance": [...]},
  "entry_suggestion": {"price": float, "type": "limit" | "market"},
  "stop_loss_suggestion": float,
  "take_profit_suggestion": float,
  "reasoning": "string explaining the analysis",
  "risk_warning": "This is educational analysis, not financial advice."
}"""


class MarketAnalyzer:
    def __init__(self, settings=None):
        s = settings or get_settings()
        self._client = anthropic.AsyncAnthropic(api_key=s.anthropic_api_key)

    async def analyze_instrument(
        self,
        instrument: str,
        candle_data: list[dict],
        indicators: dict,
        timeframe: str = "H4",
        model: str = "claude-sonnet-4-6-20250514",
    ) -> dict:
        user_prompt = self._build_prompt(instrument, candle_data, indicators, timeframe)

        message = await self._client.messages.create(
            model=model,
            max_tokens=1024,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        return self._parse_response(message.content[0].text)

    async def deep_analysis(
        self,
        instrument: str,
        multi_timeframe_data: dict[str, dict],
    ) -> dict:
        """Multi-timeframe analysis using Opus for deeper insights."""
        sections = []
        for tf, data in multi_timeframe_data.items():
            sections.append(
                f"## {tf} Timeframe\n"
                f"Last close: {data['candles'][-1]['close']}\n"
                f"RSI: {data['indicators'].get('rsi_14')}\n"
                f"MACD: {data['indicators'].get('macd_line')} / {data['indicators'].get('macd_signal')}\n"
                f"EMA20: {data['indicators'].get('ema_20')}, EMA50: {data['indicators'].get('ema_50')}, EMA200: {data['indicators'].get('ema_200')}\n"
            )

        user_prompt = (
            f"Perform a comprehensive multi-timeframe technical analysis for {instrument}.\n\n"
            + "\n".join(sections)
            + "\n\nProvide confluence signals across timeframes and a high-conviction trade setup if one exists."
        )

        message = await self._client.messages.create(
            model="claude-opus-4-6-20250514",
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        return self._parse_response(message.content[0].text)

    def _build_prompt(
        self, instrument: str, candles: list[dict], indicators: dict, timeframe: str
    ) -> str:
        last_5 = candles[-5:] if len(candles) >= 5 else candles
        candle_summary = "\n".join(
            f"  {c['timestamp']}: O={c['open']} H={c['high']} L={c['low']} C={c['close']} V={c['volume']}"
            for c in last_5
        )
        return (
            f"Analyze {instrument} on the {timeframe} timeframe.\n\n"
            f"Recent candles:\n{candle_summary}\n\n"
            f"Current indicators:\n"
            f"  RSI(14): {indicators.get('rsi_14')}\n"
            f"  MACD: line={indicators.get('macd_line')}, signal={indicators.get('macd_signal')}, hist={indicators.get('macd_histogram')}\n"
            f"  EMA20: {indicators.get('ema_20')}, EMA50: {indicators.get('ema_50')}, EMA200: {indicators.get('ema_200')}\n"
            f"  Bollinger: upper={indicators.get('bb_upper')}, mid={indicators.get('bb_middle')}, lower={indicators.get('bb_lower')}\n"
            f"  ATR(14): {indicators.get('atr_14')}\n"
            f"  Ichimoku: tenkan={indicators.get('ichimoku_tenkan')}, kijun={indicators.get('ichimoku_kijun')}\n\n"
            f"Provide your analysis as JSON."
        )

    def _parse_response(self, text: str) -> dict:
        # Try to extract JSON from the response
        text = text.strip()
        if text.startswith("```"):
            # Strip markdown code fences
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"raw_response": text, "parse_error": True}
