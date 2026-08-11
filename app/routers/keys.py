"""Self-serve API-key issuance via double opt-in.

Flow:
  1. Tally form submission -> POST /keys/request  (this webhook)
       verify Tally HMAC signature -> parse fields -> intent filter ->
       abuse checks -> store a pending key_requests row -> email a verify link.
       NO key exists yet.
  2. User clicks the link  -> GET /keys/verify?token=...
       consume the (unexpired, unconsumed) request -> mint the real key via
       app.keys.generate_key() -> insert into api_keys (active) -> show the
       plaintext key ONCE on an HTML page.

Security notes:
  * The Tally signature is HMAC-SHA256 over the RAW request body. We read
    request.body() before any JSON parsing; re-serialised JSON would not match.
  * The verify token is random (secrets) and stored only as a hash, reusing the
    same hash_key() as the API keys themselves.
  * /keys/request always returns 200 to Tally (so it doesn't retry) and never
    reveals whether an address already has a key.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timezone

from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy import text

from app.database import AsyncSessionLocal
from app.keys import generate_key, hash_key
from app.email import send_verification_email

router = APIRouter(tags=["Keys"], include_in_schema=False)

TALLY_WEBHOOK_SECRET = os.environ.get("TALLY_WEBHOOK_SECRET", "")
PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "https://api.lexicro.com")

# ---- Tally form specifics (from the captured payload) ---------------------
FIELD_EMAIL = "question_915QRG"
FIELD_NAME = "question_QryVvg"
FIELD_USECASE = "question_WodzKJ"
FIELD_INTENT = "question_eAPR0q"
INTENT_REQUEST_KEY = "ea8f8a2f-f487-4978-8a03-56d6d6333a1a"  # "Request an API key"

# ---- abuse backstops ------------------------------------------------------
MAX_PENDING_PER_EMAIL_24H = 3
MAX_PENDING_PER_IP_24H = 5
MAX_RESENDS_PER_EMAIL_24H = 3
MAX_RESENDS_PER_IP_24H = 8


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"


def _fields_by_key(payload: dict) -> dict:
    out = {}
    for f in payload.get("data", {}).get("fields", []):
        out[f.get("key")] = f
    return out


def _wants_key(fields: dict) -> bool:
    f = fields.get(FIELD_INTENT)
    if not f:
        return False
    return INTENT_REQUEST_KEY in (f.get("value") or [])


@router.post("/keys/request")
async def request_key(request: Request):
    # 1. Verify signature over the RAW body BEFORE parsing JSON.
    raw = await request.body()
    if TALLY_WEBHOOK_SECRET:
        sent = request.headers.get("tally-signature", "")
        expected = hmac.new(
            TALLY_WEBHOOK_SECRET.encode("utf-8"), raw, hashlib.sha256
        ).hexdigest()
        # Tally sends base64 in some setups; support both hex and base64.
        import base64
        expected_b64 = base64.b64encode(
            hmac.new(TALLY_WEBHOOK_SECRET.encode("utf-8"), raw, hashlib.sha256).digest()
        ).decode()
        if not (hmac.compare_digest(sent, expected) or hmac.compare_digest(sent, expected_b64)):
            return JSONResponse({"detail": "bad signature"}, status_code=401)

    # 2. Parse and filter.
    import json
    try:
        payload = json.loads(raw)
    except ValueError:
        return JSONResponse({"ok": True}, status_code=200)  # ignore junk quietly

    fields = _fields_by_key(payload)
    if not _wants_key(fields):
        # feedback / partnership / other -> Tally already notifies you; no key.
        return JSONResponse({"ok": True}, status_code=200)

    email = (fields.get(FIELD_EMAIL, {}).get("value") or "").strip().lower()
    name = (fields.get(FIELD_NAME, {}).get("value") or "").strip()
    use_case = fields.get(FIELD_USECASE, {}).get("value")
    if "@" not in email or "." not in email.split("@")[-1]:
        return JSONResponse({"ok": True}, status_code=200)  # not a real address

    ip = _client_ip(request)

    async with AsyncSessionLocal() as db:
        # already has an active key? do nothing, don't leak that fact.
        existing = await db.execute(
            text("SELECT 1 FROM api_keys WHERE email = :e AND active AND revoked_at IS NULL LIMIT 1"),
            {"e": email},
        )
        if existing.first():
            return JSONResponse({"ok": True}, status_code=200)

        # rate-limit pending requests per email and per IP over 24h
        c_email = await db.execute(
            text("SELECT count(*) FROM key_requests WHERE email = :e "
                 "AND created_at > now() - interval '24 hours'"),
            {"e": email},
        )
        c_ip = await db.execute(
            text("SELECT count(*) FROM key_requests WHERE source_ip = :ip "
                 "AND created_at > now() - interval '24 hours'"),
            {"ip": ip},
        )
        if c_email.scalar() >= MAX_PENDING_PER_EMAIL_24H or c_ip.scalar() >= MAX_PENDING_PER_IP_24H:
            return JSONResponse({"ok": True}, status_code=200)  # silently drop

        # mint a verify token; store only its hash
        token = secrets.token_urlsafe(32)
        token_hash = hash_key(token)
        await db.execute(
            text("INSERT INTO key_requests (email, name, use_case, token_hash, source_ip, email_sent_at) "
                 "VALUES (:e, :n, :u, :th, :ip, now())"),
            {"e": email, "n": name or None, "u": use_case, "th": token_hash, "ip": ip},
        )
        await db.commit()

    verify_url = f"{PUBLIC_BASE_URL}/keys/verify?token={token}"
    try:
        await send_verification_email(email, name, verify_url)
    except Exception:
        # request row is stored; a send failure can be retried out of band.
        # Don't 500 to Tally (it would retry the whole submission).
        pass

    return JSONResponse({"ok": True}, status_code=200)


def _page(title: str, body_html: str, status: int = 200) -> HTMLResponse:
    html = f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title></head>
<body style="margin:0;background:#f4f4f2;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif;color:#2c2c2a;">
<div style="max-width:560px;margin:48px auto;background:#fff;border:1px solid #e3e1d9;border-radius:10px;overflow:hidden;">
<div style="background:#0F6E56;padding:18px 26px;color:#fff;font-size:20px;font-weight:700;">LexicRo</div>
<div style="padding:26px;line-height:1.55;font-size:15px;">{body_html}</div></div></body></html>"""
    return HTMLResponse(html, status_code=status)


