"""Deduplicated, compressed and optionally encrypted payload storage.

ChromaDB keeps vectors and compact metadata. Full text lives here and is decoded
only after vector retrieval identifies the relevant object.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import threading
import zlib
from pathlib import Path

try:
    from cryptography.fernet import Fernet
except ImportError:
    Fernet = None


class PayloadStore:
    def __init__(self, state_dir: Path, encrypt: bool = False):
        state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = state_dir / "payloads.sqlite3"
        self.key_path = state_dir / "payload.key"
        self.encrypt = encrypt and (Fernet is not None)
        self._lock = threading.RLock()
        self._cipher = Fernet(self._key()) if encrypt else None
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS payloads (
                    object_id TEXT PRIMARY KEY,
                    content_hash TEXT UNIQUE NOT NULL,
                    codec TEXT NOT NULL,
                    payload BLOB NOT NULL,
                    original_bytes INTEGER NOT NULL,
                    stored_bytes INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)

    def _key(self) -> bytes:
        if self.key_path.exists():
            return self.key_path.read_bytes().strip()
        key = Fernet.generate_key()
        self.key_path.write_bytes(key + b"\n")
        os.chmod(self.key_path, 0o600)
        return key

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def put(self, text: str) -> tuple[str, bool]:
        raw = text.encode("utf-8")
        digest = hashlib.sha256(raw).hexdigest()
        object_id = digest[:32]
        compressed = zlib.compress(raw, level=9)
        payload = self._cipher.encrypt(compressed) if self._cipher else compressed
        codec = "fernet+zlib" if self._cipher else "zlib"
        with self._lock, self._connect() as conn:
            existing = conn.execute(
                "SELECT object_id FROM payloads WHERE content_hash=?", (digest,)
            ).fetchone()
            if existing:
                return str(existing[0]), False
            conn.execute(
                "INSERT INTO payloads(object_id,content_hash,codec,payload,original_bytes,stored_bytes) VALUES(?,?,?,?,?,?)",
                (object_id, digest, codec, payload, len(raw), len(payload)),
            )
        return object_id, True

    def get(self, object_id: str) -> str:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT codec,payload FROM payloads WHERE object_id=?", (object_id,)
            ).fetchone()
        if not row:
            raise KeyError(f"Unknown payload: {object_id}")
        codec, payload = row
        if codec.startswith("fernet+"):
            if not self._cipher:
                raise PermissionError("Payload key is unavailable")
            payload = self._cipher.decrypt(payload)
        return zlib.decompress(payload).decode("utf-8")

    def delete_unreferenced(self, referenced: set[str]) -> int:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT object_id FROM payloads").fetchall()
            stale = [row[0] for row in rows if row[0] not in referenced]
            conn.executemany("DELETE FROM payloads WHERE object_id=?", [(item,) for item in stale])
        return len(stale)

    def stats(self) -> dict[str, float | int | bool]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*),COALESCE(SUM(original_bytes),0),COALESCE(SUM(stored_bytes),0) FROM payloads"
            ).fetchone()
        count, original, stored = row
        return {
            "objects": int(count),
            "original_bytes": int(original),
            "stored_bytes": int(stored),
            "storage_ratio": round(stored / original, 4) if original else 0.0,
            "encrypted": self.encrypt,
        }

