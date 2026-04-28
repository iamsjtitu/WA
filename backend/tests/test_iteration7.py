"""Iteration 7 — Admin impersonation flow + audit logs."""
import os
import time
import uuid

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ADMIN_EMAIL = "admin@wa.9x.design"
ADMIN_PASSWORD = "admin123"


def _login(session: requests.Session, email: str, password: str):
    r = session.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": email, "password": password},
        timeout=30,
    )
    assert r.status_code == 200, f"login failed for {email}: {r.status_code} {r.text}"
    return r.json()


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    _login(s, ADMIN_EMAIL, ADMIN_PASSWORD)
    yield s
    # cleanup: ensure we are not stuck in impersonation mode
    try:
        s.post(f"{BASE_URL}/api/auth/exit-impersonation", timeout=15)
    except Exception:
        pass


@pytest.fixture(scope="module")
def admin_id(admin_session):
    r = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
    assert r.status_code == 200
    me = r.json()
    assert me["role"] == "admin"
    assert me["email"] == ADMIN_EMAIL
    return me["id"]


@pytest.fixture(scope="module")
def test_customer(admin_session):
    """Create a fresh customer and tear down after suite."""
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "email": f"TEST_iter7_{suffix}@wa9x.com",
        "password": "customerpw123",
        "name": f"Iter7 Customer {suffix}",
        "quota_monthly": 500,
    }
    r = admin_session.post(f"{BASE_URL}/api/admin/customers", json=payload, timeout=30)
    assert r.status_code == 200, f"create customer failed: {r.status_code} {r.text}"
    cust = r.json()
    yield {**cust, "password": payload["password"]}
    try:
        admin_session.delete(f"{BASE_URL}/api/admin/customers/{cust['id']}", timeout=15)
    except Exception:
        pass


# --------- impersonation start ---------
class TestImpersonateStart:
    def test_impersonate_unauth(self, test_customer):
        s = requests.Session()
        r = s.post(
            f"{BASE_URL}/api/admin/customers/{test_customer['id']}/impersonate",
            timeout=15,
        )
        assert r.status_code == 401

    def test_impersonate_as_customer_forbidden(self, test_customer):
        cs = requests.Session()
        _login(cs, test_customer["email"], test_customer["password"])
        r = cs.post(
            f"{BASE_URL}/api/admin/customers/{test_customer['id']}/impersonate",
            timeout=15,
        )
        assert r.status_code == 403

    def test_impersonate_unknown_customer(self, admin_session):
        r = admin_session.post(
            f"{BASE_URL}/api/admin/customers/does-not-exist-xyz/impersonate",
            timeout=15,
        )
        assert r.status_code == 404

    def test_impersonate_admin_self(self, admin_session, admin_id):
        # Admin tries on themselves — admin's role is 'admin', filter is role='customer'
        # so we expect 404 (not found in /admin/customers).
        r = admin_session.post(
            f"{BASE_URL}/api/admin/customers/{admin_id}/impersonate", timeout=15
        )
        assert r.status_code == 404


