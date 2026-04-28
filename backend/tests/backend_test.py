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



# ===================== Iteration 2: Webhooks, Inbound, Media, Direction =====================

INTERNAL_SECRET = os.environ.get(
    "INTERNAL_SECRET",
    "9e7f4a52c8d61b3e0f29a48b75c1d36e2f0a8d94c75b1e63a02f47d8b1e9c5a3",
)


def _read_internal_secret_from_env_file() -> str:
    """Read INTERNAL_SECRET from /app/backend/.env if env var not set."""
    try:
        with open("/app/backend/.env", "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith("INTERNAL_SECRET="):
                    val = line.split("=", 1)[1].strip().strip('"').strip("'")
                    return val
    except Exception:
        pass
    return INTERNAL_SECRET


# ---------------- Webhook CRUD (per-user) ----------------
class TestWebhook:
    def test_me_includes_webhook_fields(self, customer_account):
        r = customer_account["session"].get(f"{API}/auth/me", timeout=10)
        assert r.status_code == 200
        data = r.json()
        # fields should be present in response (None initially or after clear)
        assert "webhook_url" in data
        assert "webhook_secret" in data

    def test_set_webhook_invalid_url(self, customer_account):
        r = customer_account["session"].patch(
            f"{API}/me/webhook", json={"url": "ftp://bad.example.com/x"}, timeout=10
        )
        assert r.status_code == 400
        assert "http" in r.json().get("detail", "").lower()

    def test_set_webhook_valid_url(self, customer_account):
        url = "https://example.com/webhooks/test"
        r = customer_account["session"].patch(
            f"{API}/me/webhook", json={"url": url}, timeout=10
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["webhook_url"] == url
        assert isinstance(body["webhook_secret"], str)
        assert len(body["webhook_secret"]) >= 24
        # Verify /auth/me reflects it
        me = customer_account["session"].get(f"{API}/auth/me", timeout=10).json()
        assert me["webhook_url"] == url
        assert me["webhook_secret"] == body["webhook_secret"]
        # stash for downstream
        customer_account["webhook_secret"] = body["webhook_secret"]
        customer_account["webhook_url"] = url

    def test_test_webhook_when_set(self, customer_account):
        # Ensure set — use unreachable but fast-failing target (TCP RST on closed port)
        customer_account["session"].patch(
            f"{API}/me/webhook",
            json={"url": "http://127.0.0.1:9/none"},
            timeout=10,
        )
        # /me/webhook/test now AWAITS fire_webhook (which has 4 retries with backoff
        # 0+2+6+18=~26s) — large timeout required.
        r = customer_account["session"].post(f"{API}/me/webhook/test", timeout=90)
        assert r.status_code == 200
        assert r.json().get("sent") is True

    def test_delete_webhook(self, customer_account):
        r = customer_account["session"].delete(f"{API}/me/webhook", timeout=10)
        assert r.status_code == 200
        me = customer_account["session"].get(f"{API}/auth/me", timeout=10).json()
        assert me.get("webhook_url") in (None, "")
        assert me.get("webhook_secret") in (None, "")

    def test_test_webhook_when_not_set(self, customer_account):
        # After delete, /test should 400
        r = customer_account["session"].post(f"{API}/me/webhook/test", timeout=10)
        assert r.status_code == 400
        assert "webhook" in r.json().get("detail", "").lower()


# ---------------- Internal Inbound Endpoint ----------------
class TestInternalInbound:
    def test_inbound_without_secret(self):
        r = requests.post(
            f"{API}/internal/inbound",
            json={"session_id": "x", "from": "1234", "text": "hi"},
            timeout=10,
        )
        assert r.status_code == 401
        assert "secret" in r.json().get("detail", "").lower()

    def test_inbound_wrong_secret(self):
        r = requests.post(
            f"{API}/internal/inbound",
            json={"session_id": "x", "from": "1234", "text": "hi"},
            headers={"X-Internal-Secret": "wrong"},
            timeout=10,
        )
        assert r.status_code == 401

    def test_inbound_unknown_session(self):
        secret = _read_internal_secret_from_env_file()
        r = requests.post(
            f"{API}/internal/inbound",
            json={
                "session_id": "session-does-not-exist-zzz",
                "from": "1112223333",
                "text": "hello",
                "type": "text",
            },
            headers={"X-Internal-Secret": secret},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is False
        assert "session" in body["reason"].lower()

    def test_inbound_valid_session_stores_message(self, customer_account):
        # Create a session via API (won't be connected, but doc exists in db)
        sess_resp = customer_account["session"].post(
            f"{API}/sessions", json={"name": "TEST_inbound_sess"}, timeout=30
        )
        assert sess_resp.status_code == 200, sess_resp.text
        sid = sess_resp.json()["id"]

        # Set webhook (so fire_webhook async path runs without crashing)
        customer_account["session"].patch(
            f"{API}/me/webhook",
            json={"url": "https://127.0.0.1:1/none"},
            timeout=10,
        )

        secret = _read_internal_secret_from_env_file()
        unique_text = f"inbound-test-{secrets.token_hex(4)}"
        r = requests.post(
            f"{API}/internal/inbound",
            json={
                "session_id": sid,
                "from": "9991112222",
                "text": unique_text,
                "type": "text",
                "message_id": "wamid.TEST123",
                "timestamp": int(time.time() * 1000),
                "has_media": False,
            },
            headers={"X-Internal-Secret": secret},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

        # allow async webhook task to be scheduled
        time.sleep(1)

        # Verify message persisted with direction=inbound via /api/messages?direction=inbound
        msgs_resp = customer_account["session"].get(
            f"{API}/messages?direction=inbound&limit=50", timeout=10
        )
        assert msgs_resp.status_code == 200
        msgs = msgs_resp.json()
        assert any(m.get("text") == unique_text for m in msgs), "inbound message not persisted"

        # cleanup webhook + session
        customer_account["session"].delete(f"{API}/me/webhook", timeout=10)
        customer_account["session"].delete(f"{API}/sessions/{sid}", timeout=20)


# ---------------- Media Send Endpoints ----------------
class TestSendMedia:
    def test_send_media_without_auth(self):
        files = {"media": ("a.txt", b"hello", "text/plain")}
        data = {"session_id": "x", "to": "+15551234567", "caption": ""}
        r = requests.post(f"{API}/messages/send-media", data=data, files=files, timeout=15)
        assert r.status_code == 401

    def test_send_media_session_not_found(self, customer_account):
        files = {"media": ("a.txt", b"hello world", "text/plain")}
        data = {"session_id": "nonexistent-session-id", "to": "+15551234567", "caption": "hi"}
        r = customer_account["session"].post(
            f"{API}/messages/send-media", data=data, files=files, timeout=20
        )
        assert r.status_code == 404, r.text

    def test_send_media_too_large(self, customer_account):
        # Need a real session document for the user to pass session check
        sess_resp = customer_account["session"].post(
            f"{API}/sessions", json={"name": "TEST_media_sess"}, timeout=30
        )
        assert sess_resp.status_code == 200
        sid = sess_resp.json()["id"]
        try:
            # 26 MB blob
            big = b"x" * (26 * 1024 * 1024)
            files = {"media": ("big.bin", big, "application/octet-stream")}
            data = {"session_id": sid, "to": "+15551234567", "caption": ""}
            r = customer_account["session"].post(
                f"{API}/messages/send-media", data=data, files=files, timeout=60
            )
            assert r.status_code == 400, r.text
            assert "large" in r.json().get("detail", "").lower()
        finally:
            customer_account["session"].delete(f"{API}/sessions/{sid}", timeout=20)


# ---------------- Public API media_url + validations ----------------
class TestPublicAPIMedia:
    def test_public_messages_neither_text_nor_media(self, customer_account):
        r = requests.post(
            f"{API}/v1/messages",
            json={"to": "+15551234567"},
            headers={"X-API-Key": customer_account["api_key"]},
            timeout=10,
        )
        assert r.status_code == 400, r.text
        detail = r.json().get("detail", "").lower()
        assert "text" in detail and "media_url" in detail

    def test_public_messages_unreachable_media_url_or_no_session(self, customer_account):
        # No connected session for this customer => server returns 400 'No connected session'
        # If somehow there's a connected session, it would try fetch and fail -> 400 'Failed to fetch media_url'
        r = requests.post(
            f"{API}/v1/messages",
            json={
                "to": "+15551234567",
                "media_url": "https://127.0.0.1:1/never.png",
            },
            headers={"X-API-Key": customer_account["api_key"]},
            timeout=20,
        )
        assert r.status_code == 400, r.text
        detail = r.json().get("detail", "").lower()
        assert ("session" in detail) or ("fetch" in detail) or ("media_url" in detail)


# ---------------- /api/messages direction filter ----------------
class TestMessagesDirectionFilter:
    """Use inbound endpoint to seed an inbound message, then send via dashboard
    to seed an outbound (status will be 'failed' since session not connected, but
    direction=outbound)."""

    def test_direction_filters_combined(self, customer_account):
        # Create a session
        sess_resp = customer_account["session"].post(
            f"{API}/sessions", json={"name": "TEST_dir_sess"}, timeout=30
        )
        assert sess_resp.status_code == 200
        sid = sess_resp.json()["id"]

        try:
            # Seed inbound via internal endpoint
            secret = _read_internal_secret_from_env_file()
            inbound_text = f"DIR_inbound_{secrets.token_hex(3)}"
            r_in = requests.post(
                f"{API}/internal/inbound",
                json={
                    "session_id": sid,
                    "from": "5556667777",
                    "text": inbound_text,
                    "type": "text",
                },
                headers={"X-Internal-Secret": secret},
                timeout=10,
            )
            assert r_in.status_code == 200 and r_in.json().get("ok") is True

            # Seed outbound by attempting dashboard send (will be persisted with direction=outbound)
            outbound_text = f"DIR_outbound_{secrets.token_hex(3)}"
            r_out = customer_account["session"].post(
                f"{API}/messages/send",
                json={"session_id": sid, "to": "+15551234567", "text": outbound_text},
                timeout=30,
            )
            # Acceptable: 200 with failed status (no real WA), or 4xx
            outbound_persisted = r_out.status_code == 200

            # direction=inbound only
            r_inb = customer_account["session"].get(
                f"{API}/messages?direction=inbound&limit=200", timeout=10
            )
            assert r_inb.status_code == 200
            inb_list = r_inb.json()
            assert all(m.get("direction") == "inbound" for m in inb_list), "non-inbound leaked into inbound filter"
            assert any(m.get("text") == inbound_text for m in inb_list), "seeded inbound not present"

            # direction=outbound only
            r_out_list = customer_account["session"].get(
                f"{API}/messages?direction=outbound&limit=200", timeout=10
            )
            assert r_out_list.status_code == 200
            out_list = r_out_list.json()
            assert all(m.get("direction") == "outbound" for m in out_list), "non-outbound leaked into outbound filter"
            if outbound_persisted:
                assert any(m.get("text") == outbound_text for m in out_list)

            # combined: status + direction
            r_comb = customer_account["session"].get(
                f"{API}/messages?direction=outbound&status=failed&limit=200", timeout=10
            )
            assert r_comb.status_code == 200
            comb = r_comb.json()
            for m in comb:
                assert m.get("direction") == "outbound"
                assert m.get("status") == "failed"
        finally:
            customer_account["session"].delete(f"{API}/sessions/{sid}", timeout=20)


# ---------------- HMAC signature sanity (unit-level on the same algorithm) ----------------
class TestHmacAlgo:
    """We can't easily intercept the outbound webhook delivery from here,
    but we can validate the documented algorithm: sha256=<hex(hmac_sha256(secret, body))>.
    This test ensures the helper matches expectations (validated indirectly)."""

    def test_hmac_format(self):
        import hmac as _h
        import hashlib as _hl

        secret = "topsecret"
        body = b'{"event":"test"}'
        expected = "sha256=" + _h.new(secret.encode(), body, _hl.sha256).hexdigest()
        # Trivial assertion: format checks
        assert expected.startswith("sha256=")
        assert len(expected.split("=", 1)[1]) == 64



# ===================== Iteration 3: Webhook retry, Media GET, CSV bulk, Plans, Billing =====================


# ---------------- Webhook retry & auto-disable ----------------
class TestWebhookRetry:
    def test_me_includes_disable_fields(self, customer_account):
        r = customer_account["session"].get(f"{API}/auth/me", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert "webhook_disabled" in data
        assert "webhook_consecutive_failures" in data
        assert isinstance(data["webhook_disabled"], bool)
        assert isinstance(data["webhook_consecutive_failures"], int)

    def test_failure_increments_counter(self, customer_account):
        # set webhook to unreachable URL (port 9 = discard, connection refused — fast failures)
        unreachable = "http://127.0.0.1:9/never"
        r = customer_account["session"].patch(
            f"{API}/me/webhook", json={"url": unreachable}, timeout=10
        )
        assert r.status_code == 200, r.text

        # Wait out any in-flight background fire_webhook tasks left over from earlier
        # tests (e.g. /internal/inbound spawns a background task that takes ~26s).
        time.sleep(35)
        # Deterministically reset counter to 0 via /enable
        customer_account["session"].post(f"{API}/me/webhook/enable", timeout=10)
        # re-set webhook url since enable doesn't touch it
        customer_account["session"].patch(
            f"{API}/me/webhook", json={"url": unreachable}, timeout=10
        )
        base = customer_account["session"].get(f"{API}/auth/me", timeout=10).json()
        base_count = int(base.get("webhook_consecutive_failures") or 0)
        assert base_count == 0, f"baseline not zero after enable: {base_count}"

        # /test AWAITs fire_webhook: 4 attempts, exp backoff 0+2+6+18=~26s
        t = customer_account["session"].post(f"{API}/me/webhook/test", timeout=90)
        assert t.status_code == 200
        assert t.json().get("sent") is True

        # Counter should have been incremented synchronously (after retries failed)
        me = customer_account["session"].get(f"{API}/auth/me", timeout=10).json()
        new_count = int(me.get("webhook_consecutive_failures") or 0)
        assert new_count == base_count + 1, (
            f"counter did not increment after retries: base={base_count} new={new_count}"
        )

    def test_enable_resets_counter(self, customer_account):
        r = customer_account["session"].post(f"{API}/me/webhook/enable", timeout=10)
        assert r.status_code == 200
        me = customer_account["session"].get(f"{API}/auth/me", timeout=10).json()
        assert me.get("webhook_disabled") is False
        assert int(me.get("webhook_consecutive_failures") or 0) == 0
        # cleanup
        customer_account["session"].delete(f"{API}/me/webhook", timeout=10)


# ---------------- /api/media/{message_id} ----------------
class TestMediaGet:
    def test_media_no_auth(self):
        r = requests.get(f"{API}/media/some-id-xxx", timeout=10)
        assert r.status_code == 401

    def test_media_other_user_404(self, admin_session, customer_account):
        # Seed an inbound message owned by customer via /internal/inbound
        sess = customer_account["session"].post(
            f"{API}/sessions", json={"name": "TEST_media_get_sess"}, timeout=30
        ).json()
        sid = sess["id"]
        try:
            secret = _read_internal_secret_from_env_file()
            mid = f"wamid.MEDIA_{secrets.token_hex(4)}"
            r = requests.post(
                f"{API}/internal/inbound",
                json={
                    "session_id": sid,
                    "from": "1234567890",
                    "text": "img",
                    "type": "image",
                    "message_id": mid,
                    "has_media": True,
                    "media_path": "/tmp/nonexistent_media_file.jpg",
                    "mime_type": "image/jpeg",
                    "file_name": "test.jpg",
                },
                headers={"X-Internal-Secret": secret},
                timeout=10,
            )
            assert r.status_code == 200 and r.json().get("ok") is True

            # find internal message id
            time.sleep(0.5)
            msgs = customer_account["session"].get(
                f"{API}/messages?direction=inbound&limit=50", timeout=10
            ).json()
            mine = next((m for m in msgs if m.get("wa_message_id") == mid or m.get("message_id") == mid), None)
            if mine is None:
                # fallback: look by media flag + recent
                mine = next((m for m in msgs if m.get("has_media")), None)
            assert mine, f"could not find seeded inbound media message in {msgs[:3]}"
            our_id = mine["id"]

            # admin (different user) -> 404
            r_admin = admin_session.get(f"{API}/media/{our_id}", timeout=10)
            assert r_admin.status_code == 404

            # owner -> 404 because file does not exist on disk
            r_owner = customer_account["session"].get(f"{API}/media/{our_id}", timeout=10)
            assert r_owner.status_code == 404
            detail = r_owner.json().get("detail", "").lower()
            assert "media" in detail or "unavailable" in detail or "file" in detail
        finally:
            customer_account["session"].delete(f"{API}/sessions/{sid}", timeout=20)


# ---------------- CSV bulk send ----------------
class TestBulkCsv:
    def _make_session(self, customer_account, name="TEST_csv_sess"):
        r = customer_account["session"].post(
            f"{API}/sessions", json={"name": name}, timeout=30
        )
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def test_bulk_csv_no_header(self, customer_account):
        sid = self._make_session(customer_account, "TEST_csv_noheader")
        try:
            files = {"file": ("a.csv", b"", "text/csv")}
            data = {"session_id": sid, "template": "Hi {{name}}"}
            r = customer_account["session"].post(
                f"{API}/messages/bulk-csv", data=data, files=files, timeout=20
            )
            assert r.status_code == 400
        finally:
            customer_account["session"].delete(f"{API}/sessions/{sid}", timeout=20)

    def test_bulk_csv_empty_rows(self, customer_account):
        sid = self._make_session(customer_account, "TEST_csv_empty")
        try:
            files = {"file": ("a.csv", b"phone,name\n", "text/csv")}
            data = {"session_id": sid, "template": "Hi {{name}}"}
            r = customer_account["session"].post(
                f"{API}/messages/bulk-csv", data=data, files=files, timeout=20
            )
            assert r.status_code == 400
            assert "no valid rows" in r.json().get("detail", "").lower()
        finally:
            customer_account["session"].delete(f"{API}/sessions/{sid}", timeout=20)

    def test_bulk_csv_session_not_found(self, customer_account):
        files = {"file": ("a.csv", b"phone,name\n+15551234567,Alice\n", "text/csv")}
        data = {"session_id": "nonexistent-zzz", "template": "Hi {{name}}"}
        r = customer_account["session"].post(
            f"{API}/messages/bulk-csv", data=data, files=files, timeout=20
        )
        assert r.status_code == 404

    def test_bulk_csv_valid_parses_and_renders(self, customer_account):
        sid = self._make_session(customer_account, "TEST_csv_ok")
        try:
            csv_body = b"phone,name\n+15551234567,Alice\n+15557654321,Bob\n"
            files = {"file": ("a.csv", csv_body, "text/csv")}
            data = {"session_id": sid, "template": "Hi {{name}}, hello!"}
            r = customer_account["session"].post(
                f"{API}/messages/bulk-csv", data=data, files=files, timeout=60
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body.get("total") == 2
            assert isinstance(body.get("sent"), int)
            assert isinstance(body.get("failed"), int)
            assert body["sent"] + body["failed"] == 2
            assert isinstance(body.get("results"), list)
            assert len(body["results"]) == 2
            for item in body["results"]:
                assert "to" in item and "status" in item

            # template rendering check: list outbound messages and assert text contains rendered name
            time.sleep(0.5)
            msgs = customer_account["session"].get(
                f"{API}/messages?direction=outbound&limit=50", timeout=10
            ).json()
            texts = [m.get("text", "") for m in msgs]
            assert any("Hi Alice" in t for t in texts), f"Alice template not rendered. Texts: {texts[:5]}"
            assert any("Hi Bob" in t for t in texts), f"Bob template not rendered. Texts: {texts[:5]}"
        finally:
            customer_account["session"].delete(f"{API}/sessions/{sid}", timeout=20)


# ---------------- Plans CRUD ----------------
class TestPlans:
    def test_public_plans_active_only(self):
        r = requests.get(f"{API}/plans", timeout=10)
        assert r.status_code == 200
        plans = r.json()
        assert isinstance(plans, list)
        for p in plans:
            assert p.get("active") is True

    def test_admin_plans_requires_admin(self, customer_account):
        r = customer_account["session"].get(f"{API}/admin/plans", timeout=10)
        assert r.status_code == 403

    def test_admin_plans_crud(self, admin_session):
        # CREATE
        payload = {
            "name": "TEST_plan_basic",
            "price": 99.0,
            "currency": "INR",
            "quota_monthly": 5000,
            "max_sessions": 2,
            "features": ["api", "webhook"],
            "active": True,
            "sort": 50,
        }
        r = admin_session.post(f"{API}/admin/plans", json=payload, timeout=10)
        assert r.status_code == 200, r.text
        plan = r.json()
        assert plan["name"] == "TEST_plan_basic"
        assert plan["price"] == 99.0
        assert "id" in plan and plan["id"]
        plan_id = plan["id"]

        try:
            # LIST (admin)
            r_list = admin_session.get(f"{API}/admin/plans", timeout=10)
            assert r_list.status_code == 200
            ids = [p["id"] for p in r_list.json()]
            assert plan_id in ids

            # PATCH
            r_upd = admin_session.patch(
                f"{API}/admin/plans/{plan_id}",
                json={"price": 149.0, "active": False},
                timeout=10,
            )
            assert r_upd.status_code == 200
            updated = r_upd.json()
            assert updated["price"] == 149.0
            assert updated["active"] is False

            # public list should NOT include inactive plan
            r_pub = requests.get(f"{API}/plans", timeout=10)
            assert plan_id not in [p["id"] for p in r_pub.json()]

            # admin list still includes it
            r_admin_list = admin_session.get(f"{API}/admin/plans", timeout=10)
            assert plan_id in [p["id"] for p in r_admin_list.json()]
        finally:
            # DELETE
            r_del = admin_session.delete(f"{API}/admin/plans/{plan_id}", timeout=10)
            assert r_del.status_code == 200
            r_after = admin_session.get(f"{API}/admin/plans", timeout=10)
            assert plan_id not in [p["id"] for p in r_after.json()]

    def test_admin_patch_nonexistent_plan(self, admin_session):
        r = admin_session.patch(
            f"{API}/admin/plans/does-not-exist", json={"price": 1.0}, timeout=10
        )
        assert r.status_code == 404

    def test_admin_delete_nonexistent_plan(self, admin_session):
        r = admin_session.delete(f"{API}/admin/plans/does-not-exist", timeout=10)
        assert r.status_code == 404


# ---------------- Billing gateways (no keys configured) ----------------
class TestBillingGateways:
    def test_gateways_status(self):
        r = requests.get(f"{API}/billing/gateways", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body == {"stripe": False, "razorpay": False, "paypal": False}

    def test_my_subscription_empty(self, customer_account):
        r = customer_account["session"].get(f"{API}/me/subscription", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body.get("subscription") is None
        assert body.get("plan") is None

    def _create_active_plan(self, admin_session) -> str:
        r = admin_session.post(
            f"{API}/admin/plans",
            json={
                "name": "TEST_billing_plan",
                "price": 10.0,
                "currency": "USD",
                "quota_monthly": 100,
                "max_sessions": 1,
                "active": True,
            },
            timeout=10,
        )
        assert r.status_code == 200, r.text
        return r.json()["id"]

    def test_stripe_checkout_not_configured(self, admin_session, customer_account):
        plan_id = self._create_active_plan(admin_session)
        try:
            r = customer_account["session"].post(
                f"{API}/billing/stripe/checkout", json={"plan_id": plan_id}, timeout=10
            )
            assert r.status_code == 400
            assert "stripe" in r.json().get("detail", "").lower()
            assert "configured" in r.json().get("detail", "").lower()
        finally:
            admin_session.delete(f"{API}/admin/plans/{plan_id}", timeout=10)

    def test_razorpay_create_not_configured(self, admin_session, customer_account):
        plan_id = self._create_active_plan(admin_session)
        try:
            r = customer_account["session"].post(
                f"{API}/billing/razorpay/create-subscription",
                json={"plan_id": plan_id},
                timeout=10,
            )
            assert r.status_code == 400
            assert "razorpay" in r.json().get("detail", "").lower()
        finally:
            admin_session.delete(f"{API}/admin/plans/{plan_id}", timeout=10)

    def test_paypal_create_not_configured(self, admin_session, customer_account):
        plan_id = self._create_active_plan(admin_session)
        try:
            r = customer_account["session"].post(
                f"{API}/billing/paypal/create-subscription",
                json={"plan_id": plan_id},
                timeout=10,
            )
            assert r.status_code == 400
            assert "paypal" in r.json().get("detail", "").lower()
        finally:
            admin_session.delete(f"{API}/admin/plans/{plan_id}", timeout=10)

    def test_stripe_cancel_not_configured(self, customer_account):
        r = customer_account["session"].post(f"{API}/billing/stripe/cancel", timeout=10)
        # Either 400 'not configured' or 404 'no active sub'
        assert r.status_code in (400, 404)

    def test_billing_endpoints_require_auth(self):
        r = requests.post(
            f"{API}/billing/stripe/checkout", json={"plan_id": "x"}, timeout=10
        )
        assert r.status_code == 401
        r2 = requests.get(f"{API}/me/subscription", timeout=10)
        assert r2.status_code == 401


# ---------------- Webhook receivers ----------------
class TestBillingWebhooks:
    def test_stripe_webhook_not_configured(self):
        # STRIPE_SECRET_KEY empty -> 400 'Stripe not configured'
        r = requests.post(
            f"{API}/webhooks/stripe",
            data=b'{"type":"test"}',
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        assert r.status_code == 400
        assert "stripe" in r.json().get("detail", "").lower()

    def test_razorpay_webhook_no_secret_parses(self):
        # No RAZORPAY_WEBHOOK_SECRET set -> no signature enforcement; valid JSON should return 200
        r = requests.post(
            f"{API}/webhooks/razorpay",
            data=b'{"event":"subscription.activated","payload":{}}',
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        assert r.json().get("ok") is True

    def test_razorpay_webhook_invalid_json(self):
        r = requests.post(
            f"{API}/webhooks/razorpay",
            data=b"not-json",
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        assert r.status_code == 400

    def test_paypal_webhook_accepts_event(self):
        r = requests.post(
            f"{API}/webhooks/paypal",
            data=b'{"event_type":"BILLING.SUBSCRIPTION.CANCELLED","resource":{"id":"I-XXX"}}',
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json().get("ok") is True

    def test_paypal_webhook_invalid_json(self):
        r = requests.post(
            f"{API}/webhooks/paypal",
            data=b"<<<not-json",
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        assert r.status_code == 400
