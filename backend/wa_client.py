"""HTTP client for the local Baileys Node microservice."""
from __future__ import annotations

import os
from typing import Optional

import httpx

WA_SERVICE_URL = os.environ.get("WA_SERVICE_URL", "http://127.0.0.1:3001")


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=30.0, base_url=WA_SERVICE_URL)


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
    file_path: str,
    caption: str,
    file_name: str,
    mime_type: str,
    delete_after: bool = True,
) -> dict:
    async with _client() as c:
        r = await c.post(
            f"/sessions/{session_id}/send-media",
            json={
                "to": to,
                "file_path": file_path,
                "caption": caption,
                "file_name": file_name,
                "mime_type": mime_type,
                "delete_after": delete_after,
            },
        )
        if r.status_code >= 400:
            try:
                detail = r.json().get("error", "send failed")
            except Exception:
                detail = "send failed"
            raise RuntimeError(detail)
        return r.json()


async def health() -> bool:
    try:
        async with _client() as c:
            r = await c.get("/health")
            return r.status_code == 200
    except Exception:
        return False
