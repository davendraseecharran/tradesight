from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.models.api_call import ApiCall

# ── Pricing (per token) ──────────────────────────────────────────────────────
PRICING: dict[str, dict[str, float]] = {
    "claude-haiku-4-5-20251001": {
        "input":       0.80 / 1_000_000,
        "output":      4.00 / 1_000_000,
        "cache_write": 1.00 / 1_000_000,  # 25% surcharge on cache write
        "cache_read":  0.08 / 1_000_000,  # 90% discount on cache read
    },
    "claude-sonnet-4-6": {
        "input":       3.00 / 1_000_000,
        "output":     15.00 / 1_000_000,
        "cache_write": 3.75 / 1_000_000,
        "cache_read":  0.30 / 1_000_000,
    },
    "claude-opus-4-6": {
        "input":      15.00 / 1_000_000,
        "output":     75.00 / 1_000_000,
        "cache_write": 18.75 / 1_000_000,
        "cache_read":  1.50 / 1_000_000,
    },
}


def _get_pricing(model: str) -> dict[str, float]:
    """Match model string to pricing tier by prefix."""
    for key, prices in PRICING.items():
        if model.startswith(key) or key in model:
            return prices
    return PRICING["claude-sonnet-4-6"]  # safe fallback


def compute_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float:
    p = _get_pricing(model)
    return (
        input_tokens * p["input"]
        + output_tokens * p["output"]
        + cache_read_tokens * p["cache_read"]
        + cache_write_tokens * p["cache_write"]
    )


def log_api_call(
    db: Session,
    agent: str,
    model: str,
    response,  # anthropic Message object
    instrument: Optional[str] = None,
) -> ApiCall:
    """Extract usage from a Claude response and persist an ApiCall record."""
    usage = response.usage
    input_tok = getattr(usage, "input_tokens", 0)
    output_tok = getattr(usage, "output_tokens", 0)
    cache_read = getattr(usage, "cache_read_input_tokens", 0)
    cache_write = getattr(usage, "cache_creation_input_tokens", 0)

    cost = compute_cost(model, input_tok, output_tok, cache_read, cache_write)

    record = ApiCall(
        agent=agent,
        model=model,
        input_tokens=input_tok,
        output_tokens=output_tok,
        cache_read_tokens=cache_read,
        cache_write_tokens=cache_write,
        cost_usd=round(cost, 8),
        instrument=instrument,
    )
    db.add(record)
    db.commit()
    return record


def get_usage_summary(db: Session) -> dict:
    """Return aggregated token costs for daily / weekly / monthly periods."""
    now = datetime.now(timezone.utc)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = day_start - timedelta(days=now.weekday())
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    def _sum(since: datetime) -> float:
        result = (
            db.query(func.sum(ApiCall.cost_usd))
            .filter(ApiCall.timestamp >= since)
            .scalar()
        )
        return round(result or 0.0, 4)

    daily = _sum(day_start)
    weekly = _sum(week_start)
    monthly = _sum(month_start)

    # Per-agent breakdown (daily)
    by_agent_rows = (
        db.query(ApiCall.agent, func.sum(ApiCall.cost_usd))
        .filter(ApiCall.timestamp >= day_start)
        .group_by(ApiCall.agent)
        .all()
    )
    by_agent = {row[0]: round(row[1] or 0.0, 4) for row in by_agent_rows}

    # Call counts
    total_calls_today = db.query(ApiCall).filter(ApiCall.timestamp >= day_start).count()
    total_calls_month = db.query(ApiCall).filter(ApiCall.timestamp >= month_start).count()

    return {
        "daily_cost_usd": daily,
        "weekly_cost_usd": weekly,
        "monthly_cost_usd": monthly,
        "by_agent_today": by_agent,
        "total_calls_today": total_calls_today,
        "total_calls_month": total_calls_month,
    }


def check_budget_alerts(db: Session, settings) -> dict:
    """Return budget alert flags based on current spend."""
    summary = get_usage_summary(db)
    return {
        "daily_exceeded": summary["daily_cost_usd"] > settings.daily_token_budget_usd,
        "monthly_exceeded": summary["monthly_cost_usd"] > settings.monthly_token_budget_usd,
        "daily_cost": summary["daily_cost_usd"],
        "monthly_cost": summary["monthly_cost_usd"],
        "daily_budget": settings.daily_token_budget_usd,
        "monthly_budget": settings.monthly_token_budget_usd,
    }
