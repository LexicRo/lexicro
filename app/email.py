"""Transactional email via Resend.

Only used for the key-verification double-opt-in flow. Every send includes BOTH
an HTML part and a plain-text alternative: some clients render text-only, and a
message with only an HTML part scores slightly worse with spam filters.

Config comes from the environment, never code:
  RESEND_API_KEY   - from the Resend dashboard
  EMAIL_FROM       - e.g. "LexicRo <noreply@lexicro.com>"  (domain must be
                     verified in Resend with SPF/DKIM on lexicro.com)
"""

from __future__ import annotations

import os
import httpx

RESEND_API_URL = "https://api.resend.com/emails"
RESEND_API_KEY = os.environ.get("RESEND_API_KEY", "")
EMAIL_FROM = os.environ.get("EMAIL_FROM", "LexicRo <noreply@lexicro.com>")

# Inline CSS only — external stylesheets and web fonts are stripped by many
# clients. Keep it simple and it renders everywhere.
_VERIFY_HTML = """\
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#f4f4f2;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f2;padding:32px 0;">
      <tr><td align="center">
        <table role="presentation" width="480" cellpadding="0" cellspacing="0" style="background:#ffffff;border-radius:10px;overflow:hidden;border:1px solid #e3e1d9;">
          <tr><td style="background:#0F6E56;padding:20px 28px;">
            <span style="color:#ffffff;font-size:20px;font-weight:700;letter-spacing:0.2px;">LexicRo</span>
          </td></tr>
          <tr><td style="padding:28px;color:#2c2c2a;font-size:15px;line-height:1.55;">
            <p style="margin:0 0 14px;">Hi {name},</p>
            <p style="margin:0 0 14px;">You requested an API key for the LexicRo Romanian analysis API. Confirm your email address to generate it:</p>
            <p style="margin:22px 0;text-align:center;">
              <a href="{verify_url}" style="background:#0F6E56;color:#ffffff;text-decoration:none;padding:12px 26px;border-radius:6px;font-weight:600;font-size:15px;display:inline-block;">Confirm &amp; get my key</a>
            </p>
            <p style="margin:0 0 14px;color:#5f5e5a;font-size:13px;">Your key is shown once, on the page this link opens — save it then, it isn't recoverable. The link is valid for 24 hours.</p>
            <p style="margin:0;color:#5f5e5a;font-size:13px;">If you didn't request this, ignore this email — no key is created until the link is clicked.</p>
          </td></tr>
          <tr><td style="padding:16px 28px;border-top:1px solid #eeece5;color:#8a897f;font-size:12px;">
            api.lexicro.com &middot; you're receiving this because someone entered this address on the LexicRo access form.
          </td></tr>
        </table>
      </td></tr>
    </table>
  </body>
</html>
"""

_VERIFY_TEXT = """\
Hi {name},

You requested an API key for the LexicRo Romanian analysis API.
Confirm your email address to generate it:

{verify_url}

Your key is shown once, on the page this link opens - save it then, it
isn't recoverable. The link is valid for 24 hours.

If you didn't request this, ignore this email - no key is created until
the link is clicked.

api.lexicro.com
"""


async def send_verification_email(to: str, name: str, verify_url: str) -> None:
    """Send the double-opt-in verification email. Raises on transport failure so
    the caller can decide whether to surface it; the request row is already
    stored, so a failed send can be retried without losing the pending request."""
    display_name = (name or "there").strip() or "there"
    payload = {
        "from": EMAIL_FROM,
        "to": [to],
        "subject": "Confirm your LexicRo API key request",
        "html": _VERIFY_HTML.format(name=display_name, verify_url=verify_url),
        "text": _VERIFY_TEXT.format(name=display_name, verify_url=verify_url),
    }
    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=10.0) as client:
        resp = await client.post(RESEND_API_URL, json=payload, headers=headers)
        resp.raise_for_status()
