"""Iteration 9 backend tests: WhatsApp session lifecycle after the
disconnect-handling fix in /app/wa-service/server.js, plus a regression
sweep on v2 endpoints, session-scoped API keys, and admin privacy.

Focus:
1) Node WA microservice /health (via FastAPI proxy)
2) Session CRUD + status + repeated restart cycle (5x) — validates the new
   old-socket cleanup path (sock.end() + removeAllListeners) doesn't leak
   or crash.
3) Regressions from prior iterations that touch behavior potentially
   affected by these changes.
"""
from __future__ import annotations

import os
import secrets
import time

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://chat-platform-380.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@wa.9x.design"
ADMIN_PASSWORD = "admin123"


# ---------------- Fixtures ----------------
@pytest.fixture(scope="module")
def admin_session() -> requests.Session:
    s = requests.Session()
    r = s.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope="module")
def customer_account():
    email = f"TEST_iter9_{secrets.token_hex(4)}@example.com"
    password = "CustPass123!"
    s = requests.Session()
    r = s.post(
        f"{API}/auth/register",
        json={"email": email, "password": password, "name": "Iter9 Cust"},
        timeout=15,
    )
    assert r.status_code in (200, 201), r.text
    me = s.get(f"{API}/auth/me", timeout=10).json()
    return {"session": s, "email": email, "password": password, "api_key": me.get("api_key"), "id": me.get("id")}


@pytest.fixture(scope="module")
def session_id(customer_account):
    s = customer_account["session"]
    r = s.post(
        f"{API}/sessions",
        json={"name": "TEST_iter9_session"},
        timeout=30,
    )
    assert r.status_code in (200, 201), r.text
    doc = r.json()
    assert "id" in doc, doc
    return doc["id"]


# ---------------- Node service health ----------------
class TestWAServiceHealth:
    """Node WhatsApp microservice basic health via FastAPI proxy."""

    def test_api_health_reports_wa_service_ok(self):
        r = requests.get(f"{API}/health", timeout=10)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("api") == "ok"
        assert data.get("wa_service") == "ok", data


# ---------------- Session lifecycle ----------------
class TestSessionLifecycle:
    """Create, poll status, restart cycle."""

    def test_create_session_persists_with_starting_status(self, customer_account):
        s = customer_account["session"]
        r = s.post(
            f"{API}/sessions",
            json={"name": f"TEST_iter9_create_{secrets.token_hex(3)}"},
            timeout=30,
        )
        assert r.status_code in (200, 201), r.text
        doc = r.json()
        assert doc["id"]
        assert doc["user_id"] == customer_account["id"]
        # Server sets default status starting; wa-service may have already
        # transitioned it to 'connecting' or 'qr'. Accept the natural set.
        assert doc["status"] in ("starting", "connecting", "qr"), doc
        assert doc["api_key"]
        # verify persistence via list
        listing = s.get(f"{API}/sessions", timeout=15).json()
        ids = [x["id"] for x in listing]
        assert doc["id"] in ids

    def test_get_session_status_returns_valid_state(self, customer_account, session_id):
        s = customer_account["session"]
        # Give Node service a moment to spin up socket + issue QR
        time.sleep(2)
        r = s.get(f"{API}/sessions/{session_id}/status", timeout=15)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["id"] == session_id
        assert data.get("status") in (
            "starting",
            "connecting",
            "qr",
            "disconnected",
            "connected",
            "not_started",
        ), data
        # If in qr, must have qr data url
        if data.get("status") == "qr":
            assert data.get("qr"), "qr status but no qr data url"

    def test_repeated_restart_does_not_crash_service(self, customer_account, session_id):
        """5 back-to-back restarts exercise the new sock.end()/removeAllListeners
        cleanup path. Between each, hit /api/health to prove Node service is
        still alive and responsive.
        """
        s = customer_account["session"]
        for i in range(5):
            r = s.post(f"{API}/sessions/{session_id}/restart", timeout=30)
            assert r.status_code == 200, f"restart #{i+1} failed: {r.status_code} {r.text}"
            body = r.json()
            assert body.get("ok") is True, body

            # small wait so Node has time to actually re-init the socket
            time.sleep(1)

            h = requests.get(f"{API}/health", timeout=10)
            assert h.status_code == 200, f"health after restart #{i+1} bad: {h.text}"
            hd = h.json()
            assert hd.get("wa_service") == "ok", f"wa_service down after restart #{i+1}: {hd}"

        # After all restarts, status endpoint still responds
        r = s.get(f"{API}/sessions/{session_id}/status", timeout=15)
        assert r.status_code == 200, r.text

    def test_service_still_serves_after_restart_cycle(self):
        """Independent probe — Node service still healthy."""
        r = requests.get(f"{API}/health", timeout=10)
        assert r.status_code == 200
        assert r.json().get("wa_service") == "ok"


