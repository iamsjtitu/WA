#!/usr/bin/env python3
"""Focused backend/API setup and verification for the disconnect reason banner bug.

Creates disposable sessions for the admin user, simulates qr/disconnect states,
and records IDs for the UI Playwright check.
"""

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from pymongo import MongoClient


BASE_URL = os.environ.get("QA_BASE_URL", "https://chat-platform-380.preview.emergentagent.com")
LOCAL_WA = os.environ.get("QA_WA_URL", "http://127.0.0.1:3001")
ADMIN_EMAIL = "admin@wa.9x.design"
ADMIN_PASSWORD = "admin123"
INTERNAL_SECRET = "9e7f4a52c8d61b3e0f29a48b75c1d36e2f0a8d94c75b1e63a02f47d8b1e9c5a3"
MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "wapihub_db"
OUT = Path("/app/test_reports/disconnect_reason_backend_results.json")


def assert_true(condition, message):
    if not condition:
        raise AssertionError(message)


def record_check(results, name, condition, detail=""):
    results.setdefault("checks", []).append({
        "name": name,
        "passed": bool(condition),
        "detail": detail,
    })
    if not condition:
        results.setdefault("failures", []).append({"name": name, "detail": detail})


def api(session, method, path, **kwargs):
    res = session.request(method, f"{BASE_URL}/api{path}", timeout=30, **kwargs)
    if res.status_code >= 400:
        raise AssertionError(f"{method} {path} -> {res.status_code}: {res.text[:500]}")
    return res.json()


def wait_for_qr(session, sid, seconds=30):
    last = None
    for _ in range(seconds):
        last = api(session, "GET", f"/sessions/{sid}/status")
        if last.get("status") == "qr":
            return last
        time.sleep(1)
    raise AssertionError(f"session {sid} did not reach qr state; last={last}")


def create_qr_session(session, db, name, phone="916370505556"):
    doc = api(session, "POST", "/sessions", json={"name": name})
    sid = doc["id"]
    db.wa_sessions.update_one(
        {"id": sid},
        {
            "$set": {"phone": phone, "status": "qr", "qa_disconnect_reason_bug": True},
            "$unset": {
                "error_label": "",
                "error_code": "",
                "last_disconnect_at": "",
                "last_disconnect_code": "",
                "last_disconnect_label": "",
                "last_disconnect_reason": "",
                "last_disconnect_terminal": "",
            },
        },
    )
    requests.post(
        f"{LOCAL_WA}/sessions/{sid}/start",
        headers={"X-Internal-Secret": INTERNAL_SECRET},
        timeout=30,
    ).raise_for_status()
    wait_for_qr(session, sid)
    db.wa_sessions.update_one({"id": sid}, {"$set": {"phone": phone}})
    return sid


def fire_disconnect(code, sid, terminal=True, at=None):
    payload = {
        "session_id": sid,
        "code": code,
        "reason": f"qa simulated code {code}",
        "terminal": terminal,
    }
    if at:
        payload["at"] = at
    res = requests.post(
        f"{BASE_URL}/api/internal/disconnect-event",
        headers={"X-Internal-Secret": INTERNAL_SECRET},
        json=payload,
        timeout=30,
    )
    if res.status_code >= 400:
        raise AssertionError(f"disconnect-event {code} -> {res.status_code}: {res.text}")
    data = res.json()
    assert_true(data.get("ok") is True, f"disconnect event failed: {data}")
    return data


