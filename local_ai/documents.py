import csv
import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from pypdf import PdfReader

from .vision import VisionRuntime

SUPPORTED = {".txt", ".md", ".markdown", ".json", ".jsonl", ".csv", ".pdf", ".png", ".jpg", ".jpeg", ".webp"}


@dataclass(frozen=True)
class Document:
    text: str
    source: str
    title: str


@dataclass(frozen=True)
class Chunk:
    id: str
    text: str
    source: str
    title: str
    index: int


def load_document(path: Path) -> Document:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED:
        raise ValueError(f"Unsupported file type: {suffix}")
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        vision = VisionRuntime()
        text = vision.analyze_path(path, prompt="Jelaskan isi gambar ini secara menyeluruh untuk database pengetahuan AI.")
    elif suffix == ".pdf":
        reader = PdfReader(str(path))
        text = (chr(10) + chr(10)).join(page.extract_text() or "" for page in reader.pages)
    elif suffix == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
        text = chr(10).join(json.dumps(row, ensure_ascii=False) for row in rows)
    elif suffix == ".json":
        text = json.dumps(json.loads(path.read_text(encoding="utf-8")), ensure_ascii=False)
    elif suffix == ".jsonl":
        lines = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                lines.append(json.dumps(json.loads(line), ensure_ascii=False))
        text = chr(10).join(lines)
    else:
        text = path.read_text(encoding="utf-8")
    return Document(text=text.strip(), source=str(path.resolve()), title=path.stem)


def chunk_document(doc: Document, size: int = 1200, overlap: int = 180) -> list[Chunk]:
    if size <= overlap or overlap < 0:
        raise ValueError("Chunk size must be greater than overlap")
    clean = chr(10).join(line.rstrip() for line in doc.text.splitlines()).strip()
    if not clean:
        return []
    chunks: list[Chunk] = []
    start = 0
    index = 0
    d_newline = chr(10) + chr(10)
    while start < len(clean):
        end = min(start + size, len(clean))
        if end < len(clean):
            candidates = [clean.rfind(d_newline, start, end), clean.rfind(". ", start, end)]
            boundary = max(candidates)
            if boundary > start + size // 2:
                end = boundary + (2 if clean[boundary : boundary + 2] == ". " else 0)
        text = clean[start:end].strip()
        if text:
            digest = hashlib.sha256(f"{doc.source}:{index}:{text}".encode()).hexdigest()[:24]
            chunks.append(
                Chunk(id=digest, text=text, source=doc.source, title=doc.title, index=index)
            )
            index += 1
        if end >= len(clean):
            break
        start = max(end - overlap, start + 1)
    return chunks


def iter_dataset_files(path: Path) -> Iterable[Path]:
    if path.is_file():
        if path.suffix.lower() in SUPPORTED:
            yield path
        return
    for file_path in sorted(path.rglob("*")):
        if file_path.is_file() and file_path.suffix.lower() in SUPPORTED:
            yield file_path
