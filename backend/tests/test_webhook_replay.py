"""Webhook replay tool — iteration 12.

Verifies the customer-facing failure queue + replay endpoints:
  GET    /api/me/webhook/failures[?only_pending=true]
  POST   /api/me/webhook/failures/{id}/replay
  POST   /api/me/webhook/failures/replay-all
  DELETE /api/me/webhook/failures/{id}
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


# ---------------- helpers ----------------
def _run(coro):
    """Run an async coroutine using a fresh event loop so motor doesn't cache
    a stale one across pytest calls."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


async def _seed_failure(user_id: str, url: str = "https://httpbin.org/status/200") -> str:
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    fid = str(uuid.uuid4())
    await db.webhook_failures.insert_one(
        {
            "id": fid,
            "user_id": user_id,
            "url": url,
            "event": "message.received",
            "error": "test seeded",
            "payload": {
                "event": "message.received",
                "from": "919999999999",
                "text": "replay-tool-test",
                "session_id": "test",
                "message_id": "seed_" + fid,
                "timestamp": int(
                    datetime.datetime.now(datetime.timezone.utc).timestamp() * 1000
                ),
                "has_media": False,
                "type": "text",
            },
            "attempts": 4,
            "replayed_at": None,
            "replay_status": None,
            "at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
    )
    client.close()
    return fid


async def _cleanup_user_failures(user_id: str):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await db.webhook_failures.delete_many({"user_id": user_id, "error": "test seeded"})
    client.close()


async def _find_failure(fid: str):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    r = await db.webhook_failures.find_one({"id": fid}, {"_id": 0})
    client.close()
    return r


async def _mark_replayed(fid: str, status: str = "ok: HTTP 200"):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await db.webhook_failures.update_one(
        {"id": fid},
        {"$set": {"replayed_at": "2026-01-01T00:00:00+00:00", "replay_status": status}},
    )
    client.close()


async def _delete_user(user_id: str):
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await db.webhook_failures.delete_many({"user_id": user_id})
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
def admin_user_id(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
    assert r.status_code == 200
    uid = r.json()["id"]
    yield uid
    _run(_cleanup_user_failures(uid))


@pytest.fixture(autouse=True, scope="function")
def _clean_between(admin_user_id):
    """Ensure a clean slate before each test."""
    _run(_cleanup_user_failures(admin_user_id))
    yield


@pytest.fixture
def ensure_webhook_url(admin_session):
    """Point the admin's webhook URL at a public endpoint that responds 200."""
    admin_session.patch(
        f"{BASE_URL}/api/me/webhook",
        json={"url": "https://httpbin.org/status/200"},
        timeout=15,
    )


# ---------------- tests ----------------
class TestListFailures:
    def test_empty_list_returns_zero_pending(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/me/webhook/failures", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data["total_pending"] == 0
        assert data["items"] == []

    def test_only_pending_filter_excludes_replayed(self, admin_session, admin_user_id):
        f_pending = _run(_seed_failure(admin_user_id))
        f_done = _run(_seed_failure(admin_user_id))
        # mark f_done as replayed
        _run(_mark_replayed(f_done))
        r = admin_session.get(
            f"{BASE_URL}/api/me/webhook/failures?only_pending=true", timeout=15
        )
        assert r.status_code == 200
        ids = [i["id"] for i in r.json()["items"]]
        assert f_pending in ids
        assert f_done not in ids
        assert r.json()["total_pending"] == 1

    def test_listing_never_leaks_other_users_failures(self, admin_session, admin_user_id):
        # Seed a failure for a fake other user
        other_id = "other-" + uuid.uuid4().hex
        _run(_seed_failure(other_id))
        r = admin_session.get(f"{BASE_URL}/api/me/webhook/failures?limit=200", timeout=15)
        assert r.status_code == 200
        ids = [i["user_id"] for i in r.json()["items"]]
        assert other_id not in ids
        # cleanup
        _run(_delete_user(other_id))


class TestReplayOne:
    def test_replay_success_marks_record_ok(
        self, admin_session, admin_user_id, ensure_webhook_url
    ):
        fid = _run(_seed_failure(admin_user_id))
        r = admin_session.post(
            f"{BASE_URL}/api/me/webhook/failures/{fid}/replay", timeout=20
        )
        assert r.status_code == 200
        data = r.json()
        assert data["ok"] is True
        assert "HTTP 200" in data["status"]

        # DB should reflect replay
        doc = _run(_find_failure(fid))
        assert doc["replayed_at"] is not None
        assert doc["replay_status"].startswith("ok:")

    def test_replay_failure_marks_record_failed(
        self, admin_session, admin_user_id, ensure_webhook_url
    ):
        # Point webhook at a URL that returns 500 for this test
        admin_session.patch(
            f"{BASE_URL}/api/me/webhook",
            json={"url": "https://httpbin.org/status/500"},
            timeout=15,
        )
        try:
            fid = _run(_seed_failure(admin_user_id))
            r = admin_session.post(
                f"{BASE_URL}/api/me/webhook/failures/{fid}/replay", timeout=20
            )
            assert r.status_code == 200
            data = r.json()
            assert data["ok"] is False
            assert "HTTP 500" in data["status"]
            doc = _run(_find_failure(fid))
            assert doc["replay_status"].startswith("failed:")
        finally:
            # restore
            admin_session.patch(
                f"{BASE_URL}/api/me/webhook",
                json={"url": "https://httpbin.org/status/200"},
                timeout=15,
            )

    def test_replay_nonexistent_returns_404(self, admin_session, ensure_webhook_url):
        r = admin_session.post(
            f"{BASE_URL}/api/me/webhook/failures/does-not-exist/replay", timeout=15
        )
        assert r.status_code == 404


class TestReplayAll:
    def test_replay_all_replays_only_pending(
        self, admin_session, admin_user_id, ensure_webhook_url
    ):
        ids = [_run(_seed_failure(admin_user_id)) for _ in range(3)]
        # mark one as already replayed
        _run(_mark_replayed(ids[0]))
        r = admin_session.post(
            f"{BASE_URL}/api/me/webhook/failures/replay-all", timeout=30
        )
        assert r.status_code == 200
        data = r.json()
        assert data["attempted"] == 2  # only the 2 pending
        assert data["replayed"] == 2

    def test_replay_all_requires_webhook_url(self, admin_session, admin_user_id):
        # Clear the webhook first
        admin_session.delete(f"{BASE_URL}/api/me/webhook", timeout=15)
        try:
            r = admin_session.post(
                f"{BASE_URL}/api/me/webhook/failures/replay-all", timeout=15
            )
            assert r.status_code == 400
            assert "webhook" in r.text.lower()
        finally:
            admin_session.patch(
                f"{BASE_URL}/api/me/webhook",
                json={"url": "https://httpbin.org/status/200"},
                timeout=15,
            )


class TestDismiss:
    def test_dismiss_removes_record(self, admin_session, admin_user_id):
        fid = _run(_seed_failure(admin_user_id))
        r = admin_session.delete(
            f"{BASE_URL}/api/me/webhook/failures/{fid}", timeout=15
        )
        assert r.status_code == 200
        doc = _run(_find_failure(fid))
        assert doc is None

    def test_dismiss_nonexistent_returns_404(self, admin_session):
        r = admin_session.delete(
            f"{BASE_URL}/api/me/webhook/failures/does-not-exist", timeout=15
        )
        assert r.status_code == 404


class TestAuth:
    def test_endpoints_require_auth(self):
        # unauthenticated session
        s = requests.Session()
        for method, path in [
            ("get", "/api/me/webhook/failures"),
            ("post", "/api/me/webhook/failures/x/replay"),
            ("post", "/api/me/webhook/failures/replay-all"),
            ("delete", "/api/me/webhook/failures/x"),
        ]:
            r = getattr(s, method)(f"{BASE_URL}{path}", timeout=10)
            assert r.status_code in (401, 403), \
                f"{method.upper()} {path} did not require auth (got {r.status_code})"
