"""
Lifelong Episodic-Semantic Memory & Chat History Store.
Enables continuous lifelong partnership without session resets.
Maintains full chronological SQLite storage for infinite-scroll user UI,
while consolidating past days and weeks into token-dense ADILang IR memory
modules for the local AI model (ChromaDB + PayloadStore).
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

from .adilang_ir import encode_memory_chunk, encode_state

if TYPE_CHECKING:
    from .rag import RAGStore


class ChatHistoryStore:
    def __init__(self, state_dir: Path):
        state_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = state_dir / "chat_history.sqlite3"
        self._lock = threading.RLock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
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
                    consolidated INTEGER DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_project_time 
                ON chat_messages(project_id, timestamp)
            """)
            try:
                conn.execute("ALTER TABLE chat_messages ADD COLUMN consolidated INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_chat_consolidated 
                ON chat_messages(project_id, consolidated)
            """)

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
                INSERT INTO chat_messages (id, project_id, role, content, ir_reply, sources_json, timestamp, consolidated)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0)
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

    def list(
        self,
        project_id: str,
        limit: int = 40,
        before_ts: float | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch messages chronologically with optional pagination for infinite scroll."""
        with self._connect() as conn:
            if before_ts is not None:
                rows = conn.execute(
                    """
                    SELECT id, project_id, role, content, ir_reply, sources_json, timestamp, created_at
                    FROM chat_messages
                    WHERE project_id = ? AND timestamp < ?
                    ORDER BY timestamp DESC
                    LIMIT ?
                    """,
                    (project_id, before_ts, limit),
                ).fetchall()
                rows.reverse()
            else:
                rows = conn.execute(
                    """
                    SELECT id, project_id, role, content, ir_reply, sources_json, timestamp, created_at
                    FROM (
                        SELECT id, project_id, role, content, ir_reply, sources_json, timestamp, created_at
                        FROM chat_messages
                        WHERE project_id = ?
                        ORDER BY timestamp DESC
                        LIMIT ?
                    )
                    ORDER BY timestamp ASC
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

    def search(self, project_id: str, query: str, limit: int = 30) -> list[dict[str, Any]]:
        """Search across entire lifelong conversation history."""
        pattern = f"%{query}%"
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, project_id, role, content, ir_reply, sources_json, timestamp, created_at
                FROM chat_messages
                WHERE project_id = ? AND content LIKE ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (project_id, pattern, limit),
            ).fetchall()

        results = []
        for r in rows:
            results.append({
                "id": r[0],
                "project_id": r[1],
                "role": r[2],
                "content": r[3],
                "timestamp": r[6],
                "created_at": r[7],
            })
        return results

    def count(self, project_id: str) -> int:
        with self._connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM chat_messages WHERE project_id = ?", (project_id,)).fetchone()
            return int(row[0]) if row else 0

    def clear(self, project_id: str) -> int:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM chat_messages WHERE project_id = ?", (project_id,))
            return cur.rowcount

    def get_prompt_context(self, project_id: str, recent_k: int = 4) -> tuple[list[dict[str, str]], str]:
        """
        Smart Context Management:
        Extracts the recent `recent_k` turns for immediate conversational flow,
        plus an ultra-compact ADILang IR state summary of earlier turns today.
        """
        all_msgs = self.list(project_id, limit=60)
        if not all_msgs:
            return [], ""

        recent = all_msgs[-recent_k:]
        recent_turns = [{"role": m["role"], "content": m["content"]} for m in recent]

        older = all_msgs[:-recent_k]
        if not older:
            return recent_turns, ""

        older_summary_parts = []
        for msg in older[-8:]:
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

    def consolidate_unprocessed(self, project_id: str, rag: RAGStore) -> int:
        """
        Consolidates completed conversation turns into permanent episodic memories.
        Converts batches of dialogue into token-dense ADILang memory chunks
        stored in PayloadStore and vector-indexed in ChromaDB.
        """
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                """
                SELECT id, role, content, timestamp
                FROM chat_messages
                WHERE project_id = ? AND consolidated = 0
                ORDER BY timestamp ASC
                """,
                (project_id,),
            ).fetchall()

        if len(rows) < 4:
            return 0  # wait for sufficient dialogue to form a meaningful episode

        episodes_created = 0
        batch_size = 6
        for i in range(0, len(rows), batch_size):
            chunk = rows[i : i + batch_size]
            if len(chunk) < 2:
                break

            start_dt = datetime.fromtimestamp(chunk[0][3], tz=timezone.utc).strftime("%Y-%m-%d %H:%M")
            summary_lines = []
            for item in chunk:
                r_label = "Developer" if item[1] == "user" else "AI"
                c_text = item[2][:140].replace("\n", " ")
                summary_lines.append(f"{r_label}: {c_text}")

            episode_text = f"Episode [{start_dt} UTC]:\n" + "\n".join(summary_lines)
            memory_key = f"episodic_history_{int(chunk[0][3])}"

            # Store in RAG memory collection (PayloadStore Tier 1 + ChromaDB Tier 2)
            rag.remember(
                text=episode_text,
                project_id=project_id,
                scope="project",
                source=f"chat_history_{chunk[0][0][:8]}",
            )

            # Mark messages as consolidated
            msg_ids = [item[0] for item in chunk]
            with self._lock, self._connect() as conn:
                conn.executemany(
                    "UPDATE chat_messages SET consolidated = 1 WHERE id = ?",
                    [(mid,) for mid in msg_ids],
                )
            episodes_created += 1

        return episodes_created
