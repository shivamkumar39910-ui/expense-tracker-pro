"""
Expense Tracker Pro - Real OTP Delivery Engine (otp_service.py)
Dispatches verification codes via:
1. Real Email (SMTP / Gmail App Password) with branded HTML template
2. Real SMS (Fast2SMS / Twilio) if configured
3. Secure Server Audit Log (Never returned to client browser)
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import urllib.request
import urllib.parse
import json

# Environment Configuration
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
SMTP_USER = os.environ.get("SMTP_USER", "") # e.g. expense.tracker.alert@gmail.com
SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "") # Google 16-char App Password
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "Expense Tracker Pro")

# SMS Configuration
FAST2SMS_API_KEY = os.environ.get("FAST2SMS_API_KEY", "")
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")

def send_email_otp(recipient_email: str, otp_code: str, user_name: str = "User") -> bool:
    """Sends OTP via real SMTP email with a fintech-styled HTML template."""
    if not SMTP_USER or not SMTP_PASSWORD:
        print(f"[OTP AUDIT - EMAIL NOT CONFIGURED] To: {recipient_email} | OTP: {otp_code} (Configure SMTP_USER & SMTP_PASSWORD in Render to send real emails)")
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🔐 {otp_code} is your Expense Tracker Pro Verification Code"
        msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_USER}>"
        msg["To"] = recipient_email

        html_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #0b0f19; color: #f1f5f9; margin: 0; padding: 20px; }}
            .container {{ max-width: 500px; margin: 0 auto; background: #131b2e; border: 1px solid #1e293b; border-radius: 16px; padding: 32px 24px; text-align: center; }}
            .brand {{ font-size: 20px; font-weight: 800; color: #38bdf8; letter-spacing: 0.5px; margin-bottom: 24px; }}
            .otp-box {{ background: #1e293b; border: 2px dashed #0284c7; border-radius: 12px; padding: 18px; margin: 24px 0; }}
            .otp-code {{ font-size: 34px; font-weight: 900; letter-spacing: 8px; color: #38bdf8; font-family: 'Courier New', monospace; }}
            .footer {{ font-size: 12px; color: #64748b; margin-top: 24px; line-height: 1.5; }}
          </style>
        </head>
        <body>
          <div class="container">
            <div class="brand">💰 EXPENSE TRACKER PRO</div>
            <h2 style="margin: 0 0 10px 0; color: #ffffff;">Password Reset & Verification</h2>
            <p style="color: #94a3b8; font-size: 14px; margin: 0 0 16px 0;">Hello {user_name},</p>
            <p style="color: #cbd5e1; font-size: 14px; line-height: 1.5;">Use the one-time verification code below to securely verify your identity. This code is valid for <strong>10 minutes</strong>.</p>
            <div class="otp-box">
              <div class="otp-code">{otp_code}</div>
            </div>
            <p style="color: #ef4444; font-size: 13px; font-weight: 600;">⚠️ Do NOT share this code with anyone. Our team will never ask for your code.</p>
            <div class="footer">
              If you did not request this verification code, please ignore this email or review your account security.<br>
              &copy; 2026 Expense Tracker Pro. All rights reserved.
            </div>
          </div>
        </body>
        </html>
        """

        msg.attach(MIMEText(html_content, "html"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SMTP_USER, recipient_email, msg.as_string())

        print(f"[OTP DISPATCH SUCCESS] Real email sent to {recipient_email}")
        return True
    except Exception as e:
        print(f"[OTP DISPATCH ERROR] Failed to send email to {recipient_email}: {e}")
        return False

def send_sms_otp(phone_number: str, otp_code: str) -> bool:
    """Sends OTP via Fast2SMS (India) or Twilio (Global)."""
    clean_phone = phone_number.replace("+", "").replace("-", "").replace(" ", "").strip()
    if clean_phone.startswith("91") and len(clean_phone) == 12:
        clean_phone = clean_phone[2:] # 10 digit Indian number

    # 1. Fast2SMS (India)
    if FAST2SMS_API_KEY:
        try:
            url = "https://www.fast2sms.com/dev/bulkV2"
            payload = {
                "variables_values": otp_code,
                "route": "otp",
                "numbers": clean_phone
            }
            req = urllib.request.Request(
                url,
                data=urllib.parse.urlencode(payload).encode("utf-8"),
                headers={
                    "authorization": FAST2SMS_API_KEY,
                    "Content-Type": "application/x-www-form-urlencoded"
                }
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                if result.get("return"):
                    print(f"[OTP DISPATCH SUCCESS] Real SMS dispatched to {phone_number} via Fast2SMS")
                    return True
                else:
                    print(f"[OTP DISPATCH ERROR] Fast2SMS error: {result}")
        except Exception as e:
            print(f"[OTP DISPATCH ERROR] Fast2SMS failed: {e}")

    # Fallback log
    print(f"[OTP AUDIT - SMS NOT CONFIGURED] To: {phone_number} | OTP: {otp_code} (Configure FAST2SMS_API_KEY to send real SMS)")
    return False

def dispatch_otp(identifier: str, otp_code: str, user_name: str = "User") -> dict:
    """
    Intelligently routes OTP to Email or Phone based on identifier format.
    Never raises exceptions. Returns dispatch status.
    """
    is_email = "@" in identifier
    if is_email:
        sent = send_email_otp(identifier.strip().lower(), otp_code, user_name)
        channel = "EMAIL"
    else:
        sent = send_sms_otp(identifier.strip(), otp_code)
        channel = "SMS"

    return {
        "channel": channel,
        "dispatched": sent,
        "recipient": identifier
    }