@router.get("/keys/verify")
async def verify_key(token: str = ""):
    if not token:
        return _page("Invalid link", "<p>This verification link is missing its token.</p>", 400)

    token_hash = hash_key(token)
    async with AsyncSessionLocal() as db:
        row = (await db.execute(
            text("SELECT id, email, tier, daily_limit, consumed_at, expires_at "
                 "FROM key_requests WHERE token_hash = :th"),
            {"th": token_hash},
        )).first()

        if not row:
            return _page("Invalid link",
                         "<p>This link isn't valid. Please "
                         "<a href='https://tally.so/r/GxBBbz'>request a new key</a>.</p>", 404)
        if row.consumed_at is not None:
            return _page("Already used",
                         "<p>This link has already been used. If you didn't save your key, "
                         "<a href='https://tally.so/r/GxBBbz'>request a new one</a>.</p>", 410)
        if row.expires_at < datetime.now(timezone.utc):
            return _page("Link expired",
                         "<p>This link has expired. "
                         "<a href='/keys/resend'>Get a fresh verification link</a> "
                         "sent to the same address.</p>", 410)

        # mint the real key now
        newkey = generate_key()
        await db.execute(
            text("INSERT INTO api_keys (email, tier, daily_limit, active, key_hash, key_prefix, label) "
                 "VALUES (:e, :t, :dl, true, :kh, :kp, 'self-serve')"),
            {"e": row.email, "t": row.tier, "dl": row.daily_limit,
             "kh": newkey.key_hash, "kp": newkey.key_prefix},
        )
        await db.execute(
            text("UPDATE key_requests SET consumed_at = now() WHERE id = :id"),
            {"id": row.id},
        )
        await db.commit()

    body = f"""
    <p style="margin:0 0 14px;">Your email is confirmed. Here is your API key —
    <strong>copy it now, it is shown only once</strong> and can't be recovered.</p>
    <p style="margin:0 0 6px;color:#5f5e5a;font-size:13px;">Your API key</p>
    <div style="font-family:ui-monospace,Menlo,Consolas,monospace;font-size:15px;
        background:#f4f4f2;border:1px solid #e3e1d9;border-radius:6px;padding:14px;
        word-break:break-all;">{newkey.secret}</div>
    <p style="margin:16px 0 0;font-size:14px;">Send it in the <code>X-API-Key</code> header.
    Full docs at <a href="https://api.lexicro.com/guide">api.lexicro.com/guide</a>.</p>
    """
    return _page("Your API key", body)


