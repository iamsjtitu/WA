"""API reliability dashboard tests (iter 16).

Covers:
  - Middleware records public API traffic (/api/v1/* and /api/v2/*) into
    db.api_metrics with method/path/status/latency/session_id/user_id.
  - Non-public paths (/api/health, /api/auth/*, admin/*) are NOT recorded.
  - GET /api/admin/reliability requires admin auth (401 unauth, 403 non-admin).
  - Aggregation returns expected shape: total, success_rate, latency
    percentiles, top_failing_routes, per_session, series, by_status.
  - session_id filter narrows the result.
  - TTL index exists on api_metrics.at.
"""
from __future__ import annotations

import asyncio
import os
import sys
import time

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


async def _clear_metrics():
    c = AsyncIOMotorClient(MONGO_URL)
    try:
        await c[DB_NAME].api_metrics.delete_many({})
    finally:
        c.close()


async def _count_metrics(filter_: dict | None = None):
    c = AsyncIOMotorClient(MONGO_URL)
    try:
        return await c[DB_NAME].api_metrics.count_documents(filter_ or {})
    finally:
        c.close()


async def _ttl_seconds() -> int | None:
    c = AsyncIOMotorClient(MONGO_URL)
    try:
        info = await c[DB_NAME].api_metrics.index_information()
        for _, meta in info.items():
            if meta.get("expireAfterSeconds") is not None:
                return meta["expireAfterSeconds"]
        return None
    finally:
        c.close()


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
def wa_session():
    return _run(_pick_admin_session())


class TestMiddlewareRecords:
    def test_v2_request_is_recorded_with_status_and_route(self, wa_session):
        _run(_clear_metrics())
        # Send a v2 request with the session api_key
        requests.post(
            f"{BASE_URL}/api/v2/sendMessage",
            headers={"Authorization": f"Bearer {wa_session['api_key']}"},
            data={"phonenumber": "447488888888", "text": "metrics-test"},
            timeout=30,
        )
        # Give the async insert a moment
        time.sleep(0.5)

        async def _fetch():
            c = AsyncIOMotorClient(MONGO_URL)
            try:
                return await c[DB_NAME].api_metrics.find_one(
                    {"path": "/api/v2/sendMessage"}, {"_id": 0}
                )
            finally:
                c.close()

        doc = _run(_fetch())
        assert doc is not None
        assert doc["method"] == "POST"
        assert doc["route"] == "sendMessage"
        assert 200 <= doc["status"] < 600
        assert doc["latency_ms"] >= 0
        assert doc["session_id"] == wa_session["id"]

    def test_non_public_paths_not_recorded(self, admin_session):
        _run(_clear_metrics())
        # Hit various non-tracked routes
        admin_session.get(f"{BASE_URL}/api/health", timeout=10)
        admin_session.get(f"{BASE_URL}/api/auth/me", timeout=10)
        admin_session.get(f"{BASE_URL}/api/sessions", timeout=10)
        time.sleep(0.5)
        n = _run(_count_metrics())
        assert n == 0, f"Non-public paths were recorded ({n} rows)"


class TestReliabilityEndpointAuth:
    def test_unauth_rejected(self):
        r = requests.get(f"{BASE_URL}/api/admin/reliability", timeout=15)
        assert r.status_code in (401, 403)

    def test_admin_allowed(self, admin_session):
        r = admin_session.get(
            f"{BASE_URL}/api/admin/reliability?window=1h", timeout=15
        )
        assert r.status_code == 200


class TestReliabilityAggregate:
    def test_shape(self, admin_session, wa_session):
        _run(_clear_metrics())
        # Generate 3 requests
        for _ in range(3):
            requests.post(
                f"{BASE_URL}/api/v2/sendMessage",
                headers={"Authorization": f"Bearer {wa_session['api_key']}"},
                data={"phonenumber": "447488888888", "text": "x"},
                timeout=30,
            )
        time.sleep(0.6)
        r = admin_session.get(
            f"{BASE_URL}/api/admin/reliability?window=1h&bucket_minutes=1",
            timeout=15,
        )
        d = r.json()
        # Every expected field exists
        for k in (
            "window",
            "total",
            "success",
            "client_errors",
            "server_errors",
            "success_rate",
            "latency",
            "by_status",
            "top_failing_routes",
            "series",
            "per_session",
        ):
            assert k in d, f"missing key {k}"
        assert d["total"] >= 3
        assert "p50" in d["latency"] and "p95" in d["latency"] and "p99" in d["latency"]
        # This session was used → must appear in per_session
        session_ids = [row["session_id"] for row in d["per_session"]]
        assert wa_session["id"] in session_ids

    def test_session_filter(self, admin_session, wa_session):
        _run(_clear_metrics())
        requests.post(
            f"{BASE_URL}/api/v2/sendMessage",
            headers={"Authorization": f"Bearer {wa_session['api_key']}"},
            data={"phonenumber": "447488888888", "text": "x"},
            timeout=30,
        )
        time.sleep(0.5)
        r = admin_session.get(
            f"{BASE_URL}/api/admin/reliability?window=1h&session_id={wa_session['id']}",
            timeout=15,
        )
        d = r.json()
        assert d["total"] >= 1
        # per_session should be empty when a filter is applied (it's a global view)
        assert d["per_session"] == []


class TestAdminSessionsList:
    def test_admin_sessions_endpoint(self, admin_session, wa_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/sessions", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        assert isinstance(rows, list)
        ids = [x["id"] for x in rows]
        assert wa_session["id"] in ids
        # customer email attached
        row = next(x for x in rows if x["id"] == wa_session["id"])
        assert "customer" in row


class TestTTLIndex:
    def test_ttl_index_present(self):
        # Force a request to ensure the collection exists + startup ran
        requests.get(f"{BASE_URL}/api/health", timeout=10)
        ttl = _run(_ttl_seconds())
        assert ttl == 7 * 86400, f"expected 7-day TTL, got {ttl}"
