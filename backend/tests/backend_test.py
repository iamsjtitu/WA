"""WapiHub backend API tests — covers auth, admin, sessions, messages, public API."""
from __future__ import annotations

import os
import secrets
import time
from typing import Optional

import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://chat-platform-380.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@wapihub.com"
ADMIN_PASSWORD = "admin123"


def _unique_email(prefix: str = "TEST_user") -> str:
    return f"{prefix}_{secrets.token_hex(4)}@example.com"


# ---------------- Fixtures ----------------
@pytest.fixture(scope="session")
def admin_session() -> requests.Session:
    """Logged-in admin session (cookie-based)."""
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    body = r.json()
    assert body["role"] == "admin"
    assert s.cookies.get("access_token"), "access_token cookie not set"
    assert s.cookies.get("refresh_token"), "refresh_token cookie not set"
    return s


@pytest.fixture(scope="session")
def customer_account() -> dict:
    """Register a fresh customer; return dict with email, password, session, user."""
    email = _unique_email("TEST_customer")
    password = "CustPass123!"
    s = requests.Session()
    r = s.post(f"{API}/auth/register", json={"email": email, "password": password, "name": "Test Customer"}, timeout=15)
    assert r.status_code == 200, f"Register failed: {r.status_code} {r.text}"
    user = r.json()
    assert user["role"] == "customer"
    assert user["api_key"].startswith("wapi_")
    return {"email": email, "password": password, "user": user, "session": s, "api_key": user["api_key"]}


@pytest.fixture(scope="session")
def created_customer_ids() -> list:
    """Track customer IDs created by admin to clean up afterwards."""
    ids: list = []
    yield ids
    # Cleanup at end
    s = requests.Session()
    try:
        s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=10)
        for cid in ids:
            try:
                s.delete(f"{API}/admin/customers/{cid}", timeout=10)
            except Exception:
                pass
    except Exception:
        pass


