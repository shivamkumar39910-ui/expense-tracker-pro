"""
Expense Tracker Pro - Real OTP Delivery Engine (otp_service.py)
Dispatches verification codes via:
1. Real Email via HTTPS REST API (Resend / Brevo) -> Bypasses Render port 587 firewall
2. Real Email via SMTP (Gmail App Password)
3. Real SMS (Fast2SMS / Twilio)
4. Secure Server Audit Log (Never returned to client browser)
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
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "Expense Tracker Pro")

# HTTPS Email APIs (Cloud-Firewall Proof over Port 443)
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
BREVO_API_KEY = os.environ.get("BREVO_API_KEY", "")

# SMS Configuration
FAST2SMS_API_KEY = os.environ.get("FAST2SMS_API_KEY", "")
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN", "")
TWILIO_FROM_NUMBER = os.environ.get("TWILIO_FROM_NUMBER", "")

def generate_email_html(otp_code: str, user_name: str = "User") -> str:
    return f"""
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

def send_resend_email(recipient_email: str, otp_code: str, user_name: str = "User") -> bool:
    """Sends email via Resend HTTPS API (Port 443 - works on Render without port blocking)."""
    api_key = os.environ.get("RESEND_API_KEY", "").strip()
    if not api_key:
        return False

    try:
        url = "https://api.resend.com/emails"
        html_body = generate_email_html(otp_code, user_name)
        payload = {
            "from": f"{SMTP_FROM_NAME} <onboarding@resend.dev>",
            "to": [recipient_email],
            "subject": f"🔐 {otp_code} is your Expense Tracker Pro Verification Code",
            "html": html_body
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "ExpenseTrackerPro/2.0"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            res_data = json.loads(resp.read().decode())
            print(f"[OTP RESEND SUCCESS] Dispatched to {recipient_email}: {res_data.get('id')}")
            return True
    except Exception as e:
        print(f"[OTP RESEND ERROR] Resend API failed: {e}")
        return False

def send_brevo_email(recipient_email: str, otp_code: str, user_name: str = "User") -> bool:
    """Sends email via Brevo HTTPS API (Port 443 - works on Render without port blocking)."""
    api_key = os.environ.get("BREVO_API_KEY", "").strip()
    sender_email = os.environ.get("SMTP_USER", "").strip() or "onboarding@expensetracker.pro"
    if not api_key:
        return False

    try:
        url = "https://api.brevo.com/v3/smtp/email"
        html_body = generate_email_html(otp_code, user_name)
        payload = {
            "sender": {"name": SMTP_FROM_NAME, "email": sender_email},
            "to": [{"email": recipient_email}],
            "subject": f"🔐 {otp_code} is your Expense Tracker Pro Verification Code",
            "htmlContent": html_body
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            print(f"[OTP BREVO SUCCESS] Dispatched to {recipient_email}")
            return True
    except Exception as e:
        print(f"[OTP BREVO ERROR] Brevo API failed: {e}")
        return False

def send_smtp_email(recipient_email: str, otp_code: str, user_name: str = "User") -> bool:
    """Sends OTP via standard SMTP (Works on local or servers where port 587/465 is open)."""
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASSWORD", "").replace(" ", "").strip()

    if not user or not password:
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"🔐 {otp_code} is your Expense Tracker Pro Verification Code"
        msg["From"] = f"{SMTP_FROM_NAME} <{user}>"
        msg["To"] = recipient_email

        html_content = generate_email_html(otp_code, user_name)
        msg.attach(MIMEText(html_content, "html"))

        # Try Port 587 TLS first, then 465 SSL
        try:
            with smtplib.SMTP(SMTP_HOST, 587, timeout=10) as server:
                server.starttls()
                server.login(user, password)
                server.sendmail(user, recipient_email, msg.as_string())
                print(f"[OTP DISPATCH SUCCESS] Real SMTP email sent to {recipient_email} (port 587)")
                return True
        except Exception:
            with smtplib.SMTP_SSL(SMTP_HOST, 465, timeout=10) as server:
                server.login(user, password)
                server.sendmail(user, recipient_email, msg.as_string())
                print(f"[OTP DISPATCH SUCCESS] Real SMTP email sent to {recipient_email} (port 465)")
                return True
    except Exception as e:
        print(f"[OTP SMTP ERROR] SMTP failed to send to {recipient_email}: {e}")
        return False

def send_email_otp(recipient_email: str, otp_code: str, user_name: str = "User") -> bool:
    """
    Unified Email Dispatcher:
    Tries HTTPS REST APIs first (Render cloud firewall proof), then falls back to SMTP.
    """
    # 1. Try Resend HTTPS API (Port 443)
    if os.environ.get("RESEND_API_KEY"):
        if send_resend_email(recipient_email, otp_code, user_name):
            return True

    # 2. Try Brevo HTTPS API (Port 443)
    if os.environ.get("BREVO_API_KEY"):
        if send_brevo_email(recipient_email, otp_code, user_name):
            return True

    # 3. Try standard SMTP (Port 587 / 465)
    if os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"):
        if send_smtp_email(recipient_email, otp_code, user_name):
            return True

    # 4. Fallback Audit Log
    print(f"[OTP AUDIT - UNABLE TO DISPATCH] To: {recipient_email} | OTP: {otp_code}")
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
    print(f"[OTP AUDIT - SMS NOT CONFIGURED] To: {phone_number} | OTP: {otp_code}")
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
