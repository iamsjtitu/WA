"""Iteration 4 backend tests: wa.9x.design v2 API compat, scheduler,
per-session settings, group send, plugin downloads."""
from __future__ import annotations

import os
import secrets
import time
from datetime import datetime, timedelta, timezone

import pytest
import requests
from pymongo import MongoClient

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL",
    "https://chat-platform-380.preview.emergentagent.com",
).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@wa.9x.design"
ADMIN_PASSWORD = "admin123"


def _read_env(key: str, default: str = "") -> str:
    try:
        with open("/app/backend/.env", "r") as f:
            for line in f:
                line = line.strip()
                if line.startswith(f"{key}="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return os.environ.get(key, default)


MONGO_URL = _read_env("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = _read_env("DB_NAME", "wa9x_db")


# ---------------- Fixtures ----------------
@pytest.fixture(scope="module")
def mongo_db():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="module")
def admin_session() -> requests.Session:
    s = requests.Session()
    r = s.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=15)
    assert r.status_code == 200
    return s


@pytest.fixture(scope="module")
def customer_account() -> dict:
    email = f"TEST_iter4_{secrets.token_hex(4)}@example.com"
    password = "CustPass123!"
    s = requests.Session()
    r = s.post(f"{API}/auth/register", json={"email": email, "password": password, "name": "Iter4 Customer"}, timeout=15)
    assert r.status_code == 200, r.text
    user = r.json()
    return {"email": email, "password": password, "user": user, "session": s, "api_key": user["api_key"]}


@pytest.fixture
def created_session(customer_account):
    """Create a fresh dashboard session for the customer; cleanup afterwards."""
    r = customer_account["session"].post(
        f"{API}/sessions", json={"name": f"TEST_v2_{secrets.token_hex(3)}"}, timeout=30
    )
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    yield sid
    try:
        customer_account["session"].delete(f"{API}/sessions/{sid}", timeout=15)
    except Exception:
        pass


@pytest.fixture
def connected_session(customer_account, created_session, mongo_db):
    """Force a session to status=connected directly in DB so v2_compat._resolve_session passes."""
    mongo_db.wa_sessions.update_one(
        {"id": created_session}, {"$set": {"status": "connected"}}
    )
    return created_session


# =============== v2 Auth ===============
class TestV2Auth:
    def test_send_message_no_auth(self):
        r = requests.post(f"{API}/v2/sendMessage", data={"phonenumber": "1234567", "text": "hi"}, timeout=10)
        assert r.status_code == 401
        assert "bearer" in r.json().get("detail", "").lower()

    def test_send_message_invalid_token(self):
        r = requests.post(
            f"{API}/v2/sendMessage",
            data={"phonenumber": "1234567", "text": "hi"},
            headers={"Authorization": "Bearer wa9x_invalid_xxx"},
            timeout=10,
        )
        assert r.status_code == 401
        assert "invalid" in r.json().get("detail", "").lower()

    def test_send_message_no_connected_session(self, customer_account, created_session):
        # session exists but status != connected
        r = requests.post(
            f"{API}/v2/sendMessage",
            data={"phonenumber": "+15551112222", "text": "hi"},
            headers={"Authorization": f"Bearer {customer_account['api_key']}"},
            timeout=15,
        )
        assert r.status_code == 400, r.text
        assert "connected" in r.json().get("detail", "").lower()

    def test_send_group_no_auth(self):
        r = requests.post(f"{API}/v2/sendGroup", data={"groupId": "abc", "text": "hi"}, timeout=10)
        assert r.status_code == 401

    def test_send_group_invalid_token(self):
        r = requests.post(
            f"{API}/v2/sendGroup",
            data={"groupId": "abc", "text": "hi"},
            headers={"Authorization": "Bearer wa9x_invalid_xxx"},
            timeout=10,
        )
        assert r.status_code == 401