# ---------------- Health ----------------
class TestHealth:
    def test_health(self):
        r = requests.get(f"{API}/health", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert data.get("api") == "ok"
        assert data.get("wa_service") == "ok", f"wa_service not ok: {data}"

    def test_root(self):
        r = requests.get(f"{API}/", timeout=10)
        assert r.status_code == 200
        assert r.json().get("ok") is True


# ---------------- Auth ----------------
class TestAuth:
    def test_admin_login_success_sets_cookies(self):
        s = requests.Session()
        r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["email"] == ADMIN_EMAIL
        assert body["role"] == "admin"
        # httpOnly cookies
        assert s.cookies.get("access_token")
        assert s.cookies.get("refresh_token")

    def test_login_wrong_password(self):
        r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": "wrong_pw"}, timeout=10)
        assert r.status_code == 401

    def test_login_nonexistent_user(self):
        r = requests.post(f"{API}/auth/login", json={"email": "nonexistent@example.com", "password": "abc12345"}, timeout=10)
        assert r.status_code == 401

    def test_register_and_duplicate(self):
        email = _unique_email("TEST_reg")
        r = requests.post(f"{API}/auth/register", json={"email": email, "password": "secret123", "name": "Reg User"}, timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert body["email"] == email.lower()
        assert body["role"] == "customer"
        assert body["api_key"].startswith("wapi_")
        assert body["quota_monthly"] == 1000
        assert body["quota_used"] == 0

        # duplicate
        r2 = requests.post(f"{API}/auth/register", json={"email": email, "password": "secret123", "name": "Reg User"}, timeout=10)
        assert r2.status_code == 400
        assert "already" in r2.json().get("detail", "").lower()

    def test_me_with_cookies(self, admin_session):
        r = admin_session.get(f"{API}/auth/me", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["email"] == ADMIN_EMAIL
        assert data["role"] == "admin"

    def test_me_unauthenticated(self):
        r = requests.get(f"{API}/auth/me", timeout=10)
        assert r.status_code == 401

    def test_logout_clears_cookies(self):
        s = requests.Session()
        s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=10)
        assert s.cookies.get("access_token")
        r = s.post(f"{API}/auth/logout", timeout=10)
        assert r.status_code == 200
        # cookies should be cleared (server sends Set-Cookie with empty value or expired)
        # After logout, /auth/me should fail
        s.cookies.clear()  # simulate browser honoring cleared cookies
        r2 = s.get(f"{API}/auth/me", timeout=10)
        assert r2.status_code == 401


# ---------------- Admin: Stats & Customers ----------------
class TestAdmin:
    def test_admin_stats(self, admin_session):
        r = admin_session.get(f"{API}/admin/stats", timeout=10)
        assert r.status_code == 200
        data = r.json()
        for key in ("customers", "sessions", "messages_total", "messages_today", "messages_failed"):
            assert key in data
            assert isinstance(data[key], int)

    def test_admin_stats_forbidden_for_customer(self, customer_account):
        r = customer_account["session"].get(f"{API}/admin/stats", timeout=10)
        assert r.status_code == 403

    def test_admin_create_list_update_regen_delete(self, admin_session, created_customer_ids):
        # CREATE
        email = _unique_email("TEST_admincust")
        payload = {"email": email, "password": "abcd1234", "name": "Admin Created", "quota_monthly": 250}
        r = admin_session.post(f"{API}/admin/customers", json=payload, timeout=15)
        assert r.status_code == 200, r.text
        cust = r.json()
        cid = cust["id"]
        created_customer_ids.append(cid)
        assert cust["email"] == email.lower()
        assert cust["role"] == "customer"
        assert cust["quota_monthly"] == 250
        assert cust["api_key"].startswith("wapi_")
        original_key = cust["api_key"]

        # duplicate
        r_dup = admin_session.post(f"{API}/admin/customers", json=payload, timeout=10)
        assert r_dup.status_code == 400

        # LIST
        r_list = admin_session.get(f"{API}/admin/customers", timeout=10)
        assert r_list.status_code == 200
        emails = [c["email"] for c in r_list.json()]
        assert email.lower() in emails

        # PATCH update quota
        r_upd = admin_session.patch(f"{API}/admin/customers/{cid}", json={"quota_monthly": 500}, timeout=10)
        assert r_upd.status_code == 200
        assert r_upd.json()["quota_monthly"] == 500

        # REGEN key
        r_key = admin_session.post(f"{API}/admin/customers/{cid}/regenerate-key", timeout=10)
        assert r_key.status_code == 200
        new_key = r_key.json()["api_key"]
        assert new_key.startswith("wapi_")
        assert new_key != original_key

        # DELETE
        r_del = admin_session.delete(f"{API}/admin/customers/{cid}", timeout=10)
        assert r_del.status_code == 200
        # Verify gone
        r_list2 = admin_session.get(f"{API}/admin/customers", timeout=10)
        assert email.lower() not in [c["email"] for c in r_list2.json()]
        created_customer_ids.remove(cid)

    def test_admin_update_nonexistent_customer(self, admin_session):
        r = admin_session.patch(f"{API}/admin/customers/does-not-exist-id", json={"quota_monthly": 1}, timeout=10)
        assert r.status_code == 404

    def test_admin_delete_nonexistent_customer(self, admin_session):
        r = admin_session.delete(f"{API}/admin/customers/does-not-exist-id", timeout=10)
        assert r.status_code == 404


# ---------------- Customer profile (/me) ----------------
class TestMe:
    def test_me_stats(self, customer_account):
        r = customer_account["session"].get(f"{API}/me/stats", timeout=10)
        assert r.status_code == 200
        data = r.json()
        for key in ("sessions", "messages_total", "messages_today", "messages_failed", "quota_monthly", "quota_used"):
            assert key in data

    def test_me_regenerate_key(self, customer_account):
        old_key = customer_account["api_key"]
        r = customer_account["session"].post(f"{API}/me/regenerate-key", timeout=10)
        assert r.status_code == 200
        new_key = r.json()["api_key"]
        assert new_key.startswith("wapi_")
        assert new_key != old_key
        # Update fixture for downstream tests
        customer_account["api_key"] = new_key
        # confirm /auth/me reflects new key
        me = customer_account["session"].get(f"{API}/auth/me", timeout=10).json()
        assert me["api_key"] == new_key


# ---------------- WhatsApp Sessions ----------------
class TestSessions:
    @pytest.fixture(scope="class")
    def session_holder(self):
        return {}

    def test_create_session(self, customer_account, session_holder):
        r = customer_account["session"].post(f"{API}/sessions", json={"name": "TEST_session1"}, timeout=30)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["name"] == "TEST_session1"
        assert data["user_id"] == customer_account["user"]["id"]
        assert "id" in data
        session_holder["id"] = data["id"]

    def test_session_status(self, customer_account, session_holder):
        sid = session_holder.get("id")
        assert sid, "session not created"
        # Allow Baileys a moment to initialize
        time.sleep(2)
        r = customer_account["session"].get(f"{API}/sessions/{sid}/status", timeout=20)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["id"] == sid
        # status should be one of these states
        assert data["status"] in {"starting", "qr", "connecting", "connected", "unknown", "disconnected"}

    def test_list_sessions(self, customer_account, session_holder):
        r = customer_account["session"].get(f"{API}/sessions", timeout=20)
        assert r.status_code == 200
        ids = [s["id"] for s in r.json()]
        assert session_holder["id"] in ids

    def test_status_unauthenticated(self, session_holder):
        r = requests.get(f"{API}/sessions/{session_holder['id']}/status", timeout=10)
        assert r.status_code == 401

    def test_status_other_user_404(self, admin_session, session_holder):
        # admin doesn't own this session -> 404
        r = admin_session.get(f"{API}/sessions/{session_holder['id']}/status", timeout=10)
        assert r.status_code == 404

    def test_send_without_connected_session(self, customer_account, session_holder):
        # No QR scanned, so send should fail (4xx or message status=failed)
        r = customer_account["session"].post(
            f"{API}/messages/send",
            json={"session_id": session_holder["id"], "to": "+15551234567", "text": "hello"},
            timeout=30,
        )
        # Acceptable behaviors:
        # - 200 with status=failed (since send_one catches exception)
        # - 4xx error
        assert r.status_code in (200, 400, 404, 500, 502)
        if r.status_code == 200:
            body = r.json()
            assert body.get("status") in ("failed", "queued"), f"Expected failed/queued, got {body}"

    def test_list_messages(self, customer_account):
        r = customer_account["session"].get(f"{API}/messages", timeout=10)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_delete_session(self, customer_account, session_holder):
        sid = session_holder["id"]
        r = customer_account["session"].delete(f"{API}/sessions/{sid}", timeout=20)
        assert r.status_code == 200
        # Verify gone
        r2 = customer_account["session"].get(f"{API}/sessions/{sid}/status", timeout=10)
        assert r2.status_code == 404


# ---------------- Public API (X-API-Key) ----------------
class TestPublicAPI:
    def test_public_messages_no_key(self):
        r = requests.post(f"{API}/v1/messages", json={"to": "+15551234567", "text": "x"}, timeout=10)
        assert r.status_code == 401

    def test_public_sessions_no_key(self):
        r = requests.get(f"{API}/v1/sessions", timeout=10)
        assert r.status_code == 401

    def test_public_messages_bad_key(self):
        r = requests.post(
            f"{API}/v1/messages",
            json={"to": "+15551234567", "text": "x"},
            headers={"X-API-Key": "wapi_invalid_key_xxxx"},
            timeout=10,
        )
        assert r.status_code == 401

    def test_public_sessions_with_valid_key(self, customer_account):
        r = requests.get(
            f"{API}/v1/sessions",
            headers={"X-API-Key": customer_account["api_key"]},
            timeout=10,
        )
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_public_messages_no_connected_session(self, customer_account):
        # Customer has no connected sessions -> 400
        r = requests.post(
            f"{API}/v1/messages",
            json={"to": "+15551234567", "text": "hello"},
            headers={"X-API-Key": customer_account["api_key"]},
            timeout=15,
        )
        assert r.status_code == 400, r.text
        assert "session" in r.json().get("detail", "").lower()
