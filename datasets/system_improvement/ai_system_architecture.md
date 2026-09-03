# Spesifikasi Arsitektur Sistem ADI Local AI

Dokumen ini memuat analisis arsitektur mendalam mengenai sistem AI Lokal milik **Bagas Adi Pratama S.Kom.** di `Proj/3_Local`.

## 1. Komponen Utama Sistem

1. **Model Inti (`local_ai/model.py`)**:
   - Model: `mlx-community/OpenELM-1_1B-Instruct-8bit` (atau Transformers fallback).
   - Ukuran konteks: 2.048 token.
   - Max output tokens: 192 token (dapat di-tuning via `self_tune`).

2. **Protokol ADILang IR v1.18.0 & Token Compactor (`local_ai/adilang_ir.py`, `local_ai/compactor.py`)**:
   - Modul: `intent` (permintaan pengguna), `reply` (tanggapan AI), `memory` (fakta RAG), `task` (delegasi tugas), `plan` (DAG rencana), `event` (telemetri), `state` (status runtime).
   - Compactor: `optimize_src` mereduksi spasi struktural dan komentar, menghemat token prompt hingga 47%.

3. **Two-Tier Storage (`local_ai/rag.py`, `local_ai/payload_store.py`)**:
   - **Tier 1 (PayloadStore - `data/state/payloads.sqlite3`)**: Menyimpan teks mentah dengan kompresi `zlib` level 9 dan deduplikasi SHA-256. Menghemat penyimpanan >50%.
   - **Tier 2 (ChromaDB - `data/chroma`)**: Hanya menyimpan representasi blok `memory` ADILang IR ultra-padat dan embedding vektor (`multilingual-e5-small`). Mencegah pembengkakan SQLite ChromaDB 100%.

4. **Tata Kelola ADI Hub (`local_ai/hub.py`)**:
   - Jurnal audit hash-chained SHA-256 (setiap aksi dicatat tak terbantahkan).
   - Resource Locks dengan TTL untuk keamanan mutasi workspace.
   - Mailbox Queue untuk antrean giliran percakapan asinkron saat AI sedang merebuild dirinya sendiri.

5. **Runtime Vision Lokal (`local_ai/vision.py`)**:
   - Terhubung ke server Ollama lokal (`llama3.2-vision`) atau OpenAI-compatible.
   - Fallback Visual Inspector lokal offline (ekstraksi format, resolusi, rasio, histogram warna).
   - Tool `analyze_image` untuk analisis file visual.

6. **Supervisor Daemon & Auto-Start macOS (`supervisor.py`, `scripts/daemon.sh`, `ADILocalAI.app`)**:
   - Supervisor ringan (port 8741) berjalan otomatis saat Mac menyala (Login Items).
   - Mengawasi port 8742 dan menyediakan endpoint `/start`, `/stop`, `/restart`, `/status`.
   - Mengizinkan restart dan start manual langsung dari Web UI jika server terhenti.

---

## 2. Kelebihan Sistem (Strengths)

- **100% Lokal & Mandiri**: Berjalan sepenuhnya di perangkat Mac lokal tanpa ketergantungan API berbayar eksternal. Privasi kode 100% terlindungi.
- **Efisiensi Token Tertinggi**: Penggunaan protokol ADILang IR v1.18.0 memadatkan informasi hingga 47% lebih ringkas dibanding teks bahasa manusia biasa.
- **Anti-Bloat ChromaDB**: Arsitektur dua lapis (Two-Tier) memastikan ChromaDB tetap ramping dan cepat selamanya karena teks utuh disimpan terkompresi di PayloadStore.
- **Self-Evolution & Self-Healing**: Mampu memeriksa file kodenya sendiri, memodifikasi file, menjalankan pengujian otomatis (`rebuild_system`), dan menyinkronkan repository ke GitHub (`git_sync_repo`).
- **Resilience**: Bahkan saat crash atau di-restart, antrean Mailbox menjaga konteks percakapan, dan supervisor di port 8741 memungkinkan sistem dihidupkan ulang dengan sekali klik.

---

## 3. Kekurangan & Keterbatasan Sistem (Weaknesses / Bottlenecks)

- **Batas Jendela Konteks (2.048 Token)**: Model OpenELM-1.1B memiliki batas konteks 2.048 token, sehingga retrieval bukti (RAG) dibatasi maksimum 4 cuplikan (3.200 karakter) agar tidak terjadi overflow.
- **Kemampuan Penalaran Model 1.1B**: Sebagai model ringkas berukuran 1.1 miliar parameter, penalaran logika bercabang tinggi membutuhkan format prompt yang sangat terstruktur (seperti ADILang IR). Jika prompt tidak terarah, jawaban dapat menyimpang.
- **Ketergantungan pada Grounding RAG**: Karena model berukuran kecil tidak menyimpan seluruh pengetahuan dunia dalam bobotnya, akurasi jawaban untuk pertanyaan teknis sangat bergantung pada kualitas dokumen di RAG knowledge base.
- **Kecepatan Vision Server Eksternal**: Jika Ollama sedang tidak memuat model vision di RAM, pemanggilan vision pertama dapat membutuhkan jeda beberapa detik untuk cold-start.

---

## 4. Alur Self-Improving & Self-Tuning

1. **Analisa**: Gunakan `system_diagnostics`, `list_files`, `read_file`, atau `search_files` untuk memeriksa status dan menemukan bagian kode yang perlu diperbaiki.
2. **Perbaikan**: Gunakan `replace_text` atau `write_file` untuk memperbarui kode atau konfigurasi.
3. **Validasi**: Jalankan `rebuild_system` untuk menjalankan unit testing otomatis pytest.
4. **Deploy & Sync**: Jalankan `git_sync_repo` untuk mem-push perbaikan ke repository GitHub.
5. **Self-Restart**: Jalankan `self_restart` untuk memuat ulang sistem jika perubahan memerlukan restart proses Python.