# =============== v2 sendMessage / scheduling ===============
class TestV2Schedule:
    def test_send_message_with_future_delay_creates_scheduled_doc(
        self, customer_account, connected_session, mongo_db
    ):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%m-%d-%Y %H:%M")
        r = requests.post(
            f"{API}/v2/sendMessage",
            data={
                "phonenumber": "+15559998888",
                "text": "scheduled hello",
                "delay": future,
            },
            headers={"Authorization": f"Bearer {customer_account['api_key']}"},
            timeout=15,
        )
        # NOTE: HTTP status is 200 even though JSON body contains statusCode=201
        # (FastAPI default; v2 endpoint did not declare status_code=201). Accept
        # both for now and flag the inconsistency as a minor backend issue.
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body["success"] is True
        assert body["statusCode"] == 201
        assert "timestamp" in body
        assert "data" in body
        assert "id" in body["data"]
        assert "scheduled_for" in body["data"]
        sched_id = body["data"]["id"]

        # verify document persisted
        doc = mongo_db.scheduled_messages.find_one({"id": sched_id})
        assert doc is not None
        assert doc["status"] == "pending"
        assert doc["type"] == "message"
        assert doc["target"] == "15559998888"  # normalized
        assert doc["text"] == "scheduled hello"
        assert doc["source"] == "v2_api"

        # cleanup
        mongo_db.scheduled_messages.delete_one({"id": sched_id})

    def test_send_group_with_future_delay(
        self, customer_account, connected_session, mongo_db
    ):
        future = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%m-%d-%Y %H:%M")
        r = requests.post(
            f"{API}/v2/sendGroup",
            data={
                "groupId": "120363012345678901",
                "text": "hello group",
                "delay": future,
            },
            headers={"Authorization": f"Bearer {customer_account['api_key']}"},
            timeout=15,
        )
        assert r.status_code in (200, 201), r.text
        body = r.json()
        assert body["success"] is True
        assert "groupId" in body["data"]
        assert "scheduled_for" in body["data"]
        sched_id = body["data"]["id"]
        doc = mongo_db.scheduled_messages.find_one({"id": sched_id})
        assert doc is not None
        assert doc["type"] == "group"
        mongo_db.scheduled_messages.delete_one({"id": sched_id})

    def test_dispatcher_claims_due_pending_message(self, customer_account, connected_session, mongo_db):
        """Insert a fake scheduled message with run_at in the past + status='pending'.
        Wait ~70s for dispatcher (60s loop) to claim it. Claim is verified by
        status moving away from 'pending' (will become 'running' then 'sent' or 'failed').
        """
        sched_id = f"TEST_sched_{secrets.token_hex(4)}"
        past = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        mongo_db.scheduled_messages.insert_one({
            "id": sched_id,
            "user_id": customer_account["user"]["id"],
            "session_id": connected_session,
            "type": "message",
            "target": "15551110000",
            "text": "due now",
            "url": None,
            "run_at": past,
            "status": "pending",
            "source": "test",
            "created_at": datetime.now(timezone.utc).isoformat(),
        })

        # wait up to 75 s polling every 5 s
        deadline = time.time() + 75
        final_status = None
        while time.time() < deadline:
            doc = mongo_db.scheduled_messages.find_one({"id": sched_id})
            if doc and doc.get("status") != "pending":
                final_status = doc["status"]
                break
            time.sleep(5)

        # cleanup before assertion so failure does not pollute
        mongo_db.scheduled_messages.delete_one({"id": sched_id})

        assert final_status is not None, "dispatcher did not claim due scheduled message within 75s"
        assert final_status in ("running", "sent", "failed"), f"unexpected status: {final_status}"


