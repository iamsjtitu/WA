"""WapiHub backend — WhatsApp messaging API platform."""
from __future__ import annotations

from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path as PathLib
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
)
import httpx
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from starlette.middleware.cors import CORSMiddleware

import auth as auth_mod
import billing as billing_mod
import wa_client
import wa_supervisor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("wapihub")

mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

app = FastAPI(title="WapiHub API")
api = APIRouter(prefix="/api")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def gen_api_key() -> str:
    return "wapi_" + secrets.token_urlsafe(32)


# ---------------- Models ----------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    name: str = Field(min_length=1, max_length=80)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: str
    email: str
    name: str
    role: str
    api_key: str
    quota_monthly: int
    quota_used: int
    created_at: str
    webhook_url: Optional[str] = None
    webhook_secret: Optional[str] = None
    webhook_disabled: bool = False
    webhook_consecutive_failures: int = 0


class CustomerCreateIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6, max_length=128)
    name: str = Field(min_length=1, max_length=80)
    quota_monthly: int = 1000


class CustomerUpdateIn(BaseModel):
    name: Optional[str] = None
    quota_monthly: Optional[int] = None
    password: Optional[str] = Field(default=None, min_length=6, max_length=128)


class SessionCreateIn(BaseModel):
    name: str = Field(min_length=1, max_length=60)


class SendMessageIn(BaseModel):
    session_id: str
    to: str
    text: str = Field(min_length=1, max_length=4096)


class BulkSendIn(BaseModel):
    session_id: str
    recipients: List[str] = Field(min_length=1, max_length=2000)
    text: str = Field(min_length=1, max_length=4096)


class ApiSendIn(BaseModel):
    session_id: Optional[str] = None
    to: str
    text: Optional[str] = Field(default=None, max_length=4096)
    media_url: Optional[str] = None
    caption: Optional[str] = Field(default=None, max_length=4096)
    file_name: Optional[str] = None


class WebhookSetIn(BaseModel):
    url: str = Field(min_length=8, max_length=500)


class InboundIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    session_id: str
    from_: str = Field(alias="from")
    text: str = ""
    type: str = "text"
    message_id: Optional[str] = None
    timestamp: Optional[int] = None
    has_media: bool = False
    media_path: Optional[str] = None
    mime_type: Optional[str] = None
    file_name: Optional[str] = None


class BulkCsvIn(BaseModel):
    session_id: str
    template: str = Field(min_length=1, max_length=4096)


class WebhookEnableIn(BaseModel):
    pass


# ---------------- Helpers ----------------
async def current_user(request: Request) -> dict:
    return await auth_mod.get_current_user(request, db)


async def admin_only(request: Request) -> dict:
    user = await current_user(request)
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin only")
    return user


def user_to_out(u: dict) -> UserOut:
    return UserOut(
        id=u["id"],
        email=u["email"],
        name=u["name"],
        role=u["role"],
        api_key=u.get("api_key", ""),
        quota_monthly=u.get("quota_monthly", 1000),
        quota_used=u.get("quota_used", 0),
        created_at=u.get("created_at", ""),
        webhook_url=u.get("webhook_url"),
        webhook_secret=u.get("webhook_secret"),
        webhook_disabled=bool(u.get("webhook_disabled", False)),
        webhook_consecutive_failures=int(u.get("webhook_consecutive_failures", 0) or 0),
    )


def normalize_phone(phone: str) -> str:
    return re.sub(r"[^0-9]", "", phone or "")


# ---------------- Webhook helpers ----------------
UPLOAD_DIR = PathLib("/app/wa-service/uploads")
INBOUND_MEDIA_DIR = PathLib("/app/wa-service/uploads/inbound")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
INBOUND_MEDIA_DIR.mkdir(parents=True, exist_ok=True)

WEBHOOK_RETRY_DELAYS = [2, 6, 18]  # seconds — 3 attempts total
WEBHOOK_AUTO_DISABLE_AFTER = 10  # consecutive failures


def public_backend_url() -> str:
    return (
        os.environ.get("BACKEND_PUBLIC_URL")
        or os.environ.get("APP_URL")
        or "http://localhost:8001"
    ).rstrip("/")


