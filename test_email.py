#!/usr/bin/env python3
"""
TradeSight — SMTP Email Test
Sends a test email using .env SMTP settings.
"""
import sys
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime, timezone

# Auto-detect and relaunch with venv Python if running under system Python
venv_python = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".venv", "bin", "python")
if os.path.exists(venv_python) and sys.executable != os.path.realpath(venv_python):
    os.execv(venv_python, [venv_python] + sys.argv)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Remove any shell overrides so .env is authoritative
for key in ["ANTHROPIC_API_KEY", "ANTHROPIC_BASE_URL"]:
    os.environ.pop(key, None)

from backend.app.config import get_settings
get_settings.cache_clear()
settings = get_settings()

def send_test_email():
    if not settings.smtp_username or not settings.smtp_password:
        print("✗ SMTP credentials not configured in .env")
        print("  Set SMTP_USERNAME and SMTP_PASSWORD")
        return False

    if not settings.alert_email_to:
        print("✗ ALERT_EMAIL_TO not configured in .env")
        return False

    # Mask account ID — show only last 4 chars
    acct_masked = "***" + settings.oanda_account_id[-4:]
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    html = f"""\
    <html>
    <body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: #1a1f2e; color: #e2e8f0; padding: 30px;">
      <div style="max-width: 500px; margin: 0 auto; background: #242938; border-radius: 12px; padding: 30px; border: 1px solid #3a4259;">
        <h1 style="color: #6c5ce7; font-size: 22px; margin-top: 0;">TradeSight</h1>
        <p style="font-size: 16px; color: #a0e6a0;">&#10003; Your TradeSight email alerts are configured correctly.</p>
        <hr style="border: none; border-top: 1px solid #3a4259; margin: 20px 0;">
        <table style="width: 100%; font-size: 14px; color: #c8d6e5;">
          <tr><td style="padding: 6px 0; color: #8892a8;">Execution Mode</td><td style="text-align: right;">{settings.execution_mode}</td></tr>
          <tr><td style="padding: 6px 0; color: #8892a8;">OANDA Account</td><td style="text-align: right; font-family: monospace;">{acct_masked}</td></tr>
          <tr><td style="padding: 6px 0; color: #8892a8;">Timestamp</td><td style="text-align: right;">{now}</td></tr>
        </table>
        <hr style="border: none; border-top: 1px solid #3a4259; margin: 20px 0;">
        <p style="font-size: 13px; color: #8892a8;">
          You will receive trade recommendations at this address when the AI analysis engine detects setups.
        </p>
      </div>
    </body>
    </html>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "TradeSight — Email Alerts Working"
    msg["From"] = settings.smtp_username
    msg["To"] = settings.alert_email_to
    msg.attach(MIMEText(html, "html"))

    print(f"Sending test email...")
    print(f"  From: {settings.smtp_username}")
    print(f"  To:   {settings.alert_email_to}")
    print(f"  SMTP: {settings.smtp_host}:{settings.smtp_port}")

    try:
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as server:
            server.starttls()
            server.login(settings.smtp_username, settings.smtp_password)
            server.sendmail(settings.smtp_username, settings.alert_email_to, msg.as_string())
        print(f"\n✓ Test email sent successfully to {settings.alert_email_to}")
        return True
    except smtplib.SMTPAuthenticationError as e:
        print(f"\n✗ SMTP Authentication failed: {e}")
        print("  Check SMTP_USERNAME and SMTP_PASSWORD in .env")
        print("  For Gmail, use an App Password (not your regular password)")
        return False
    except smtplib.SMTPException as e:
        print(f"\n✗ SMTP error: {e}")
        return False
    except Exception as e:
        print(f"\n✗ Connection error: {e}")
        return False


if __name__ == "__main__":
    print("=" * 50)
    print("  TradeSight — Email Alert Test")
    print("=" * 50)
    success = send_test_email()
    sys.exit(0 if success else 1)
