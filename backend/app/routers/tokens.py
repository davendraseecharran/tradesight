from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.database import get_db
from backend.app.services.token_tracker import check_budget_alerts, get_usage_summary

router = APIRouter(prefix="/api/v1/tokens", tags=["tokens"])


@router.get("/usage")
def get_token_usage(db: Session = Depends(get_db)):
    """Return daily / weekly / monthly token cost breakdown with budget alerts."""
    settings = get_settings()
    summary = get_usage_summary(db)
    alerts = check_budget_alerts(db, settings)

    return {
        **summary,
        "budget": {
            "daily_budget_usd": settings.daily_token_budget_usd,
            "monthly_budget_usd": settings.monthly_token_budget_usd,
            "daily_exceeded": alerts["daily_exceeded"],
            "monthly_exceeded": alerts["monthly_exceeded"],
            "daily_utilization_pct": round(
                (summary["daily_cost_usd"] / settings.daily_token_budget_usd) * 100, 1
            ) if settings.daily_token_budget_usd > 0 else 0,
            "monthly_utilization_pct": round(
                (summary["monthly_cost_usd"] / settings.monthly_token_budget_usd) * 100, 1
            ) if settings.monthly_token_budget_usd > 0 else 0,
        },
    }