def hmac_sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def fire_webhook(user_id: str, payload: dict):
    """Deliver webhook with exponential backoff & auto-disable on persistent failure."""
    user = await db.users.find_one({"id": user_id}, {"_id": 0})
    if not user or not user.get("webhook_url") or user.get("webhook_disabled"):
        return
    url = user["webhook_url"]
    secret = user.get("webhook_secret") or user.get("api_key", "")
    body = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac_sign(secret, body)
    headers = {
        "Content-Type": "application/json",
        "X-Wapihub-Signature": sig,
        "X-Wapihub-Event": payload.get("event", "message.received"),
        "User-Agent": "WapiHub-Webhook/1.0",
    }

    last_error = "delivery failed"
    for attempt, delay in enumerate([0] + WEBHOOK_RETRY_DELAYS):
        if delay:
            await asyncio.sleep(delay)
        try:
            async with httpx.AsyncClient(timeout=10.0) as c:
                r = await c.post(url, content=body, headers=headers)
            if 200 <= r.status_code < 300:
                # success — clear failure counter
                await db.users.update_one(
                    {"id": user_id},
                    {"$set": {"webhook_consecutive_failures": 0}},
                )
                return
            last_error = f"HTTP {r.status_code}"
        except Exception as e:
            last_error = str(e)
        logger.info(
            "webhook attempt %d/%d failed user=%s url=%s err=%s",
            attempt + 1,
            len(WEBHOOK_RETRY_DELAYS) + 1,
            user_id,
            url,
            last_error,
        )

    # all attempts failed — record + maybe disable
    new_count = int(user.get("webhook_consecutive_failures", 0) or 0) + 1
    update: dict = {"$inc": {"webhook_consecutive_failures": 1}}
    if new_count >= WEBHOOK_AUTO_DISABLE_AFTER:
        update["$set"] = {"webhook_disabled": True}
    await db.users.update_one({"id": user_id}, update)
    try:
        await db.webhook_failures.insert_one(
            {
                "id": new_id(),
                "user_id": user_id,
                "url": url,
                "event": payload.get("event"),
                "error": last_error,
                "at": now_iso(),
            }
        )
    except Exception:
        pass


# ---------------- Auth Endpoints ----------------
@api.post("/auth/register")
async def register(payload: RegisterIn, response: Response):
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already registered")

    user_doc = {
        "id": new_id(),
        "email": email,
        "name": payload.name.strip(),
        "password_hash": auth_mod.hash_password(payload.password),
        "role": "customer",
        "api_key": gen_api_key(),
        "quota_monthly": 1000,
        "quota_used": 0,
        "created_at": now_iso(),
    }
    await db.users.insert_one(user_doc)

    access = auth_mod.create_access_token(user_doc["id"], email, "customer")
    refresh = auth_mod.create_refresh_token(user_doc["id"])
    auth_mod.set_auth_cookies(response, access, refresh)

    user_doc.pop("password_hash", None)
    user_doc.pop("_id", None)
    return user_to_out(user_doc)


@api.post("/auth/login")
async def login(payload: LoginIn, response: Response):
    email = payload.email.lower().strip()
    user = await db.users.find_one({"email": email})
    if not user or not auth_mod.verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    access = auth_mod.create_access_token(user["id"], user["email"], user["role"])
    refresh = auth_mod.create_refresh_token(user["id"])
    auth_mod.set_auth_cookies(response, access, refresh)

    user.pop("password_hash", None)
    user.pop("_id", None)
    return user_to_out(user)


@api.post("/auth/logout")
async def logout(response: Response):
    auth_mod.clear_auth_cookies(response)
    return {"ok": True}


@api.get("/auth/me")
async def me(user: dict = Depends(current_user)):
    return user_to_out(user)


@api.post("/auth/refresh")
async def refresh_endpoint(request: Request, response: Response):
    token = request.cookies.get("refresh_token")
    if not token:
        raise HTTPException(status_code=401, detail="No refresh token")
    try:
        payload = auth_mod.decode_token(token)
        if payload.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="Invalid token type")
        user = await db.users.find_one({"id": payload["sub"]})
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        access = auth_mod.create_access_token(user["id"], user["email"], user["role"])
        response.set_cookie(
            key="access_token",
            value=access,
            httponly=True,
            secure=True,
            samesite="none",
            max_age=12 * 3600,
            path="/",
        )
        return {"ok": True}
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid refresh token")


