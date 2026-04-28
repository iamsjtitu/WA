"""Email service via Resend — async/non-blocking transactional emails.

Provides 4 templates wired to product events:
  - notify_disconnect     — WhatsApp service disconnected
  - notify_reconnect      — WhatsApp service reconnected
  - notify_quota_warning  — quota usage crosses 90%
  - notify_payment_failed — billing webhook reports payment failure

Templates are inline-CSS HTML, brand-tinted (#1FA855), with the user dashboard
URL injected. All sends honour the user's `email_notifications` flag (default
True). Failures are swallowed and logged so they never break product flows.
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

logger = logging.getLogger("wa9x.email")

try:
    import resend  # type: ignore
except ImportError:
    resend = None


# Resend free tier allows 2 req/s; queue sends with a small gap to stay under it.
_send_lock = asyncio.Lock()
_last_send_at: list[float] = [0.0]
_MIN_GAP_SECONDS = 0.6


def _api_key() -> Optional[str]:
    return os.environ.get("RESEND_API_KEY", "").strip() or None


def _from_address() -> str:
    return os.environ.get("EMAIL_FROM", "wa.9x.design <noreply@9x.design>")


def _frontend_url() -> str:
    return (
        os.environ.get("FRONTEND_URL")
        or os.environ.get("BACKEND_PUBLIC_URL")
        or "https://wa.9x.design"
    ).rstrip("/")


def is_configured() -> bool:
    return bool(_api_key()) and resend is not None


# ---------------- Low-level send ----------------
async def send_email(
    to: str, subject: str, html: str, *, text: Optional[str] = None
) -> bool:
    """Send a single email through Resend. Returns True on success."""
    if not is_configured():
        logger.info("email skipped (Resend not configured): to=%s subject=%s", to, subject)
        return False
    resend.api_key = _api_key()
    params = {
        "from": _from_address(),
        "to": [to],
        "subject": subject,
        "html": html,
    }
    if text:
        params["text"] = text
    try:
        async with _send_lock:
            import time

            wait = _MIN_GAP_SECONDS - (time.monotonic() - _last_send_at[0])
            if wait > 0:
                await asyncio.sleep(wait)
            result = await asyncio.to_thread(resend.Emails.send, params)
            _last_send_at[0] = time.monotonic()
        logger.info("email sent to=%s id=%s", to, (result or {}).get("id"))
        return True
    except Exception as e:  # noqa: BLE001
        logger.warning("email send failed to=%s err=%s", to, e)
        return False


# ---------------- Shared HTML chrome ----------------
_BASE_CSS_BLOCK = """
font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
line-height: 1.55; color: #1a1a1a; max-width: 560px; margin: 0 auto;
"""


def _wrap(title: str, body_html: str, cta_url: str, cta_label: str) -> str:
    return f"""
<div style="background:#f5f5f5; padding:32px 16px;">
  <div style="{_BASE_CSS_BLOCK} background:#ffffff; border:1px solid #e5e5e5; border-radius:0; padding:32px;">
    <div style="display:flex; align-items:center; gap:8px; margin-bottom:24px;">
      <div style="width:32px; height:32px; background:#1FA855; display:flex; align-items:center; justify-content:center;">
        <span style="color:#fff; font-weight:700; font-size:14px;">W</span>
      </div>
      <span style="font-weight:700; font-size:18px; letter-spacing:-0.01em;">wa.9x.design</span>
    </div>
    <h1 style="margin:0 0 16px 0; font-size:22px; font-weight:700; letter-spacing:-0.01em;">{title}</h1>
    {body_html}
    <div style="margin-top:28px;">
      <a href="{cta_url}" style="display:inline-block; background:#1FA855; color:#ffffff !important; text-decoration:none; padding:12px 22px; font-weight:600; font-size:14px;">{cta_label}</a>
    </div>
    <p style="margin-top:32px; padding-top:20px; border-top:1px solid #e5e5e5; font-size:12px; color:#777;">
      This is an automated notification from wa.9x.design. To stop receiving these emails, visit your
      <a href="{_frontend_url()}/app/settings" style="color:#1FA855;">notification settings</a>.
    </p>
  </div>
</div>"""


# ---------------- High-level templates ----------------
async def notify_disconnect(user: dict, session_name: str = "Your service") -> bool:
    if not user or not user.get("email_notifications", True):
        return False
    name = user.get("name") or "there"
    body = f"""
<p>Dear {name},</p>
<p><strong>{session_name}</strong> has been disconnected from WhatsApp.</p>
<p>This problem will cause your messages not to be sent. Please go to your user
panel and re-link this service to WhatsApp to resume sending.</p>
"""
    html = _wrap(
        title="Service Disconnected",
        body_html=body,
        cta_url=f"{_frontend_url()}/app/sessions",
        cta_label="Reconnect now",
    )
    return await send_email(user["email"], "[wa.9x.design] Service disconnected", html)


async def notify_reconnect(user: dict, session_name: str = "Your service") -> bool:
    if not user or not user.get("email_notifications", True):
        return False
    name = user.get("name") or "there"
    body = f"""
<p>Hi {name},</p>
<p>Good news — <strong>{session_name}</strong> is back online and connected to WhatsApp.
Your messages will now be sent normally.</p>
"""
    html = _wrap(
        title="Service Reconnected",
        body_html=body,
        cta_url=f"{_frontend_url()}/app/sessions",
        cta_label="Open dashboard",
    )
    return await send_email(user["email"], "[wa.9x.design] Service reconnected", html)


async def notify_quota_warning(user: dict, used: int, total: int) -> bool:
    if not user or not user.get("email_notifications", True):
        return False
    name = user.get("name") or "there"
    pct = int(round((used / total) * 100)) if total else 0
    body = f"""
<p>Hi {name},</p>
<p>You have used <strong>{used:,} of {total:,}</strong> messages
({pct}%) this billing cycle.</p>
<p>Once you reach 100%, message sending will be paused until your quota resets
or you upgrade your plan.</p>
"""
    html = _wrap(
        title="You are approaching your quota",
        body_html=body,
        cta_url=f"{_frontend_url()}/app/billing",
        cta_label="Upgrade plan",
    )
    return await send_email(user["email"], "[wa.9x.design] 90% of monthly quota used", html)


async def notify_payment_failed(
    user: dict, plan_name: str = "your plan", reason: str = ""
) -> bool:
    if not user or not user.get("email_notifications", True):
        return False
    name = user.get("name") or "there"
    reason_block = (
        f"<p style='color:#b91c1c; font-family:ui-monospace,monospace; font-size:13px;'>"
        f"Reason: {reason}</p>"
        if reason
        else ""
    )
    body = f"""
<p>Dear {name},</p>
<p>We were unable to charge your payment method for <strong>{plan_name}</strong>.</p>
{reason_block}
<p>To avoid service interruption, please update your payment details or retry
the payment from the billing page.</p>
"""
    html = _wrap(
        title="Payment Failed",
        body_html=body,
        cta_url=f"{_frontend_url()}/app/billing",
        cta_label="Update payment",
    )
    return await send_email(user["email"], "[wa.9x.design] Payment failed — action required", html)


# ---------------- Fire-and-forget wrappers ----------------
def schedule(coro):
    """Schedule a coroutine without awaiting (use inside async or sync code)."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(coro)
        else:
            loop.run_until_complete(coro)
    except RuntimeError:
        # No running loop — run synchronously
        asyncio.run(coro)
