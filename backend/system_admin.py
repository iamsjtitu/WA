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
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger("wa9x.system")

LOG_PATH = "/var/log/wa9x-update.log"


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
        rc, branch, _ = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
        rc, last_msg, _ = _run(["git", "log", "-1", "--pretty=%s|%an|%ai"])

        # fetch to learn what's behind (may take a few seconds)
        rc, _, fetch_err = _run(["git", "fetch", "--quiet", "origin"], timeout=30)
        fetch_ok = rc == 0

        rc, behind_str, _ = _run(
            ["git", "rev-list", "--count", f"HEAD..origin/{branch.strip() or 'main'}"]
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
                f"HEAD..origin/{branch.strip() or 'main'}",
            ]
        )

        result.update(
            {
                "commit": current_commit.strip(),
                "short_commit": short_commit.strip(),
                "branch": branch.strip(),
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

        # Detach the script so it survives a backend supervisor restart
        try:
            log_fh = open(LOG_PATH, "ab", buffering=0)
            subprocess.Popen(
                ["nohup", "bash", str(script)],
                stdout=log_fh,
                stderr=subprocess.STDOUT,
                start_new_session=True,
                cwd=str(install),
                env={**os.environ, "INSTALL_DIR": str(install)},
            )
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