# ---------------- Admin: Customers ----------------
@api.get("/admin/customers")
async def list_customers(_: dict = Depends(admin_only)):
    cursor = db.users.find({"role": "customer"}, {"_id": 0, "password_hash": 0})
    customers = await cursor.to_list(length=1000)
    return [user_to_out(c).model_dump() for c in customers]


@api.post("/admin/customers")
async def create_customer(payload: CustomerCreateIn, _: dict = Depends(admin_only)):
    email = payload.email.lower().strip()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Email already exists")
    doc = {
        "id": new_id(),
        "email": email,
        "name": payload.name.strip(),
        "password_hash": auth_mod.hash_password(payload.password),
        "role": "customer",
        "api_key": gen_api_key(),
        "quota_monthly": int(payload.quota_monthly),
        "quota_used": 0,
        "created_at": now_iso(),
    }
    await db.users.insert_one(doc)
    doc.pop("password_hash", None)
    doc.pop("_id", None)
    return user_to_out(doc)


@api.patch("/admin/customers/{customer_id}")
async def update_customer(
    customer_id: str, payload: CustomerUpdateIn, _: dict = Depends(admin_only)
):
    user = await db.users.find_one({"id": customer_id, "role": "customer"})
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found")
    updates: dict = {}
    if payload.name is not None:
        updates["name"] = payload.name.strip()
    if payload.quota_monthly is not None:
        updates["quota_monthly"] = int(payload.quota_monthly)
    if payload.password:
        updates["password_hash"] = auth_mod.hash_password(payload.password)
    if updates:
        await db.users.update_one({"id": customer_id}, {"$set": updates})
    user = await db.users.find_one({"id": customer_id}, {"_id": 0, "password_hash": 0})
    return user_to_out(user)


@api.delete("/admin/customers/{customer_id}")
async def delete_customer(customer_id: str, _: dict = Depends(admin_only)):
    user = await db.users.find_one({"id": customer_id, "role": "customer"})
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found")
    sessions = await db.wa_sessions.find({"user_id": customer_id}).to_list(length=500)
    for s in sessions:
        try:
            await wa_client.logout_session(s["id"])
        except Exception:
            pass
    await db.wa_sessions.delete_many({"user_id": customer_id})
    await db.messages.delete_many({"user_id": customer_id})
    await db.users.delete_one({"id": customer_id})
    return {"ok": True}


@api.post("/admin/customers/{customer_id}/regenerate-key")
async def regen_key(customer_id: str, _: dict = Depends(admin_only)):
    user = await db.users.find_one({"id": customer_id})
    if not user:
        raise HTTPException(status_code=404, detail="Customer not found")
    new_key = gen_api_key()
    await db.users.update_one({"id": customer_id}, {"$set": {"api_key": new_key}})
    return {"api_key": new_key}


@api.get("/admin/stats")
async def admin_stats(_: dict = Depends(admin_only)):
    customers_count = await db.users.count_documents({"role": "customer"})
    sessions_count = await db.wa_sessions.count_documents({})
    today = datetime.now(timezone.utc).date().isoformat()
    msgs_total = await db.messages.count_documents({})
    msgs_today = await db.messages.count_documents({"sent_at": {"$gte": today}})
    msgs_failed = await db.messages.count_documents({"status": "failed"})
    return {
        "customers": customers_count,
        "sessions": sessions_count,
        "messages_total": msgs_total,
        "messages_today": msgs_today,
        "messages_failed": msgs_failed,
    }


# ---------------- Customer Profile ----------------
@api.post("/me/regenerate-key")
async def regen_my_key(user: dict = Depends(current_user)):
    new_key = gen_api_key()
    await db.users.update_one({"id": user["id"]}, {"$set": {"api_key": new_key}})
    return {"api_key": new_key}


