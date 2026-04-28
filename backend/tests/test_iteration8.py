"""Iteration 8 — Auto-Update (system_admin) endpoint tests.

Covers admin-only gating, response shape, and behavior in the preview env where
/app is a git checkout but no `origin` remote is configured.

Endpoints under test:
  GET  /api/admin/system/status
  GET  /api/admin/system/log
  POST /api/admin/system/update
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path

import pytest
import requests

BASE_URL = os.environ.get(
    "REACT_APP_BACKEND_URL", "https://chat-platform-380.preview.emergentagent.com"
).rstrip("/")
API = f"{BASE_URL}/api"

ADMIN_EMAIL = "admin@wa.9x.design"
ADMIN_PASSWORD = "admin123"


def _unique_email(prefix: str = "TEST_iter8") -> str:
    return f"{prefix}_{secrets.token_hex(4)}@wa9x.com"


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
    body = r.json()
    assert body["role"] == "admin"
    assert s.cookies.get("access_token"), "access_token cookie not set on admin login"
    return s


@pytest.fixture(scope="module")
def customer_session() -> requests.Session:
    """Register a fresh customer (role=customer) for 403 gating tests."""
    s = requests.Session()
    email = _unique_email("TEST_iter8_cust")
    r = s.post(
        f"{API}/auth/register",
        json={"email": email, "password": "CustPass123!", "name": "Iter8 Cust"},
        timeout=15,
    )
    assert r.status_code == 200, f"Customer register failed: {r.status_code} {r.text}"
    body = r.json()
    assert body["role"] == "customer"
    assert s.cookies.get("access_token"), "access_token cookie not set on customer register"
    return s


@pytest.fixture(scope="module")
def anon_session() -> requests.Session:
    return requests.Session()


# ---------------- Auth gating: unauth (401) ----------------
class TestUnauthGating:
    def test_status_unauth_401(self, anon_session):
        r = anon_session.get(f"{API}/admin/system/status", timeout=10)
        assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"

    def test_log_unauth_401(self, anon_session):
        r = anon_session.get(f"{API}/admin/system/log", timeout=10)
        assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"

    def test_update_unauth_401(self, anon_session):
        r = anon_session.post(f"{API}/admin/system/update", timeout=10)
        assert r.status_code == 401, f"Expected 401, got {r.status_code}: {r.text}"


# ---------------- Auth gating: customer (403) ----------------
class TestCustomerGating:
    def test_status_customer_403(self, customer_session):
        r = customer_session.get(f"{API}/admin/system/status", timeout=10)
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"

    def test_log_customer_403(self, customer_session):
        r = customer_session.get(f"{API}/admin/system/log", timeout=10)
        assert r.status_code == 403, f"Expected 403, got {r.status_code}: {r.text}"

    def test_update_customer_403(self, customer_session):
        # Endpoint exists & gating fires before any side-effect.
        r = customer_session.post(f"{API}/admin/system/update", timeout=10)
        assert r.status_code == 403, f"Expected 403 (not 404 — endpoint must exist), got {r.status_code}: {r.text}"


# ---------------- Admin: GET /admin/system/status ----------------
class TestAdminSystemStatus:
    def test_status_200_and_shape(self, admin_session):
        r = admin_session.get(f"{API}/admin/system/status", timeout=45)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()

        # Always present
        assert "install_dir" in data
        assert isinstance(data["install_dir"], str)
        assert "git_available" in data
        assert isinstance(data["git_available"], bool)

    def test_status_git_available_true(self, admin_session):
        """/app has a .git directory in the preview env → git_available must be True."""
        r = admin_session.get(f"{API}/admin/system/status", timeout=45)
        assert r.status_code == 200
        data = r.json()
        assert data["git_available"] is True, (
            f"Expected git_available=True (since /app/.git exists), got: {data}"
        )

    def test_status_fetch_fails_no_origin(self, admin_session):
        """Preview env has no origin remote → fetch_ok=False, fetch_error mentions origin."""
        r = admin_session.get(f"{API}/admin/system/status", timeout=45)
        assert r.status_code == 200
        data = r.json()

        # When git_available is true, the fetch_ok / fetch_error / branch / commit fields must be present.
        assert "fetch_ok" in data, f"fetch_ok missing in response: {data}"
        assert data["fetch_ok"] is False, (
            f"Expected fetch_ok=False (no origin remote in preview), got fetch_ok={data.get('fetch_ok')}, full={data}"
        )
        # fetch_error should be a non-empty string referencing 'origin'
        assert data.get("fetch_error"), f"fetch_error missing/empty: {data}"
        assert "origin" in data["fetch_error"].lower(), (
            f"fetch_error should mention 'origin', got: {data['fetch_error']}"
        )

    def test_status_commit_and_branch(self, admin_session):
        r = admin_session.get(f"{API}/admin/system/status", timeout=45)
        assert r.status_code == 200
        data = r.json()
        # commit & branch should be non-empty strings
        assert data.get("commit"), f"commit missing/empty: {data}"
        assert isinstance(data["commit"], str)
        assert len(data["commit"]) >= 7  # full sha is 40, short is 7
        assert data.get("branch"), f"branch missing/empty: {data}"
        assert isinstance(data["branch"], str)
        # short_commit should be present
        assert data.get("short_commit"), f"short_commit missing/empty: {data}"

    def test_status_behind_count_int(self, admin_session):
        r = admin_session.get(f"{API}/admin/system/status", timeout=45)
        assert r.status_code == 200
        data = r.json()
        assert "behind_count" in data
        assert isinstance(data["behind_count"], int)
        # When fetch fails there's nothing to compare against → behind_count defaults to 0
        assert data["behind_count"] == 0, (
            f"Expected behind_count=0 when fetch fails, got: {data['behind_count']}"
        )

    def test_status_install_dir_is_app(self, admin_session):
        r = admin_session.get(f"{API}/admin/system/status", timeout=45)
        assert r.status_code == 200
        data = r.json()
        # In the preview env INSTALL_DIR should be /app (default).
        assert data["install_dir"] == "/app", f"Expected install_dir=/app, got: {data['install_dir']}"


# ---------------- Admin: GET /admin/system/log ----------------
class TestAdminSystemLog:
    def test_log_200_and_shape(self, admin_session):
        r = admin_session.get(f"{API}/admin/system/log", timeout=15)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert "log" in data
        assert "exists" in data
        assert isinstance(data["log"], str)
        assert isinstance(data["exists"], bool)

    def test_log_log_file_may_not_exist(self, admin_session):
        """In preview env /var/log/wa9x-update.log may not exist; if not, exists=False & log==''."""
        r = admin_session.get(f"{API}/admin/system/log", timeout=15)
        assert r.status_code == 200
        data = r.json()
        if not data["exists"]:
            assert data["log"] == "", f"Expected empty log when exists=False, got: {data['log']!r}"

    def test_log_lines_param_accepted(self, admin_session):
        r = admin_session.get(f"{API}/admin/system/log", params={"lines": 50}, timeout=15)
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        body = r.json()
        assert "log" in body and "exists" in body

    def test_log_lines_param_clamped(self, admin_session):
        # Server clamps lines to [10, 2000]; an out-of-range value should still 200.
        r = admin_session.get(f"{API}/admin/system/log", params={"lines": 5}, timeout=15)
        assert r.status_code == 200
        r = admin_session.get(f"{API}/admin/system/log", params={"lines": 99999}, timeout=15)
        assert r.status_code == 200


# ---------------- Admin: POST /admin/system/update (existence + script presence) ----------------
class TestAdminSystemUpdate:
    """We deliberately do NOT exercise the success path repeatedly — it spawns a detached
    bash script. Per review_request, validate that the endpoint exists for admin (not 404)
    and that the underlying auto-update.sh script is present on disk.
    """

    def test_update_script_exists_on_disk(self):
        """/app/deploy/auto-update.sh must exist for POST /update to succeed."""
        script = Path("/app/deploy/auto-update.sh")
        assert script.exists(), f"auto-update.sh missing at {script}"
        assert script.is_file()

    def test_update_endpoint_exists_for_admin(self, admin_session):
        """Endpoint MUST exist (not 404). /app is a git checkout AND auto-update.sh exists,
        so the implementation will spawn the script and return 200.

        Per review_request: 'Test that the endpoint returns 200 with a message AND that the
        script path /app/deploy/auto-update.sh exists.'
        """
        r = admin_session.post(f"{API}/admin/system/update", timeout=15)
        # Must NOT be 404 (endpoint wired) or 401/403 (admin is authenticated)
        assert r.status_code != 404, f"Endpoint not wired (404). Body: {r.text}"
        assert r.status_code not in (401, 403), (
            f"Admin should not be gated. Got {r.status_code}: {r.text}"
        )
        # Expected success path: 200 with ok=True + message
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data.get("ok") is True, f"Expected ok=True, got: {data}"
        assert "message" in data and isinstance(data["message"], str) and data["message"], (
            f"Expected non-empty message, got: {data}"
        )
