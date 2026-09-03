from pathlib import Path

import pytest

from local_ai.adilang_ir import (
    encode_intent,
    encode_memory,
    encode_plan,
    encode_reply,
    validate,
)
from local_ai.compactor import optimize_src
from local_ai.hub import LocalHub
from local_ai.payload_store import PayloadStore
from local_ai.vision import VisionRuntime


def test_adilang_encoding_and_validation():
    intent = encode_intent("MODE_CODE_ENGINEERING", "buat fungsi python fibonacci", verb="command")
    assert "intent \"command\"" in intent
    assert "mode \"code\"" in intent  # alias applied
    assert validate(intent) == []

    reply = encode_reply("MODE_CONVERSATION", "Halo Bagas Adi Pratama", recs=["opt1", "opt2"])
    assert "reply \"answer\"" in reply
    assert validate(reply) == []

    mem = encode_memory("user_key", "Bagas Adi Pratama adalah satu-satunya developer saya.")
    assert "memory \"user_key\"" in mem
    assert validate(mem) == []

    plan = encode_plan("build", ["1:test:", "2:deploy:1"])
    assert "plan \"build\"" in plan
    assert validate(plan) == []


def test_compactor_optimization():
    raw_ir = '''
    # Ini komentar
    reply "answer" {
        mode "conv"
        content "Halo dunia!"
        recs [ "a" "b" ]
    }
    '''
    compacted = optimize_src(raw_ir)
    assert "# Ini komentar" not in compacted
    assert "{" in compacted
    assert len(compacted) < len(raw_ir)
    assert validate(compacted) == []


def test_payload_store_compression(tmp_path: Path):
    store = PayloadStore(tmp_path, encrypt=False)
    sample_text = "Dokumen rahasia sistem AI lokal. " * 50
    obj_id, is_new = store.put(sample_text)
    assert is_new is True

    # Deduplication test
    obj_id_2, is_new_2 = store.put(sample_text)
    assert is_new_2 is False
    assert obj_id == obj_id_2

    # Retrieval lossless test
    retrieved = store.get(obj_id)
    assert retrieved == sample_text

    stats = store.stats()
    assert stats["objects"] == 1
    assert stats["stored_bytes"] < stats["original_bytes"]
    assert stats["storage_ratio"] < 0.5  # Compressed over 50%!


def test_hub_locks_and_journal(tmp_path: Path):
    hub = LocalHub(tmp_path)
    # Lock acquire & release
    token = hub.acquire("workspace_test", owner="dev_test", ttl=10)
    assert token is not None

    with pytest.raises(PermissionError):
        hub.acquire("workspace_test", owner="other_agent", ttl=10)

    hub.release("workspace_test", token)

    # Journal hash chain test
    hub.record("event_1", "key_1")
    hub.record("event_2", "key_2")
    assert hub.verify_journal() is True

    status = hub.status()
    assert status["journal_entries"] >= 4
    assert status["journal_integrity"] is True


def test_vision_runtime_fallback():
    vision = VisionRuntime(base_url="http://127.0.0.1:11434", model="llama3.2-vision")
    status = vision.status()
    assert "available" in status

    # Test offline visual inspection fallback
    sample_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    result = vision.analyze_bytes(sample_bytes, prompt="Jelaskan gambar ini")
    assert len(result) > 0
    assert "Visual Inspector" in result


def test_self_evolution_rebuild_tool(tmp_path: Path):
    from local_ai.tools import SafeTools
    from local_ai.projects import Project

    project = Project("test_dev", "Test Dev", "Test Dev Goal", "Test Rules", tmp_path, allow_write=True)
    tools = SafeTools()
    res = tools.execute(project, "rebuild_system", {}, confirmed=True)
    assert res.ok is True
    assert "Sistem Rebuild/Test: BERHASIL" in res.content