@api.get("/me/stats")
async def my_stats(user: dict = Depends(current_user)):
    sessions_count = await db.wa_sessions.count_documents({"user_id": user["id"]})
    today = datetime.now(timezone.utc).date().isoformat()
    msgs_total = await db.messages.count_documents({"user_id": user["id"]})
    msgs_today = await db.messages.count_documents(
        {"user_id": user["id"], "sent_at": {"$gte": today}}
    )
    msgs_failed = await db.messages.count_documents(
        {"user_id": user["id"], "status": "failed"}
    )
    return {
        "sessions": sessions_count,
        "messages_total": msgs_total,
        "messages_today": msgs_today,
        "messages_failed": msgs_failed,
        "quota_monthly": user.get("quota_monthly", 0),
        "quota_used": user.get("quota_used", 0),
    }


# ---------------- WhatsApp Sessions ----------------
@api.get("/sessions")
async def my_sessions(user: dict = Depends(current_user)):
    cursor = db.wa_sessions.find({"user_id": user["id"]}, {"_id": 0})
    sessions = await cursor.to_list(length=200)
    out = []
    for s in sessions:
        try:
            live = await wa_client.session_status(s["id"])
            s["status"] = live.get("status", s.get("status", "unknown"))
            s["phone"] = live.get("phone") or s.get("phone")
        except Exception:
            s["status"] = "unreachable"
        out.append(s)
    return out


@api.post("/sessions")
async def create_session_endpoint(
    payload: SessionCreateIn, user: dict = Depends(current_user)
):
    sid = new_id()
    doc = {
        "id": sid,
        "user_id": user["id"],
        "name": payload.name.strip(),
        "phone": None,
        "status": "starting",
        "created_at": now_iso(),
    }
    await db.wa_sessions.insert_one(doc)
    try:
        await wa_client.start_session(sid)
    except Exception as e:
        logger.exception("start session failed")
        raise HTTPException(status_code=500, detail=f"WA service error: {e}")
    doc.pop("_id", None)
    return doc


@api.get("/sessions/{session_id}/status")
async def get_session_status(session_id: str, user: dict = Depends(current_user)):
    s = await db.wa_sessions.find_one({"id": session_id, "user_id": user["id"]}, {"_id": 0})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        live = await wa_client.session_status(session_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"WA service error: {e}")
    update = {"status": live.get("status", "unknown")}
    if live.get("phone"):
        update["phone"] = live["phone"]
    await db.wa_sessions.update_one({"id": session_id}, {"$set": update})
    return {**s, **update, "qr": live.get("qr")}


@api.post("/sessions/{session_id}/restart")
async def restart_session(session_id: str, user: dict = Depends(current_user)):
    s = await db.wa_sessions.find_one({"id": session_id, "user_id": user["id"]})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        await wa_client.start_session(session_id)
        return {"ok": True}
    except Exception as e:
        raise HTTPException(status_code=502, detail=str(e))


@api.delete("/sessions/{session_id}")
async def delete_session(session_id: str, user: dict = Depends(current_user)):
    s = await db.wa_sessions.find_one({"id": session_id, "user_id": user["id"]})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    try:
        await wa_client.logout_session(session_id)
    except Exception:
        pass
    await db.wa_sessions.delete_one({"id": session_id})
    return {"ok": True}


# ---------------- Messages (dashboard) ----------------
async def _send_one(user_id: str, session_id: str, to: str, text: str, source: str):
    phone = normalize_phone(to)
    if not phone:
        return {"to": to, "status": "failed", "error": "invalid phone"}
    msg_doc = {
        "id": new_id(),
        "user_id": user_id,
        "session_id": session_id,
        "direction": "outbound",
        "to": phone,
        "text": text,
        "type": "text",
        "has_media": False,
        "status": "queued",
        "error": None,
        "source": source,
        "wa_message_id": None,
        "sent_at": now_iso(),
    }
    try:
        result = await wa_client.send_message(session_id, phone, text)
        msg_doc["status"] = "sent"
        msg_doc["wa_message_id"] = result.get("message_id")
    except Exception as e:
        msg_doc["status"] = "failed"
        msg_doc["error"] = str(e)
    await db.messages.insert_one(msg_doc)
    msg_doc.pop("_id", None)
    return msg_doc


