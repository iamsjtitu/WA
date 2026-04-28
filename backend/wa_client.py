"""HTTP client for the local Baileys Node microservice."""
from __future__ import annotations

import os
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


async def health() -> bool:
    try:
        async with _client() as c:
            r = await c.get("/health")
            return r.status_code == 200
    except Exception:
        return False
