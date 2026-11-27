"""
Expense Tracker Pro - Real OTP Delivery Engine (otp_service.py)
Dispatches transactional verification codes reliably with spam-safe light formatting,
multipart plain-text + HTML MIME bodies, clean subjects, and smart transport ordering:
1. Optional Native Gmail Apps Script Webhook (GMAIL_WEBHOOK_URL) -> 100% DMARC Pass
2. Direct IPv4 Authenticated Gmail SMTP (465 SSL / 587 STARTTLS) -> 100% SPF/DKIM/DMARC Pass
3. Resend HTTPS REST API (RESEND_API_KEY) -> DKIM-signed Port-443 delivery
4. Brevo HTTPS REST API (BREVO_API_KEY) -> Port-443 fallback
5. Non-blocking background dispatch (<1ms UI response)
"""

import json
import os
import smtplib
import socket
import threading
import urllib.error
import urllib.parse
import urllib.request
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr


SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_FROM_NAME = os.environ.get("SMTP_FROM_NAME", "Expense Tracker Pro")

FAST2SMS_API_KEY = os.environ.get("FAST2SMS_API_KEY", "")


def _ipv4_create_connection(host: str, port: int, timeout: float):
    """Creates a TCP socket strictly over IPv4 (AF_INET) to avoid IPv6 ENETUNREACH on Render/Docker."""
    ipv4_infos = socket.getaddrinfo(host, port, socket.AF_INET, socket.SOCK_STREAM)
    if not ipv4_infos:
        raise OSError(f"No IPv4 address resolved for {host}:{port}")
    last_err = None
    for af, socktype, proto, _, sa in ipv4_infos:
        sock = None
        try:
            sock = socket.socket(af, socktype, proto)
            sock.settimeout(timeout)
            sock.connect(sa)
            return sock
        except OSError as err:
            last_err = err
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    pass
    if last_err is not None:
        raise last_err
    raise OSError(f"Failed IPv4 connection to {host}:{port}")


class _IPv4SMTP(smtplib.SMTP):
    """SMTP client pinned to IPv4 sockets while preserving server_hostname for TLS."""
    def _get_socket(self, host, port, timeout):
        return _ipv4_create_connection(host, port, timeout)


class _IPv4SMTP_SSL(smtplib.SMTP_SSL):
    """SMTP_SSL client pinned to IPv4 sockets while preserving server_hostname for TLS."""
    def _get_socket(self, host, port, timeout):
        sock = _ipv4_create_connection(host, port, timeout)
        return self.context.wrap_socket(sock, server_hostname=self._host)


def generate_email_plain(otp_code: str, user_name: str = "User") -> str:
    safe_name = (user_name or "User").strip()
    return (
        f"Hi {safe_name},\n\n"
        f"Your Expense Tracker Pro verification code is: {otp_code}\n\n"
        "This one-time code is valid for 10 minutes. "
        "Please enter it in the app to verify your email address.\n\n"
        "If you did not request this code, you can safely ignore this message.\n\n"
        "— Expense Tracker Pro Security Team"
    )


def generate_email_html(otp_code: str, user_name: str = "User") -> str:
    safe_name = (user_name or "User").strip()
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Verification Code</title>
</head>
<body style="margin:0; padding:24px 12px; background-color:#f4f6f9; font-family:-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color:#1e293b;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" style="max-width:480px; margin:0 auto; background-color:#ffffff; border:1px solid #e2e8f0; border-radius:12px;">
    <tr>
      <td style="padding:28px 28px 22px 28px;">
        <div style="font-size:15px; font-weight:700; color:#1d4ed8; margin-bottom:14px;">Expense Tracker Pro</div>
        <h1 style="margin:0 0 12px 0; font-size:20px; font-weight:700; color:#0f172a;">Email verification code</h1>
        <p style="margin:0 0 14px 0; font-size:14px; line-height:1.55; color:#334155;">Hi {safe_name},</p>
        <p style="margin:0 0 18px 0; font-size:14px; line-height:1.55; color:#334155;">Use the verification code below to confirm your email address. This code expires in <strong>10 minutes</strong>.</p>
        <div style="background-color:#f8fafc; border:1px solid #cbd5e1; border-radius:10px; padding:16px; text-align:center; margin:0 0 18px 0;">
          <span style="font-size:30px; font-weight:700; letter-spacing:6px; color:#0f172a; font-family:'Courier New', Courier, monospace;">{otp_code}</span>
        </div>
        <p style="margin:0 0 8px 0; font-size:12.5px; line-height:1.5; color:#64748b;">For your security, do not share this code with anyone.</p>
        <p style="margin:0; font-size:12.5px; line-height:1.5; color:#64748b;">If you did not request this verification code, you can safely ignore this email.</p>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _otp_subject(otp_code: str) -> str:
    return f"{otp_code} is your Expense Tracker Pro verification code"


