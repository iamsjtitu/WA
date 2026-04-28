"""System admin module — git status + auto-update from GitHub.

Endpoints (admin only):
  GET  /api/admin/system/status   — current commit, branch, behind count
  GET  /api/admin/system/log      — tail of /var/log/wa9x-update.log
  POST /api/admin/system/update   — spawn detached auto-update.sh
"""
from __future__ import annotations

import logging
import os
import subprocess
import threading
import time
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger("wa9x.system")

LOG_PATH = "/var/log/wa9x-update.log"

# In-memory guard against concurrent update spawns
_UPDATE_LOCK = threading.Lock()
_UPDATE_TS = {"started_at": 0.0}
_UPDATE_COOLDOWN_SECONDS = 30  # block a second click within this window


def _install_dir() -> Path:
    return Path(os.environ.get("INSTALL_DIR", "/app"))


def _run(cmd: list[str], timeout: int = 30) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            cmd,
            cwd=_install_dir(),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "timeout"
    except FileNotFoundError as e:
        return -1, "", str(e)


def make_router(admin_only):
    api = APIRouter()

    @api.get("/admin/system/status")
    async def system_status(_: dict = Depends(admin_only)):
        install = _install_dir()
        git_dir = install / ".git"
        result: dict = {
            "install_dir": str(install),
            "git_available": git_dir.exists(),
        }
        if not git_dir.exists():
            result["reason"] = (
                f"{install} is not a Git checkout. To enable auto-update, "
                "redeploy your VPS using `bash setup-vps.sh --git <repo-url>`."
            )
            return result

        rc, current_commit, _ = _run(["git", "rev-parse", "HEAD"])
        rc, short_commit, _ = _run(["git", "rev-parse", "--short", "HEAD"])
        rc, branch_raw, _ = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        branch = (branch_raw or "").strip() or "main"
        rc, last_msg, _ = _run(["git", "log", "-1", "--pretty=%s|%an|%ai"])

        # fetch to learn what's behind (may take a few seconds)
        rc, _, fetch_err = _run(["git", "fetch", "--quiet", "origin"], timeout=30)
        fetch_ok = rc == 0

        rc, behind_str, _ = _run(
            ["git", "rev-list", "--count", f"HEAD..origin/{branch}"]
        )
        try:
            behind = int(behind_str.strip())
        except ValueError:
            behind = 0

        # log of incoming commits
        rc, incoming, _ = _run(
            [
                "git",
                "log",
                "--oneline",
                "-n",
                "10",
                f"HEAD..origin/{branch}",
            ]
        )

        result.update(
            {
                "commit": current_commit.strip(),
                "short_commit": short_commit.strip(),
                "branch": branch,
                "last_commit": last_msg.strip(),
                "behind_count": behind,
                "fetch_ok": fetch_ok,
                "fetch_error": fetch_err.strip() if fetch_err and not fetch_ok else None,
                "incoming_commits": incoming.strip(),
            }
        )

        # Last update log timestamp
        try:
            log_p = Path(LOG_PATH)
            if log_p.exists():
                result["last_update_at"] = log_p.stat().st_mtime
        except Exception:
            pass

        return result

    @api.get("/admin/system/log")
    async def system_log(_: dict = Depends(admin_only), lines: int = 100):
        log_p = Path(LOG_PATH)
        if not log_p.exists():
            return {"log": "", "exists": False}
        lines = max(10, min(int(lines), 2000))
        rc, out, _ = _run(["tail", "-n", str(lines), LOG_PATH], timeout=5)
        return {"log": out, "exists": True}

    @api.post("/admin/system/update")
    async def system_update(_: dict = Depends(admin_only)):
        install = _install_dir()
        if not (install / ".git").exists():
            raise HTTPException(
                status_code=400,
                detail=(
                    f"{install} is not a Git checkout — auto-update is unavailable. "
                    "Re-run setup-vps.sh with --git <repo-url> to enable it."
                ),
            )
        script = install / "deploy" / "auto-update.sh"
        if not script.exists():
            raise HTTPException(
                status_code=500, detail=f"Auto-update script not found at {script}"
            )

        # Prevent concurrent spawns within a short cooldown window
        now = time.time()
        with _UPDATE_LOCK:
            if now - _UPDATE_TS["started_at"] < _UPDATE_COOLDOWN_SECONDS:
                raise HTTPException(
                    status_code=409,
                    detail="An update was just started — please wait for it to finish.",
                )
            _UPDATE_TS["started_at"] = now

        # Detach the script so it survives a backend supervisor restart.
        # Open the log file, hand it to the child, then close our copy so
        # the long-lived FastAPI worker doesn't leak fds across updates.
        try:
            try:
                os.chmod(script, 0o755)
            except OSError:
                pass  # filesystem may be read-only; bash invocation still works
            log_fh = open(LOG_PATH, "ab", buffering=0)
            try:
                subprocess.Popen(
                    ["nohup", "bash", str(script)],
                    stdout=log_fh,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    cwd=str(install),
                    env={**os.environ, "INSTALL_DIR": str(install)},
                )
            finally:
                log_fh.close()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to start update: {e}")

        return {
            "ok": True,
            "message": (
                "Update started. The backend will restart automatically in ~30s. "
                "Tail the log to see progress."
            ),
        }

    return api
