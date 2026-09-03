"""
Persistent Chat History Store with Smart Context Management.
Maintains full chronological conversation history in SQLite for the user UI,
while synthesizing ultra-compact ADILang IR state summaries for the model
to prevent token-window bloat and avoid hallucinations.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from .adilang_ir import encode_state


class ChatHistoryStore:
    def __init__(self, state_dir: Path):
        state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = state_dir / "chat_history.sqlite3"
        self._lock = threading.RLock()
        with self._connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS chat_messages (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    ir_reply TEXT,
                    sources_json TEXT,
                    timestamp REAL NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_project_time 
                ON chat_messages(project_id, timestamp)
            """)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def add(
        self,
        project_id: str,
        role: str,
        content: str,
        *,
        ir_reply: str = "",
        sources: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        msg_id = uuid.uuid4().hex
        ts = time.time()
        sources_str = json.dumps(sources or [], ensure_ascii=False)
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_messages (id, project_id, role, content, ir_reply, sources_json, timestamp)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (msg_id, project_id, role, content, ir_reply, sources_str, ts),
            )
        return {
            "id": msg_id,
            "project_id": project_id,
            "role": role,
            "content": content,
            "ir_reply": ir_reply,
            "sources": sources or [],
            "timestamp": ts,
        }

    def list(self, project_id: str, limit: int = 100) -> list[dict[str, Any]]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, project_id, role, content, ir_reply, sources_json, timestamp, created_at
                FROM chat_messages
                WHERE project_id = ?
                ORDER BY timestamp ASC
                LIMIT ?
                """,
                (project_id, limit),
            ).fetchall()

        messages = []
        for r in rows:
            sources = []
            if r[5]:
                try:
                    sources = json.loads(r[5])
                except Exception:
                    pass
            messages.append({
                "id": r[0],
                "project_id": r[1],
                "role": r[2],
                "content": r[3],
                "ir_reply": r[4] or "",
                "sources": sources,
                "timestamp": r[6],
                "created_at": r[7],
            })
        return messages

    def clear(self, project_id: str) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM chat_messages WHERE project_id = ?", (project_id,))
            return cur.rowcount

    def get_prompt_context(self, project_id: str, recent_k: int = 4) -> tuple[list[dict[str, str]], str]:
        """
        Smart Context Management:
        Extracts the recent `recent_k` turns for verbatim conversational flow,
        plus an ultra-compact ADILang IR state summary of older conversation context.
        This prevents context window bloat and eliminates hallucinations.
        """
        all_msgs = self.list(project_id, limit=200)
        if not all_msgs:
            return [], ""

        # Last recent_k turns
        recent = all_msgs[-recent_k:]
        recent_turns = [{"role": m["role"], "content": m["content"]} for m in recent]

        # If there are older turns, synthesize an ultra-compact ADILang state block
        older = all_msgs[:-recent_k]
        if not older:
            return recent_turns, ""

        older_summary_parts = []
        for msg in older[-8:]:  # sample up to 8 older messages
            role_prefix = "U" if msg["role"] == "user" else "AI"
            snippet = msg["content"][:60].replace("\n", " ")
            older_summary_parts.append(f"{role_prefix}:{snippet}")

        compact_history_text = " | ".join(older_summary_parts)
        state_ir = encode_state(
            project_id,
            status=compact_history_text[:200],
            progress=str(len(older)),
            compact=True,
        )
        return recent_turns, state_ir
