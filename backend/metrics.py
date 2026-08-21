"""API reliability metrics — lightweight in-DB request telemetry.

Records public-API traffic (/api/v1/*, /api/v2/*) so admins can spot flaky
sessions/endpoints without wiring Prometheus/Grafana. Each event is a small
document (~120 bytes) stored in ``db.api_metrics`` with a 7-day TTL index
so the collection stays bounded regardless of throughput.

Schema:
    {
      "id":         uuid,
      "at":         datetime (UTC, TTL-indexed → 7d),
      "method":     "POST" | "GET" | ...,
      "path":       "/api/v2/sendMessage" (raw, no query),
      "route":      "sendMessage" (last segment for grouping),
      "status":     int,                    # HTTP status
      "latency_ms": int,
      "session_id": Optional[str],          # resolved via per-session api_key
      "user_id":    Optional[str],
    }
"""
from __future__ import annotations

import time
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware


# Only these path prefixes are recorded. Admin/dashboard/webhook internals
# are excluded to keep the collection lean.
_TRACKED_PREFIXES = ("/api/v1/", "/api/v2/")

# Static routes that would spam the metrics without providing signal.
_SKIP_PATHS = {"/api/health"}

_route_re = re.compile(r"/api/v[12]/([^/?]+)")


def _extract_route(path: str) -> str:
    m = _route_re.match(path)
    return m.group(1) if m else "unknown"


async def _resolve_owner(db, request: Request) -> tuple[Optional[str], Optional[str]]:
    """Best-effort auth resolution WITHOUT running the full auth deps.
    Returns (user_id, session_id) or (None, None)."""
    token: Optional[str] = None
    ah = request.headers.get("Authorization", "")
    if ah.startswith("Bearer "):
        token = ah[7:].strip()
    if not token:
        token = request.headers.get("X-API-Key")
    if not token:
        return None, None
    # Cheap prefix filter: our keys start with wa9x_
    if not token.startswith("wa9x_"):
        return None, None
    # Try per-session key first
    s = await db.wa_sessions.find_one(
        {"api_key": token}, {"_id": 0, "id": 1, "user_id": 1}
    )
    if s:
        return s.get("user_id"), s.get("id")
    u = await db.users.find_one({"api_key": token}, {"_id": 0, "id": 1})
    if u:
        return u.get("id"), None
    return None, None


class ApiMetricsMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, db):
        super().__init__(app)
        self.db = db

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        if path in _SKIP_PATHS or not path.startswith(_TRACKED_PREFIXES):
            return await call_next(request)

        started = time.perf_counter()
        response = await call_next(request)
        latency_ms = int((time.perf_counter() - started) * 1000)

        # Never block the response on metric writes
        try:
            user_id, session_id = await _resolve_owner(self.db, request)
            await self.db.api_metrics.insert_one(
                {
                    "id": _short_id(),
                    "at": datetime.now(timezone.utc),
                    "method": request.method,
                    "path": path,
                    "route": _extract_route(path),
                    "status": response.status_code,
                    "latency_ms": latency_ms,
                    "session_id": session_id,
                    "user_id": user_id,
                }
            )
        except Exception:
            pass  # metrics are best-effort
        return response


def _short_id() -> str:
    import uuid
    return uuid.uuid4().hex[:16]


# ---------------- aggregation ----------------
_WINDOWS = {
    "5m": timedelta(minutes=5),
    "1h": timedelta(hours=1),
    "6h": timedelta(hours=6),
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
}


def _percentile(sorted_vals: list[int], p: float) -> int:
    if not sorted_vals:
        return 0
    idx = min(len(sorted_vals) - 1, int(len(sorted_vals) * p))
    return sorted_vals[idx]