async def _send_media_one(
    user_id: str,
    session_id: str,
    to: str,
    caption: str,
    file_path: str,
    file_name: str,
    mime_type: str,
    source: str,
):
    phone = normalize_phone(to)
    if not phone:
        try:
            PathLib(file_path).unlink(missing_ok=True)
        except Exception:
            pass
        return {"to": to, "status": "failed", "error": "invalid phone"}
    primary = mime_type.split("/")[0] if "/" in mime_type else "document"
    msg_doc = {
        "id": new_id(),
        "user_id": user_id,
        "session_id": session_id,
        "direction": "outbound",
        "to": phone,
        "text": caption or "",
        "status": "queued",
        "type": primary if primary in ("image", "video", "audio") else "document",
        "has_media": True,
        "file_name": file_name,
        "mime_type": mime_type,
        "source": source,
        "sent_at": now_iso(),
        "wa_message_id": None,
        "error": None,
    }
    try:
        result = await wa_client.send_media(
            session_id, phone, file_path, caption or "", file_name, mime_type, True
        )
        msg_doc["status"] = "sent"
        msg_doc["wa_message_id"] = result.get("message_id")
    except Exception as e:
        msg_doc["status"] = "failed"
        msg_doc["error"] = str(e)
        try:
            PathLib(file_path).unlink(missing_ok=True)
        except Exception:
            pass
    await db.messages.insert_one(msg_doc)
    msg_doc.pop("_id", None)
    return msg_doc


async def _enforce_quota(user: dict, count: int):
    used = user.get("quota_used", 0)
    quota = user.get("quota_monthly", 0)
    if quota and used + count > quota:
        raise HTTPException(
            status_code=403,
            detail=f"Quota exceeded ({used}/{quota}). Contact admin to upgrade.",
        )


@api.post("/messages/send")
async def send_message_dashboard(
    payload: SendMessageIn, user: dict = Depends(current_user)
):
    s = await db.wa_sessions.find_one({"id": payload.session_id, "user_id": user["id"]})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    await _enforce_quota(user, 1)
    msg = await _send_one(user["id"], payload.session_id, payload.to, payload.text, "dashboard")
    if msg["status"] == "sent":
        await db.users.update_one({"id": user["id"]}, {"$inc": {"quota_used": 1}})
    return msg


@api.post("/messages/bulk")
async def send_bulk_dashboard(payload: BulkSendIn, user: dict = Depends(current_user)):
    s = await db.wa_sessions.find_one({"id": payload.session_id, "user_id": user["id"]})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    recipients = [r for r in (normalize_phone(x) for x in payload.recipients) if r]
    if not recipients:
        raise HTTPException(status_code=400, detail="No valid recipients")
    await _enforce_quota(user, len(recipients))

    results = []
    sent_count = 0
    for to in recipients:
        msg = await _send_one(user["id"], payload.session_id, to, payload.text, "dashboard_bulk")
        if msg["status"] == "sent":
            sent_count += 1
        results.append({"to": msg["to"], "status": msg["status"], "error": msg.get("error")})
        await asyncio.sleep(0.6)
    if sent_count:
        await db.users.update_one({"id": user["id"]}, {"$inc": {"quota_used": sent_count}})
    return {"total": len(recipients), "sent": sent_count, "failed": len(recipients) - sent_count, "results": results}


@api.post("/messages/send-media")
async def send_media_dashboard(
    session_id: str = Form(...),
    to: str = Form(...),
    caption: str = Form(""),
    media: UploadFile = File(...),
    user: dict = Depends(current_user),
):
    s = await db.wa_sessions.find_one({"id": session_id, "user_id": user["id"]})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")
    await _enforce_quota(user, 1)

    ext = PathLib(media.filename or "file").suffix or ""
    file_path = UPLOAD_DIR / f"{new_id()}{ext}"
    contents = await media.read()
    if len(contents) > 25 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (max 25MB)")
    file_path.write_bytes(contents)
    mime = media.content_type or "application/octet-stream"

    msg = await _send_media_one(
        user["id"],
        session_id,
        to,
        caption,
        str(file_path),
        media.filename or "file",
        mime,
        "dashboard_media",
    )
    if msg["status"] == "sent":
        await db.users.update_one({"id": user["id"]}, {"$inc": {"quota_used": 1}})
    return msg


