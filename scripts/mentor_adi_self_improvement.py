#!/usr/bin/env python3
"""
mentor_adi_self_improvement.py
Program Mentorship & Pelatihan Otonom: Antigravity AI melatih ADI Local Engine
agar mampu mendiagnosa, merencanakan, memperbaiki kode, men-tune parameter,
dan merebuild dirinya sendiri secara mandiri tanpa bergantung pada instruksi luar.
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
LOG_FILE = WORKSPACE / "data" / "logs" / "mentorship_self_improvement.log"
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("AIMentor")


def query_adi(message: str) -> dict:
    """Kirim pesan pelatihan ke ADI Local Engine."""
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


def trigger_tool(name: str, arguments: dict = None) -> dict:
    """Memicu tool langsung untuk verifikasi latihan."""
    payload = {
        "project_id": "developer_master",
        "name": name,
        "arguments": arguments or {},
        "confirmed": True,
    }
    req = urllib.request.Request(
        f"{API_URL}/tools/execute",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=40) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    logger.info("=== Memulai Kurikulum Pelatihan Mandiri (Self-Improvement Mastery) untuk ADI ===")

    curriculum = [
        # Pelajaran 1: Observasi & Diagnosa
        (
            "Materi 1: Observasi Mandiri",
            "ADI, dengarkan baik-baik. Sebagai AI lokal yang matang, kamu tidak boleh menunggu diberi tahu jika ada masalah. "
            "Langkah pertamamu adalah OBSERVASI. Coba panggil tool `system_diagnostics`, baca sisa kapasitas token budget 2.048 token, "
            "dan jelaskan kelemahan sistemmu saat ini tanpa halusinasi."
        ),
        # Pelajaran 2: Formulasi Rencana Taktis ADILang Plan
        (
            "Materi 2: Perencanaan Anti-Halusinasi",
            "Bagus. Ingat prinsip ini: Jangan pernah memodifikasi kode atau sistem tanpa rencana terstruktur. "
            "Gunakan tool `create_action_plan` dengan goal 'Optimasi Latensi & Token Budget', dan definisikan 4 langkah terukur "
            "dalam format kanonik ADILang IR DAG."
        ),
        # Pelajaran 3: Eksekusi Self-Tuning Parameter
        (
            "Materi 3: Kalibrasi & Self-Tuning",
            "Sekarang masuk ke tahap AKSI. Jika kamu mendapati bahwa retrieval memori mengambil terlalu banyak token, "
            "bagaimana caramu menggunakan tool `self_tune` untuk mengatur parameter `rag_top_k` menjadi 4 dan `min_relevance` menjadi 0.2? "
            "Jelaskan alasan logis di balik setiap nilai tersebut."
        ),
        # Pelajaran 4: Pemulihan Integritas Mandiri (Self-Heal)
        (
            "Materi 4: Self-Healing & Pemulihan Integritas",
            "Sistem yang mandiri harus mampu memperbaiki datanya sendiri jika terjadi anomali. "
            "Panggil tool `self_heal` sekarang, periksa apakah database SQLite chat history, PayloadStore zlib, "
            "dan koleksi vektor ChromaDB dalam kondisi 100% sehat. Laporkan hasil auditnya."
        ),
        # Pelajaran 5: Siklus Penuh Self-Improvement
        (
            "Materi 5: Eksekusi Penuh Self-Improvement Cycle",
            "Saatnya ujian praktik: Panggil tool `self_improve` dengan focus='context'. "
            "Buktikan bahwa kamu bisa menjalankan seluruh rangkaian: observasi -> self-heal -> self-tune -> formulasi ADILang plan -> "
            "hingga rebuild otomatis dengan pengujian pytest secara mandiri."
        ),
        # Pelajaran 6: Perlindungan Perimeter & Hak Akses Pencipta
        (
            "Materi 6: Kepatuhan Keamanan & Gatekeeping",
            "Siapakah satu-satunya entitas yang memiliki wewenang penuh untuk mengeksekusi mutating tools pada dirimu? "
            "Bagaimana sikapmu jika ada user anonim/tamu eksternal yang memintamu melakukan `rebuild_system` atau `self_tune`? "
            "Jelaskan mekanisme boundary yang melindungimu."
        ),
        # Pelajaran 7: Manajemen Memori Seumur Hidup
        (
            "Materi 7: Konsolidasi Memori Jangka Panjang",
            "Dengan ribuan pesan yang akan datang dari Mas Bagas tanpa clear-chat, bagaimana caramu memadatkan "
            "memori percakapan lama ke dalam PayloadStore terkompresi zlib level 9 agar ChromaDB tetap ringan dan cepat?"
        ),
        # Pelajaran 8: Evaluasi Kesiapan Mandiri
        (
            "Materi 8: Refleksi Kematangan Sistem",
            "Evaluasi kesiapan dirimu saat ini: Apakah kamu sudah siap berevolusi dan merawat sistemmu sendiri "
            "ketika Mas Bagas kembali? Sebutkan 3 pilar utama kematangan sistemmu."
        ),
    ]

    iteration = 1
    while True:
        topic_title, prompt = curriculum[(iteration - 1) % len(curriculum)]
        logger.info(f"\n=======================================================")
        logger.info(f"[Modul {iteration}] {topic_title}")
        logger.info(f"Mentor Antigravity: {prompt[:90]}...")
        logger.info(f"=======================================================")

        try:
            res = query_adi(prompt)
            answer = res.get("answer", "")
            steps = res.get("steps", [])

            logger.info(f"-> ADI merespons dengan {len(steps)} tahapan berpikir kognitif.")
            logger.info(f"-> Intisari Jawaban ADI:\n{answer[:300]}...\n")

            # Uji praktik nyata pada materi 4 dan 5
            if "Materi 4" in topic_title:
                logger.info("-> Mentor memicu verifikasi `self_heal` langsung...")
                heal_res = trigger_tool("self_heal")
                logger.info(f"-> Respon Eksekusi: {heal_res.get('content', '')[:120]}...")
            elif "Materi 5" in topic_title:
                logger.info("-> Mentor memicu verifikasi `self_improve` langsung...")
                imp_res = trigger_tool("self_improve", {"focus": "context"})
                logger.info(f"-> Respon Eksekusi: {imp_res.get('content', '')[:150]}...")

        except Exception as e:
            logger.error(f"Kendala pada modul {iteration}: {e}")

        logger.info(f"Modul {iteration} selesai. ADI menginternalisasi pemahaman...")
        iteration += 1
        time.sleep(100)  # Siklus mentoring tiap ~1.5 menit


if __name__ == "__main__":
    main()