# --------- happy path: impersonate, do customer things, exit ---------
class TestImpersonateFlow:
    def test_full_flow(self, test_customer, admin_id):
        # Use a fresh session so cookies are isolated.
        s = requests.Session()
        _login(s, ADMIN_EMAIL, ADMIN_PASSWORD)

        original_admin_token = s.cookies.get("access_token")
        assert original_admin_token, "admin login should set access_token cookie"

        # Start impersonation
        r = s.post(
            f"{BASE_URL}/api/admin/customers/{test_customer['id']}/impersonate",
            timeout=20,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        u = body["user"]
        assert u["id"] == test_customer["id"]
        assert u["email"] == test_customer["email"]
        assert u["role"] == "customer"
        assert u["impersonated_by"] == admin_id
        assert u["impersonated_by_email"] == ADMIN_EMAIL

        # Cookies — access_token should now be the customer JWT (different),
        # admin_original_token should equal the admin's previous access token.
        new_access = s.cookies.get("access_token")
        admin_orig = s.cookies.get("admin_original_token")
        assert new_access, "impersonation must set access_token cookie"
        assert new_access != original_admin_token, "access_token must be replaced"
        assert admin_orig == original_admin_token, (
            "admin_original_token must preserve the original admin token"
        )

        # /auth/me should now return customer with impersonation fields
        r = s.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200
        me = r.json()
        assert me["id"] == test_customer["id"]
        assert me["role"] == "customer"
        assert me["impersonated_by"] == admin_id
        assert me["impersonated_by_email"] == ADMIN_EMAIL

        # Customer endpoints work
        r = s.get(f"{BASE_URL}/api/me/stats", timeout=15)
        assert r.status_code == 200
        stats = r.json()
        assert "messages_total" in stats and "sessions" in stats

        r = s.get(f"{BASE_URL}/api/sessions", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

        r = s.get(f"{BASE_URL}/api/messages", timeout=15)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

        # Admin endpoint must be forbidden while impersonating
        r = s.get(f"{BASE_URL}/api/admin/customers", timeout=15)
        assert r.status_code == 403

        # Exit impersonation
        r = s.post(f"{BASE_URL}/api/auth/exit-impersonation", timeout=15)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("ok") is True
        admin_user = body["user"]
        assert admin_user["role"] == "admin"
        assert admin_user["email"] == ADMIN_EMAIL
        assert admin_user["id"] == admin_id

        # admin_original_token cookie should be deleted
        admin_orig_after = s.cookies.get("admin_original_token")
        assert not admin_orig_after, (
            f"admin_original_token should be cleared, got {admin_orig_after!r}"
        )
        # access_token should be a fresh admin token
        restored = s.cookies.get("access_token")
        assert restored, "access_token should be restored"
        # /auth/me should return admin without impersonation fields
        r = s.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200
        me = r.json()
        assert me["role"] == "admin"
        assert me["id"] == admin_id
        assert not me.get("impersonated_by")
        assert not me.get("impersonated_by_email")

        # Admin endpoint accessible again
        r = s.get(f"{BASE_URL}/api/admin/customers", timeout=15)
        assert r.status_code == 200

    def test_exit_without_impersonation(self, admin_session):
        # admin_session is currently NOT impersonating
        # Make sure no admin_original_token is around.
        try:
            admin_session.cookies.pop("admin_original_token")
        except KeyError:
            pass
        r = admin_session.post(
            f"{BASE_URL}/api/auth/exit-impersonation", timeout=15
        )
        assert r.status_code == 400
        assert "Not in impersonation mode" in r.text


# --------- audit logs ---------
class TestAuditLogs:
    def test_audit_logs_admin_access(self, admin_session, test_customer, admin_id):
        # Trigger fresh impersonation start+end so we have known recent entries.
        s = requests.Session()
        _login(s, ADMIN_EMAIL, ADMIN_PASSWORD)
        r = s.post(
            f"{BASE_URL}/api/admin/customers/{test_customer['id']}/impersonate",
            timeout=20,
        )
        assert r.status_code == 200
        time.sleep(0.5)
        r = s.post(f"{BASE_URL}/api/auth/exit-impersonation", timeout=15)
        assert r.status_code == 200

        # Now query as admin
        r = admin_session.get(
            f"{BASE_URL}/api/admin/audit-logs?limit=50", timeout=15
        )
        assert r.status_code == 200
        logs = r.json()
        assert isinstance(logs, list)
        assert len(logs) >= 2

        starts = [
            x for x in logs
            if x.get("type") == "impersonation_start"
            and x.get("customer_id") == test_customer["id"]
        ]
        ends = [x for x in logs if x.get("type") == "impersonation_end"]
        assert starts, "expected at least one impersonation_start for our customer"
        assert ends, "expected at least one impersonation_end"

        s0 = starts[0]
        assert s0.get("admin_id") == admin_id
        assert s0.get("admin_email") == ADMIN_EMAIL
        assert s0.get("customer_email") == test_customer["email"]
        assert s0.get("at")

        e0 = ends[0]
        assert e0.get("admin_id") == admin_id
        assert e0.get("admin_email") == ADMIN_EMAIL
        assert e0.get("at")

    def test_audit_logs_filter_by_type(self, admin_session):
        r = admin_session.get(
            f"{BASE_URL}/api/admin/audit-logs?type=impersonation_start&limit=20",
            timeout=15,
        )
        assert r.status_code == 200
        logs = r.json()
        assert isinstance(logs, list)
        for entry in logs:
            assert entry.get("type") == "impersonation_start"

    def test_audit_logs_customer_forbidden(self, test_customer):
        cs = requests.Session()
        _login(cs, test_customer["email"], test_customer["password"])
        r = cs.get(f"{BASE_URL}/api/admin/audit-logs", timeout=15)
        assert r.status_code == 403

    def test_audit_logs_unauth(self):
        s = requests.Session()
        r = s.get(f"{BASE_URL}/api/admin/audit-logs", timeout=15)
        assert r.status_code == 401


# --------- regression sanity (iter 1-6) ---------
class TestRegression:
    def test_health(self):
        r = requests.get(f"{BASE_URL}/api/health", timeout=15)
        assert r.status_code == 200
        assert r.json().get("api") == "ok"

    def test_admin_stats_still_works(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/admin/stats", timeout=15)
        assert r.status_code == 200
        for k in ("customers", "sessions", "messages_total", "messages_today", "messages_failed"):
            assert k in r.json()

    def test_admin_list_customers(self, admin_session, test_customer):
        r = admin_session.get(f"{BASE_URL}/api/admin/customers", timeout=15)
        assert r.status_code == 200
        emails = [c["email"] for c in r.json()]
        assert test_customer["email"] in emails

    def test_me_profile_admin_unchanged(self, admin_session):
        r = admin_session.get(f"{BASE_URL}/api/auth/me", timeout=15)
        assert r.status_code == 200
        me = r.json()
        assert me["role"] == "admin"
        assert me["email"] == ADMIN_EMAIL
        # No leftover impersonation fields after our cleanup.
        assert not me.get("impersonated_by")
