import fcntl
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import chromadb
from chromadb.api.types import Documents, EmbeddingFunction, Embeddings
from sentence_transformers import SentenceTransformer

from .adilang_ir import encode_memory_chunk
from .config import Settings
from .documents import chunk_document, iter_dataset_files, load_document
from .payload_store import PayloadStore


class E5EmbeddingFunction(EmbeddingFunction[Documents]):
    def __init__(self, model_name: str, device: str = "cpu", offline: bool = False):
        self.model_name = model_name
        self.device = device
        self.offline = offline
        self._model: SentenceTransformer | None = None

    @property
    def model(self) -> SentenceTransformer:
        if self._model is None:
            self._model = SentenceTransformer(
                self.model_name, device=self.device, local_files_only=self.offline
            )
        return self._model

    def __call__(self, input: Documents) -> Embeddings:
        texts = [f"passage: {text}" for text in input]
        return self.model.encode(texts, normalize_embeddings=True).tolist()

    def embed_query(self, input: Documents) -> Embeddings:
        texts = [f"query: {text}" for text in input]
        return self.model.encode(texts, normalize_embeddings=True).tolist()


@dataclass(frozen=True)
class Evidence:
    id: str
    text: str
    source: str
    title: str
    relevance: float
    kind: str
    ir_text: str = ""

    def citation(self, number: int) -> str:
        return f"[{number}] {self.title} — {self.source}"


class RAGStore:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.payloads = PayloadStore(settings.state_dir, encrypt=False)
        lock_path = settings.state_dir / "chroma-init.lock"
        with lock_path.open("w") as init_lock:
            fcntl.flock(init_lock.fileno(), fcntl.LOCK_EX)
            self.client = chromadb.PersistentClient(path=str(settings.chroma_dir))
            embedding = E5EmbeddingFunction(
                settings.embedding_model, settings.embedding_device, settings.offline_mode
            )
            self.knowledge = self.client.get_or_create_collection(
                "knowledge", embedding_function=embedding, metadata={"hnsw:space": "cosine"}
            )
            self.memory = self.client.get_or_create_collection(
                "memory", embedding_function=embedding, metadata={"hnsw:space": "cosine"}
            )
            fcntl.flock(init_lock.fileno(), fcntl.LOCK_UN)

    def ingest(self, path: Path, project_id: str, scope: str = "project") -> dict[str, int]:
        if scope not in {"project", "shared"}:
            raise ValueError("scope must be project or shared")
        file_count = chunk_count = 0
        for file_path in iter_dataset_files(path):
            doc = load_document(file_path)
            chunks = chunk_document(doc)
            if not chunks:
                continue

            ids = []
            docs = []
            metadatas = []
            for chunk in chunks:
                payload_id, _ = self.payloads.put(chunk.text)
                # Store ultra-compact AI-only ADILang IR representation in ChromaDB
                # saving massive database bloating while keeping semantic vector intact
                ir_doc = encode_memory_chunk(
                    chunk.id,
                    chunk.text[:300],
                    source=chunk.source,
                    topic=chunk.title,
                    compact=True,
                )
                ids.append(chunk.id)
                docs.append(ir_doc)
                metadatas.append({
                    "payload_id": payload_id,
                    "project_id": project_id,
                    "scope": scope,
                    "source": chunk.source,
                    "title": chunk.title,
                    "chunk": chunk.index,
                    "kind": "knowledge",
                    "compressed": True,
                    "ingested_at": int(time.time()),
                })

            self.knowledge.upsert(ids=ids, documents=docs, metadatas=metadatas)
            file_count += 1
            chunk_count += len(chunks)
        return {"files": file_count, "chunks": chunk_count}

    def remember(
        self, text: str, project_id: str, *, scope: str = "project", source: str = "conversation"
    ) -> str:
        if scope not in {"project", "shared"}:
            raise ValueError("scope must be project or shared")
        memory_id = uuid.uuid4().hex
        payload_id, _ = self.payloads.put(text)
        ir_doc = encode_memory_chunk(
            memory_id,
            text[:300],
            source=source,
            topic="Long-term memory",
            compact=True,
        )
        self.memory.add(
            ids=[memory_id],
            documents=[ir_doc],
            metadatas=[{
                "payload_id": payload_id,
                "project_id": project_id,
                "scope": scope,
                "source": source,
                "title": "Long-term memory",
                "kind": "memory",
                "compressed": True,
                "ingested_at": int(time.time()),
            }],
        )
        return memory_id

    def search(self, query: str, project_id: str, top_k: int | None = None) -> list[Evidence]:
        limit = top_k or self.settings.rag_top_k
        where: dict[str, Any] = {
            "$or": [
                {"project_id": {"$eq": project_id}},
                {"scope": {"$eq": "shared"}},
            ]
        }
        evidence: list[Evidence] = []
        for collection in (self.knowledge, self.memory):
            if collection.count() == 0:
                continue
            result = collection.query(
                query_texts=[query], n_results=min(limit, collection.count()), where=where
            )
            for item_id, ir_text, meta, distance in zip(
                result["ids"][0],
                result["documents"][0],
                result["metadatas"][0],
                result["distances"][0],
            ):
                relevance = max(0.0, 1.0 - float(distance))
                if relevance >= self.settings.min_relevance:
                    # Decompress full text from PayloadStore if available
                    payload_id = meta.get("payload_id")
                    if payload_id:
                        try:
                            full_text = self.payloads.get(payload_id)
                        except KeyError:
                            full_text = ir_text
                    else:
                        full_text = ir_text

                    evidence.append(Evidence(
                        id=item_id,
                        text=full_text,
                        source=str(meta.get("source", "unknown")),
                        title=str(meta.get("title", "Untitled")),
                        relevance=relevance,
                        kind=str(meta.get("kind", "knowledge")),
                        ir_text=ir_text,
                    ))
        evidence.sort(key=lambda item: item.relevance, reverse=True)
        return evidence[:limit]

    def stats(self) -> dict[str, Any]:
        return {
            "payload_store": self.payloads.stats(),
            "chroma_chunks": self.knowledge.count() + self.memory.count(),
        }
