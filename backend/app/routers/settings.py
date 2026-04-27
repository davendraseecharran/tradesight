from __future__ import annotations

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.app.config import get_settings, _ENV_FILE

router = APIRouter(prefix="/api/v1/settings", tags=["settings"])

# Keys that are sensitive and should be masked in GET responses
_SENSITIVE_KEYS = {"OANDA_API_TOKEN", "ANTHROPIC_API_KEY", "SMTP_PASSWORD", "BINANCE_API_SECRET"}

# Keys that can be updated via the API
_UPDATABLE_KEYS = {
    "OANDA_API_TOKEN", "OANDA_ACCOUNT_ID",
    "ANTHROPIC_API_KEY",
    "ALERT_EMAIL_TO", "SMTP_USERNAME", "SMTP_PASSWORD", "SMTP_HOST", "SMTP_PORT",
    "EXECUTION_MODE",
}


def _read_env() -> dict[str, str]:
    """Read .env file into a dict, preserving order."""
    values = {}
    if _ENV_FILE.exists():
        for line in _ENV_FILE.read_text().splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, _, val = stripped.partition("=")
                values[key.strip()] = val.strip()
    return values


def _mask(key: str, val: str) -> str:
    """Mask sensitive values, showing only last 4 chars."""
    if key in _SENSITIVE_KEYS and len(val) > 4:
        return "***" + val[-4:]
    return val


@router.get("/config")
async def get_config():
    """Return current config with sensitive values masked."""
    env = _read_env()
    masked = {k: _mask(k, v) for k, v in env.items()}
    return {"config": masked}


class ConfigUpdate(BaseModel):
    updates: dict[str, str]


@router.post("/config")
async def update_config(body: ConfigUpdate):
    """Update .env file with new values. Only whitelisted keys allowed."""
    invalid = set(body.updates.keys()) - _UPDATABLE_KEYS
    if invalid:
        raise HTTPException(400, f"Cannot update keys: {', '.join(invalid)}")

    # Read existing .env preserving comments and structure
    lines = []
    if _ENV_FILE.exists():
        lines = _ENV_FILE.read_text().splitlines()

    updated_keys = set()

    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _, _ = stripped.partition("=")
            key = key.strip()
            if key in body.updates:
                lines[i] = f"{key}={body.updates[key]}"
                updated_keys.add(key)

    # Append any new keys not already in file
    for key, val in body.updates.items():
        if key not in updated_keys:
            lines.append(f"{key}={val}")

    _ENV_FILE.write_text("\n".join(lines) + "\n")

    # Clear the lru_cache. The next get_settings() call rebuilds the Settings
    # object from the freshly-written .env. Scheduled jobs call get_settings()
    # on each run, so changes are picked up without a server restart.
    get_settings.cache_clear()

    return {"status": "ok", "updated": list(body.updates.keys()),
            "note": "Changes are live — applied on the next scheduled run."}


@router.post("/test-email")
async def test_email():
    """Send a test email using current SMTP config from .env."""
    get_settings.cache_clear()
    s = get_settings()

    if not s.smtp_username or not s.smtp_password:
        raise HTTPException(400, "SMTP credentials not configured")
    if not s.alert_email_to:
        raise HTTPException(400, "ALERT_EMAIL_TO not configured")

    acct_masked = "***" + s.oanda_account_id[-4:]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = f"""\
    <html>
    <body style="font-family: -apple-system, sans-serif; background: #0a0a0a; color: #fafafa; padding: 30px;">
      <div style="max-width: 500px; margin: 0 auto; background: #161616; border-radius: 12px; padding: 30px; border: 1px solid #262626;">
        <h1 style="color: #ffffff; font-size: 22px; margin-top: 0;">TradeSight</h1>
        <p style="color: #22c55e;">&#10003; Your email alerts are configured correctly.</p>
        <hr style="border: none; border-top: 1px solid #262626; margin: 20px 0;">
        <table style="width: 100%; font-size: 14px; color: #a3a3a3;">
          <tr><td style="padding: 6px 0; color: #525252;">Mode</td><td style="text-align:right;">{s.execution_mode}</td></tr>
          <tr><td style="padding: 6px 0; color: #525252;">Account</td><td style="text-align:right; font-family:monospace;">{acct_masked}</td></tr>
          <tr><td style="padding: 6px 0; color: #525252;">Time</td><td style="text-align:right;">{now}</td></tr>
        </table>
        <hr style="border: none; border-top: 1px solid #262626; margin: 20px 0;">
        <p style="font-size: 13px; color: #525252;">You will receive trade alerts when setups are detected.</p>
      </div>
    </body></html>"""

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "TradeSight — Email Alerts Working"
    msg["From"] = s.smtp_username
    msg["To"] = s.alert_email_to
    msg.attach(MIMEText(html, "html"))

    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as server:
            server.starttls()
            server.login(s.smtp_username, s.smtp_password)
            server.sendmail(s.smtp_username, s.alert_email_to, msg.as_string())
        return {"status": "ok", "sent_to": s.alert_email_to}
    except smtplib.SMTPAuthenticationError as e:
        raise HTTPException(400, f"SMTP auth failed: {e}")
    except Exception as e:
        raise HTTPException(502, f"Email send failed: {e}")