# ---------------- Webhook (per-user) ----------------
@api.patch("/me/webhook")
async def set_webhook(payload: WebhookSetIn, user: dict = Depends(current_user)):
    if not payload.url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="Webhook URL must start with http:// or https://")
    secret = secrets.token_urlsafe(24)
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"webhook_url": payload.url, "webhook_secret": secret}},
    )
    return {"webhook_url": payload.url, "webhook_secret": secret}


@api.delete("/me/webhook")
async def clear_webhook(user: dict = Depends(current_user)):
    await db.users.update_one(
        {"id": user["id"]},
        {
            "$unset": {
                "webhook_url": "",
                "webhook_secret": "",
                "webhook_disabled": "",
                "webhook_consecutive_failures": "",
            }
        },
    )
    return {"ok": True}


@api.post("/me/webhook/enable")
async def enable_webhook(user: dict = Depends(current_user)):
    """Re-enable webhook after auto-disable from consecutive failures."""
    await db.users.update_one(
        {"id": user["id"]},
        {"$set": {"webhook_disabled": False, "webhook_consecutive_failures": 0}},
    )
    return {"ok": True}


@api.post("/me/webhook/test")
async def test_webhook(user: dict = Depends(current_user)):
    refreshed = await db.users.find_one({"id": user["id"]}, {"_id": 0})
    if not refreshed.get("webhook_url"):
        raise HTTPException(status_code=400, detail="Set a webhook URL first")
    payload = {
        "event": "test",
        "session_id": "test-session",
        "from": "0000000000",
        "text": "WapiHub webhook test event",
        "type": "text",
        "message_id": "test_" + new_id(),
        "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
        "has_media": False,
    }
    await fire_webhook(user["id"], payload)
    return {"sent": True}


# ---------------- Internal: inbound from Node service ----------------
@api.post("/internal/inbound")
async def inbound_message(payload: InboundIn, request: Request):
    expected = os.environ.get("INTERNAL_SECRET", "")
    got = request.headers.get("X-Internal-Secret", "")
    if not expected or got != expected:
        raise HTTPException(status_code=401, detail="invalid internal secret")

    s = await db.wa_sessions.find_one({"id": payload.session_id})
    if not s:
        return {"ok": False, "reason": "session not found"}

    user_id = s["user_id"]
    msg_id = new_id()
    msg_doc = {
        "id": msg_id,
        "user_id": user_id,
        "session_id": payload.session_id,
        "direction": "inbound",
        "from": payload.from_,
        "to": s.get("phone") or "",
        "text": payload.text,
        "type": payload.type,
        "has_media": payload.has_media,
        "media_path": payload.media_path,
        "mime_type": payload.mime_type,
        "file_name": payload.file_name,
        "wa_message_id": payload.message_id,
        "status": "received",
        "source": "inbound",
        "sent_at": now_iso(),
    }
    await db.messages.insert_one(msg_doc)

    media_url = None
    if payload.has_media and payload.media_path:
        media_url = f"{public_backend_url()}/api/media/{msg_id}"

    asyncio.create_task(
        fire_webhook(
            user_id,
            {
                "event": "message.received",
                "session_id": payload.session_id,
                "from": payload.from_,
                "text": payload.text,
                "type": payload.type,
                "message_id": payload.message_id,
                "timestamp": payload.timestamp,
                "has_media": payload.has_media,
                "media_url": media_url,
                "mime_type": payload.mime_type,
                "file_name": payload.file_name,
            },
        )
    )
    return {"ok": True, "id": msg_id}


# ---------------- Inbound media download ----------------
from fastapi.responses import FileResponse  # noqa: E402


