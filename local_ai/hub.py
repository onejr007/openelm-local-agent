"""Local governance layer inspired by ADI HUB.

Preserves guarantees for the local agent: deny-by-default mutations,
resource locks with TTL, append-only hash-chained journal (SHA-256),
and an asynchronous mailbox queue for resilient chat turns.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .adilang_ir import encode_event


class LocalHub:
    def __init__(self, state_dir: Path):
        self.path = state_dir / "hub.sqlite3"
        self._lock = threading.RLock()
        with self._connect() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS locks(
                    resource TEXT PRIMARY KEY, owner TEXT NOT NULL, token TEXT NOT NULL,
                    expires_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS journal(
                    seq INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, event TEXT NOT NULL,
                    ir TEXT NOT NULL, previous_hash TEXT NOT NULL, entry_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS mailbox(
                    id TEXT PRIMARY KEY,
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    subject TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    status TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    processed_at REAL
                );
            """)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def acquire(self, resource: str, owner: str = "openelm-local", ttl: int = 120) -> str:
        now = time.time()
        token = uuid.uuid4().hex
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM locks WHERE expires_at<=?", (now,))
            row = conn.execute("SELECT owner FROM locks WHERE resource=?", (resource,)).fetchone()
            if row:
                raise PermissionError(f"Resource locked by {row[0]}: {resource}")
            conn.execute(
                "INSERT INTO locks(resource,owner,token,expires_at) VALUES(?,?,?,?)",
                (resource, owner, token, now + ttl),
            )
        self.record("lock_acquired", resource)
        return token

    def release(self, resource: str, token: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM locks WHERE resource=? AND token=?", (resource, token))
        self.record("lock_released", resource)

    def record(self, event: str, key: str, ir_override: str | None = None) -> str:
        at = dt.datetime.now(dt.timezone.utc).isoformat()
        ir = ir_override or encode_event(event, "openelm-local", key=key, compact=True)
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT entry_hash FROM journal ORDER BY seq DESC LIMIT 1").fetchone()
            previous = row[0] if row else "0" * 16
            digest = hashlib.sha256(f"{at}|{event}|{ir}|{previous}".encode()).hexdigest()[:16]
            conn.execute(
                "INSERT INTO journal(at,event,ir,previous_hash,entry_hash) VALUES(?,?,?,?,?)",
                (at, event, ir, previous, digest),
            )
        return digest

    def enqueue_message(self, sender: str, recipient: str, subject: str, payload: str) -> str:
        msg_id = uuid.uuid4().hex
        now = time.time()
        with self._lock, self._connect() as conn:
            conn.execute(
                "INSERT INTO mailbox(id,sender,recipient,subject,payload,status,created_at) VALUES(?,?,?,?,?,?,?)",
                (msg_id, sender, recipient, subject, payload, "pending", now),
            )
        self.record("mailbox_enqueued", msg_id)
        return msg_id

    def pop_pending_message(self, recipient: str = "openelm-local") -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT id,sender,recipient,subject,payload,created_at FROM mailbox WHERE recipient=? AND status='pending' ORDER BY created_at ASC LIMIT 1",
                (recipient,),
            ).fetchone()
            if not row:
                return None
            msg_id = row[0]
            conn.execute(
                "UPDATE mailbox SET status='processing', processed_at=? WHERE id=?",
                (time.time(), msg_id),
            )
            return {
                "id": row[0],
                "sender": row[1],
                "recipient": row[2],
                "subject": row[3],
                "payload": row[4],
                "created_at": row[5],
            }

    def mark_message_done(self, msg_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("UPDATE mailbox SET status='completed', processed_at=? WHERE id=?", (time.time(), msg_id))
        self.record("mailbox_completed", msg_id)

    def status(self) -> dict[str, Any]:
        now = time.time()
        with self._connect() as conn:
            conn.execute("DELETE FROM locks WHERE expires_at<=?", (now,))
            locks = conn.execute("SELECT resource,owner,expires_at FROM locks").fetchall()
            count = conn.execute("SELECT COUNT(*) FROM journal").fetchone()[0]
            pending_msgs = conn.execute("SELECT COUNT(*) FROM mailbox WHERE status='pending'").fetchone()[0]
        return {
            "policy": "deny-by-default",
            "active_locks": [
                {"resource": row[0], "owner": row[1], "expires_at": row[2]} for row in locks
            ],
            "journal_entries": count,
            "journal_integrity": self.verify_journal(),
            "pending_mailbox_messages": pending_msgs,
        }

    def verify_journal(self) -> bool:
        previous = "0" * 16
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT at,event,ir,previous_hash,entry_hash FROM journal ORDER BY seq"
            ).fetchall()
        for at, event, ir, stored_previous, entry_hash in rows:
            expected = hashlib.sha256(f"{at}|{event}|{ir}|{previous}".encode()).hexdigest()[:16]
            if stored_previous != previous or entry_hash != expected:
                return False
            previous = entry_hash
        return True

    def journal(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT seq,at,event,ir,entry_hash FROM journal ORDER BY seq DESC LIMIT ?", (limit,)
            ).fetchall()
        return [
            {"seq": row[0], "at": row[1], "event": row[2], "ir": row[3], "hash": row[4]}
            for row in rows
        ]
