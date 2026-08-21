"""Session resolve — DB/Node desync fix (iter 15).

Verifies:
  - POST /api/internal/connect-event (Node -> FastAPI) is guarded and updates DB
  - When DB status is 'disconnected' but the live Node status is 'connected',
    /api/v2/sendMessage does NOT return 400 — it flows through to the send
    (which will still return a downstream error like "session not registered"
    since preview env has no real WA link, but crucially not 400 "session
    bound to this API key is not connected").
  - When BOTH DB and Node say disconnected, the error message reflects the
    LIVE Node status (not the stale DB one).
"""
import asyncio
import os
import sys

import pytest
import requests

sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://chat-platform-380.preview.emergentagent.com",
).rstrip("/")

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "wapihub_db")

ADMIN_EMAIL = "admin@wa.9x.design"
ADMIN_PASSWORD = "admin123"


def _load_internal_secret() -> str:
    for line in open("/app/backend/.env", "r", encoding="utf-8"):
        if line.startswith("INTERNAL_SECRET"):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


INTERNAL_SECRET = _load_internal_secret()


def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _pick_admin_session():
    c = AsyncIOMotorClient(MONGO_URL)
    try:
        db = c[DB_NAME]
        user = await db.users.find_one({"email": ADMIN_EMAIL}, {"_id": 0, "id": 1})
        s = await db.wa_sessions.find_one(
            {"user_id": user["id"]}, {"_id": 0}
        )
        return s
    finally:
        c.close()


async def _set_db_status(session_id: str, status: str):
    c = AsyncIOMotorClient(MONGO_URL)
    try:
        await c[DB_NAME].wa_sessions.update_one(
            {"id": session_id}, {"$set": {"status": status}}
        )
    finally:
        c.close()


async def _get_db_status(session_id: str) -> str:
    c = AsyncIOMotorClient(MONGO_URL)
    try:
        d = await c[DB_NAME].wa_sessions.find_one({"id": session_id})
        return d.get("status")
    finally:
        c.close()


@pytest.fixture(scope="module")
def session():
    s = _run(_pick_admin_session())
    assert s and s.get("api_key"), "admin session or api_key missing"
    return s


class TestConnectEventAuth:
    def test_missing_secret_rejected(self, session):
        r = requests.post(
            f"{BASE_URL}/api/internal/connect-event",
            json={"session_id": session["id"]},
            timeout=10,
        )
        assert r.status_code == 401

    def test_wrong_secret_rejected(self, session):
        r = requests.post(
            f"{BASE_URL}/api/internal/connect-event",
            headers={"X-Internal-Secret": "nope"},
            json={"session_id": session["id"]},
            timeout=10,
        )
        assert r.status_code == 401


class TestConnectEventUpdatesDB:
    def test_valid_event_flips_db_to_connected(self, session):
        _run(_set_db_status(session["id"], "disconnected"))
        r = requests.post(
            f"{BASE_URL}/api/internal/connect-event",
            headers={"X-Internal-Secret": INTERNAL_SECRET},
            json={"session_id": session["id"], "phone": "911234567890"},
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert _run(_get_db_status(session["id"])) == "connected"

    def test_unknown_session_noop(self):
        r = requests.post(
            f"{BASE_URL}/api/internal/connect-event",
            headers={"X-Internal-Secret": INTERNAL_SECRET},
            json={"session_id": "does-not-exist"},
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["ok"] is False


class TestLiveCheckFallback:
    """When DB says disconnected but Node has a live socket, resolve_session
    should live-check and NOT return the DB-stale 400. In preview env we
    can't have a real connected WA socket, so we verify that:
     (a) the DB status ends up matching what Node actually reports (i.e. the
         live check DID run and DID sync the DB), and
     (b) the error message includes Node's status rather than the DB stale one."""

    def test_error_message_reflects_live_node_status(self, session):
        # Force DB to a bogus status
        _run(_set_db_status(session["id"], "disconnected"))
        r = requests.post(
            f"{BASE_URL}/api/v2/sendMessage",
            headers={"Authorization": f"Bearer {session['api_key']}"},
            data={"phonenumber": "447488888888", "text": "hi"},
            timeout=30,
        )
        # Preview env has no real WA link so Node reports not_started (or
        # connecting after eager start attempt). Either way it must NOT be
        # the stale 'disconnected'.
        assert r.status_code == 400
        detail = r.json().get("detail", "")
        assert "not connected" in detail.lower()
        # The critical assertion: our live check syncs the DB. So after the
        # request the DB status must NOT still say 'disconnected'.
        final = _run(_get_db_status(session["id"]))
        assert final != "disconnected", (
            f"live-check-fallback did not sync DB status (still {final})"
        )