@api.get("/media/{message_id}")
async def get_media(message_id: str, request: Request):
    """Serve inbound media. Auth via cookie OR X-API-Key header."""
    user = None
    api_key = request.headers.get("X-API-Key")
    if api_key:
        user = await db.users.find_one(
            {"api_key": api_key}, {"_id": 0, "password_hash": 0}
        )
    if not user:
        try:
            user = await auth_mod.get_current_user(request, db)
        except Exception:
            user = None
    if not user:
        raise HTTPException(status_code=401, detail="auth required (X-API-Key or session)")

    msg = await db.messages.find_one(
        {"id": message_id, "user_id": user["id"]}, {"_id": 0}
    )
    if not msg:
        raise HTTPException(status_code=404, detail="message not found")
    path = msg.get("media_path")
    if not path or not PathLib(path).exists():
        raise HTTPException(status_code=404, detail="media file unavailable")
    return FileResponse(
        path,
        media_type=msg.get("mime_type") or "application/octet-stream",
        filename=msg.get("file_name") or PathLib(path).name,
    )


# ---------------- CSV bulk send ----------------
import csv as _csv  # noqa: E402
import io  # noqa: E402


def _render_template(template: str, row: dict) -> str:
    out = template
    for k, v in row.items():
        out = out.replace("{{" + k + "}}", str(v) if v is not None else "")
    return out


@api.post("/messages/bulk-csv")
async def bulk_csv_send(
    session_id: str = Form(...),
    template: str = Form(...),
    file: UploadFile = File(...),
    user: dict = Depends(current_user),
):
    """CSV must have a header row; first column = phone (or 'phone'), rest are template vars."""
    s = await db.wa_sessions.find_one({"id": session_id, "user_id": user["id"]})
    if not s:
        raise HTTPException(status_code=404, detail="Session not found")

    contents = (await file.read()).decode("utf-8", errors="replace")
    reader = _csv.DictReader(io.StringIO(contents))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV must include a header row")

    phone_key = next(
        (h for h in reader.fieldnames if h.lower() in ("phone", "number", "mobile", "to")),
        reader.fieldnames[0],
    )
    rows = []
    for row in reader:
        phone = normalize_phone(row.get(phone_key, ""))
        if not phone:
            continue
        rows.append({"phone": phone, "row": row})
    if not rows:
        raise HTTPException(status_code=400, detail="No valid rows with phone numbers found")

    await _enforce_quota(user, len(rows))

    sent_count = 0
    failed = 0
    results = []
    for r in rows:
        rendered = _render_template(template, r["row"])
        msg = await _send_one(user["id"], session_id, r["phone"], rendered, "csv_bulk")
        if msg["status"] == "sent":
            sent_count += 1
        else:
            failed += 1
        results.append({"to": msg["to"], "status": msg["status"], "error": msg.get("error")})
        await asyncio.sleep(0.6)
    if sent_count:
        await db.users.update_one({"id": user["id"]}, {"$inc": {"quota_used": sent_count}})
    return {"total": len(rows), "sent": sent_count, "failed": failed, "results": results}


@api.get("/messages")
async def list_messages(
    user: dict = Depends(current_user),
    limit: int = Query(default=100, le=500),
    status: Optional[str] = None,
    direction: Optional[str] = None,
):
    q: dict = {"user_id": user["id"]}
    if status:
        q["status"] = status
    if direction in ("inbound", "outbound"):
        q["direction"] = direction
    cursor = db.messages.find(q, {"_id": 0}).sort("sent_at", -1).limit(limit)
    return await cursor.to_list(length=limit)


# ---------------- Public API (for customers) ----------------
async def user_from_api_key(request: Request) -> dict:
    api_key = request.headers.get("X-API-Key") or request.query_params.get("api_key")
    if not api_key:
        raise HTTPException(status_code=401, detail="X-API-Key header required")
    user = await db.users.find_one({"api_key": api_key}, {"_id": 0, "password_hash": 0})
    if not user:
        raise HTTPException(status_code=401, detail="Invalid API key")
    return user


