"""v2 API — drop-in compatible legacy endpoints.

Bearer auth, multipart bodies, identical response shapes for easy migration
of any existing WhatsApp-API integrations. Path: /api/v2/*
"""
from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path as PathLib
from typing import Optional

import httpx
from fastapi import APIRouter, Form, HTTPException, Request, Response, UploadFile, File

logger = logging.getLogger("wa9x.v2")
UPLOAD_DIR = PathLib("/app/wa-service/uploads")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def now_ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_id() -> str:
    return str(uuid.uuid4())


def normalize_phone(phone: str) -> str:
    return re.sub(r"[^0-9]", "", phone or "")


def v2_ok(data: dict, status: int = 201) -> dict:
    return {
        "success": True,
        "statusCode": status,
        "timestamp": now_ts(),
        "data": data,
    }


def v2_err(message: str, status: int = 400) -> dict:
    return {
        "success": False,
        "statusCode": status,
        "timestamp": now_ts(),
        "error": message,
    }


def parse_delay(delay_str: str) -> Optional[datetime]:
    """wa.9x.design delay format: 'MM-DD-YYYY HH:MM' in GMT."""
    if not delay_str:
        return None
    try:
        dt = datetime.strptime(delay_str.strip(), "%m-%d-%Y %H:%M")
        return dt.replace(tzinfo=timezone.utc)
    except ValueError:
        try:
            # ISO fallback
            return datetime.fromisoformat(delay_str.replace("Z", "+00:00"))
        except Exception:
            return None