def main():
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]

    s = requests.Session()
    user = api(s, "POST", "/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert_true(user.get("email") == ADMIN_EMAIL, "admin login failed")

    results = {"base_url": BASE_URL, "created_session_ids": {}, "checks": [], "failures": []}

    # Legacy qr session: phone exists, no recorded reason/label.
    legacy_sid = create_qr_session(s, db, f"QA Legacy QR No Reason {run_id}")
    legacy_status = api(s, "GET", f"/sessions/{legacy_sid}/status")
    record_check(results, "legacy status is qr", legacy_status.get("status") == "qr", str(legacy_status))
    record_check(results, "legacy has no error_label", not legacy_status.get("error_label"), str(legacy_status))
    record_check(results, "legacy has no last_disconnect_label", not legacy_status.get("last_disconnect_label"), str(legacy_status))
    results["created_session_ids"]["legacy_qr_no_reason"] = legacy_sid

    # qr session with a recorded disconnect label from the internal event pipeline.
    label_sid = create_qr_session(s, db, f"QA QR With 440 Label {run_id}")
    fire_disconnect(440, label_sid, terminal=True, at="2026-07-01T10:00:00.000Z")
    # keep live WA side in qr so status endpoint returns qr while DB has last_disconnect_label.
    requests.post(
        f"{LOCAL_WA}/sessions/{label_sid}/start",
        headers={"X-Internal-Secret": INTERNAL_SECRET},
        timeout=30,
    ).raise_for_status()
    label_status = wait_for_qr(s, label_sid)
    record_check(results, "code-only internal event stores last_disconnect_code=440", label_status.get("last_disconnect_code") == 440, str(label_status))
    record_check(
        results,
        "code-only internal event maps 440 to human label",
        label_status.get("last_disconnect_label") == "Replaced by another device (someone else linked to this number)",
        str(label_status),
    )
    required_fields = [
        "error",
        "error_code",
        "error_label",
        "last_disconnect_at",
        "last_disconnect_code",
        "last_disconnect_label",
        "last_disconnect_terminal",
    ]
    missing = [k for k in required_fields if k not in label_status]
    record_check(results, "status endpoint includes required disconnect fields", not missing, f"missing={missing}; status={label_status}")
    results["created_session_ids"]["qr_with_440_label"] = label_sid

    # A second labeled session mimics the real Node -> FastAPI payload, where Node supplies labelForCode(code).
    node_label_sid = create_qr_session(s, db, f"QA QR With Node 440 Label {run_id}")
    res = requests.post(
        f"{BASE_URL}/api/internal/disconnect-event",
        headers={"X-Internal-Secret": INTERNAL_SECRET},
        json={
            "session_id": node_label_sid,
            "code": 440,
            "reason": "qa simulated code 440 with node label",
            "label": "Replaced by another device (someone else linked to this number)",
            "terminal": True,
            "at": "2026-07-01T10:05:00.000Z",
        },
        timeout=30,
    )
    res.raise_for_status()
    requests.post(
        f"{LOCAL_WA}/sessions/{node_label_sid}/start",
        headers={"X-Internal-Secret": INTERNAL_SECRET},
        timeout=30,
    ).raise_for_status()
    node_label_status = wait_for_qr(s, node_label_sid)
    record_check(
        results,
        "labeled internal event preserves human 440 label",
        node_label_status.get("last_disconnect_label") == "Replaced by another device (someone else linked to this number)",
        str(node_label_status),
    )
    results["created_session_ids"]["qr_with_node_440_label"] = node_label_sid

    # Empty history case.
    empty_sid = create_qr_session(s, db, f"QA Empty History {run_id}")
    empty_history = api(s, "GET", f"/sessions/{empty_sid}/disconnect-history?limit=20")
    record_check(results, "empty disconnect history returns []", empty_history.get("items") == [], str(empty_history))
    results["created_session_ids"]["empty_history"] = empty_sid

    # Recorded-event history ordering: newest first.
    order_sid = create_qr_session(s, db, f"QA History Order {run_id}")
    fire_disconnect(401, order_sid, terminal=True, at="2026-07-01T09:00:00.000Z")
    fire_disconnect(440, order_sid, terminal=True, at="2026-07-01T11:00:00.000Z")
    history = api(s, "GET", f"/sessions/{order_sid}/disconnect-history?limit=10")
    codes = [item.get("code") for item in history.get("items", [])[:2]]
    record_check(results, "disconnect history returns newest-first", codes == [440, 401], str(history))
    results["created_session_ids"]["history_order"] = order_sid

    OUT.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()