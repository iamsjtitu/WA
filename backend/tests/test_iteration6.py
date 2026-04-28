"""Iteration 6 tests — extended profile fields on register, /me/profile, /me/credentials, /admin/customers/{id}."""
from __future__ import annotations

import os
import secrets

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://chat-platform-380.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@wa.9x.design"
ADMIN_PASSWORD = "admin123"


def _unique_email(prefix: str = "TEST_iter6") -> str:
    return f"{prefix}_{secrets.token_hex(4)}@example.com"


# ---------------- Fixtures ----------------
@pytest.fixture(scope="module")
def admin_session() -> requests.Session:
    s = requests.Session()
    r = s.post(
        f"{API}/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=15,
    )
    assert r.status_code == 200, f"Admin login failed: {r.status_code} {r.text}"
    return s


@pytest.fixture(scope="module")
def fresh_customer():
    """Register a fresh customer with all profile fields."""
    email = _unique_email("TEST_iter6_fullprof")
    password = "CustPass123!"
    s = requests.Session()
    payload = {
        "email": email,
        "password": password,
        "name": "Profile User",
        "phone": "+15551234567",
        "company": "Acme Corp",
        "country": "US",
        "city": "San Francisco",
    }
    r = s.post(f"{API}/auth/register", json=payload, timeout=15)
    assert r.status_code == 200, f"Register failed: {r.status_code} {r.text}"
    user = r.json()
    return {
        "email": email,
        "password": password,
        "user": user,
        "session": s,
        "payload": payload,
    }


