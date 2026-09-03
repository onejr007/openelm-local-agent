import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .config import Settings

PROJECT_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,63}$")


@dataclass(frozen=True)
class Project:
    id: str
    name: str
    goal: str
    system_prompt: str
    workspace: Path
    allow_write: bool = False
    allowed_domains: tuple[str, ...] = ()

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "goal": self.goal,
            "workspace": str(self.workspace),
            "allow_write": self.allow_write,
            "allowed_domains": list(self.allowed_domains),
        }


class ProjectRegistry:
    def __init__(self, settings: Settings):
        self.settings = settings

    def list(self) -> list[Project]:
        return [self._load(path) for path in sorted(self.settings.project_dir.glob("*.json"))]

    def get(self, project_id: str) -> Project:
        if not PROJECT_ID.fullmatch(project_id):
            raise ValueError("Invalid project id")
        path = self.settings.project_dir / f"{project_id}.json"
        if not path.is_file():
            raise KeyError(f"Unknown project: {project_id}")
        return self._load(path)

    def create(self, definition: dict[str, Any]) -> Project:
        project_id = str(definition.get("id", ""))
        if not PROJECT_ID.fullmatch(project_id):
            raise ValueError("Project id must contain 2-64 lowercase letters, numbers, _ or -")
        path = self.settings.project_dir / f"{project_id}.json"
        if path.exists():
            raise ValueError(f"Project already exists: {project_id}")
        workspace = str(definition.get("workspace") or f"workspaces/{project_id}")
        candidate = (self.settings.root_dir / workspace).resolve()
        if not candidate.is_relative_to(self.settings.root_dir.resolve()):
            raise ValueError("Project workspace must stay inside the application root")
        payload = {
            "id": project_id,
            "name": str(definition["name"]),
            "goal": str(definition["goal"]),
            "system_prompt": str(definition["system_prompt"]),
            "workspace": workspace,
            "allow_write": bool(definition.get("allow_write", False)),
            "allowed_domains": list(definition.get("allowed_domains", [])),
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return self._load(path)

    def _load(self, path: Path) -> Project:
        raw = json.loads(path.read_text(encoding="utf-8"))
        project_id = str(raw.get("id", ""))
        if path.stem != project_id or not PROJECT_ID.fullmatch(project_id):
            raise ValueError(f"Invalid project definition: {path.name}")
        workspace = (self.settings.root_dir / raw["workspace"]).resolve()
        root = self.settings.root_dir.resolve()
        if not workspace.is_relative_to(root):
            raise ValueError(f"Project workspace escapes application root: {project_id}")
        workspace.mkdir(parents=True, exist_ok=True)
        return Project(
            id=project_id,
            name=raw["name"],
            goal=raw["goal"],
            system_prompt=raw["system_prompt"],
            workspace=workspace,
            allow_write=bool(raw.get("allow_write", False)),
            allowed_domains=tuple(raw.get("allowed_domains", [])),
        )
