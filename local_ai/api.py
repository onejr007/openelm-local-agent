from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from .agent import LocalAgent
from .config import get_settings
from .history import ChatHistoryStore
from .hub import LocalHub
from .model import OpenELMRuntime
from .projects import ProjectRegistry
from .rag import RAGStore
from .tools import SafeTools
from .vision import VisionRuntime

settings = get_settings()
hub = LocalHub(settings.state_dir)
history_store = ChatHistoryStore(settings.state_dir)
vision = VisionRuntime(base_url=settings.vision_base_url, model=settings.vision_model)
registry = ProjectRegistry(settings)
rag = RAGStore(settings)
runtime = OpenELMRuntime(settings)
tools = SafeTools(settings=settings, vision=vision, hub=hub, rag=rag)
agent = LocalAgent(settings, registry, rag, runtime, tools, hub=hub, history_store=history_store)

WEB_DIR = Path(__file__).resolve().parent / "web"


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.auto_load_model:
        runtime.load()
    yield


app = FastAPI(
    title="ADI Local AI Developer Agent",
    version="1.18.0",
    description="Autonomous Local AI with ADILang IR Protocol v1.18.0, Two-Tier ChromaDB Compression, and Vision.",
    lifespan=lifespan,
)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    index_file = WEB_DIR / "index.html"
    if index_file.exists():
        return index_file.read_text(encoding="utf-8")
    return "<h1>ADI Local AI Agent Active</h1><p>Open /docs for API documentation.</p>"


class HistoryItem(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=12000)


class ChatRequest(BaseModel):
    project_id: str
    message: str = Field(min_length=1, max_length=24000)
    history: list[HistoryItem] = Field(default_factory=list, max_length=20)
    remember: bool = False
    allow_mutations: bool = False


class IngestRequest(BaseModel):
    project_id: str
    path: str
    scope: Literal["project", "shared"] = "project"


class SearchRequest(BaseModel):
    project_id: str
    query: str = Field(min_length=1)
    top_k: int = Field(default=4, ge=1, le=20)


class MemoryRequest(BaseModel):
    project_id: str
    text: str = Field(min_length=1, max_length=24000)
    scope: Literal["project", "shared"] = "project"
    source: str = "manual"


class ToolRequest(BaseModel):
    project_id: str
    name: str
    arguments: dict = Field(default_factory=dict)
    confirmed: bool = False


class ProjectCreateRequest(BaseModel):
    id: str
    name: str = Field(min_length=2, max_length=120)
    goal: str = Field(min_length=5, max_length=2000)
    system_prompt: str = Field(min_length=5, max_length=6000)
    workspace: str | None = None
    allow_write: bool = False
    allowed_domains: list[str] = Field(default_factory=list, max_length=50)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "model_id": settings.model_id,
        "model_loaded": runtime.loaded,
        "knowledge_chunks": rag.knowledge.count(),
        "memories": rag.memory.count(),
        "hub_integrity": hub.verify_journal(),
        "vision_available": vision.status().get("available", False),
    }


@app.get("/storage/stats")
def storage_stats() -> dict:
    return rag.stats()


@app.get("/hub/status")
def hub_status() -> dict:
    return hub.status()


@app.get("/hub/journal")
def hub_journal(limit: int = 100) -> list[dict]:
    return hub.journal(limit=limit)


@app.get("/vision/status")
def vision_status() -> dict:
    return vision.status()


@app.post("/vision/analyze")
async def vision_analyze(file: UploadFile = File(...), prompt: str = Form("")) -> dict:
    try:
        content = await file.read()
        analysis = vision.analyze_bytes(content, prompt=prompt)
        hub.record("vision_analyze", file.filename or "uploaded_image")
        return {"filename": file.filename, "analysis": analysis}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/projects")
def projects() -> list[dict]:
    return [project.public() for project in registry.list()]


