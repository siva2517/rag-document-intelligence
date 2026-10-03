"""API. Pipeline per document, each stage persisted to the artifact store:

upload -> insights -> requirements -> council review -> highlight   (+ ground-truth comparison at any point)
"""

import uuid
from contextlib import asynccontextmanager
from uuid import UUID

from fastapi import FastAPI, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from qdrant_client import QdrantClient

from app import compare, council, highlight, rag
from app.artifacts import ArtifactStore
from app.config import settings
from app.ingest import chunk_pages, read_pdf_pages
from app.llm import LLM, OpenAILLM
from app.store import VectorStore

DOWNLOADABLE = {"original.pdf", "highlighted.pdf"}


class AskRequest(BaseModel):
    question: str
    doc_id: str | None = None


def create_app(
    llm: LLM | None = None,
    qdrant: QdrantClient | None = None,
    reviewers: list[tuple[str, LLM]] | None = None,
    data_dir: str | None = None,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.llm = llm or OpenAILLM(settings.openai_api_key, settings.chat_model, settings.embedding_model)
        client = qdrant or QdrantClient(url=settings.qdrant_url)
        app.state.store = VectorStore(client, settings.collection, settings.embedding_dim)
        app.state.reviewers = reviewers or [
            (m.strip(), OpenAILLM(settings.openai_api_key, m.strip(), settings.embedding_model))
            for m in settings.council_models.split(",")
            if m.strip()
        ]
        app.state.artifacts = ArtifactStore(data_dir or settings.data_dir)
        yield

    app = FastAPI(title="RAG Document Intelligence", lifespan=lifespan)

    def require(doc_id: str, name: str, hint: str):
        data = app.state.artifacts.load_json(doc_id, name)
        if data is None:
            raise HTTPException(409, f"Run {hint} first.")
        return data

    def current_requirements(doc_id: str) -> list[dict]:
        """Council-reviewed requirements (minus rejected) when available, otherwise the raw extraction."""
        reviewed = app.state.artifacts.load_json(doc_id, "review.json")
        if reviewed is not None:
            return [r for r in reviewed if r["status"] != "rejected"]
        return require(doc_id, "requirements.json", "requirement extraction")

    @app.get("/api/health")
    def health():
        return {"status": "ok"}

    @app.post("/api/documents")
    async def upload(file: UploadFile):
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(400, "Only PDF files are supported.")
        data = await file.read()
        pages = read_pdf_pages(data)
        doc_id = str(uuid.uuid4())
        chunks = chunk_pages(pages, doc_id, file.filename, settings.chunk_size, settings.chunk_overlap)
        if not chunks:
            raise HTTPException(422, "No extractable text found (scanned PDFs need OCR first).")
        app.state.store.upsert(chunks, app.state.llm.embed([c.text for c in chunks]))
        app.state.artifacts.save_bytes(doc_id, "original.pdf", data)
        app.state.artifacts.save_json(doc_id, "pages.json", pages)
        return {"doc_id": doc_id, "name": file.filename, "pages": len(pages), "chunks": len(chunks)}

    @app.get("/api/documents")
    def list_documents():
        return app.state.store.list_documents()

    @app.delete("/api/documents/{doc_id}")
    def delete_document(doc_id: UUID):
        app.state.store.delete_document(str(doc_id))
        app.state.artifacts.delete(str(doc_id))
        return {"deleted": str(doc_id)}

    @app.post("/api/ask")
    def ask(req: AskRequest):
        return rag.answer(req.question, app.state.llm, app.state.store, settings.top_k, req.doc_id)

    @app.post("/api/documents/{doc_id}/insights")
    def insights(doc_id: UUID):
        result = rag.insights(str(doc_id), app.state.llm, app.state.store)
        app.state.artifacts.save_json(str(doc_id), "insights.json", result)
        return result

    @app.post("/api/documents/{doc_id}/requirements")
    def requirements(doc_id: UUID):
        reqs = rag.extract_requirements(str(doc_id), app.state.llm, app.state.store)
        app.state.artifacts.save_json(str(doc_id), "requirements.json", reqs)
        return {"doc_id": str(doc_id), "requirements": reqs}

    @app.post("/api/documents/{doc_id}/review")
    def review(doc_id: UUID):
        reqs = require(str(doc_id), "requirements.json", "requirement extraction")
        pages = require(str(doc_id), "pages.json", "upload")
        reviewed = council.review(reqs, pages, app.state.reviewers)
        app.state.artifacts.save_json(str(doc_id), "review.json", reviewed)
        return {"doc_id": str(doc_id), "reviewers": [n for n, _ in app.state.reviewers], "requirements": reviewed}

    @app.post("/api/documents/{doc_id}/highlight")
    def highlight_pdf(doc_id: UUID):
        artifacts = app.state.artifacts
        original = artifacts.path(str(doc_id), "original.pdf")
        if not original.exists():
            raise HTTPException(404, "Original PDF not found.")
        pdf, located = highlight.highlight(original.read_bytes(), current_requirements(str(doc_id)))
        artifacts.save_bytes(str(doc_id), "highlighted.pdf", pdf)
        artifacts.save_json(str(doc_id), "highlight.json", located)
        return {"located": sum(r["found"] for r in located), "total": len(located), "requirements": located}

    @app.post("/api/documents/{doc_id}/ground-truth")
    async def ground_truth(doc_id: UUID, file: UploadFile):
        try:
            truth = compare.load_ground_truth(file.filename or "", await file.read())
        except ValueError as e:
            raise HTTPException(400, str(e)) from e
        if not truth:
            raise HTTPException(422, "No requirements found in the ground-truth file.")
        result = compare.compare(current_requirements(str(doc_id)), truth, app.state.llm, settings.match_threshold)
        app.state.artifacts.save_json(str(doc_id), "comparison.json", result)
        return result

    @app.post("/api/documents/{doc_id}/pipeline")
    def pipeline(doc_id: UUID):
        """Run every automatic stage in order; ground truth stays a separate upload."""
        insights(doc_id)
        requirements(doc_id)
        review(doc_id)
        highlight_pdf(doc_id)
        return state(doc_id)

    @app.get("/api/documents/{doc_id}/state")
    def state(doc_id: UUID):
        """Everything produced so far for a document, so the UI can restore a previous run."""
        load = lambda name: app.state.artifacts.load_json(str(doc_id), name)  # noqa: E731
        return {
            "manifest": app.state.artifacts.manifest(str(doc_id)),
            "insights": load("insights.json"),
            "requirements": load("requirements.json"),
            "review": load("review.json"),
            "highlight": load("highlight.json"),
            "comparison": load("comparison.json"),
        }

    @app.get("/api/documents/{doc_id}/files/{name}")
    def download(doc_id: UUID, name: str):
        path = app.state.artifacts.path(str(doc_id), name)
        if name not in DOWNLOADABLE or not path.exists():
            raise HTTPException(404, "File not found.")
        return FileResponse(path, media_type="application/pdf", filename=name)

    return app


app = create_app()