# ---------------- Register: full profile fields ----------------
class TestRegisterProfileFields:
    def test_register_with_full_profile(self, fresh_customer):
        u = fresh_customer["user"]
        p = fresh_customer["payload"]
        assert u["email"] == p["email"].lower()
        assert u["name"] == p["name"]
        assert u["phone"] == p["phone"]
        assert u["company"] == p["company"]
        assert u["country"] == p["country"]
        assert u["city"] == p["city"]
        assert u["role"] == "customer"
        assert u["api_key"].startswith("wa9x_")

    def test_register_minimal_only_required(self):
        email = _unique_email("TEST_iter6_minimal")
        s = requests.Session()
        r = s.post(
            f"{API}/auth/register",
            json={"email": email, "password": "MinPass123!", "name": "Minimal"},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["email"] == email.lower()
        assert u["name"] == "Minimal"
        # optional fields default to None
        assert u.get("phone") is None
        assert u.get("company") is None
        assert u.get("country") is None
        assert u.get("city") is None

    def test_auth_me_includes_profile_fields(self, fresh_customer):
        s = fresh_customer["session"]
        r = s.get(f"{API}/auth/me", timeout=15)
        assert r.status_code == 200, r.text
        u = r.json()
        # all four keys are present (even if null for some users)
        for k in ("phone", "company", "country", "city"):
            assert k in u
        # for this customer they should match the registered values
        p = fresh_customer["payload"]
        assert u["phone"] == p["phone"]
        assert u["company"] == p["company"]
        assert u["country"] == p["country"]
        assert u["city"] == p["city"]


# ---------------- PATCH /me/profile ----------------
class TestUpdateProfile:
    def test_update_all_profile_fields(self, fresh_customer):
        s = fresh_customer["session"]
        new_data = {
            "name": "Updated Name",
            "phone": "+447700900123",
            "company": "Globex",
            "country": "UK",
            "city": "London",
        }
        r = s.patch(f"{API}/me/profile", json=new_data, timeout=15)
        assert r.status_code == 200, r.text
        u = r.json()
        for k, v in new_data.items():
            assert u[k] == v, f"field {k} did not update: {u.get(k)} vs {v}"

        # verify persistence
        r2 = s.get(f"{API}/auth/me", timeout=15)
        u2 = r2.json()
        for k, v in new_data.items():
            assert u2[k] == v

    def test_update_partial_only_phone(self, fresh_customer):
        s = fresh_customer["session"]
        r = s.patch(f"{API}/me/profile", json={"phone": "+10000000001"}, timeout=15)
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["phone"] == "+10000000001"
        # name from previous test should remain
        assert u["name"] == "Updated Name"

    def test_update_empty_body_returns_current_user(self, fresh_customer):
        s = fresh_customer["session"]
        r = s.patch(f"{API}/me/profile", json={}, timeout=15)
        assert r.status_code == 200, r.text
        u = r.json()
        assert u["email"] == fresh_customer["email"].lower()
        # nothing should change
        assert u["phone"] == "+10000000001"

    def test_update_profile_unauth(self):
        s = requests.Session()
        r = s.patch(f"{API}/me/profile", json={"phone": "x"}, timeout=15)
        assert r.status_code == 401, f"expected 401, got {r.status_code}: {r.text}"


# ---------------- PATCH /me/credentials ----------------
class TestUpdateCredentials:
    def test_credentials_unauth(self):
        s = requests.Session()
        r = s.patch(
            f"{API}/me/credentials",
            json={"current_password": "x", "new_password": "yyyyyy"},
            timeout=15,
        )
        assert r.status_code == 401

    def test_wrong_current_password(self):
        # use a fresh user to keep state isolated
        email = _unique_email("TEST_iter6_wrongpw")
        s = requests.Session()
        s.post(
            f"{API}/auth/register",
            json={"email": email, "password": "RightPass1!", "name": "WrongPW"},
            timeout=15,
        ).raise_for_status()
        r = s.patch(
            f"{API}/me/credentials",
            json={"current_password": "WRONG", "new_password": "NewPass456!"},
            timeout=15,
        )
        assert r.status_code == 401, r.text
        body = r.json()
        assert "incorrect" in str(body.get("detail", "")).lower()

    def test_nothing_to_update(self):
        email = _unique_email("TEST_iter6_nothing")
        s = requests.Session()
        s.post(
            f"{API}/auth/register",
            json={"email": email, "password": "RightPass1!", "name": "Nothing"},
            timeout=15,
        ).raise_for_status()
        r = s.patch(
            f"{API}/me/credentials",
            json={"current_password": "RightPass1!"},
            timeout=15,
        )
        assert r.status_code == 400, r.text
        assert "nothing" in str(r.json().get("detail", "")).lower()

    def test_change_password_flow(self):
        email = _unique_email("TEST_iter6_chpw")
        old_pw = "OldPass111!"
        new_pw = "NewPass222!"
        s = requests.Session()
        s.post(
            f"{API}/auth/register",
            json={"email": email, "password": old_pw, "name": "PW change"},
            timeout=15,
        ).raise_for_status()
        # change password
        r = s.patch(
            f"{API}/me/credentials",
            json={"current_password": old_pw, "new_password": new_pw},
            timeout=15,
        )
        assert r.status_code == 200, r.text

        # old password should no longer log in
        s_old = requests.Session()
        r_old = s_old.post(
            f"{API}/auth/login",
            json={"email": email, "password": old_pw},
            timeout=15,
        )
        assert r_old.status_code == 401, f"old pw still works! {r_old.text}"

        # new password should work
        s_new = requests.Session()
        r_new = s_new.post(
            f"{API}/auth/login",
            json={"email": email, "password": new_pw},
            timeout=15,
        )
        assert r_new.status_code == 200, r_new.text

    def test_change_email_flow(self):
        email = _unique_email("TEST_iter6_chmail")
        new_email = _unique_email("TEST_iter6_chmail_new")
        password = "MailPass111!"
        s = requests.Session()
        s.post(
            f"{API}/auth/register",
            json={"email": email, "password": password, "name": "Mail change"},
            timeout=15,
        ).raise_for_status()
        r = s.patch(
            f"{API}/me/credentials",
            json={"current_password": password, "new_email": new_email},
            timeout=15,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["email"] == new_email.lower()

        # login with new email works
        s_new = requests.Session()
        r_new = s_new.post(
            f"{API}/auth/login",
            json={"email": new_email, "password": password},
            timeout=15,
        )
        assert r_new.status_code == 200

        # login with old email fails
        s_old = requests.Session()
        r_old = s_old.post(
            f"{API}/auth/login",
            json={"email": email, "password": password},
            timeout=15,
        )
        assert r_old.status_code == 401

    def test_change_email_to_existing_returns_400(self):
        # register two users; user A tries to change email to user B's
        email_a = _unique_email("TEST_iter6_dupA")
        email_b = _unique_email("TEST_iter6_dupB")
        password = "DupPass111!"
        sa = requests.Session()
        sb = requests.Session()
        sa.post(
            f"{API}/auth/register",
            json={"email": email_a, "password": password, "name": "A"},
            timeout=15,
        ).raise_for_status()
        sb.post(
            f"{API}/auth/register",
            json={"email": email_b, "password": password, "name": "B"},
            timeout=15,
        ).raise_for_status()
        r = sa.patch(
            f"{API}/me/credentials",
            json={"current_password": password, "new_email": email_b},
            timeout=15,
        )
        assert r.status_code == 400, r.text
        assert "already" in str(r.json().get("detail", "")).lower()


# ---------------- GET /admin/customers/{id} ----------------
class TestAdminGetCustomerDetail:
    def test_admin_get_customer_detail(self, admin_session, fresh_customer):
        cust_id = fresh_customer["user"]["id"]
        r = admin_session.get(f"{API}/admin/customers/{cust_id}", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert "user" in body and "sessions_count" in body and "messages_total" in body
        assert body["user"]["id"] == cust_id
        assert body["user"]["email"] == fresh_customer["email"].lower()
        assert isinstance(body["sessions_count"], int)
        assert isinstance(body["messages_total"], int)
        assert body["sessions_count"] >= 0
        assert body["messages_total"] >= 0
        # profile fields surfaced in user object
        for k in ("phone", "company", "country", "city"):
            assert k in body["user"]

    def test_customer_cannot_access_admin_detail(self, fresh_customer):
        s = fresh_customer["session"]
        cust_id = fresh_customer["user"]["id"]
        r = s.get(f"{API}/admin/customers/{cust_id}", timeout=15)
        assert r.status_code == 403, r.text

    def test_admin_get_unknown_customer_returns_404(self, admin_session):
        r = admin_session.get(
            f"{API}/admin/customers/this-does-not-exist-iter6", timeout=15
        )
        assert r.status_code == 404, r.text


# ---------------- Light regression on previous endpoints ----------------
class TestRegression:
    def test_admin_login_still_works(self):
        s = requests.Session()
        r = s.post(
            f"{API}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15,
        )
        assert r.status_code == 200
        u = r.json()
        assert u["role"] == "admin"
        assert u["api_key"].startswith("wa9x_")
        # iter6: admin /auth/me should also include profile fields (null)
        for k in ("phone", "company", "country", "city"):
            assert k in u

    def test_health(self):
        r = requests.get(f"{API}/health", timeout=10)
        assert r.status_code == 200
        body = r.json()
        assert body.get("api") == "ok"

    def test_admin_list_customers(self, admin_session):
        r = admin_session.get(f"{API}/admin/customers", timeout=15)
        assert r.status_code == 200
        body = r.json()
        assert isinstance(body, list)
        # each customer entry should also have profile keys (forward-compat)
        if body:
            for k in ("phone", "company", "country", "city"):
                assert k in body[0]

    def test_customer_list_forbidden(self, fresh_customer):
        r = fresh_customer["session"].get(f"{API}/admin/customers", timeout=15)
        assert r.status_code == 403

    def test_v1_messages_unauth(self):
        # public api v1 still requires X-API-Key
        r = requests.post(
            f"{API}/v1/messages",
            json={"to": "+1", "text": "hi"},
            timeout=10,
        )
        assert r.status_code in (401, 403, 422)

    def test_register_duplicate_email_400(self, fresh_customer):
        r = requests.post(
            f"{API}/auth/register",
            json={
                "email": fresh_customer["email"],
                "password": "Whatever123!",
                "name": "dup",
            },
            timeout=15,
        )
        assert r.status_code == 400
