"""Spawn and supervise the Node.js Baileys microservice as a child process."""
from __future__ import annotations

import os
import signal
import subprocess
import threading
import time
from pathlib import Path

WA_DIR = Path("/app/wa-service")
LOG_FILE = Path("/var/log/supervisor/wa-service.log")

_proc: subprocess.Popen | None = None
_lock = threading.Lock()


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


def start():
    global _proc
    with _lock:
        if _proc and _proc.poll() is None:
            return

        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        log = open(LOG_FILE, "ab", buffering=0)

        env = os.environ.copy()
        env["PORT"] = "3001"

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
