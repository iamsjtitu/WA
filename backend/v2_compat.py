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
        "error": "",
        "data": data,
    }


def v2_err(message: str, status: int = 400) -> dict:
    return {
        "success": False,
        "statusCode": status,
        "timestamp": now_ts(),
        "error": message,
    }

_GROUP_ID_PATTERN = re.compile(r"^(\d+)(?:@g\.us)?$")


def normalize_group_id(group_id: str) -> tuple[str, str]:
    """Accept either '120363xxx' or '120363xxx@g.us' and return (digits, jid).

    Raises HTTPException(400) with a clear message on invalid input.
    """
    raw = (group_id or "").strip()
    m = _GROUP_ID_PATTERN.match(raw)
    if not m:
        raise HTTPException(
            status_code=400,
            detail="Invalid groupId format. Expected <number>@g.us",
        )
    digits = m.group(1)
    return digits, f"{digits}@g.us"


# WhatsApp 100 MB cap on outbound media.
MAX_FILE_SIZE_BYTES = 100 * 1024 * 1024
ALLOWED_MIME_PREFIXES = ("image/", "video/")
ALLOWED_MIME_EXACT = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "application/zip",
    "application/x-zip-compressed",
    "text/csv",
    "text/plain",
    "application/rtf",
    "application/vnd.oasis.opendocument.text",
    "application/vnd.oasis.opendocument.spreadsheet",
}
EXT_TO_MIME = {
    ".pdf": "application/pdf",
    ".doc": "application/msword",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xls": "application/vnd.ms-excel",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".ppt": "application/vnd.ms-powerpoint",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".zip": "application/zip",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".rtf": "application/rtf",
    ".odt": "application/vnd.oasis.opendocument.text",
    ".ods": "application/vnd.oasis.opendocument.spreadsheet",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".mp4": "video/mp4",
    ".mov": "video/quicktime",
}


def detect_mime(content_type: Optional[str], filename: Optional[str]) -> str:
    """Trust the extension when filename is given, else fall back to content-type."""
    name = (filename or "").lower()
    for ext, mime in EXT_TO_MIME.items():
        if name.endswith(ext):
            return mime
    if content_type:
        return content_type.split(";")[0].strip().lower()
    return "application/octet-stream"


def is_mime_allowed(mime: str) -> bool:
    if not mime:
        return False
    if mime in ALLOWED_MIME_EXACT:
        return True
    return any(mime.startswith(p) for p in ALLOWED_MIME_PREFIXES)