@api.post("/v1/messages")
async def public_send(payload: ApiSendIn, request: Request):
    user = await user_from_api_key(request)
    if not payload.text and not payload.media_url:
        raise HTTPException(status_code=400, detail="Either text or media_url is required")
    if payload.session_id:
        s = await db.wa_sessions.find_one(
            {"id": payload.session_id, "user_id": user["id"]}
        )
    else:
        s = await db.wa_sessions.find_one({"user_id": user["id"], "status": "connected"})
    if not s:
        raise HTTPException(
            status_code=400,
            detail="No connected WhatsApp session. Link a session first.",
        )
    await _enforce_quota(user, 1)

    if payload.media_url:
        try:
            async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c:
                r = await c.get(payload.media_url)
                r.raise_for_status()
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Failed to fetch media_url: {e}")
        url_path = httpx.URL(payload.media_url).path
        ext = PathLib(url_path).suffix or ""
        file_path = UPLOAD_DIR / f"{new_id()}{ext}"
        file_path.write_bytes(r.content)
        mime = (
            r.headers.get("content-type", "application/octet-stream")
            .split(";")[0]
            .strip()
        )
        msg = await _send_media_one(
            user["id"],
            s["id"],
            payload.to,
            payload.caption or payload.text or "",
            str(file_path),
            payload.file_name or PathLib(url_path).name or "file",
            mime,
            "api_media",
        )
    else:
        msg = await _send_one(user["id"], s["id"], payload.to, payload.text, "api")

    if msg["status"] == "sent":
        await db.users.update_one({"id": user["id"]}, {"$inc": {"quota_used": 1}})
    return {
        "status": msg["status"],
        "message_id": msg.get("wa_message_id"),
        "error": msg.get("error"),
        "to": msg["to"],
    }


@api.get("/v1/sessions")
async def public_sessions(request: Request):
    user = await user_from_api_key(request)
    cursor = db.wa_sessions.find({"user_id": user["id"]}, {"_id": 0})
    return await cursor.to_list(length=100)


# ---------------- Health ----------------
@api.get("/")
async def root():
    return {"service": "WapiHub API", "ok": True}


@api.get("/health")
async def health():
    wa_ok = await wa_client.health()
    return {"api": "ok", "wa_service": "ok" if wa_ok else "down"}


# ---------------- Wire app ----------------
app.include_router(api)
# Billing router (plans, subscriptions, webhooks for stripe/razorpay/paypal)
app.include_router(billing_mod.make_router(db, current_user, admin_only), prefix="/api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"],
)


# ---------------- Startup / Shutdown ----------------
@app.on_event("startup")
async def on_startup():
    wa_supervisor.start()
    logger.info("WA Node service spawned")

    try:
        await db.users.create_index("email", unique=True)
        await db.users.create_index("api_key", unique=True)
        await db.wa_sessions.create_index([("user_id", 1)])
        await db.messages.create_index([("user_id", 1), ("sent_at", -1)])
    except Exception:
        logger.exception("index creation failed (non-fatal)")

    admin_email = os.environ.get("ADMIN_EMAIL", "admin@wapihub.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        await db.users.insert_one(
            {
                "id": new_id(),
                "email": admin_email,
                "name": "Admin",
                "password_hash": auth_mod.hash_password(admin_password),
                "role": "admin",
                "api_key": gen_api_key(),
                "quota_monthly": 1_000_000,
                "quota_used": 0,
                "created_at": now_iso(),
            }
        )
        logger.info("Admin seeded: %s", admin_email)
    else:
        if not auth_mod.verify_password(admin_password, existing["password_hash"]):
            await db.users.update_one(
                {"email": admin_email},
                {"$set": {"password_hash": auth_mod.hash_password(admin_password)}},
            )
            logger.info("Admin password updated from .env")

    try:
        Path("/app/memory").mkdir(parents=True, exist_ok=True)
        Path("/app/memory/test_credentials.md").write_text(
            f"""# Test Credentials

## Admin
- Email: {admin_email}
- Password: {admin_password}
- Role: admin

## Test Customer
- Email: customer@wapihub.com
- Password: customer123
- Role: customer (create via admin panel or POST /api/auth/register)

## Auth Endpoints
- POST /api/auth/register
- POST /api/auth/login
- POST /api/auth/logout
- GET  /api/auth/me

## Public API (for customers)
- POST /api/v1/messages   header: X-API-Key
- GET  /api/v1/sessions   header: X-API-Key
"""
        )
    except Exception:
        logger.exception("could not write test_credentials.md")


@app.on_event("shutdown")
async def on_shutdown():
    wa_supervisor.stop()
    client.close()
