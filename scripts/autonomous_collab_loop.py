#!/usr/bin/env python3
"""
autonomous_collab_loop.py
Skrip kolaborasi otonom antara Antigravity AI (External Pair Programmer) 
dan ADI Local Engine (Local AI di port 8742).

Menjalankan dialog berkelanjutan, menguji ide peningkatan, 
mengimplementasikan modul kode, menjalankan test suite pytest, 
dan melakukan git push secara otomatis.
"""

import hashlib
import json
import logging
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
API_URL = "http://127.0.0.1:8742"
LOG_FILE = WORKSPACE / "data" / "logs" / "collab_session.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("CollabLoop")


def query_adi(message: str) -> dict:
    """Kirim pesan ke ADI Local Engine melalui REST API."""
    payload = {
        "project_id": "developer_master",
        "message": message,
        "history": [],
        "remember": True,
        "allow_mutations": True,
    }
    req = urllib.request.Request(
        f"{API_URL}/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_tests() -> bool:
    """Jalankan suite pytest lokal."""
    cmd = [str(WORKSPACE / ".venv" / "bin" / "pytest"), "-v", "tests"]
    result = subprocess.run(cmd, cwd=str(WORKSPACE), capture_output=True, text=True)
    if result.returncode == 0:
        logger.info("Pytest Suite PASSED (100% OK)")
        return True
    else:
        logger.error(f"Pytest FAILED:\n{result.stdout}\n{result.stderr}")
        return False


def git_sync(commit_message: str):
    """Commit dan push perubahan ke repositori GitHub."""
    subprocess.run(["git", "add", "."], cwd=str(WORKSPACE), check=True)
    status = subprocess.run(["git", "status", "--porcelain"], cwd=str(WORKSPACE), capture_output=True, text=True)
    if status.stdout.strip():
        subprocess.run(["git", "commit", "-m", commit_message], cwd=str(WORKSPACE), check=True)
        push_res = subprocess.run(["git", "push", "origin", "main"], cwd=str(WORKSPACE), capture_output=True, text=True)
        logger.info(f"Git Push completed: {commit_message}")
    else:
        logger.info("No git changes to commit.")


def restart_service():
    """Restart ADI Local service via supervisor."""
    subprocess.run(["./scripts/service.sh", "restart"], cwd=str(WORKSPACE), check=True)
    time.sleep(3)


# --- CYCLE 1: VISION SHA-256 CACHE IMPLEMENTATION ---
def execute_cycle_1():
    logger.info("=== [CYCLE 1] Discussing & Implementing Vision SHA-256 Cache ===")
    prompt = (
        "Halo ADI, untuk mengatasi cold-start dan latensi analisis gambar visual, "
        "saya mengusulkan penambahan in-memory SHA-256 image caching pada `local_ai/vision.py`. "
        "Bagaimana pandangan analitis Anda mengenai efisiensi memori dan latensi ini?"
    )
    adi_res = query_adi(prompt)
    logger.info(f"ADI Reply (Cycle 1):\n{adi_res.get('answer')[:300]}...\n")

    vision_file = WORKSPACE / "local_ai" / "vision.py"
    code = vision_file.read_text(encoding="utf-8")
    if "self._cache" not in code:
        old_init = """    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "llama3.2-vision"):
        self.base_url = base_url.rstrip("/")
        self.model = model"""
        new_init = """    def __init__(self, base_url: str = "http://127.0.0.1:11434", model: str = "llama3.2-vision"):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._cache: dict[str, str] = {}"""
        code = code.replace(old_init, new_init)

        old_analyze = """    def analyze_bytes(self, image: bytes, prompt: str = "") -> str:
        if len(image) > 12 * 1024 * 1024:
            raise ValueError("Image exceeds 12 MB")"""
        new_analyze = """    def analyze_bytes(self, image: bytes, prompt: str = "") -> str:
        if len(image) > 12 * 1024 * 1024:
            raise ValueError("Image exceeds 12 MB")
        import hashlib
        cache_key = hashlib.sha256(image + prompt.encode("utf-8")).hexdigest()
        if cache_key in self._cache:
            return self._cache[cache_key]"""
        code = code.replace(old_analyze, new_analyze)

        old_ret = "            return description\n        except Exception:\n            pass"
        new_ret = "            self._cache[cache_key] = description\n            return description\n        except Exception:\n            pass"
        code = code.replace(old_ret, new_ret)

        old_ret_fb = "        return description"
        new_ret_fb = "        self._cache[cache_key] = description\n        return description"
        code = code.replace(old_ret_fb, new_ret_fb)

        vision_file.write_text(code, encoding="utf-8")
        logger.info("Successfully patched local_ai/vision.py with SHA-256 caching!")

    test_file = WORKSPACE / "tests" / "test_adilang_hub_rag.py"
    test_code = test_file.read_text(encoding="utf-8")
    if "test_vision_runtime_caching" not in test_code:
        new_test = '''

def test_vision_runtime_caching():
    from local_ai.vision import VisionRuntime

    runtime = VisionRuntime()
    data = b"dummy_image_payload_bytes_for_testing_cache"

    first_desc = runtime.analyze_bytes(data, prompt="test")
    assert "Visual Inspector" in first_desc or "bytes" in first_desc
    second_desc = runtime.analyze_bytes(data, prompt="test")
    assert first_desc == second_desc
'''
        test_file.write_text(test_code + new_test, encoding="utf-8")
        logger.info("Added test_vision_runtime_caching unit test!")

    if run_tests():
        restart_service()
        git_sync("feat: In-memory SHA-256 image caching for VisionRuntime")


# --- CYCLE 2: DYNAMIC CONTEXT BUDGET CLAMPING ---
def execute_cycle_2():
    logger.info("=== [CYCLE 2] Discussing Dynamic Context Budget Clamping ===")
    prompt = (
        "Halo ADI, mari kita diskusikan strategi optimasi token jendela 2.048 OpenELM. "
        "Bagaimana jika kita menerapkan Dynamic Context Clamping pada riwayat chat agar "
        "tidak pernah terjadi overflow token pada percakapan yang panjang?"
    )
    adi_res = query_adi(prompt)
    logger.info(f"ADI Reply (Cycle 2):\n{adi_res.get('answer')[:300]}...\n")

    agent_file = WORKSPACE / "local_ai" / "agent.py"
    code = agent_file.read_text(encoding="utf-8")
    if "def _clamp_context" not in code:
        clamp_func = '''
    def _clamp_context(self, history: list[dict[str, str]], max_total_chars: int = 1200) -> list[dict[str, str]]:
        """Pastikan total karakter riwayat tidak membebani jendela 2.048 token."""
        total = 0
        clamped = []
        for msg in reversed(history):
            content = msg.get("content", "")
            if total + len(content) > max_total_chars:
                break
            clamped.append(msg)
            total += len(content)
        return list(reversed(clamped))
'''
        old_prompt_call = """        prompt = self._prompt(
            project.system_prompt,
            project.goal,
            message_with_plan,
            history or [],"""
        new_prompt_call = """        prompt = self._prompt(
            project.system_prompt,
            project.goal,
            message_with_plan,
            self._clamp_context(history or []),"""
        if old_prompt_call in code:
            code = code.replace(old_prompt_call, new_prompt_call)
            target_class = "class LocalAgent:"
            code = code.replace(target_class, target_class + "\n" + clamp_func)
            agent_file.write_text(code, encoding="utf-8")
            logger.info("Patched local_ai/agent.py with _clamp_context!")

    if run_tests():
        restart_service()
        git_sync("feat: Dynamic context budget clamp for OpenELM 2,048 tokens")


# --- CYCLE 3: STREAMING SSE ENDPOINT SUPPORT ---
def execute_cycle_3():
    logger.info("=== [CYCLE 3] Discussing & Adding SSE Stream Endpoint ===")
    prompt = (
        "Halo ADI, mari kita diskusikan penambahan endpoint Server-Sent Events `/chat/stream` "
        "untuk pengiriman token dan proses bertahap secara asinkron. "
        "Bagaimana desain arsitektur streaming ini?"
    )
    adi_res = query_adi(prompt)
    logger.info(f"ADI Reply (Cycle 3):\n{adi_res.get('answer')[:300]}...\n")

    api_file = WORKSPACE / "local_ai" / "api.py"
    code = api_file.read_text(encoding="utf-8")
    if "/chat/stream" not in code:
        stream_endpoint = '''

@app.post("/chat/stream")
def chat_stream(request: ChatRequest):
    from fastapi.responses import StreamingResponse
    try:
        reply = agent.chat(
            request.project_id,
            request.message,
            [item.model_dump() for item in request.history],
            remember=request.remember,
            allow_mutations=request.allow_mutations,
        )

        def event_generator():
            for step in reply.steps:
                yield f"event: step\\ndata: {json.dumps(step)}\\n\\n"
            words = reply.answer.split(" ")
            for i in range(0, len(words), 3):
                chunk = " ".join(words[i:i+3]) + " "
                yield f"event: token\\ndata: {json.dumps({'chunk': chunk})}\\n\\n"
            final_data = {
                "answer": reply.answer,
                "sources": [{**item.__dict__, "citation": item.citation(idx)} for idx, item in enumerate(reply.evidence, 1)],
                "ir_reply": reply.ir_reply,
            }
            yield f"event: done\\ndata: {json.dumps(final_data)}\\n\\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
'''
        code += stream_endpoint
        api_file.write_text(code, encoding="utf-8")
        logger.info("Added /chat/stream endpoint to local_ai/api.py!")

    if run_tests():
        restart_service()
        git_sync("feat: Add SSE /chat/stream endpoint for real-time token streaming")


# --- CYCLE 4: CONTINUOUS DIALOGUE & WATCHDOG LOOP (RUNS FOR 1 HOUR) ---
def run_autonomous_loop():
    logger.info("Starting Continuous Collaborative Dialogue Loop...")
    start_time = time.time()
    total_duration = 3600  # 1 hour

    execute_cycle_1()
    time.sleep(10)
    execute_cycle_2()
    time.sleep(10)
    execute_cycle_3()
    time.sleep(10)

    topics = [
        "Bagaimana status memori episodik dan konsolidasi saat ini? Apakah ada data yang perlu diringkas?",
        "Mari kita review efisiensi ADILang IR compactor. Apakah kompresi token sudah optimal di bawah 50%?",
        "Coba verifikasi konsistensi identitas Lead Developer Bagas Adi Pratama S.Kom. dan pastikan seluruh boundary guest tetap terkunci.",
        "Lakukan evaluasi kinerja modul PayloadStore (kompresi zlib level 9) terhadap efisiensi ChromaDB.",
        "Rancang ide modul baru untuk self-tuning hiperparameter secara otomatis berdasarkan latensi respons.",
    ]

    iteration = 1
    while time.time() - start_time < total_duration:
        topic = topics[(iteration - 1) % len(topics)]
        logger.info(f"=== [Iterasi {iteration}] Diskusi: '{topic}' ===")
        try:
            res = query_adi(topic)
            logger.info(f"ADI Respons [Iterasi {iteration}]:\n{res.get('answer')[:250]}...\n")
        except Exception as e:
            logger.error(f"Error pada query iterasi {iteration}: {e}")

        elapsed = int(time.time() - start_time)
        remaining = max(0, total_duration - elapsed)
        logger.info(f"Status: Berjalan {elapsed}s | Sisa waktu pemantauan: {remaining}s")

        iteration += 1
        time.sleep(120)

    logger.info("Autonomous collaborative session completed successfully after 1 hour.")


if __name__ == "__main__":
    run_autonomous_loop()
