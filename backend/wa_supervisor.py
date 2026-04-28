"""Spawn and supervise the Node.js Baileys microservice as a child process."""
from __future__ import annotations

import os
import signal
import socket
import subprocess
import threading
import time
from pathlib import Path

WA_DIR = Path(os.environ.get("WA_SERVICE_DIR", "/app/wa-service"))
LOG_FILE = Path(os.environ.get("WA_SERVICE_LOG", "/var/log/supervisor/wa-service.log"))
WA_PORT = int(os.environ.get("WA_PORT", "3001"))

_proc: subprocess.Popen | None = None
_lock = threading.Lock()
_watchdog_started = False


def _stream_to_log(stream, log):
    try:
        for line in iter(stream.readline, b""):
            try:
                log.write(line.decode("utf-8", errors="replace"))
                log.flush()
            except Exception:
                pass
    except Exception:
        pass


def _port_in_use(port: int) -> bool:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.settimeout(0.5)
    try:
        s.connect(("127.0.0.1", port))
        return True
    except Exception:
        return False
    finally:
        s.close()


def _watchdog():
    """Respawn Node if it dies (and nobody else is on the port)."""
    while True:
        time.sleep(15)
        try:
            with _lock:
                proc_alive = bool(_proc and _proc.poll() is None)
            if proc_alive:
                continue
            if _port_in_use(WA_PORT):
                # someone else (e.g. supervisor) is managing it
                continue
            print("[wa_supervisor] node not running, respawning")
            start()
        except Exception as e:
            print(f"[wa_supervisor] watchdog error: {e}")


def start():
    global _proc, _watchdog_started

    # If port already taken (e.g. by external supervisor), don't double-spawn
    if _port_in_use(WA_PORT):
        if not _watchdog_started:
            _watchdog_started = True
            threading.Thread(target=_watchdog, daemon=True).start()
        return

    with _lock:
        if _proc and _proc.poll() is None:
            return

        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        log = open(LOG_FILE, "ab", buffering=0)

        env = os.environ.copy()
        env["PORT"] = str(WA_PORT)
        env["FASTAPI_URL"] = os.environ.get("FASTAPI_URL", "http://127.0.0.1:8001")
        env["INTERNAL_SECRET"] = os.environ.get("INTERNAL_SECRET", "")
        env["WA_AUTH_DIR"] = os.environ.get(
            "WA_AUTH_DIR", str(WA_DIR / "auth")
        )

        _proc = subprocess.Popen(
            ["node", "server.js"],
            cwd=str(WA_DIR),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            preexec_fn=os.setsid,
        )

        threading.Thread(
            target=_stream_to_log, args=(_proc.stdout, log), daemon=True
        ).start()

        if not _watchdog_started:
            _watchdog_started = True
            threading.Thread(target=_watchdog, daemon=True).start()

        # tiny grace
        time.sleep(0.5)


def stop():
    global _proc
    with _lock:
        if _proc and _proc.poll() is None:
            try:
                os.killpg(os.getpgid(_proc.pid), signal.SIGTERM)
            except Exception:
                pass
            try:
                _proc.wait(timeout=5)
            except Exception:
                try:
                    os.killpg(os.getpgid(_proc.pid), signal.SIGKILL)
                except Exception:
                    pass
        _proc = None


def is_running() -> bool:
    with _lock:
        return bool(_proc and _proc.poll() is None)