@app.post("/projects", status_code=201)
def create_project(request: ProjectCreateRequest) -> dict:
    try:
        return registry.create(request.model_dump(exclude_none=True)).public()
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/ingest")
def ingest(request: IngestRequest) -> dict:
    try:
        project = registry.get(request.project_id)
        source = Path(request.path).expanduser().resolve()
        allowed_roots = [project.workspace.resolve(), settings.root_dir.resolve()]
        if not source.exists():
            raise ValueError("Dataset path does not exist")
        if not any(source.is_relative_to(root) for root in allowed_roots):
            raise PermissionError("Dataset must be inside this application or project workspace")
        res = rag.ingest(source, request.project_id, request.scope)
        hub.record("ingest", f"{request.project_id}:{request.path}")
        return res
    except (KeyError, ValueError, PermissionError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/search")
def search(request: SearchRequest) -> dict:
    try:
        registry.get(request.project_id)
        results = rag.search(request.query, request.project_id, request.top_k)
        return {"results": [item.__dict__ for item in results]}
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/memory")
def memory(request: MemoryRequest) -> dict:
    try:
        registry.get(request.project_id)
        memory_id = rag.remember(
            request.text, request.project_id, scope=request.scope, source=request.source
        )
        hub.record("memory_added", f"{request.project_id}:{memory_id}")
        return {"id": memory_id}
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/tools/execute")
def execute_tool(request: ToolRequest) -> dict:
    try:
        project = registry.get(request.project_id)
        result = tools.execute(project, request.name, request.arguments, confirmed=request.confirmed)
        return result.__dict__
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/chat")
def chat(request: ChatRequest) -> dict:
    try:
        reply = agent.chat(
            request.project_id,
            request.message,
            [item.model_dump() for item in request.history],
            remember=request.remember,
            allow_mutations=request.allow_mutations,
        )
        return {
            "answer": reply.answer,
            "grounded": reply.grounded,
            "grounding_status": (
                "cited_evidence" if reply.grounded else
                "evidence_found_but_answer_not_verified" if reply.evidence else
                "no_relevant_evidence"
            ),
            "retrieval_confidence": (
                round(max(item.relevance for item in reply.evidence), 4) if reply.evidence else 0.0
            ),
            "sources": [
                {**item.__dict__, "citation": item.citation(index)}
                for index, item in enumerate(reply.evidence, 1)
            ],
            "pending_tool": reply.pending_tool,
            "ir_reply": reply.ir_reply,
            "steps": reply.steps,
        }
    except (KeyError, ValueError, RuntimeError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/chat/history")
def get_chat_history(
    project_id: str = "developer_master",
    limit: int = 40,
    before_ts: float | None = None,
) -> list[dict]:
    try:
        registry.get(project_id)
        return history_store.list(project_id, limit=limit, before_ts=before_ts)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/chat/search")
def search_chat_history(
    project_id: str = "developer_master",
    query: str = "",
    limit: int = 20,
) -> list[dict]:
    try:
        registry.get(project_id)
        if not query.strip():
            return []
        return history_store.search(project_id, query=query.strip(), limit=limit)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/chat/consolidate")
def consolidate_chat_memory(project_id: str = "developer_master") -> dict:
    try:
        registry.get(project_id)
        created = history_store.consolidate_unprocessed(project_id, rag)
        return {"episodes_created": created, "total_messages": history_store.count(project_id)}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.delete("/chat/history")
def delete_chat_history(project_id: str = "developer_master") -> dict:
    try:
        registry.get(project_id)
        cleared = history_store.clear(project_id)
        return {"cleared": cleared}
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


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
                yield f"event: step\ndata: {json.dumps(step)}\n\n"
            words = reply.answer.split(" ")
            for i in range(0, len(words), 3):
                chunk = " ".join(words[i:i+3]) + " "
                yield f"event: token\ndata: {json.dumps({'chunk': chunk})}\n\n"
            final_data = {
                "answer": reply.answer,
                "sources": [{**item.__dict__, "citation": item.citation(idx)} for idx, item in enumerate(reply.evidence, 1)],
                "ir_reply": reply.ir_reply,
            }
            yield f"event: done\ndata: {json.dumps(final_data)}\n\n"

        return StreamingResponse(event_generator(), media_type="text/event-stream")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