# ---------------- v2 API regressions ----------------
class TestV2Regressions:
    """Ensure earlier v2 fixes still hold after wa-service refactor."""

    def test_v2_group_list_no_session_returns_400_not_500(self, customer_account):
        """With valid Bearer but no connected session => 400 (not 500)."""
        api_key = customer_account["api_key"]
        assert api_key
        r = requests.get(
            f"{API}/v2/groupChat/getGroupList",
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=15,
        )
        # Should not be a server crash; must be a clean 400 (no connected
        # session) or 200 with empty groups. NEVER 500.
        assert r.status_code != 500, f"500 crash: {r.text}"
        assert r.status_code in (200, 400), r.text
        if r.status_code == 400:
            body = r.json()
            # error field populated with useful text
            err = body.get("error") or body.get("detail") or ""
            assert err, f"empty error field: {body}"

    def test_v2_group_list_invalid_bearer_returns_401(self):
        r = requests.get(
            f"{API}/v2/groupChat/getGroupList",
            headers={"Authorization": "Bearer not_a_real_key_xyz"},
            timeout=15,
        )
        assert r.status_code == 401, r.text

    def test_v2_sendGroup_preserves_g_us_jid(self, customer_account):
        """POST /v2/sendGroup with a full @g.us group id must not strip the @.
        Without a connected session we'll get a 400, but the error should
        NOT complain about JID format — meaning the @ was preserved.
        """
        api_key = customer_account["api_key"]
        r = requests.post(
            f"{API}/v2/sendGroup",
            headers={"Authorization": f"Bearer {api_key}"},
            data={"groupId": "120363012345678900@g.us", "text": "hi"},
            timeout=15,
        )
        assert r.status_code != 500, f"500 crash: {r.text}"
        # 400 is acceptable ("no connected session") — JID validation error is NOT
        body = {}
        try:
            body = r.json()
        except Exception:
            pass
        err_txt = str(body.get("error") or body.get("detail") or "").lower()
        assert "invalid" not in err_txt or "jid" not in err_txt, (
            f"sendGroup stripped or rejected @g.us: {body}"
        )

    def test_v2_sendMessageFile_unsupported_mime_returns_400_with_error(
        self, customer_account
    ):
        """Upload a file with an unsupported MIME. Must return 400 with a
        non-empty error field."""
        api_key = customer_account["api_key"]
        # Contrived .exe upload (definitely unsupported)
        files = {"file": ("payload.exe", b"MZ\x90\x00" + b"\x00" * 32, "application/x-msdownload")}
        r = requests.post(
            f"{API}/v2/sendMessageFile",
            headers={"Authorization": f"Bearer {api_key}"},
            data={"phonenumber": "1234567890"},
            files=files,
            timeout=20,
        )
        assert r.status_code in (400, 415), f"expected 400/415, got {r.status_code}: {r.text}"
        body = {}
        try:
            body = r.json()
        except Exception:
            pytest.fail(f"non-JSON error body: {r.text}")
        err = body.get("error") or body.get("detail")
        assert err, f"empty error field: {body}"
        assert isinstance(err, str) and len(err) > 0


# ---------------- Session-scoped API keys ----------------
class TestSessionScopedApiKey:
    """Bearer with a session's api_key must pin API calls to that session."""

    def test_session_api_key_differs_from_user_master_key(
        self, customer_account, session_id
    ):
        s = customer_account["session"]
        r = s.get(f"{API}/sessions", timeout=10)
        assert r.status_code == 200
        sessions = r.json()
        our = next((x for x in sessions if x["id"] == session_id), None)
        assert our, "created session missing from list"
        sess_api_key = our.get("api_key")
        assert sess_api_key
        assert sess_api_key != customer_account["api_key"], (
            "session api_key must differ from user master api_key"
        )

    def test_session_bearer_accepted_by_v2_endpoint(
        self, customer_account, session_id
    ):
        s = customer_account["session"]
        listing = s.get(f"{API}/sessions", timeout=10).json()
        our = next((x for x in listing if x["id"] == session_id), None)
        sess_api_key = our["api_key"]
        # With session api_key, v2/groupChat/getGroupList should authenticate
        # (won't have groups since not connected, but must not 401)
        r = requests.get(
            f"{API}/v2/groupChat/getGroupList",
            headers={"Authorization": f"Bearer {sess_api_key}"},
            timeout=15,
        )
        assert r.status_code != 401, f"session api_key rejected: {r.text}"
        assert r.status_code != 500, r.text


# ---------------- Privacy / Admin ----------------
class TestPrivacy:
    """Cross-tenant privacy invariants."""

    def test_messages_endpoint_filters_by_user(self, customer_account):
        """/api/messages must only return the caller's rows."""
        s = customer_account["session"]
        r = s.get(f"{API}/messages", timeout=15)
        assert r.status_code == 200, r.text
        rows = r.json()
        assert isinstance(rows, list)
        # Every returned row is for this user
        for row in rows:
            assert row.get("user_id") == customer_account["id"], (
                f"leak: row user_id={row.get('user_id')} caller={customer_account['id']}"
            )

    def test_messages_endpoint_rejects_cross_user_query(self, customer_account):
        """Even with user_id query param, admin (or anyone) cannot query
        other users' messages via this endpoint — no such override exists."""
        s = customer_account["session"]
        r = s.get(f"{API}/messages?user_id=someone-else", timeout=15)
        assert r.status_code == 200
        rows = r.json()
        for row in rows:
            assert row.get("user_id") == customer_account["id"], (
                "user_id query param wrongly leaks other users' messages"
            )

    def test_admin_customer_detail_returns_aggregate_only(
        self, admin_session, customer_account
    ):
        """/api/admin/customers/{id} must not expose message content."""
        r = admin_session.get(
            f"{API}/admin/customers/{customer_account['id']}", timeout=15
        )
        assert r.status_code == 200, r.text
        data = r.json()
        # Aggregate messages_total present
        assert "messages_total" in data, data
        assert isinstance(data["messages_total"], int)
        # No raw message bodies leaked
        assert "messages" not in data, "raw messages leaked in admin detail"
        assert "message_bodies" not in data
        # Spot check: no field with obvious message content
        for k, v in data.items():
            if isinstance(v, list) and v and isinstance(v[0], dict):
                # Any list of dicts should not contain 'text' or 'body'
                for item in v:
                    assert "text" not in item, f"message text leaked under key {k}"
                    assert "body" not in item, f"message body leaked under key {k}"