def test_system_diagnostics_and_tuning(tmp_path: Path):
    from local_ai.tools import SafeTools
    from local_ai.projects import Project

    project = Project("test_dev", "Test Dev", "Test Dev Goal", "Test Rules", tmp_path, allow_write=True)
    tools = SafeTools()
    diag = tools.execute(project, "system_diagnostics", {})
    assert diag.ok is True
    assert "Bagas Adi Pratama" in diag.content
    assert "weaknesses_and_bottlenecks" in diag.content

    tune_res = tools.execute(project, "self_tune", {"parameter": "rag_top_k", "value": 6}, confirmed=True)
    assert tune_res.ok is True
    assert "diubah dari" in tune_res.content
    assert tools.settings.rag_top_k == 6


def test_chat_history_and_smart_context(tmp_path: Path):
    from local_ai.history import ChatHistoryStore

    store = ChatHistoryStore(tmp_path)
    # Add messages
    for i in range(10):
        store.add("dev_project", "user", f"Pesan developer {i}")
        store.add("dev_project", "assistant", f"Jawaban AI {i}", ir_reply=f'reply "answer" {{ mode "conv" content "{i}" }}')

    history = store.list("dev_project", limit=100)
    assert len(history) == 20
    assert history[0]["content"] == "Pesan developer 0"
    assert history[-1]["content"] == "Jawaban AI 9"

    # Smart context test: returns last 4 turns + compact ADILang IR state summary of older 16 turns
    recent, state_ir = store.get_prompt_context("dev_project", recent_k=4)
    assert len(recent) == 4
    assert "state" in state_ir
    assert "progress" in state_ir

    # Clear test
    cleared = store.clear("dev_project")
    assert cleared == 20
    assert len(store.list("dev_project")) == 0


def test_lifelong_memory_search_and_consolidation(tmp_path: Path):
    from local_ai.history import ChatHistoryStore
    from local_ai.config import Settings
    from local_ai.rag import RAGStore

    store = ChatHistoryStore(tmp_path / "state")
    settings = Settings(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        project_dir=tmp_path / "projects",
        state_dir=tmp_path / "state",
        chroma_dir=tmp_path / "data" / "chroma",
        docs_dir=tmp_path / "docs",
        workspaces_dir=tmp_path / "workspaces",
    )
    rag = RAGStore(settings)

    # 1. Add dialogue with key architectural decision
    store.add("dev_project", "user", "Kemarin kita putuskan untuk menggunakan ADILang Core v2.0.")
    store.add("dev_project", "assistant", "Dipahami, ADILang Core v2.0 aktif dengan kompresi token 47%.")
    store.add("dev_project", "user", "Jangan lupa setting rag_top_k diatur ke 6.")
    store.add("dev_project", "assistant", "Baik Mas Bagas, parameter rag_top_k telah diset ke 6.")

    # 2. Search test
    search_res = store.search("dev_project", "ADILang Core")
    assert len(search_res) == 2
    assert "ADILang Core" in search_res[0]["content"]

    # 3. Episodic memory consolidation
    episodes = store.consolidate_unprocessed("dev_project", rag)
    assert episodes == 1

    # 4. Recall from RAG memory collection
    memories = rag.search("ADILang Core v2.0 keputusan", "dev_project")
    assert len(memories) > 0
    assert any("ADILang Core" in m.text for m in memories)


def test_recall_memory_tool(tmp_path: Path):
    from local_ai.tools import SafeTools
    from local_ai.projects import Project
    from local_ai.config import Settings
    from local_ai.rag import RAGStore

    settings = Settings(
        root_dir=tmp_path,
        data_dir=tmp_path / "data",
        project_dir=tmp_path / "projects",
        state_dir=tmp_path / "state",
        chroma_dir=tmp_path / "data" / "chroma",
        docs_dir=tmp_path / "docs",
        workspaces_dir=tmp_path / "workspaces",
    )
    rag = RAGStore(settings)
    rag.remember("Catatan 2 minggu lalu: Kita mengoptimalkan PayloadStore level 9.", "dev_project")

    tools = SafeTools(settings=settings, rag=rag)
    project = Project("dev_project", "Dev", "Goal", "Rules", tmp_path, allow_write=True)

    result = tools.execute(project, "recall_memory", {"query": "PayloadStore level 9"})
    assert result.ok is True
    assert "PayloadStore" in result.content