def make_router(db, wa_client, fire_webhook, send_one, send_media_one, enforce_quota):
    api = APIRouter()

    async def user_from_bearer(request: Request) -> dict:
        # Accept Authorization: Bearer {api_key} OR X-API-Key OR ?token=
        token = None
        ah = request.headers.get("Authorization", "")
        if ah.startswith("Bearer "):
            token = ah[7:].strip()
        if not token:
            token = request.headers.get("X-API-Key")
        if not token:
            token = request.query_params.get("token")
        if not token:
            raise HTTPException(status_code=401, detail="Bearer token required")
        user = await db.users.find_one(
            {"api_key": token}, {"_id": 0, "password_hash": 0}
        )
        if not user:
            raise HTTPException(status_code=401, detail="Invalid API token")
        return user

    async def _resolve_session(user_id: str) -> dict:
        s = await db.wa_sessions.find_one(
            {"user_id": user_id, "status": "connected"}, {"_id": 0}
        )
        if not s:
            raise HTTPException(
                status_code=400,
                detail="No connected WhatsApp session. Link a session first.",
            )
        return s

    async def _maybe_apply_country_code(session: dict, phone: str) -> str:
        cc = (session.get("default_country_code") or "").strip().lstrip("+")
        if (
            session.get("auto_prefix")
            and cc
            and phone
            and not phone.startswith(cc)
            and len(phone) <= 11  # heuristic: short number → likely missing CC
        ):
            return cc + phone
        return phone

    # ------------ v2 / sendMessage ------------
    @api.post("/v2/sendMessage", status_code=201)
    async def send_message_v2(
        request: Request,
        response: Response,
        phonenumber: str = Form(...),
        text: str = Form(""),
        url: str = Form(""),
        delay: str = Form(""),
    ):
        user = await user_from_bearer(request)
        session = await _resolve_session(user["id"])
        phone = normalize_phone(phonenumber)
        phone = await _maybe_apply_country_code(session, phone)
        if not phone:
            raise HTTPException(status_code=400, detail="Invalid phonenumber")
        if not text and not url:
            raise HTTPException(
                status_code=400, detail="Either text or url is required"
            )

        # Schedule path
        if delay:
            when = parse_delay(delay)
            if when is None:
                raise HTTPException(status_code=400, detail="Invalid delay format. Use 'MM-DD-YYYY HH:MM' (GMT)")
            if when <= datetime.now(timezone.utc):
                raise HTTPException(status_code=400, detail="delay must be in the future")
            sched_id = new_id()
            await db.scheduled_messages.insert_one(
                {
                    "id": sched_id,
                    "user_id": user["id"],
                    "session_id": session["id"],
                    "type": "message",
                    "target": phone,
                    "text": text,
                    "url": url or None,
                    "run_at": when.isoformat(),
                    "status": "pending",
                    "source": "v2_api",
                    "created_at": now_iso(),
                }
            )
            return v2_ok({"phonenumber": phone, "id": sched_id, "scheduled_for": when.isoformat()}, 201)

        # Immediate send
        await enforce_quota(user, 1)
        if url:
            try:
                async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as c:
                    r = await c.get(url)
                    r.raise_for_status()
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to fetch url: {e}")
            url_path = httpx.URL(url).path
            ext = PathLib(url_path).suffix or ""
            file_path = UPLOAD_DIR / f"{new_id()}{ext}"
            file_path.write_bytes(r.content)
            mime = (
                r.headers.get("content-type", "application/octet-stream")
                .split(";")[0]
                .strip()
            )
            msg = await send_media_one(
                user["id"],
                session["id"],
                phone,
                text or "",
                str(file_path),
                PathLib(url_path).name or "file",
                mime,
                "v2_api",
            )
        else:
            msg = await send_one(user["id"], session["id"], phone, text, "v2_api")

        if msg["status"] == "sent":
            await db.users.update_one(
                {"id": user["id"]}, {"$inc": {"quota_used": 1}}
            )
        if msg["status"] == "sent":
            return v2_ok({"phonenumber": phone, "id": msg["id"]}, 201)
        return {
            "success": False,
            "statusCode": 400,
            "timestamp": now_ts(),
            "error": msg.get("error") or "send failed",
            "data": {"phonenumber": phone, "id": msg["id"]},
        }

    # ------------ v2 / sendGroup ------------
    @api.post("/v2/sendGroup")
    async def send_group_v2(
        request: Request,
        groupId: str = Form(...),
        text: str = Form(""),
        url: str = Form(""),
        delay: str = Form(""),
    ):
        user = await user_from_bearer(request)
        session = await _resolve_session(user["id"])
        gid_clean = re.sub(r"[^0-9A-Za-z\-]", "", groupId or "")
        if not gid_clean:
            raise HTTPException(status_code=400, detail="Invalid groupId")

        when = parse_delay(delay) if delay else None
        if when and when > datetime.now(timezone.utc):
            sched_id = new_id()
            await db.scheduled_messages.insert_one(
                {
                    "id": sched_id,
                    "user_id": user["id"],
                    "session_id": session["id"],
                    "type": "group",
                    "target": gid_clean,
                    "text": text,
                    "url": url or None,
                    "run_at": when.isoformat(),
                    "status": "pending",
                    "source": "v2_api",
                    "created_at": now_iso(),
                }
            )
            return v2_ok({"groupId": gid_clean, "id": sched_id, "scheduled_for": when.isoformat()}, 201)

        await enforce_quota(user, 1)
        msg_id = new_id()
        try:
            result = await wa_client.send_group(session["id"], gid_clean, text, url or None)
            await db.messages.insert_one(
                {
                    "id": msg_id,
                    "user_id": user["id"],
                    "session_id": session["id"],
                    "direction": "outbound",
                    "to": gid_clean,
                    "text": text,
                    "type": "group",
                    "has_media": bool(url),
                    "status": "sent",
                    "source": "v2_api",
                    "wa_message_id": result.get("message_id"),
                    "sent_at": now_iso(),
                    "is_group": True,
                }
            )
            await db.users.update_one(
                {"id": user["id"]}, {"$inc": {"quota_used": 1}}
            )
            return v2_ok({"groupId": gid_clean, "id": msg_id}, 201)
        except Exception as e:
            await db.messages.insert_one(
                {
                    "id": msg_id,
                    "user_id": user["id"],
                    "session_id": session["id"],
                    "direction": "outbound",
                    "to": gid_clean,
                    "text": text,
                    "status": "failed",
                    "error": str(e),
                    "is_group": True,
                    "source": "v2_api",
                    "sent_at": now_iso(),
                }
            )
            return {
                "success": False,
                "statusCode": 400,
                "timestamp": now_ts(),
                "error": str(e),
                "data": {"groupId": gid_clean, "id": msg_id},
            }

    # ------------ v2 / message / status ------------
    @api.get("/v2/message/status")
    async def message_status_v2(request: Request, id: str):
        user = await user_from_bearer(request)
        # check messages collection
        msg = await db.messages.find_one(
            {"id": id, "user_id": user["id"]}, {"_id": 0}
        )
        if msg:
            status_map = {
                "sent": ("OK", "message successfully sent.", "device"),
                "failed": ("FAILED", msg.get("error") or "send failed", "not delivered"),
                "queued": ("QUEUED", "queued for delivery", "queued"),
            }
            status, info, delivery = status_map.get(
                msg.get("status", ""), ("UNKNOWN", "unknown state", "unknown")
            )
            return {
                "success": True,
                "result": {
                    "status": status,
                    "statusInfo": info,
                    "delivery": delivery,
                    "id": msg["id"],
                    "text": msg.get("text", ""),
                    "phonenumber": msg.get("to", ""),
                    "createdAt": msg.get("sent_at", ""),
                    "executedAt": msg.get("sent_at", ""),
                    "url": msg.get("media_url") or "",
                },
                "statusCode": 200,
                "timestamp": now_ts(),
            }
        # check scheduled_messages
        sched = await db.scheduled_messages.find_one(
            {"id": id, "user_id": user["id"]}, {"_id": 0}
        )
        if sched:
            return {
                "success": True,
                "result": {
                    "status": "SCHEDULED" if sched["status"] == "pending" else sched["status"].upper(),
                    "statusInfo": "scheduled for future delivery",
                    "delivery": "scheduled",
                    "id": sched["id"],
                    "text": sched.get("text", ""),
                    "phonenumber": sched.get("target", ""),
                    "createdAt": sched.get("created_at", ""),
                    "executedAt": sched.get("run_at", ""),
                    "url": sched.get("url") or "",
                },
                "statusCode": 200,
                "timestamp": now_ts(),
            }
        raise HTTPException(status_code=404, detail="Message not found")

    # ------------ v2 / message / sentMessages ------------
    @api.get("/v2/message/sentMessages")
    async def sent_messages_v2(
        request: Request, page: int = 1, phonenumber: str = ""
    ):
        user = await user_from_bearer(request)
        page = max(1, int(page))
        per_page = 50
        q: dict = {"user_id": user["id"], "direction": "outbound"}
        if phonenumber:
            q["to"] = {"$regex": re.escape(normalize_phone(phonenumber))}
        total = await db.messages.count_documents(q)
        cursor = (
            db.messages.find(q, {"_id": 0})
            .sort("sent_at", -1)
            .skip((page - 1) * per_page)
            .limit(per_page)
        )
        rows = await cursor.to_list(length=per_page)
        page_count = max(1, (total + per_page - 1) // per_page)
        data = []
        for m in rows:
            status_map = {
                "sent": ("OK", "message successfully sent.", "device"),
                "failed": ("FAILED", m.get("error") or "send failed", "not delivered"),
                "queued": ("QUEUED", "queued", "queued"),
            }
            st, info, dlv = status_map.get(
                m.get("status", ""), ("UNKNOWN", "unknown", "unknown")
            )
            data.append(
                {
                    "status": st,
                    "statusInfo": info,
                    "delivery": dlv,
                    "id": m["id"],
                    "text": m.get("text", ""),
                    "phonenumber": m.get("to", ""),
                    "createdAt": m.get("sent_at", ""),
                    "executedAt": m.get("sent_at", ""),
                    "url": m.get("media_url") or "",
                }
            )
        return {
            "success": True,
            "result": {
                "count": total,
                "pageCount": page_count,
                "page": f"{page} of {page_count}",
                "data": data,
            },
            "statusCode": 200,
            "timestamp": now_ts(),
        }

    # ------------ v2 / message / receivedMessages ------------
    @api.get("/v2/message/receivedMessages")
    async def received_messages_v2(
        request: Request, page: int = 1, phonenumber: str = ""
    ):
        user = await user_from_bearer(request)
        page = max(1, int(page))
        per_page = 50
        q: dict = {"user_id": user["id"], "direction": "inbound"}
        if phonenumber:
            q["from"] = {"$regex": re.escape(normalize_phone(phonenumber))}
        total = await db.messages.count_documents(q)
        cursor = (
            db.messages.find(q, {"_id": 0})
            .sort("sent_at", -1)
            .skip((page - 1) * per_page)
            .limit(per_page)
        )
        rows = await cursor.to_list(length=per_page)
        page_count = max(1, (total + per_page - 1) // per_page)
        data = [
            {
                "id": m["id"],
                "text": m.get("text", ""),
                "phonenumber": m.get("from", ""),
                "type": m.get("type", "text"),
                "hasMedia": bool(m.get("has_media")),
                "mimeType": m.get("mime_type"),
                "fileName": m.get("file_name"),
                "createdAt": m.get("sent_at", ""),
            }
            for m in rows
        ]
        return {
            "success": True,
            "result": {
                "count": total,
                "pageCount": page_count,
                "page": f"{page} of {page_count}",
                "data": data,
            },
            "statusCode": 200,
            "timestamp": now_ts(),
        }

    # ------------ Account ping ------------
    @api.get("/v2/account")
    async def account_v2(request: Request):
        user = await user_from_bearer(request)
        sub = await db.subscriptions.find_one(
            {"user_id": user["id"], "status": "active"}, {"_id": 0}
        )
        plan = (
            await db.plans.find_one({"id": sub["plan_id"]}, {"_id": 0}) if sub else None
        )
        sessions = await db.wa_sessions.count_documents({"user_id": user["id"]})
        return {
            "success": True,
            "result": {
                "name": user.get("name"),
                "email": user.get("email"),
                "plan": plan.get("name") if plan else "Free",
                "quota_monthly": user.get("quota_monthly", 0),
                "quota_used": user.get("quota_used", 0),
                "sessions": sessions,
                "expires_at": sub.get("current_period_end") if sub else None,
            },
            "statusCode": 200,
            "timestamp": now_ts(),
        }

    return api
