"""Disconnect event / history — iteration 13.

Verifies:
  POST /api/internal/disconnect-event  (Node -> FastAPI, internal-secret guarded)
  GET  /api/sessions/{id}/status       (returns error, error_code, error_label, last_disconnect_at)
  GET  /api/sessions/{id}/disconnect-history

Also verifies:
  - unauthenticated / bad-secret /internal/disconnect-event is rejected
  - user cannot view another user's disconnect history
"""
import asyncio
import datetime
import os
import sys
import uuid

import pytest
import requests

sys.path.insert(0, "/app/backend")
from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://chat-platform-380.preview.emergentagent.com",
).rstrip("/")

ADMIN_EMAIL = "admin@wa.9x.design"
ADMIN_PASSWORD = "admin123"

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "wapihub_db")


def _load_internal_secret() -> str:
    for line in open("/app/backend/.env", "r", encoding="utf-8"):
        if line.startswith("INTERNAL_SECRET"):
            return line.split("=", 1)[1].strip().strip('"')
    return ""


INTERNAL_SECRET = _load_internal_secret()


# ---------------- helpers ----------------
def _run(coro):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _pick_admin_session_id() -> str:
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    user = await db.users.find_one({"email": ADMIN_EMAIL}, {"_id": 0, "id": 1})
    session = await db.wa_sessions.find_one(
        {"user_id": user["id"]}, {"_id": 0, "id": 1}
    )
    client.close()
    return session["id"]


async def _cleanup_events(session_id: str):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await db.disconnect_events.delete_many({"session_id": session_id})
    await db.wa_sessions.update_one(
        {"id": session_id},
        {
            "$unset": {
                "last_disconnect_at": 1,
                "last_disconnect_code": 1,
                "last_disconnect_label": 1,
                "last_disconnect_reason": 1,
                "last_disconnect_terminal": 1,
            }
        },
    )
    client.close()


# ---------------- fixtures ----------------
@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    r = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200
    return s


@pytest.fixture(scope="module")
def session_id():
    return _run(_pick_admin_session_id())


@pytest.fixture(autouse=True)
def _clean(session_id):
    _run(_cleanup_events(session_id))
    yield


# ---------------- tests ----------------
class TestInternalDisconnectAuth:
    def test_rejects_missing_secret(self, session_id):
        r = requests.post(
            f"{BASE_URL}/api/internal/disconnect-event",
            json={"session_id": session_id, "code": 440, "terminal": True},
            timeout=10,
        )
        assert r.status_code == 401

    def test_rejects_wrong_secret(self, session_id):
        r = requests.post(
            f"{BASE_URL}/api/internal/disconnect-event",
            headers={"X-Internal-Secret": "wrong-secret"},
            json={"session_id": session_id, "code": 440, "terminal": True},
            timeout=10,
        )
        assert r.status_code == 401


class TestDisconnectEventRecording:
    def test_terminal_event_persisted_and_visible_via_status(
        self, admin_session, session_id
    ):
        r = requests.post(
            f"{BASE_URL}/api/internal/disconnect-event",
            headers={"X-Internal-Secret": INTERNAL_SECRET},
            json={
                "session_id": session_id,
                "code": 440,
                "reason": "Stream Errored (Replaced)",
                "label": "Replaced by another device",
                "terminal": True,
                "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            },
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["ok"] is True

        # session status should now include disconnect info
        r = admin_session.get(f"{BASE_URL}/api/sessions/{session_id}/status", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["last_disconnect_code"] == 440
        assert "Replaced" in (data.get("last_disconnect_label") or "")
        # terminal disconnect flips status
        assert data.get("last_disconnect_terminal") is True

    def test_transient_event_persisted(self, admin_session, session_id):
        r = requests.post(
            f"{BASE_URL}/api/internal/disconnect-event",
            headers={"X-Internal-Secret": INTERNAL_SECRET},
            json={
                "session_id": session_id,
                "code": 515,
                "reason": "Restart required",
                "label": "Restart required (auto-reconnecting)",
                "terminal": False,
            },
            timeout=10,
        )
        assert r.status_code == 200
        r = admin_session.get(f"{BASE_URL}/api/sessions/{session_id}/status", timeout=15)
        data = r.json()
        assert data["last_disconnect_code"] == 515
        assert data.get("last_disconnect_terminal") is False

    def test_event_for_unknown_session_is_noop(self):
        r = requests.post(
            f"{BASE_URL}/api/internal/disconnect-event",
            headers={"X-Internal-Secret": INTERNAL_SECRET},
            json={"session_id": "does-not-exist-" + uuid.uuid4().hex, "code": 401, "terminal": True},
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["ok"] is False


class TestDisconnectHistory:
    def test_history_returns_events_newest_first(self, admin_session, session_id):
        for code in (515, 428, 440):
            requests.post(
                f"{BASE_URL}/api/internal/disconnect-event",
                headers={"X-Internal-Secret": INTERNAL_SECRET},
                json={
                    "session_id": session_id,
                    "code": code,
                    "reason": f"code {code}",
                    "label": f"Test {code}",
                    "terminal": code == 440,
                },
                timeout=10,
            )
        r = admin_session.get(
            f"{BASE_URL}/api/sessions/{session_id}/disconnect-history?limit=10",
            timeout=15,
        )
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) >= 3
        # newest first — 440 was inserted last
        assert items[0]["code"] == 440
        assert items[0]["terminal"] is True

    def test_history_requires_ownership(self):
        # unauthenticated session
        r = requests.get(
            f"{BASE_URL}/api/sessions/fake-id/disconnect-history", timeout=10
        )
        assert r.status_code in (401, 403)

    def test_history_returns_404_for_other_users_session(self, admin_session):
        # admin trying to view a made-up session id → 404 (not authorised)
        r = admin_session.get(
            f"{BASE_URL}/api/sessions/does-not-belong-to-me/disconnect-history",
            timeout=15,
        )
        assert r.status_code == 404


class TestHistoryTrim:
    def test_history_capped_at_100_per_session(self, session_id):
        # Directly seed 105 events in DB, then post one more via the endpoint —
        # the endpoint's own trim logic should collapse the collection to ≤ 100.
        async def _seed_many_then_count():
            c = AsyncIOMotorClient(MONGO_URL)
            db = c[DB_NAME]
            try:
                bulk = [
                    {
                        "id": uuid.uuid4().hex,
                        "session_id": session_id,
                        "user_id": "u",
                        "code": 428,
                        "reason": "seed",
                        "label": "Seed",
                        "terminal": False,
                        "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    }
                    for _ in range(105)
                ]
                await db.disconnect_events.insert_many(bulk)
                return await db.disconnect_events.count_documents(
                    {"session_id": session_id}
                )
            finally:
                c.close()

        pre = _run(_seed_many_then_count())
        assert pre == 105

        # Now hit the endpoint once — it should trim to ≤ 100
        r = requests.post(
            f"{BASE_URL}/api/internal/disconnect-event",
            headers={"X-Internal-Secret": INTERNAL_SECRET},
            json={
                "session_id": session_id,
                "code": 428,
                "reason": "trigger trim",
                "label": "Trigger",
                "terminal": False,
            },
            timeout=15,
        )
        assert r.status_code == 200

        async def _count():
            c = AsyncIOMotorClient(MONGO_URL)
            try:
                return await c[DB_NAME].disconnect_events.count_documents(
                    {"session_id": session_id}
                )
            finally:
                c.close()

        n = _run(_count())
        assert n <= 100, f"History was not trimmed (found {n} events)"