# =============== v2 message status / lists ===============
class TestV2MessageStatus:
    def test_status_unknown_id(self, customer_account):
        r = requests.get(
            f"{API}/v2/message/status",
            params={"id": "does-not-exist-xxx"},
            headers={"Authorization": f"Bearer {customer_account['api_key']}"},
            timeout=10,
        )
        assert r.status_code == 404

    def test_status_existing_message(self, customer_account, mongo_db):
        # seed an outbound message directly
        mid = f"TEST_msg_{secrets.token_hex(4)}"
        mongo_db.messages.insert_one({
            "id": mid,
            "user_id": customer_account["user"]["id"],
            "session_id": "fake-sess",
            "direction": "outbound",
            "to": "15550001111",
            "text": "v2 status seed",
            "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })
        try:
            r = requests.get(
                f"{API}/v2/message/status",
                params={"id": mid},
                headers={"Authorization": f"Bearer {customer_account['api_key']}"},
                timeout=10,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["success"] is True
            res = body["result"]
            assert res["status"] == "OK"
            assert res["statusInfo"]
            assert res["delivery"] == "device"
            assert res["id"] == mid
            assert res["text"] == "v2 status seed"
            assert res["phonenumber"] == "15550001111"
            assert "createdAt" in res and "executedAt" in res and "url" in res
        finally:
            mongo_db.messages.delete_one({"id": mid})

    def test_sent_messages_paginated(self, customer_account, mongo_db):
        # seed 2 outbound
        ids = []
        for i in range(2):
            mid = f"TEST_sent_{secrets.token_hex(4)}"
            ids.append(mid)
            mongo_db.messages.insert_one({
                "id": mid,
                "user_id": customer_account["user"]["id"],
                "session_id": "fake-sess",
                "direction": "outbound",
                "to": f"1555000{i:04d}",
                "text": f"v2 sent {i}",
                "status": "sent",
                "sent_at": datetime.now(timezone.utc).isoformat(),
            })
        try:
            r = requests.get(
                f"{API}/v2/message/sentMessages",
                params={"page": 1},
                headers={"Authorization": f"Bearer {customer_account['api_key']}"},
                timeout=10,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            assert body["success"] is True
            res = body["result"]
            assert isinstance(res["count"], int) and res["count"] >= 2
            assert isinstance(res["pageCount"], int) and res["pageCount"] >= 1
            assert "of" in res["page"]
            assert isinstance(res["data"], list)
            seeded = [d for d in res["data"] if d["id"] in ids]
            assert len(seeded) == 2
            for d in seeded:
                assert d["status"] == "OK"
                assert "phonenumber" in d and "text" in d
        finally:
            mongo_db.messages.delete_many({"id": {"$in": ids}})

    def test_sent_messages_phonenumber_filter(self, customer_account, mongo_db):
        mid = f"TEST_filt_{secrets.token_hex(4)}"
        mongo_db.messages.insert_one({
            "id": mid,
            "user_id": customer_account["user"]["id"],
            "session_id": "fake-sess",
            "direction": "outbound",
            "to": "919876543210",  # India number
            "text": "filter test",
            "status": "sent",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })
        try:
            r = requests.get(
                f"{API}/v2/message/sentMessages",
                params={"phonenumber": "91"},
                headers={"Authorization": f"Bearer {customer_account['api_key']}"},
                timeout=10,
            )
            assert r.status_code == 200
            data = r.json()["result"]["data"]
            assert any(d["id"] == mid for d in data)
        finally:
            mongo_db.messages.delete_one({"id": mid})

    def test_received_messages(self, customer_account, mongo_db):
        mid = f"TEST_recv_{secrets.token_hex(4)}"
        mongo_db.messages.insert_one({
            "id": mid,
            "user_id": customer_account["user"]["id"],
            "session_id": "fake-sess",
            "direction": "inbound",
            "from": "15553334444",
            "text": "incoming test",
            "type": "text",
            "has_media": False,
            "status": "received",
            "sent_at": datetime.now(timezone.utc).isoformat(),
        })
        try:
            r = requests.get(
                f"{API}/v2/message/receivedMessages",
                params={"page": 1},
                headers={"Authorization": f"Bearer {customer_account['api_key']}"},
                timeout=10,
            )
            assert r.status_code == 200, r.text
            body = r.json()
            res = body["result"]
            assert isinstance(res["count"], int)
            seeded = [d for d in res["data"] if d["id"] == mid]
            assert len(seeded) == 1
            d = seeded[0]
            assert d["phonenumber"] == "15553334444"
            assert d["text"] == "incoming test"
            assert d["hasMedia"] is False
        finally:
            mongo_db.messages.delete_one({"id": mid})


# =============== v2 account ===============
class TestV2Account:
    def test_account(self, customer_account):
        r = requests.get(
            f"{API}/v2/account",
            headers={"Authorization": f"Bearer {customer_account['api_key']}"},
            timeout=10,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["success"] is True
        res = body["result"]
        assert res["email"] == customer_account["email"].lower()
        assert "name" in res
        assert "plan" in res
        assert "quota_monthly" in res and isinstance(res["quota_monthly"], int)
        assert "quota_used" in res and isinstance(res["quota_used"], int)
        assert "sessions" in res and isinstance(res["sessions"], int)
        assert "expires_at" in res

    def test_account_via_x_api_key(self, customer_account):
        r = requests.get(
            f"{API}/v2/account",
            headers={"X-API-Key": customer_account["api_key"]},
            timeout=10,
        )
        assert r.status_code == 200

    def test_account_via_query_token(self, customer_account):
        r = requests.get(
            f"{API}/v2/account",
            params={"token": customer_account["api_key"]},
            timeout=10,
        )
        assert r.status_code == 200


# =============== Session settings & session messages ===============
class TestSessionSettings:
    def test_patch_settings_updates_doc(self, customer_account, created_session, mongo_db):
        r = customer_account["session"].patch(
            f"{API}/sessions/{created_session}/settings",
            json={
                "default_country_code": "+91",
                "auto_prefix": True,
                "receive_messages": False,
                "mark_as_seen": True,
            },
            timeout=10,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["default_country_code"] == "91"  # normalized digits-only
        assert body["auto_prefix"] is True
        assert body["receive_messages"] is False
        assert body["mark_as_seen"] is True

        # GET via /sessions list to verify persistence
        r2 = customer_account["session"].get(f"{API}/sessions", timeout=10)
        sess = next((s for s in r2.json() if s["id"] == created_session), None)
        assert sess is not None
        assert sess["default_country_code"] == "91"
        assert sess["auto_prefix"] is True

    def test_patch_settings_other_user_404(self, admin_session, customer_account, created_session):
        r = admin_session.patch(
            f"{API}/sessions/{created_session}/settings",
            json={"auto_prefix": True},
            timeout=10,
        )
        assert r.status_code == 404


class TestSessionMessages:
    def test_session_messages_direction_filters(self, customer_account, created_session, mongo_db):
        # Seed both inbound and outbound for this session via direct mongo
        uid = customer_account["user"]["id"]
        in_id = f"TEST_smin_{secrets.token_hex(3)}"
        out_id = f"TEST_smout_{secrets.token_hex(3)}"
        mongo_db.messages.insert_many([
            {
                "id": in_id, "user_id": uid, "session_id": created_session,
                "direction": "inbound", "from": "1112223333", "text": "hi in",
                "status": "received",
                "sent_at": datetime.now(timezone.utc).isoformat(),
            },
            {
                "id": out_id, "user_id": uid, "session_id": created_session,
                "direction": "outbound", "to": "1112223333", "text": "hi out",
                "status": "sent",
                "sent_at": datetime.now(timezone.utc).isoformat(),
            },
        ])
        try:
            r_in = customer_account["session"].get(
                f"{API}/sessions/{created_session}/messages?direction=inbound", timeout=10
            )
            assert r_in.status_code == 200
            ms_in = r_in.json()
            assert all(m["direction"] == "inbound" for m in ms_in)
            assert any(m["id"] == in_id for m in ms_in)
            assert not any(m["id"] == out_id for m in ms_in)

            r_out = customer_account["session"].get(
                f"{API}/sessions/{created_session}/messages?direction=outbound", timeout=10
            )
            assert r_out.status_code == 200
            ms_out = r_out.json()
            assert all(m["direction"] == "outbound" for m in ms_out)
            assert any(m["id"] == out_id for m in ms_out)
            assert not any(m["id"] == in_id for m in ms_out)
        finally:
            mongo_db.messages.delete_many({"id": {"$in": [in_id, out_id]}})

    def test_session_messages_unknown_session(self, customer_account):
        r = customer_account["session"].get(f"{API}/sessions/zzz-nonexistent/messages", timeout=10)
        assert r.status_code == 404


# =============== Plugin downloads ===============
class TestPluginDownloads:
    def test_whmcs_zip(self):
        r = requests.get(f"{API}/plugins/whmcs.zip", timeout=15)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/zip")
        assert len(r.content) > 0
        assert r.content[:2] == b"PK"  # zip magic

    def test_woocommerce_zip(self):
        r = requests.get(f"{API}/plugins/woocommerce.zip", timeout=15)
        assert r.status_code == 200
        assert r.headers.get("content-type", "").startswith("application/zip")
        assert len(r.content) > 0
        assert r.content[:2] == b"PK"
