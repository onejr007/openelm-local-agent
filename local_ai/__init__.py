"""Local, project-aware OpenELM agent."""

import os
from pathlib import Path

# Hugging Face reads its cache path during module import, before Settings is created.
# Pin it to this project early so model assets remain portable and available offline.
os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parent.parent / "data" / "models"))

__version__ = "0.1.0"
