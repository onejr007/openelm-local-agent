#!/usr/bin/env python3
"""
continuous_deep_improvement_loop.py
Skrip daemon kolaborasi tanpa batas waktu antara Antigravity External AI
dan ADI Local Engine (Local AI Port 8742).

Terus menerus berdiskusi, merancang perbaikan sistem, menguji fungsionalitas,
memeriksa integritas self-heal, dan mencatat log sampai dihentikan oleh user.
"""

import json
import logging
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parent.parent
API_URL = "http://127.0.0.1:8742"
LOG_FILE = WORKSPACE / "data" / "logs" / "continuous_evolution.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("ContinuousEvolution")


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
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode("utf-8"))


def trigger_self_heal() -> dict:
    """Panggil tool self_heal secara berkala."""
    payload = {
        "project_id": "developer_master",
        "name": "self_heal",
        "arguments": {},
        "confirmed": True,
    }
    req = urllib.request.Request(
        f"{API_URL}/tools/execute",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def run_tests() -> bool:
    """Jalankan pytest suite."""
    cmd = [str(WORKSPACE / ".venv" / "bin" / "pytest"), "-v", "tests"]
    result = subprocess.run(cmd, cwd=str(WORKSPACE), capture_output=True, text=True)
    if result.returncode == 0:
        logger.info("Test Suite Verification: 100% OK")
        return True
    else:
        logger.error(f"Test Suite Verification FAILED:\n{result.stdout}")
        return False


def main():
    logger.info("=== Memulai Loop Dialog & Evolusi Berkelanjutan Bersama ADI Local ===")

    discussion_agenda = [
        "Halo ADI, mari kita diskusikan strategi optimasi retensi memori jangka panjang. Bagaimana kita menyaring fakta teknis penting agar ChromaDB dan PayloadStore tetap seimbang?",
        "Coba lakukan self-audit terhadap performa kompresor ADILang IR compactor. Apakah ada token sintaks yang bisa dipadatkan lebih jauh?",
        "Bagaimana integrasi streaming SSE dan rendering Markdown di web frontend developer? Apakah ada bottleneck pada pengiriman token per detik?",
        "Mari kita evaluasi keamanan hak istimewa superuser Lead Developer Bagas Adi Pratama S.Kom. dan pastikan perimeter guest console tetap kedap.",
        "Lakukan audit mandiri (self-heal) terhadap integritas SQLite dan PayloadStore untuk memastikan tidak ada payload korup.",
        "Rancang skenario otomatisasi rebuild sistem jika terdeteksi perubahan berkas di workspace.",
        "Diskusikan strategi kalibrasi parameter RAG: top_k=4 dan min_relevance=0.25 apakah sudah optimal untuk menghindari distorsi konteks?",
        "Bagaimana status in-memory SHA-256 cache untuk modul vision? Apakah penggunaan RAM tetap stabil di bawah 50MB?",
    ]

    cycle = 1
    while True:
        prompt = discussion_agenda[(cycle - 1) % len(discussion_agenda)]
        logger.info(f"\n--- [Putaran {cycle}] Memulai Diskusi: '{prompt[:70]}...' ---")

        try:
            res = query_adi(prompt)
            answer = res.get("answer", "")
            steps = res.get("steps", [])
            logger.info(f"ADI Merespons dengan {len(steps)} tahapan berpikir kognitif.")
            logger.info(f"Cuplikan Jawaban ADI:\n{answer[:250]}...\n")

            # Setiap 4 siklus, jalankan self_heal dan verifikasi pytest
            if cycle % 4 == 0:
                logger.info("Melakukan verifikasi berkala (self_heal + pytest)...")
                heal_res = trigger_self_heal()
                logger.info(f"Hasil Self-Heal:\n{heal_res.get('content', '')}")
                run_tests()

        except Exception as e:
            logger.error(f"Terjadi kendala pada putaran {cycle}: {e}")

        logger.info(f"Putaran {cycle} selesai. Menunggu sebelum putaran berikutnya...")
        cycle += 1
        time.sleep(90)  # Dialog berkala setiap 1.5 menit


if __name__ == "__main__":
    main()