async def aggregate(
    db,
    window: str = "1h",
    session_id: Optional[str] = None,
    bucket_minutes: int = 1,
) -> dict[str, Any]:
    """Return summary + time-series for the requested window."""
    delta = _WINDOWS.get(window, _WINDOWS["1h"])
    since = datetime.now(timezone.utc) - delta

    match: dict[str, Any] = {"at": {"$gte": since}}
    if session_id:
        match["session_id"] = session_id

    # Fetch raw docs (bounded by window). For a busy API this could be big,
    # so we cap at 20k rows per window.
    docs = await db.api_metrics.find(
        match, {"_id": 0}, sort=[("at", 1)], limit=20_000
    ).to_list(length=20_000)

    total = len(docs)
    success = sum(1 for d in docs if 200 <= d["status"] < 300)
    client_err = sum(1 for d in docs if 400 <= d["status"] < 500)
    server_err = sum(1 for d in docs if 500 <= d["status"] < 600)

    latencies = sorted(d["latency_ms"] for d in docs)
    p50 = _percentile(latencies, 0.50)
    p95 = _percentile(latencies, 0.95)
    p99 = _percentile(latencies, 0.99)

    # Status-code breakdown (aggregate 4xx/5xx into buckets a human can read)
    by_status: dict[int, int] = {}
    for d in docs:
        by_status[d["status"]] = by_status.get(d["status"], 0) + 1

    # Top failing routes (non-2xx count, then rate)
    per_route: dict[str, dict[str, int]] = {}
    for d in docs:
        r = per_route.setdefault(d["route"], {"total": 0, "failed": 0})
        r["total"] += 1
        if d["status"] >= 400:
            r["failed"] += 1
    top_failing = sorted(
        [
            {
                "route": route,
                "total": v["total"],
                "failed": v["failed"],
                "fail_rate": round(v["failed"] * 100 / max(v["total"], 1), 1),
            }
            for route, v in per_route.items()
        ],
        key=lambda x: (-x["failed"], -x["total"]),
    )[:10]

    # Time-series buckets
    bucket_sec = max(bucket_minutes * 60, 15)
    buckets: dict[int, dict[str, int]] = {}
    for d in docs:
        ts = int(d["at"].replace(tzinfo=timezone.utc).timestamp())
        key = ts - (ts % bucket_sec)
        b = buckets.setdefault(key, {"ok": 0, "err_4xx": 0, "err_5xx": 0})
        if 200 <= d["status"] < 300:
            b["ok"] += 1
        elif 400 <= d["status"] < 500:
            b["err_4xx"] += 1
        elif 500 <= d["status"] < 600:
            b["err_5xx"] += 1
    series = [
        {
            "t": datetime.fromtimestamp(k, tz=timezone.utc).isoformat(),
            **v,
        }
        for k, v in sorted(buckets.items())
    ]

    # Per-session breakdown (only if not filtered)
    per_session = []
    if not session_id:
        s_agg: dict[str, dict[str, int]] = {}
        for d in docs:
            sid = d.get("session_id") or "master"
            row = s_agg.setdefault(sid, {"total": 0, "failed": 0})
            row["total"] += 1
            if d["status"] >= 400:
                row["failed"] += 1
        per_session = sorted(
            [
                {
                    "session_id": sid,
                    "total": v["total"],
                    "failed": v["failed"],
                    "fail_rate": round(v["failed"] * 100 / max(v["total"], 1), 1),
                }
                for sid, v in s_agg.items()
            ],
            key=lambda x: -x["total"],
        )[:20]

    return {
        "window": window,
        "since": since.isoformat(),
        "total": total,
        "success": success,
        "client_errors": client_err,
        "server_errors": server_err,
        "success_rate": round(success * 100 / max(total, 1), 2),
        "latency": {"p50": p50, "p95": p95, "p99": p99, "max": latencies[-1] if latencies else 0},
        "by_status": by_status,
        "top_failing_routes": top_failing,
        "series": series,
        "per_session": per_session,
    }


async def ensure_indexes(db) -> None:
    """Create the TTL index so metrics auto-purge after 7 days."""
    try:
        await db.api_metrics.create_index("at", expireAfterSeconds=7 * 86400)
        await db.api_metrics.create_index([("session_id", 1), ("at", -1)])
        await db.api_metrics.create_index([("status", 1), ("at", -1)])
    except Exception:
        pass
