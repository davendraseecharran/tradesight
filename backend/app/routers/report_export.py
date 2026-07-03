from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.app.database import get_db
from backend.app.services.diagnostics import build_report

router = APIRouter(prefix="/api/v1/report", tags=["report"])


@router.get("/export")
def export_report(days: Optional[int] = 7, db: Session = Depends(get_db)):
    """Download the full diagnostic report as a JSON file.

    Contains performance analytics (signals, trades, win rate, P&L),
    AI costs, job health, candle freshness, and error-log excerpts —
    everything needed for a weekly Claude review. `days=0` = all history.
    """
    report = build_report(db, days=None if not days else days)
    filename = f"tradesight-report-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}.json"
    return Response(
        content=json.dumps(report, indent=2, default=str),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
