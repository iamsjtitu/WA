"""HTTP client for the local Baileys Node microservice."""
from __future__ import annotations

import base64
import os
from typing import Optional

import httpx

WA_SERVICE_URL = os.environ.get("WA_SERVICE_URL", "http://127.0.0.1:3001")
INTERNAL_SECRET = os.environ.get("INTERNAL_SECRET", "")


def _client() -> httpx.AsyncClient:
    headers = {}
    if INTERNAL_SECRET:
        headers["X-Internal-Secret"] = INTERNAL_SECRET
    return httpx.AsyncClient(timeout=30.0, base_url=WA_SERVICE_URL, headers=headers)


async def start_session(session_id: str) -> dict:
    async with _client() as c:
        r = await c.post(f"/sessions/{session_id}/start")
        r.raise_for_status()
        return r.json()


async def session_status(session_id: str) -> dict:
    async with _client() as c:
        r = await c.get(f"/sessions/{session_id}/status")
        r.raise_for_status()
        return r.json()


async def logout_session(session_id: str) -> dict:
    async with _client() as c:
        r = await c.post(f"/sessions/{session_id}/logout")
        r.raise_for_status()
        return r.json()


async def send_message(session_id: str, to: str, text: str) -> dict:
    async with _client() as c:
        r = await c.post(
            f"/sessions/{session_id}/send",
            json={"to": to, "text": text},
        )
        if r.status_code >= 400:
            try:
                detail = r.json().get("error", "send failed")
            except Exception:
                detail = "send failed"
            raise RuntimeError(detail)
        return r.json()


async def send_group(
    session_id: str, group_id: str, text: str, url: Optional[str] = None
) -> dict:
    async with _client() as c:
        r = await c.post(
            f"/sessions/{session_id}/send-group",
            json={"group_id": group_id, "text": text, "url": url},
        )
        if r.status_code >= 400:
            try:
                detail = r.json().get("error", "send failed")
            except Exception:
                detail = "send failed"
            raise RuntimeError(detail)
        return r.json()


async def list_groups(session_id: str) -> dict:
    async with _client() as c:
        r = await c.get(f"/sessions/{session_id}/groups")
        if r.status_code >= 400:
            try:
                detail = r.json().get("error", "list groups failed")
            except Exception:
                detail = "list groups failed"
            raise RuntimeError(detail)
        return r.json()


async def request_pairing_code(session_id: str, phone: str) -> dict:
    async with _client() as c:
        r = await c.post(
            f"/sessions/{session_id}/pair",
            json={"phone": phone},
        )
        if r.status_code >= 400:
            try:
                detail = r.json().get("error", "pair failed")
            except Exception:
                detail = "pair failed"
            raise RuntimeError(detail)
        return r.json()


async def send_media(
    session_id: str,
    to: str,
    data: bytes,
    caption: str,
    file_name: str,
    mime_type: str,
) -> dict:
    """Stream the media bytes straight to the co-located Node process.

    Nothing is written to disk on the backend; Node hands the Buffer to Baileys.
    Metadata rides in base64 headers (captions/filenames may be non-latin-1).
    """
    headers = {
        "Content-Type": "application/octet-stream",
        "X-Wa-To": str(to),
        "X-Wa-Caption-B64": base64.b64encode((caption or "").encode()).decode(),
        "X-Wa-File-Name-B64": base64.b64encode((file_name or "file").encode()).decode(),
        "X-Wa-Mime": mime_type or "application/octet-stream",
    }
    async with _client() as c:
        r = await c.post(
            f"/sessions/{session_id}/send-media",
            content=data,
            headers=headers,
            timeout=180.0,
        )
        if r.status_code >= 400:
            try:
                detail = r.json().get("error", "send failed")
            except Exception:
                detail = "send failed"
            if "file_path" in detail:
                # Old Node build still running (pre raw-body contract).
                detail = (
                    "wa-service is running outdated code — run "
                    "`supervisorctl restart wa9x-wa-service` on the server"
                )
            raise RuntimeError(detail)
        return r.json()


async def health() -> bool:
    try:
        async with _client() as c:
            r = await c.get("/health")
            return r.status_code == 200
    except Exception:
        return False


async def diag() -> dict:
    async with _client() as c:
        r = await c.get("/diag", timeout=25.0)
        r.raise_for_status()
        return r.json()