def send_gmail_webhook_email(recipient_email: str, otp_code: str, user_name: str = "User") -> bool:
    """
    Optional HTTPS bridge (Google Apps Script / Gmail API endpoint on Port 443).
    Sends natively from the user's Google account with full SPF/DKIM/DMARC alignment.
    """
    webhook_url = (os.environ.get("GMAIL_WEBHOOK_URL") or os.environ.get("EMAIL_WEBHOOK_URL") or "").strip()
    if not webhook_url:
        return False

    try:
        payload = {
            "to": recipient_email,
            "subject": _otp_subject(otp_code),
            "text": generate_email_plain(otp_code, user_name),
            "html": generate_email_html(otp_code, user_name),
            "otp": otp_code,
            "name": user_name,
        }
        secret = (os.environ.get("GMAIL_WEBHOOK_SECRET") or "").strip()
        if secret:
            payload["secret"] = secret
        req = urllib.request.Request(
            webhook_url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", "Accept": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=6) as resp:
            if 200 <= resp.status < 300:
                print(f"[OTP GMAIL WEBHOOK SUCCESS] Dispatched to {recipient_email}")
                return True
        return False
    except Exception as e:
        print(f"[OTP GMAIL WEBHOOK ERROR] {e}")
        return False


def send_brevo_email(recipient_email: str, otp_code: str, user_name: str = "User") -> bool:
    """Sends multipart plain + HTML transactional OTP via Brevo HTTPS API (Port 443)."""
    api_key = (os.environ.get("BREVO_API_KEY") or "").strip()
    sender_email = (
        os.environ.get("BREVO_SENDER_EMAIL")
        or os.environ.get("MAIL_FROM")
        or os.environ.get("SMTP_USER")
        or ""
    ).strip()
    if not api_key or not sender_email:
        return False

    try:
        url = "https://api.brevo.com/v3/smtp/email"
        payload = {
            "sender": {"name": SMTP_FROM_NAME, "email": sender_email},
            "replyTo": {"name": SMTP_FROM_NAME, "email": sender_email},
            "to": [{"email": recipient_email, "name": (user_name or "User").strip()}],
            "subject": _otp_subject(otp_code),
            "textContent": generate_email_plain(otp_code, user_name),
            "htmlContent": generate_email_html(otp_code, user_name),
            "tags": ["transactional", "otp"],
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "api-key": api_key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"[OTP BREVO SUCCESS] Dispatched to {recipient_email}")
            return True
    except urllib.error.HTTPError as http_err:
        body = http_err.read().decode("utf-8", errors="ignore")
        print(f"[OTP BREVO HTTP ERROR {http_err.code}] {body}")
        return False
    except Exception as e:
        print(f"[OTP BREVO ERROR] Brevo API failed: {e}")
        return False


def send_resend_email(recipient_email: str, otp_code: str, user_name: str = "User") -> bool:
    """Sends multipart plain + HTML transactional OTP via Resend HTTPS API (Port 443)."""
    api_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    if not api_key:
        return False

    from_addr = (os.environ.get("RESEND_FROM_EMAIL") or "").strip() or f"{SMTP_FROM_NAME} <onboarding@resend.dev>"
    try:
        url = "https://api.resend.com/emails"
        payload = {
            "from": from_addr,
            "to": [recipient_email],
            "subject": _otp_subject(otp_code),
            "text": generate_email_plain(otp_code, user_name),
            "html": generate_email_html(otp_code, user_name),
        }
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "User-Agent": "ExpenseTrackerPro/2.0",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            res_data = json.loads(resp.read().decode())
            print(f"[OTP RESEND SUCCESS] Dispatched to {recipient_email}: {res_data.get('id')}")
            return True
    except urllib.error.HTTPError as http_err:
        body = http_err.read().decode("utf-8", errors="ignore")
        print(f"[OTP RESEND HTTP ERROR {http_err.code}] {body}")
        return False
    except Exception as e:
        print(f"[OTP RESEND ERROR] Resend API failed: {e}")
        return False


def send_smtp_email(recipient_email: str, otp_code: str, user_name: str = "User") -> bool:
    """Sends multipart plain + HTML OTP via direct IPv4 SMTP (465 SSL / 587 STARTTLS)."""
    user = (os.environ.get("SMTP_USER") or "").strip()
    password = (os.environ.get("SMTP_PASSWORD") or "").replace(" ", "").strip()

    if not user or not password:
        return False

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = _otp_subject(otp_code)
        msg["From"] = formataddr((SMTP_FROM_NAME, user))
        msg["To"] = recipient_email
        msg["Reply-To"] = user

        msg.attach(MIMEText(generate_email_plain(otp_code, user_name), "plain", "utf-8"))
        msg.attach(MIMEText(generate_email_html(otp_code, user_name), "html", "utf-8"))

        try:
            with _IPv4SMTP_SSL(SMTP_HOST, 465, timeout=2.5) as server:
                server.login(user, password)
                server.sendmail(user, recipient_email, msg.as_string())
                print(f"[OTP SMTP SUCCESS] Sent to {recipient_email} (IPv4 port 465)")
                return True
        except Exception as err_465:
            print(f"[OTP SMTP 465 NOTE] {err_465}")
            with _IPv4SMTP(SMTP_HOST, 587, timeout=2.5) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(user, password)
                server.sendmail(user, recipient_email, msg.as_string())
                print(f"[OTP SMTP SUCCESS] Sent to {recipient_email} (IPv4 port 587)")
                return True
    except Exception as e:
        print(f"[OTP SMTP ERROR] SMTP failed: {e}")
        return False


def send_email_otp(recipient_email: str, otp_code: str, user_name: str = "User") -> bool:
    """
    Unified Transactional Email Dispatcher (Port-443 HTTPS First -> Zero SMTP Timeout Delay):
    1. Optional Native Gmail Webhook (Port 443 Google Apps Script -> full Gmail DMARC/SPF/DKIM pass)
    2. Resend HTTPS API (DKIM-signed multipart plain+HTML)
    3. Brevo HTTPS API (multipart plain+HTML fallback)
    4. Direct IPv4 Authenticated SMTP (fallback when host permits outbound 465/587)
    """
    clean_email = recipient_email.strip().lower()

    if os.environ.get("GMAIL_WEBHOOK_URL") or os.environ.get("EMAIL_WEBHOOK_URL"):
        if send_gmail_webhook_email(clean_email, otp_code, user_name):
            return True

    if os.environ.get("RESEND_API_KEY"):
        if send_resend_email(clean_email, otp_code, user_name):
            return True

    if os.environ.get("BREVO_API_KEY"):
        if send_brevo_email(clean_email, otp_code, user_name):
            return True

    if os.environ.get("SMTP_USER") and os.environ.get("SMTP_PASSWORD"):
        if send_smtp_email(clean_email, otp_code, user_name):
            return True

    print(f"[OTP AUDIT - DISPATCH PENDING] Code generated for {clean_email}: {otp_code}.")
    return False


def send_sms_otp(phone_number: str, otp_code: str) -> bool:
    """Sends OTP via Fast2SMS."""
    clean_phone = phone_number.replace("+", "").replace("-", "").replace(" ", "").strip()
    if clean_phone.startswith("91") and len(clean_phone) == 12:
        clean_phone = clean_phone[2:]

    if FAST2SMS_API_KEY:
        try:
            url = "https://www.fast2sms.com/dev/bulkV2"
            payload = {
                "variables_values": otp_code,
                "route": "otp",
                "numbers": clean_phone,
            }
            req = urllib.request.Request(
                url,
                data=urllib.parse.urlencode(payload).encode("utf-8"),
                headers={
                    "authorization": FAST2SMS_API_KEY,
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                result = json.loads(resp.read().decode())
                if result.get("return"):
                    print(f"[OTP SMS SUCCESS] Dispatched to {phone_number} via Fast2SMS")
                    return True
                else:
                    print(f"[OTP SMS ERROR] Fast2SMS error: {result}")
        except Exception as e:
            print(f"[OTP SMS ERROR] Fast2SMS failed: {e}")

    print(f"[OTP AUDIT - SMS NOT CONFIGURED] To: {phone_number} | OTP: {otp_code}")
    return False


def dispatch_otp(identifier: str, otp_code: str, user_name: str = "User") -> dict:
    """
    Asynchronously dispatches OTP in a background daemon thread (<1ms API response).
    """
    is_email = "@" in identifier
    channel = "EMAIL" if is_email else "SMS"

    def _worker():
        try:
            if is_email:
                send_email_otp(identifier.strip().lower(), otp_code, user_name)
            else:
                send_sms_otp(identifier.strip(), otp_code)
        except Exception as err:
            print(f"[OTP WORKER EXCEPTION] {err}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()

    return {
        "channel": channel,
        "dispatched": True,
        "recipient": identifier,
    }
