import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT / ".env", env_prefix="LOCAL_AI_", extra="ignore"
    )

    model_id: str = "mlx-community/OpenELM-1_1B-Instruct-8bit"
    embedding_model: str = "intfloat/multilingual-e5-small"
    embedding_device: str = "cpu"
    host: str = "127.0.0.1"
    port: int = 8742
    max_context_tokens: int = 2048
    max_new_tokens: int = 192
    rag_top_k: int = 4
    min_relevance: float = 0.30
    auto_load_model: bool = True
    offline_mode: bool = True

    # Vision settings
    vision_base_url: str = "http://127.0.0.1:11434"
    vision_model: str = "llama3.2-vision"
    vision_enabled: bool = True

    # GitHub integration
    github_token: str = ""
    github_username: str = "onejr007"

    # Message queue & Redis for background tasks & self-rebuilding
    redis_url: str = "redis://127.0.0.1:6379/0"
    rabbitmq_url: str = "amqp://guest:guest@127.0.0.1:5672/"

    root_dir: Path = ROOT
    project_dir: Path = ROOT / "projects"
    chroma_dir: Path = ROOT / "data" / "chroma"
    state_dir: Path = ROOT / "data" / "state"
    model_dir: Path = ROOT / "data" / "models"

    def prepare(self) -> None:
        self.chroma_dir.mkdir(parents=True, exist_ok=True)
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.model_dir.mkdir(parents=True, exist_ok=True)
        os.environ.setdefault("HF_HOME", str(self.model_dir))
        if self.offline_mode:
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

        # Auto-detect GITHUB_TOKEN from 1_Local/.env.txt if not set
        if not self.github_token:
            for env_candidate in [
                Path("/Users/bagasadipratama/Documents/Proj/1_Local/.env.txt"),
                Path("/Users/bagasadipratama/Documents/Proj/1_local/.env.txt"),
                ROOT / ".env",
            ]:
                if env_candidate.exists():
                    try:
                        for line in env_candidate.read_text(encoding="utf-8").splitlines():
                            line = line.strip()
                            if line.startswith("GITHUB_TOKEN="):
                                self.github_token = line.split("=", 1)[1].strip().strip('"').strip("'")
                            elif line.startswith("GITHUB_USERNAME="):
                                self.github_username = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if self.github_token:
                            break
                    except Exception:
                        pass


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.prepare()
    return settings
