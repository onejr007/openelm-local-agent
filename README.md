# OpenELM Local Multi-Project Agent

Local AI berbasis OpenELM 1.1B untuk Apple Silicon, dengan satu ChromaDB persisten,
isolasi konteks per project, long-term memory, RAG dengan sumber, FastAPI, dan tool
file/browser yang dibatasi policy.

## Yang sudah disiapkan

- OpenELM 1.1B Instruct 8-bit melalui MLX untuk menjaga kualitas pada RAM 24 GB.
- Embedding multilingual E5 untuk Bahasa Indonesia dan bahasa lain.
- ChromaDB persisten di `data/chroma`.
- Knowledge dan memory dipisahkan, tetapi dicari lewat satu lapisan retrieval.
- Project-specific memory plus optional shared memory.
- Ingestion MD, TXT, PDF, JSON, JSONL, dan CSV.
- Tool `list_files`, `read_file`, `search_files`, `write_file`, `replace_text`, dan
  `fetch_url`.
- Operasi tulis/edit memerlukan `confirmed=true` atau `allow_mutations=true`.
- URL private/local diblokir untuk mengurangi risiko SSRF.

## Menjalankan

Environment proyek sudah terisolasi di `.venv`.

```bash
./run.sh
```

Buka dokumentasi interaktif di <http://127.0.0.1:8742/docs> dan status service di
<http://127.0.0.1:8742/health>.

Model dan embedding diunduh pada penggunaan pertama, lalu berada di cache lokal.

## Ingest dataset

Letakkan dataset pada salah satu folder `datasets/<project>` lalu jalankan:

```bash
curl -X POST http://127.0.0.1:8742/ingest \
  -H 'content-type: application/json' \
  -d '{"project_id":"video_prompt","path":"datasets/video_prompt","scope":"project"}'
```

Gunakan `scope: "shared"` hanya untuk data yang memang boleh tersedia pada semua
project. Secara default data tetap terisolasi pada project asal.

## Chat grounded

```bash
curl -X POST http://127.0.0.1:8742/chat \
  -H 'content-type: application/json' \
  -d '{"project_id":"video_prompt","message":"Buat prompt video berdasarkan dataset saya"}'
```

Response berisi `answer`, status `grounded`, daftar `sources`, dan `pending_tool` jika
model mengusulkan operasi yang memerlukan konfirmasi.

## Long-term memory

Memory tidak otomatis disimpan kecuali request chat memakai `remember: true`. Untuk
menyimpan fakta yang telah diverifikasi secara eksplisit:

```bash
curl -X POST http://127.0.0.1:8742/memory \
  -H 'content-type: application/json' \
  -d '{"project_id":"daily_chat","text":"Pengguna memilih jawaban ringkas dalam Bahasa Indonesia","scope":"project"}'
```

Hindari memasukkan password, API key, private key, atau data pribadi yang tidak
diperlukan.

## Project

Konfigurasi berada di `projects/*.json`:

- `video_prompt`: prompt engineering untuk Higgsfield.
- `daily_chat`: asisten sehari-hari.
- `system_improvement`: audit dan peningkatan sistem ini.

Project baru dibuat dengan menambahkan file JSON dan workspace-nya. `project_id`
menjadi namespace retrieval sehingga pengetahuan satu project tidak otomatis bocor
ke project lain.

## Strategi anti-halusinasi

Sistem menerapkan retrieval threshold, citation, pemisahan fakta/saran, serta aturan
untuk mengakui ketika bukti tidak cukup. Ini mengurangi halusinasi, tetapi tidak dapat
menjamin nol halusinasi. Untuk keputusan penting, hasil tetap harus diverifikasi.

Konteks OpenELM hanya 2.048 token. Karena itu retrieval sengaja mengambil sedikit
chunk paling relevan; menambahkan seluruh database ke prompt justru menurunkan
kualitas. Luas memory berasal dari pencarian semantik atas ChromaDB, bukan dari
memasukkan seluruh isi database sekaligus.

## Pengujian

```bash
.venv/bin/pytest -q
.venv/bin/ruff check local_ai tests
```
