from pathlib import Path

import pytest

from local_ai.documents import Document, chunk_document
from local_ai.projects import Project
from local_ai.tools import SafeTools


def test_chunking_is_deterministic():
    doc = Document(text="Kalimat uji. " * 300, source="sample.md", title="sample")
    first = chunk_document(doc, size=300, overlap=50)
    second = chunk_document(doc, size=300, overlap=50)
    assert len(first) > 2
    assert [item.id for item in first] == [item.id for item in second]


def test_tool_cannot_escape_workspace(tmp_path: Path):
    project = Project("test", "Test", "Test", "Test", tmp_path)
    with pytest.raises(PermissionError):
        SafeTools()._path(project, "../secret.txt")


def test_write_requires_confirmation(tmp_path: Path):
    project = Project("test", "Test", "Test", "Test", tmp_path, allow_write=True)
    result = SafeTools().execute(
        project, "write_file", {"path": "note.txt", "content": "hello"}
    )
    assert result.requires_confirmation
    assert not (tmp_path / "note.txt").exists()

