"""Lightweight system health tracking + failure alerting.

JSON-file-backed (no DB migration) record of the last run/outcome of each
scheduled job, so /health and the report exporter can show *why* the bot
isn't trading instead of failing silently. Sends an email alert after
repeated pipeline failures (throttled to one alert per 12h).
"""
from __future__ import annotations

import json
import logging
import smtplib
from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_STATUS_FILE = Path(__file__).resolve().parent.parent.parent.parent / "system_status.json"

ALERT_AFTER_CONSECUTIVE_FAILURES = 3
ALERT_THROTTLE_HOURS = 12


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_status() -> dict:
    try:
        return json.loads(_STATUS_FILE.read_text())
    except Exception:
        return {}


def _save(status: dict) -> None:
    try:
        _STATUS_FILE.write_text(json.dumps(status, indent=2, default=str))
    except Exception as exc:
        logger.warning("system_status: save failed: %s", exc)


def record_success(job: str, detail: str = "") -> None:
    status = load_status()
    status[job] = {
        "last_success": _now(),
        "last_error": status.get(job, {}).get("last_error"),
        "consecutive_failures": 0,
        "detail": detail,
    }
    _save(status)


def record_failure(job: str, error: str) -> int:
    """Record a job failure; returns the consecutive failure count."""
    status = load_status()
    entry = status.get(job, {})
    failures = int(entry.get("consecutive_failures", 0)) + 1
    status[job] = {
        "last_success": entry.get("last_success"),
        "last_error": {"at": _now(), "message": str(error)[:500]},
        "consecutive_failures": failures,
        "detail": entry.get("detail", ""),
    }
    _save(status)

    if failures >= ALERT_AFTER_CONSECUTIVE_FAILURES:
        _maybe_send_alert(status, job, error, failures)
    return failures


def _maybe_send_alert(status: dict, job: str, error: str, failures: int) -> None:
    """Email the user about repeated failures, at most once per 12h per job."""
    last_alert = status.get("_alerts", {}).get(job)
    if last_alert:
        try:
            last_dt = datetime.fromisoformat(last_alert)
            if datetime.now(timezone.utc) - last_dt < timedelta(hours=ALERT_THROTTLE_HOURS):
                return
        except Exception:
            pass

    from backend.app.config import get_settings
    s = get_settings()
    if not s.smtp_username or not s.alert_email_to:
        return

    msg = MIMEText(
        f"TradeSight job '{job}' has failed {failures} times in a row.\n\n"
        f"Last error:\n{str(error)[:1000]}\n\n"
        f"The watchdog keeps the server alive, but this job will keep failing "
        f"until the cause is fixed (e.g. API credits exhausted, network down).\n"
        f"Check /health or download a report from the dashboard for details."
    )
    msg["Subject"] = f"[TradeSight] ALERT: {job} failing repeatedly"
    msg["From"] = s.smtp_username
    msg["To"] = s.alert_email_to

    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
            smtp.starttls()
            smtp.login(s.smtp_username, s.smtp_password)
            smtp.sendmail(s.smtp_username, s.alert_email_to, msg.as_string())
        status.setdefault("_alerts", {})[job] = _now()
        _save(status)
        logger.info("system_status: failure alert emailed for %s", job)
    except Exception as exc:
        logger.error("system_status: alert email failed: %s", exc)


def health_snapshot(candle_max_age_hours: float = 6.0) -> dict:
    """Compact health view for /health and the report exporter."""
    status = load_status()
    now = datetime.now(timezone.utc)

    def _age_hours(iso: Optional[str]) -> Optional[float]:
        if not iso:
            return None
        try:
            return round((now - datetime.fromisoformat(iso)).total_seconds() / 3600, 1)
        except Exception:
            return None

    jobs = {}
    problems = []
    for job, entry in status.items():
        if job.startswith("_"):
            continue
        age = _age_hours(entry.get("last_success"))
        jobs[job] = {
            "last_success_age_hours": age,
            "consecutive_failures": entry.get("consecutive_failures", 0),
            "last_error": entry.get("last_error"),
        }
        if entry.get("consecutive_failures", 0) >= ALERT_AFTER_CONSECUTIVE_FAILURES:
            problems.append(f"{job}: {entry['consecutive_failures']} consecutive failures")

    candle_age = jobs.get("candle_refresh", {}).get("last_success_age_hours")
    if candle_age is not None and candle_age > candle_max_age_hours:
        problems.append(f"candle data stale: last refresh {candle_age}h ago")

    return {"ok": len(problems) == 0, "problems": problems, "jobs": jobs}
