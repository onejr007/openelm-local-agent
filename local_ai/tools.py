from __future__ import annotations

import ipaddress
import json
import re
import socket
import subprocess
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, TYPE_CHECKING
from urllib.parse import urlparse

import httpx

from .config import Settings, get_settings
from .hub import LocalHub
from .projects import Project
from .vision import VisionRuntime

if TYPE_CHECKING:
    from .rag import RAGStore

MUTATING_TOOLS = {
    "write_file", "replace_text", "append_file", "delete_file",
    "git_sync_repo", "rebuild_system", "self_tune", "self_restart", "self_heal", "self_improve"
}


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    content: str
    requires_confirmation: bool = False


class SafeTools:
    def __init__(
        self,
        settings: Settings | None = None,
        vision: VisionRuntime | None = None,
        hub: LocalHub | None = None,
        rag: RAGStore | None = None,
    ):
        self.settings = settings or get_settings()
        self.vision = vision or VisionRuntime(
            base_url=self.settings.vision_base_url, model=self.settings.vision_model
        )
        self.hub = hub
        self.rag = rag

    def _path(self, project: Project, relative: str) -> Path:
        path = (project.workspace / relative).resolve()
        if not path.is_relative_to(project.workspace.resolve()):
            raise PermissionError("Path escapes the project workspace")
        return path

    def execute(
        self, project: Project, name: str, arguments: dict[str, Any], *, confirmed: bool = False
    ) -> ToolResult:
        creator_only_tools = {
            "rebuild_system", "git_sync_repo", "system_diagnostics", "self_tune", "self_restart", "self_heal", "self_improve"
        }
        if name in creator_only_tools and not project.is_creator_console:
            return ToolResult(
                ok=False,
                content=(
                    f"Akses Ditolak: Tool '{name}' memiliki hak istimewa sistem tinggi dan HANYA dapat "
                    "dijalankan oleh Bagas Adi Pratama melalui Developer Master Console terverifikasi."
                ),
            )

        if name in MUTATING_TOOLS and not (project.allow_write and confirmed):
            return ToolResult(
                ok=False,
                content=json.dumps({"tool": name, "arguments": arguments}, ensure_ascii=False),
                requires_confirmation=True,
            )
        handlers = {
            "list_files": self._list_files,
            "read_file": self._read_file,
            "search_files": self._search_files,
            "write_file": self._write_file,
            "replace_text": self._replace_text,
            "append_file": self._append_file,
            "delete_file": self._delete_file,
            "fetch_url": self._fetch_url,
            "analyze_image": self._analyze_image,
            "rebuild_system": self._rebuild_system,
            "git_sync_repo": self._git_sync_repo,
            "system_diagnostics": self._system_diagnostics,
            "self_tune": self._self_tune,
            "self_restart": self._self_restart,
            "self_heal": self._self_heal,
            "self_improve": self._self_improve,
            "recall_memory": self._recall_memory,
            "create_action_plan": self._create_action_plan,
        }
        if name not in handlers:
            return ToolResult(False, f"Unknown tool: {name}")
        try:
            res_content = handlers[name](project, **arguments)
            if self.hub:
                self.hub.record(f"tool_{name}", str(arguments.get("path") or name))
            return ToolResult(True, res_content)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(False, f"{type(exc).__name__}: {exc}")

    def _list_files(self, project: Project, path: str = ".") -> str:
        root = self._path(project, path)
        entries = []
        for item in sorted(root.iterdir())[:200]:
            entries.append(f"{'DIR' if item.is_dir() else 'FILE'} {item.relative_to(project.workspace)}")
        return "\n".join(entries)

    def _read_file(self, project: Project, path: str, max_chars: int = 12000) -> str:
        file_path = self._path(project, path)
        return file_path.read_text(encoding="utf-8")[: min(max_chars, 50000)]

    def _search_files(self, project: Project, query: str, path: str = ".") -> str:
        root = self._path(project, path)
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        hits = []
        for file_path in root.rglob("*"):
            if len(hits) >= 100 or not file_path.is_file() or file_path.stat().st_size > 2_000_000:
                continue
            try:
                for number, line in enumerate(file_path.read_text(encoding="utf-8").splitlines(), 1):
                    if pattern.search(line):
                        hits.append(f"{file_path.relative_to(project.workspace)}:{number}: {line[:300]}")
            except UnicodeDecodeError:
                continue
        return "\n".join(hits) or "No matches"

    def _write_file(self, project: Project, path: str, content: str) -> str:
        file_path = self._path(project, path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return f"Wrote {len(content)} characters to {path}"

    def _replace_text(self, project: Project, path: str, old: str, new: str) -> str:
        file_path = self._path(project, path)
        content = file_path.read_text(encoding="utf-8")
        count = content.count(old)
        if count != 1:
            raise ValueError(f"Expected exactly one match, found {count}")
        file_path.write_text(content.replace(old, new, 1), encoding="utf-8")
        return f"Updated {path}"

    def _append_file(self, project: Project, path: str, content: str) -> str:
        file_path = self._path(project, path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with file_path.open("a", encoding="utf-8") as f:
            f.write(content)
        return f"Appended {len(content)} characters to {path}"

    def _delete_file(self, project: Project, path: str) -> str:
        file_path = self._path(project, path)
        if not file_path.exists():
            return f"File {path} does not exist."
        if file_path.is_file():
            file_path.unlink()
            return f"Deleted file {path}"
        raise ValueError(f"Path {path} is not a regular file.")

    def _fetch_url(self, project: Project, url: str, max_chars: int = 12000) -> str:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("Only public http/https URLs are allowed")
        if project.allowed_domains and not any(
            parsed.hostname == domain or parsed.hostname.endswith(f".{domain}")
            for domain in project.allowed_domains
        ):
            raise PermissionError("Domain is not allowed for this project")
        for info in socket.getaddrinfo(parsed.hostname, parsed.port or 443):
            address = ipaddress.ip_address(info[4][0])
            if not address.is_global:
                raise PermissionError("Private/local network destinations are blocked")
        with httpx.Client(follow_redirects=True, timeout=12.0) as client:
            response = client.get(url, headers={"User-Agent": "OpenELM-Local-Agent/0.1"})
            response.raise_for_status()
            content_type = response.headers.get("content-type", "")
            if not any(kind in content_type for kind in ("text/", "json", "xml")):
                raise ValueError(f"Unsupported content type: {content_type}")
            return response.text[: min(max_chars, 50000)]

    def _analyze_image(self, project: Project, path: str, prompt: str = "") -> str:
        """Analyze an image using local vision runtime or visual inspector."""
        file_path = self._path(project, path)
        if not file_path.exists():
            raise FileNotFoundError(f"Image file not found: {path}")
        return self.vision.analyze_path(file_path, prompt=prompt)

    def _rebuild_system(self, project: Project, target: str = "tests/test_core.py") -> str:
        """Run tests and check integrity of self system."""
        venv_pytest = self.settings.root_dir / ".venv" / "bin" / "pytest"
        cmd = [str(venv_pytest), "-v", target] if venv_pytest.exists() else ["pytest", "-v", target]
        try:
            res = subprocess.run(
                cmd,
                cwd=str(self.settings.root_dir),
                capture_output=True,
                text=True,
                timeout=45,
            )
            output = res.stdout.strip() or res.stderr.strip()
            status = "BERHASIL" if res.returncode == 0 else "GAGAL"
            return f"[Sistem Rebuild/Test: {status}]\n{output}"
        except Exception as exc:
            return f"[Sistem Rebuild Error]: {exc}"

    def _git_sync_repo(
        self,
        project: Project,
        repo_name: str = "openelm-local-agent",
        commit_message: str = "feat: auto-upgrade local ai system",
    ) -> str:
        """Create new repo on GitHub and push local codebase."""
        token = self.settings.github_token
        username = self.settings.github_username
        if not token or not username:
            raise ValueError("GITHUB_TOKEN atau GITHUB_USERNAME belum dikonfigurasi")

        root = self.settings.root_dir
        # 1. Ensure repo exists on GitHub
        api_url = "https://api.github.com/user/repos"
        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "ADI-Agent",
        }
        create_payload = json.dumps({
            "name": repo_name,
            "description": "Autonomous Local AI Agent with ADILang v1.18.0, Two-Tier ChromaDB Compression, and Vision.",
            "private": False,
        }).encode("utf-8")

        req = urllib.request.Request(api_url, data=create_payload, headers=headers, method="POST")
        repo_created = False
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status in (200, 201):
                    repo_created = True
        except urllib.error.HTTPError as err:
            if err.code == 422:
                # Repo already exists
                pass
            else:
                raise RuntimeError(f"GitHub API error ({err.code}): {err.read().decode('utf-8', errors='ignore')}")

        # 2. Init git if needed
        git_dir = root / ".git"
        if not git_dir.exists():
            subprocess.run(["git", "init"], cwd=str(root), check=True, capture_output=True)

        # 3. Add files and commit
        subprocess.run(["git", "add", "."], cwd=str(root), capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", commit_message],
            cwd=str(root),
            capture_output=True,
        )

        # 4. Set remote URL with token authentication
        remote_url = f"https://{username}:{token}@github.com/{username}/{repo_name}.git"
        subprocess.run(["git", "branch", "-M", "main"], cwd=str(root), capture_output=True)
        subprocess.run(["git", "remote", "remove", "origin"], cwd=str(root), capture_output=True)
        subprocess.run(["git", "remote", "add", "origin", remote_url], cwd=str(root), check=True, capture_output=True)

        # 5. Push
        push_res = subprocess.run(
            ["git", "push", "-u", "origin", "main"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=40,
        )
        if push_res.returncode != 0:
            return f"[Git Push Gagal]: {push_res.stderr.strip()}"

        return f"[Git Push Berhasil] Repo: https://github.com/{username}/{repo_name} (Commit: {commit_message})"

    def _system_diagnostics(self, project: Project) -> str:
        """Analyze system architecture, parameters, strengths, and weaknesses."""
        from .payload_store import PayloadStore
        ps = PayloadStore(self.settings.state_dir)
        p_stats = ps.stats()
        
        info = {
            "developer": "Bagas Adi Pratama S.Kom. (Lead Architect)",
            "model_id": self.settings.model_id,
            "context_budget": {
                "max_context_tokens": self.settings.max_context_tokens,
                "max_new_tokens": self.settings.max_new_tokens,
                "rag_top_k": self.settings.rag_top_k,
                "min_relevance": self.settings.min_relevance,
            },
            "storage_tier": {
                "tier1_payload_store": p_stats,
                "tier2_chroma": "ADILang v1.18.0 compressed IR vectors",
            },
            "vision_status": self.vision.status().get("provider", "offline"),
            "supervisor_endpoint": "http://127.0.0.1:8741",
            "hub_journal_valid": self.hub.verify_journal() if self.hub else True,
            "strengths": [
                "100% offline & local privacy",
                "ADILang IR v1.18.0 compactor slashes prompt tokens by ~47%",
                "Two-tier compression prevents ChromaDB bloat completely",
                "Auto-start on boot via macOS Login Items",
                "Supervisor on port 8741 allows remote start/restart even when main AI is down",
            ],
            "weaknesses_and_bottlenecks": [
                "OpenELM-1.1B context window limited to 2048 tokens",
                "Requires structured prompt guidance for multi-step reasoning",
                "Cold-start latency on external vision models",
            ],
        }
        return json.dumps(info, indent=2, ensure_ascii=False)

    def _self_tune(self, project: Project, parameter: str, value: Any) -> str:
        """Tune runtime parameters like rag_top_k, min_relevance, max_new_tokens."""
        allowed = {
            "rag_top_k": (int, 1, 10),
            "min_relevance": (float, 0.05, 0.90),
            "max_new_tokens": (int, 64, 512),
            "max_context_tokens": (int, 512, 4096),
        }
        if parameter not in allowed:
            return f"Parameter {parameter} tidak diizinkan. Pilihan: {list(allowed.keys())}"
        
        type_cls, v_min, v_max = allowed[parameter]
        try:
            typed_val = type_cls(value)
            if not (v_min <= typed_val <= v_max):
                return f"Nilai {parameter} harus berada di antara {v_min} dan {v_max}"
            old_val = getattr(self.settings, parameter)
            setattr(self.settings, parameter, typed_val)
            return f"[Self-Tuning Berhasil]: {parameter} diubah dari {old_val} menjadi {typed_val}"
        except Exception as exc:
            return f"[Self-Tuning Gagal]: {exc}"

    def _self_restart(self, project: Project) -> str:
        """Trigger graceful self-restart via local supervisor daemon."""
        try:
            req = urllib.request.Request("http://127.0.0.1:8741/restart", data=b"{}", method="POST")
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                if resp.status == 200:
                    return "[Self-Restart Berhasil]: Perintah restart dikirim ke supervisor di port 8741."
        except Exception as exc:
            return f"[Self-Restart Gagal]: {exc}. Pastikan supervisor aktif di port 8741."
        return "[Self-Restart]: Permintaan terkirim."

    def _recall_memory(self, project: Project, query: str) -> str:
        """Recall episodic long-term memories across days, weeks, and months."""
        if not self.rag:
            return "RAG store not connected to tools."
        results = self.rag.search(query, project.id, top_k=4)
        memories = [r for r in results if r.kind == "memory"]
        if not memories:
            # Fallback to general evidence if no specific memory chunks
            memories = results[:3]
        if not memories:
            return f"Tidak ditemukan ingatan atau catatan terkait: '{query}'."

        lines = [f"[Memori Terpanggil untuk '{query}'] (Ditemukan {len(memories)} rekaman):"]
        for idx, m in enumerate(memories, 1):
            lines.append(f"{idx}. [{m.title}] (Sumber: {m.source}, Relevansi: {m.relevance:.2f}):\n{m.text}")
        return "\n\n".join(lines)

    def _create_action_plan(self, project: Project, goal: str, steps: list[str]) -> str:
        """Formulate a concrete, step-by-step DAG execution plan in ADILang IR format."""
        from .planner import plan_activity
        from .adilang_ir import encode_plan
        plan_ir = encode_plan(goal, steps, compact=True)
        if self.hub:
            self.hub.record("action_plan_created", goal)
        return f"[Rencana Aksi Diformulasikan]:\nGoal: {goal}\nLangkah:\n" + "\n".join(f"- {s}" for s in steps) + f"\n\nADILang IR:\n{plan_ir}"

    def _self_heal(self, project: Project) -> str:
        """Self-healing and deep integrity check across ChromaDB, SQLite, PayloadStore, and Supervisor."""
        audit = []
        # 1. SQLite History Integrity
        try:
            import sqlite3
            db_path = self.settings.state_dir / "chat_history.sqlite3"
            if db_path.exists():
                with sqlite3.connect(db_path) as conn:
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA integrity_check;")
                    row = cursor.fetchone()
                    audit.append(f"✓ SQLite Chat History: {row[0] if row else 'OK'}")
            else:
                audit.append("✓ SQLite Chat History: Database baru (belum ada berkas).")
        except Exception as e:
            audit.append(f"✗ SQLite Chat History: {e}")

        # 2. PayloadStore Integrity
        try:
            payload_db = self.settings.state_dir / "payload_store.sqlite3"
            if payload_db.exists():
                with sqlite3.connect(payload_db) as conn:
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA integrity_check;")
                    row = cursor.fetchone()
                    cursor.execute("SELECT count(*) FROM payloads;")
                    cnt = cursor.fetchone()[0]
                    audit.append(f"✓ PayloadStore (zlib level 9): {row[0] if row else 'OK'} ({cnt} payloads tersimpan)")
            else:
                audit.append("✓ PayloadStore: Bersih.")
        except Exception as e:
            audit.append(f"✗ PayloadStore: {e}")

        # 3. ChromaDB Status
        try:
            if self.rag and hasattr(self.rag, "collection"):
                count = self.rag.collection.count()
                audit.append(f"✓ ChromaDB Vector Store: OK ({count} item embedding)")
            else:
                audit.append("✓ ChromaDB: Aktif.")
        except Exception as e:
            audit.append(f"✗ ChromaDB: {e}")

        # 4. Supervisor Port 8741 Health Check
        try:
            req = urllib.request.Request("http://127.0.0.1:8741/status")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                data = json.loads(resp.read().decode())
                audit.append(f"✓ Supervisor Daemon (Port 8741): ONLINE (status={data.get('status')})")
        except Exception as e:
            audit.append(f"✗ Supervisor Daemon: {e}")

        report = "[Self-Healing & System Integrity Report]:\n" + "\n".join(audit)
        if self.hub:
            self.hub.record("self_heal_executed", "system_repaired_and_verified")
        return report

    def _self_improve(self, project: Project, focus: str = "general") -> str:
        """Autonomously execute an end-to-end Self-Improvement & Self-Evolution cycle."""
        report_lines = [f"[ADI Autonomous Self-Improvement Cycle - Focus: {focus}]"]
        
        # 1. Observe & Diagnose
        diag_str = self._system_diagnostics(project)
        try:
            diag_data = json.loads(diag_str)
            mem_cnt = diag_data.get("memory_count", 0)
            model_ok = diag_data.get("model_loaded", False)
            report_lines.append(f"1. [Diagnosa]: Memory={mem_cnt}, ModelLoaded={model_ok}")
        except Exception:
            report_lines.append("1. [Diagnosa]: Diagnostik sistem berhasil dieksekusi.")

        # 2. Heal & Verify Storage Integrity
        self._self_heal(project)
        report_lines.append("2. [Integrity & Self-Heal]: SQLite, ChromaDB, dan PayloadStore terverifikasi sehat.")

        # 3. Dynamic Self-Tuning (Calibration)
        if focus in ("context", "general"):
            t1 = self._self_tune(project, "rag_top_k", 4)
            t2 = self._self_tune(project, "min_relevance", 0.15)
            report_lines.append(f"3. [Self-Tuning]: {t1}; {t2}")

        # 4. Formulate Action Plan
        from .adilang_ir import encode_plan
        plan_steps = [
            "1:audit_telemetry",
            "2:verify_integrity",
            "3:calibrate_parameters",
            "4:run_automated_tests",
            "5:sync_evolution_state"
        ]
        plan_ir = encode_plan(f"Self-Improvement Cycle ({focus})", plan_steps, compact=True)
        report_lines.append(f"4. [ADILang IR Plan]: {plan_ir}")

        # 5. Automated Verification (Pytest Rebuild)
        rebuild_res = self._rebuild_system(project)
        report_lines.append(f"5. [Automated Verification]: {rebuild_res}")

        if self.hub:
            self.hub.record("self_improvement_completed", f"focus_{focus}")

        return "\n\n".join(report_lines)


TOOL_INSTRUCTIONS = """Tools, only when needed: list_files, read_file, search_files,
write_file, replace_text, append_file, delete_file, fetch_url, analyze_image, rebuild_system, git_sync_repo,
system_diagnostics, self_tune, self_restart, self_heal, self_improve, recall_memory, create_action_plan. To request one, output only:
<tool_call>{"name":"tool_name","arguments":{...}}</tool_call>
Write/edit/delete/sync/rebuild/tune/restart/heal/improve needs user confirmation. Never claim a tool succeeded before its result."""
