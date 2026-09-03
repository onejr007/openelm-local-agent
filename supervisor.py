"""
ADI AI Supervisor Daemon (Port 8741)
Supervises local_ai on port 8742. Provides HTTP control endpoints for starting,
stopping, restarting, and querying AI engine status even if the main server is down.
Uses Python standard library only.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

SUPERVISOR_PORT = 8741
AI_PORT = 8742
ROOT_DIR = Path(__file__).resolve().parent
RUN_SH = ROOT_DIR / "run.sh"
PID_FILE = ROOT_DIR / "data" / "state" / "ai_server.pid"
LOG_FILE = ROOT_DIR / "data" / "logs" / "service.log"
ERR_FILE = ROOT_DIR / "data" / "logs" / "service-error.log"

ai_process: subprocess.Popen | None = None


def is_ai_running() -> tuple[bool, int | None]:
    # Check via HTTP ping first
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{AI_PORT}/health", headers={"User-Agent": "Supervisor"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            if resp.status == 200:
                pid = get_saved_pid()
                return True, pid
    except Exception:
        pass

    # Check via PID file
    pid = get_saved_pid()
    if pid:
        try:
            os.kill(pid, 0)
            return True, pid
        except OSError:
            pass
    return False, None


def get_saved_pid() -> int | None:
    if PID_FILE.exists():
        try:
            val = PID_FILE.read_text(encoding="utf-8").strip()
            if val.isdigit():
                return int(val)
        except Exception:
            pass
    return None


def start_ai() -> dict:
    global ai_process
    running, pid = is_ai_running()
    if running:
        return {"status": "already_running", "pid": pid}

    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)

    stdout_handle = open(LOG_FILE, "a", encoding="utf-8")
    stderr_handle = open(ERR_FILE, "a", encoding="utf-8")

    ai_process = subprocess.Popen(
        [str(RUN_SH)],
        cwd=str(ROOT_DIR),
        stdout=stdout_handle,
        stderr=stderr_handle,
        preexec_fn=os.setsid,
    )
    PID_FILE.write_text(str(ai_process.pid), encoding="utf-8")

    # Wait up to 3 seconds to confirm startup
    time.sleep(1.5)
    running, pid = is_ai_running()
    return {"status": "started" if running else "starting", "pid": ai_process.pid}


def stop_ai() -> dict:
    global ai_process
    running, pid = is_ai_running()
    if not running and not pid:
        return {"status": "not_running"}

    target_pid = pid or (ai_process.pid if ai_process else None)
    if target_pid:
        try:
            os.killpg(os.getpgid(target_pid), signal.SIGTERM)
        except Exception:
            try:
                os.kill(target_pid, signal.SIGTERM)
            except Exception:
                pass
        time.sleep(1.0)

    if PID_FILE.exists():
        try:
            PID_FILE.unlink()
        except Exception:
            pass
    ai_process = None
    return {"status": "stopped"}


def restart_ai() -> dict:
    stop_ai()
    time.sleep(1.0)
    return start_ai()


class SupervisorHandler(BaseHTTPRequestHandler):
    def _send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def do_OPTIONS(self):
        self.send_response(204)
        self._send_cors_headers()
        self.end_headers()

    def do_GET(self):
        if self.path in ("/status", "/health"):
            running, pid = is_ai_running()
            data = {
                "supervisor": "online",
                "ai_running": running,
                "ai_pid": pid,
                "port": AI_PORT,
            }
            body = json.dumps(data).encode("utf-8")
            self.send_response(200)
            self._send_cors_headers()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        result = {}
        if self.path == "/start":
            result = start_ai()
        elif self.path == "/stop":
            result = stop_ai()
        elif self.path == "/restart":
            result = restart_ai()
        else:
            self.send_response(404)
            self.end_headers()
            return

        body = json.dumps(result).encode("utf-8")
        self.send_response(200)
        self._send_cors_headers()
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        # Silent logging to avoid console pollution
        pass


def run_supervisor():
    # Make sure AI is started on supervisor boot
    print(f"ADI Supervisor starting on http://127.0.0.1:{SUPERVISOR_PORT}...")
    running, pid = is_ai_running()
    if not running:
        print("Auto-starting AI engine on port 8742...")
        start_ai()
    else:
        print(f"AI engine already running (PID: {pid}).")

    server = HTTPServer(("127.0.0.1", SUPERVISOR_PORT), SupervisorHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nSupervisor shutting down...")
    finally:
        server.server_close()


if __name__ == "__main__":
    run_supervisor()