@router.post("/keys/resend")
async def resend_verification(request: Request, email: str = Form(...)):
    """Re-send the verification link for a pending request. Neutral response
    always — does not reveal whether the address has a pending request."""
    email = (email or "").strip().lower()
    ip = _client_ip(request)

    neutral = _page(
        "Check your inbox",
        "<p>If that address has a pending key request, we've re-sent the "
        "verification link. It can take a minute to arrive — check spam too.</p>"
        "<p style='color:#5f5e5a;font-size:13px;'>Still nothing after a few "
        "minutes? <a href='https://tally.so/r/GxBBbz'>Start a new request</a>.</p>",
    )

    if "@" not in email or "." not in email.split("@")[-1]:
        return neutral  # invalid address — same neutral page, no work done

    async with AsyncSessionLocal() as db:
        # resend rate limits — count recent email_sent_at bumps
        c_email = await db.execute(
            text("SELECT count(*) FROM key_requests WHERE email = :e "
                 "AND email_sent_at > now() - interval '24 hours'"),
            {"e": email},
        )
        c_ip = await db.execute(
            text("SELECT count(*) FROM key_requests WHERE source_ip = :ip "
                 "AND email_sent_at > now() - interval '24 hours'"),
            {"ip": ip},
        )
        if c_email.scalar() >= MAX_RESENDS_PER_EMAIL_24H or c_ip.scalar() >= MAX_RESENDS_PER_IP_24H:
            return neutral  # silently drop over the cap

        # find the most recent unconsumed request for this email
        row = (await db.execute(
            text("SELECT id, name, expires_at FROM key_requests "
                 "WHERE email = :e AND consumed_at IS NULL "
                 "ORDER BY created_at DESC LIMIT 1"),
            {"e": email},
        )).first()

        if not row:
            return neutral  # nothing pending — don't reveal that

        # if expired, roll a fresh token and extend; else reuse the live token
        # by minting a new one and replacing (old link stops working, which is
        # fine — the user is asking for a new link anyway).
        token = secrets.token_urlsafe(32)
        await db.execute(
            text("UPDATE key_requests SET token_hash = :th, "
                 "expires_at = now() + interval '24 hours', email_sent_at = now() "
                 "WHERE id = :id"),
            {"th": hash_key(token), "id": row.id},
        )
        await db.commit()
        name = row.name or ""

    verify_url = f"{PUBLIC_BASE_URL}/keys/verify?token={token}"
    try:
        await send_verification_email(email, name, verify_url)
    except Exception:
        pass  # neutral either way; row is updated, can be retried

    return neutral


@router.get("/keys/resend")
async def resend_form():
    """Tiny public page to request a fresh verification link."""
    body = """
    <p style="margin:0 0 14px;">Didn't get your verification email? Enter your
    address and we'll re-send the link.</p>
    <form method="post" action="/keys/resend" style="margin:0;">
      <input type="email" name="email" required placeholder="you@example.com"
        style="width:100%;box-sizing:border-box;padding:11px;border:1px solid #d3d1c7;
        border-radius:6px;font-size:15px;margin-bottom:12px;">
      <button type="submit" style="background:#0F6E56;color:#fff;border:0;
        padding:11px 22px;border-radius:6px;font-weight:600;font-size:15px;
        cursor:pointer;">Re-send verification link</button>
    </form>
    """
    return _page("Re-send verification", body)