def file_type_label(mime: str, filename: Optional[str]) -> str:
    """A short fileType label suitable for the response body (e.g. 'pdf')."""
    if filename:
        suffix = PathLib(filename).suffix.lstrip(".").lower()
        if suffix:
            return suffix
    if "/" in mime:
        return mime.split("/")[1].lower()
    return mime.lower()




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
        # Validate groupId format BEFORE touching the session
        gid_digits, gid_jid = normalize_group_id(groupId)
        session = await _resolve_session(user["id"])

        when = parse_delay(delay) if delay else None
        if when and when > datetime.now(timezone.utc):
            sched_id = new_id()
            await db.scheduled_messages.insert_one(
                {
                    "id": sched_id,
                    "user_id": user["id"],
                    "session_id": session["id"],
                    "type": "group",
                    "target": gid_digits,
                    "text": text,
                    "url": url or None,
                    "run_at": when.isoformat(),
                    "status": "pending",
                    "source": "v2_api",
                    "created_at": now_iso(),
                }
            )
            return v2_ok({"groupId": gid_jid, "id": sched_id, "scheduled_for": when.isoformat()}, 201)

        await enforce_quota(user, 1)
        msg_id = new_id()
        try:
            result = await wa_client.send_group(session["id"], gid_digits, text, url or None)
            await db.messages.insert_one(
                {
                    "id": msg_id,
                    "user_id": user["id"],
                    "session_id": session["id"],
                    "direction": "outbound",
                    "to": gid_digits,
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
            return v2_ok({"groupId": gid_jid, "id": msg_id}, 201)
        except Exception as e:
            err_msg = str(e) or "send failed"
            await db.messages.insert_one(
                {
                    "id": msg_id,
                    "user_id": user["id"],
                    "session_id": session["id"],
                    "direction": "outbound",
                    "to": gid_digits,
                    "text": text,
                    "status": "failed",
                    "error": err_msg,
                    "is_group": True,
                    "source": "v2_api",
                    "sent_at": now_iso(),
                }
            )
            return {
                "success": False,
                "statusCode": 400,
                "timestamp": now_ts(),
                "error": err_msg,
                "data": {"groupId": gid_jid, "id": msg_id},
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

    @api.get("/v2/groups")
    async def list_groups_v2(request: Request):
        """List all WhatsApp groups the connected session is part of."""
        user = await user_from_bearer(request)
        session = await _resolve_session(user["id"])
        try:
            result = await wa_client.list_groups(session["id"])
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        groups = result.get("groups", [])
        return {
            "success": True,
            "statusCode": 200,
            "timestamp": now_ts(),
            "result": {
                "count": len(groups),
                "data": groups,
            },
        }

    # ------------ v2 / sendDocument ------------
    # Document attachments (PDF, Word, Excel, PowerPoint, ZIP, …). Accepts EITHER
    # a multipart `file` upload OR a public `url`. Single-recipient or group.
    _ALLOWED_DOCUMENT_MIMES = {
        "application/pdf": ".pdf",
        "application/msword": ".doc",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
        "application/vnd.ms-excel": ".xls",
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
        "application/vnd.ms-powerpoint": ".ppt",
        "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
        "application/zip": ".zip",
        "application/x-zip-compressed": ".zip",
        "text/csv": ".csv",
        "text/plain": ".txt",
        "application/rtf": ".rtf",
        "application/vnd.oasis.opendocument.text": ".odt",
        "application/vnd.oasis.opendocument.spreadsheet": ".ods",
    }

    @api.post("/v2/sendDocument", status_code=201)
    async def send_document_v2(
        request: Request,
        phonenumber: str = Form(""),
        groupId: str = Form(""),
        caption: str = Form(""),
        file_name: str = Form(""),
        url: str = Form(""),
        file: Optional[UploadFile] = File(None),
    ):
        """Send a PDF / Word / Excel / PowerPoint / ZIP / etc. as a WhatsApp document.

        Provide either a `file` multipart upload OR a public `url`. Address
        recipient with either `phonenumber` (1-on-1) or `groupId` (group).
        """
        user = await user_from_bearer(request)

        # Validate inputs before touching the WhatsApp session
        if not phonenumber and not groupId:
            raise HTTPException(
                status_code=400, detail="Either phonenumber or groupId is required"
            )
        if phonenumber and groupId:
            raise HTTPException(
                status_code=400,
                detail="Provide phonenumber OR groupId — not both",
            )
        if not file and not url:
            raise HTTPException(
                status_code=400, detail="Either file (multipart) or url is required"
            )
        if file and url:
            raise HTTPException(
                status_code=400, detail="Provide file OR url — not both"
            )

        session = await _resolve_session(user["id"])

        # Materialise the document onto disk so the Node service can stream it
        if file:
            ext = PathLib(file.filename or "").suffix or ""
            local = UPLOAD_DIR / f"{new_id()}{ext}"
            content = await file.read()
            local.write_bytes(content)
            mime = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
            display_name = file_name or file.filename or local.name
        else:
            try:
                async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as c:
                    r = await c.get(url)
                    r.raise_for_status()
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Failed to fetch url: {e}")
            mime = (
                r.headers.get("content-type", "application/octet-stream")
                .split(";")[0]
                .strip()
                .lower()
            )
            url_path = httpx.URL(url).path
            ext = (
                _ALLOWED_DOCUMENT_MIMES.get(mime)
                or PathLib(url_path).suffix
                or ""
            )
            local = UPLOAD_DIR / f"{new_id()}{ext}"
            local.write_bytes(r.content)
            display_name = file_name or PathLib(url_path).name or local.name

        # Quota: 1 message per recipient
        await enforce_quota(user, 1)

        if phonenumber:
            phone = normalize_phone(phonenumber)
            phone = await _maybe_apply_country_code(session, phone)
            if not phone:
                raise HTTPException(status_code=400, detail="Invalid phonenumber")
            msg = await send_media_one(
                user["id"],
                session["id"],
                phone,
                caption or "",
                str(local),
                display_name,
                mime,
                "v2_api_document",
            )
            if msg["status"] == "sent":
                await db.users.update_one(
                    {"id": user["id"]}, {"$inc": {"quota_used": 1}}
                )
                return v2_ok(
                    {
                        "phonenumber": phone,
                        "id": msg["id"],
                        "file_name": display_name,
                        "mime_type": mime,
                    },
                    201,
                )
            return {
                "success": False,
                "statusCode": 400,
                "timestamp": now_ts(),
                "error": msg.get("error") or "send failed",
                "data": {"phonenumber": phone, "id": msg["id"]},
            }

        # groupId path — send via Node service group endpoint
        gid_clean = re.sub(r"[^0-9A-Za-z\-]", "", groupId or "")
        if not gid_clean:
            raise HTTPException(status_code=400, detail="Invalid groupId")

        msg_id = new_id()
        msg_doc = {
            "id": msg_id,
            "user_id": user["id"],
            "session_id": session["id"],
            "direction": "outbound",
            "to": gid_clean,
            "is_group": True,
            "text": caption or "",
            "status": "queued",
            "type": "document",
            "has_media": True,
            "file_name": display_name,
            "mime_type": mime,
            "source": "v2_api_document",
            "sent_at": now_iso(),
            "wa_message_id": None,
            "error": None,
        }
        try:
            rj = await wa_client.send_media(
                session["id"],
                f"{gid_clean}@g.us",
                str(local),
                caption or "",
                display_name,
                mime,
                True,
            )
            msg_doc["status"] = "sent"
            msg_doc["wa_message_id"] = rj.get("message_id")
        except Exception as e:
            msg_doc["status"] = "failed"
            msg_doc["error"] = str(e)
            try:
                local.unlink(missing_ok=True)
            except Exception:
                pass

        await db.messages.insert_one(msg_doc)
        if msg_doc["status"] == "sent":
            await db.users.update_one(
                {"id": user["id"]}, {"$inc": {"quota_used": 1}}
            )
            return v2_ok(
                {
                    "groupId": gid_clean,
                    "id": msg_id,
                    "file_name": display_name,
                    "mime_type": mime,
                },
                201,
            )
        return {
            "success": False,
            "statusCode": 400,
            "timestamp": now_ts(),
            "error": msg_doc.get("error") or "send failed",
            "data": {"groupId": gid_clean, "id": msg_id},
        }

    # ------------ v2 / sendMessageFile ------------
    # Direct file upload to a phone number — exact spec format.
    @api.post("/v2/sendMessageFile")
    async def send_message_file_v2(
        request: Request,
        response: Response,
        phonenumber: str = Form(...),
        file: UploadFile = File(...),
        caption: str = Form(""),
        filename: str = Form(""),
    ):
        user = await user_from_bearer(request)

        # Validate inputs BEFORE hitting the WA session
        display_name = filename or file.filename or "file"
        mime = detect_mime(file.content_type, display_name)
        if not is_mime_allowed(mime):
            response.status_code = 400
            return {
                "success": False,
                "statusCode": 400,
                "timestamp": now_ts(),
                "error": (
                    f"Unsupported MIME type '{mime}'. Allowed: PDF, Word, Excel, "
                    "PowerPoint, image/*, video/mp4."
                ),
                "data": {},
            }

        session = await _resolve_session(user["id"])

        phone = normalize_phone(phonenumber)
        phone = await _maybe_apply_country_code(session, phone)
        if not phone:
            response.status_code = 400
            return {
                "success": False,
                "statusCode": 400,
                "timestamp": now_ts(),
                "error": "Invalid phonenumber",
                "data": {},
            }

        ext = PathLib(display_name).suffix or ""
        local = UPLOAD_DIR / f"{new_id()}{ext}"
        size = 0
        with local.open("wb") as out:
            while True:
                chunk = await file.read(1 << 20)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_FILE_SIZE_BYTES:
                    out.close()
                    local.unlink(missing_ok=True)
                    response.status_code = 413
                    return {
                        "success": False,
                        "statusCode": 413,
                        "timestamp": now_ts(),
                        "error": (
                            f"File too large. Max {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
                        ),
                        "data": {},
                    }
                out.write(chunk)

        await enforce_quota(user, 1)
        msg = await send_media_one(
            user["id"],
            session["id"],
            phone,
            caption or "",
            str(local),
            display_name,
            mime,
            "v2_api_message_file",
        )
        if msg["status"] == "sent":
            await db.users.update_one(
                {"id": user["id"]}, {"$inc": {"quota_used": 1}}
            )
            return {
                "success": True,
                "statusCode": 200,
                "timestamp": now_ts(),
                "error": "",
                "data": {
                    "messageId": msg["id"],
                    "phonenumber": phone,
                    "fileType": file_type_label(mime, display_name),
                },
            }
        response.status_code = 400
        return {
            "success": False,
            "statusCode": 400,
            "timestamp": now_ts(),
            "error": msg.get("error") or "send failed",
            "data": {"messageId": msg["id"], "phonenumber": phone},
        }

    # ------------ v2 / sendGroupFile ------------
    # Direct file upload to a WhatsApp group — exact spec format.
    @api.post("/v2/sendGroupFile")
    async def send_group_file_v2(
        request: Request,
        response: Response,
        groupId: str = Form(...),
        file: UploadFile = File(...),
        caption: str = Form(""),
        filename: str = Form(""),
    ):
        user = await user_from_bearer(request)

        # Validate inputs before resolving the session
        gid_digits, gid_jid = normalize_group_id(groupId)
        display_name = filename or file.filename or "file"
        mime = detect_mime(file.content_type, display_name)
        if not is_mime_allowed(mime):
            response.status_code = 400
            return {
                "success": False,
                "statusCode": 400,
                "timestamp": now_ts(),
                "error": (
                    f"Unsupported MIME type '{mime}'. Allowed: PDF, Word, Excel, "
                    "PowerPoint, image/*, video/mp4."
                ),
                "data": {},
            }

        session = await _resolve_session(user["id"])

        ext = PathLib(display_name).suffix or ""
        local = UPLOAD_DIR / f"{new_id()}{ext}"
        size = 0
        with local.open("wb") as out:
            while True:
                chunk = await file.read(1 << 20)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_FILE_SIZE_BYTES:
                    out.close()
                    local.unlink(missing_ok=True)
                    response.status_code = 413
                    return {
                        "success": False,
                        "statusCode": 413,
                        "timestamp": now_ts(),
                        "error": (
                            f"File too large. Max {MAX_FILE_SIZE_BYTES // (1024 * 1024)} MB."
                        ),
                        "data": {},
                    }
                out.write(chunk)

        await enforce_quota(user, 1)
        msg_id = new_id()
        msg_doc = {
            "id": msg_id,
            "user_id": user["id"],
            "session_id": session["id"],
            "direction": "outbound",
            "to": gid_digits,
            "is_group": True,
            "text": caption or "",
            "status": "queued",
            "type": "document",
            "has_media": True,
            "file_name": display_name,
            "mime_type": mime,
            "source": "v2_api_group_file",
            "sent_at": now_iso(),
            "wa_message_id": None,
            "error": None,
        }
        try:
            rj = await wa_client.send_media(
                session["id"],
                gid_jid,
                str(local),
                caption or "",
                display_name,
                mime,
                True,
            )
            msg_doc["status"] = "sent"
            msg_doc["wa_message_id"] = rj.get("message_id")
        except Exception as e:
            msg_doc["status"] = "failed"
            msg_doc["error"] = str(e) or "group file send failed"
            try:
                local.unlink(missing_ok=True)
            except Exception:
                pass

        await db.messages.insert_one(msg_doc)
        if msg_doc["status"] == "sent":
            await db.users.update_one(
                {"id": user["id"]}, {"$inc": {"quota_used": 1}}
            )
            return {
                "success": True,
                "statusCode": 200,
                "timestamp": now_ts(),
                "error": "",
                "data": {
                    "messageId": msg_id,
                    "groupId": gid_jid,
                    "fileType": file_type_label(mime, display_name),
                },
            }
        response.status_code = 400
        return {
            "success": False,
            "statusCode": 400,
            "timestamp": now_ts(),
            "error": msg_doc.get("error") or "send failed",
            "data": {"messageId": msg_id, "groupId": gid_jid},
        }

    # Drop-in compatible with 360messenger's exact path + payload
    @api.get("/v2/groupChat/getGroupList")
    async def group_chat_get_group_list(request: Request):
        """Drop-in compatible with 360messenger /v2/groupChat/getGroupList."""
        user = await user_from_bearer(request)
        session = await _resolve_session(user["id"])
        try:
            result = await wa_client.list_groups(session["id"])
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))
        groups = [
            {
                "id": g.get("jid") or (f"{g['id']}@g.us" if g.get("id") else ""),
                "name": g.get("subject") or "",
                "size": g.get("size", 0),
            }
            for g in result.get("groups", [])
        ]
        return {
            "success": True,
            "statusCode": 200,
            "timestamp": now_ts(),
            "error": "",
            "data": {"groups": groups},
        }

    return api
