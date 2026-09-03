# ADI (Agent Distributed Intelligence) — Local Engine Architecture

> **Lead Developer & System Architect**: **BAGAS ADI PRATAMA S.Kom. (@onejr007)**  
> **Identitas Sistem**: **ADI Local** (100% Offline, Zero API-Key, Zero External Cloud Dependency)  
> **Lokasi Workspace**: `Proj/3_Local`  
> **Versi Protokol IR**: **ADILang Core v2.0.0** (Standalone Repo: `onejr007/adilang-core`)  
> **Model Bahasa Lokal**: **Apple OpenELM-1.1B-Instruct** (8-bit quantized via MLX / Metal GPU)

---

## 1. Perbedaan Utama: ADI Cloud (`1_local`) vs ADI Local (`3_Local`)

| Fitur | ADI Cloud (`1_local`) | ADI Local (`3_Local`) |
| :--- | :--- | :--- |
| **Konektivitas** | Butuh Internet / Multi-Cloud Failover (Groq, OpenRouter, Mistral, dll.) | **100% Offline & Private** di Mac lokal |
| **API Keys** | Butuh lusinan API Key berbayar/free | **Nol (0) API Key** eksternal diperlukan |
| **Model LLM** | Cloud API (Claude, Llama-3, GPT-4) | **OpenELM-1.1B-Instruct** berjalan lokal di Apple Silicon |
| **Protokol IR** | ADILang v1.18.0 embedded di repo | **ADILang Core v2.0.0** mandiri di repo GitHub terpisah |
| **Storage RAG** | ChromaDB Cloud (rentan pembengkakan) | **Two-Tier Storage** (PayloadStore zlib lv 9 + ChromaDB e5-small) |
| **Lifecycle** | Docker Compose di VPS / Railway | **macOS Login Items + Supervisor Daemon (Port 8741)** |

---

## 2. Kelebihan ADI Local (Strengths)

1. **Kemandirian Mutlak (Zero Cost & 100% Privacy)**: Seluruh data percakapan, kode program, dan analisis tidak pernah meninggalkan perangkat MacBook/Mac lokal Mas Bagas.
2. **Efisiensi Token Maksimal (~47% Reduction)**: Menggunakan ADILang Core v2.0 compactor (`optimize_src`) untuk memangkas token prompt sehingga OpenELM-1.1B dapat membaca konteks lebih luas.
3. **Arsitektur Anti-Bloat Dua Lapis (Two-Tier)**: Dokumen mentah dikompresi `zlib` level 9 di PayloadStore SQLite, sementara ChromaDB hanya menyimpan embedding dan ringkasan kanonik IR.
4. **Lifelong Continuous Memory**: Percakapan tanpa session reset otomatis dikompilasi oleh thread latar belakang menjadi modul memori jangka panjang episodic.
5. **Supervisor & Self-Healing (Port 8741)**: Berjalan otomatis saat boot macOS dan dapat dihidupkan/dimatikan langsung dari Web Chatbox.

---

## 3. Kekurangan Sistem yang Nyata & Jujur (Real Weaknesses & Bottlenecks)

Saat Mas Bagas meminta analisa kekurangan, ADI wajib transparan mengenai keterbatasan berikut:

1. **Batas Konteks 2.048 Token (OpenELM)**:
   - *Masalah*: Jendela konteks OpenELM-1.1B dibatasi 2.048 token, sehingga retrieval bukti harus dibatasi maksimal 4 cuplikan agar prompt tidak overflow.
   - *Solusi & Planning*: Kompresi ADILang IR bertahap, paging selektif, dan self-tuning `max_context_tokens`.
2. **Penalaran Multi-Langkah Model Ringkas (1.1B Parameter)**:
   - *Masalah*: Berbeda dengan model 70B atau Claude 3.5 Sonnet, OpenELM-1.1B memerlukan format instruksi yang sangat presisi agar tidak melenceng atau berhalusinasi saat eksekusi berantai.
   - *Solusi & Planning*: Penggunaan format rencana terstruktur `plan "activity" { steps [...] }` sebelum memanggil tools.
3. **Cold-Start Model Vision Eksternal**:
   - *Masalah*: Jika server Ollama lokal belum memuat model vision di RAM, analisis visual memerlukan jeda beberapa detik pada pemanggilan awal.
   - *Solusi & Planning*: Pre-warm visual inspector lokal offline dan fallback ekstraksi metadata gambar.

---

## 4. Siklus Eksekusi Planning Mandiri (Actionable Planning & Self-Execution)

Ketika Mas Bagas meminta ADI untuk merencanakan dan mengeksekusi perbaikan sistem:
1. **Fase 1: Diagnosa & Inventarisasi**: ADI membaca kondisi runtime via `system_diagnostics` atau `read_file`.
2. **Fase 2: Perumusan Rencana Terstruktur (Plan Formulation)**: ADI menyusun langkah DAG terukur (Langkah 1 s/d N) tanpa berhalusinasi.
3. **Fase 3: Eksekusi Bertahap (Step-by-Step Tool Call)**: ADI mengeksekusi modifikasi file via `replace_text` / `write_file` atau parameter via `self_tune`.
4. **Fase 4: Verifikasi & Rebuild Otomatis**: ADI memanggil `rebuild_system` (menjalankan pytest 14 tests) untuk membuktikan kodenya benar.
5. **Fase 5: Pelaporan & Sinkronisasi Git**: ADI memanggil `git_sync_repo` untuk mem-push perbaikan ke repository GitHub.
