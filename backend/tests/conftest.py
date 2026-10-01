import hashlib
import math
import re
from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from qdrant_client import QdrantClient

from app.config import settings
from app.main import create_app

SAMPLE_PDF = Path(__file__).parents[2] / "samples" / "sample_services_agreement.pdf"


class FakeLLM:
    """Deterministic stand-in for OpenAI: bag-of-words hashed embeddings and scripted chat replies."""

    def __init__(self):
        self.chat_calls: list[tuple[str, str]] = []
        # Either a fixed reply, or a function (system, user) -> reply for multi-stage flows.
        self.next_reply: dict | Callable[[str, str], dict] = {}

    def embed(self, texts):
        vectors = []
        for text in texts:
            vec = [0.0] * settings.embedding_dim
            for word in re.findall(r"[a-z0-9]+", text.lower()):
                vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % settings.embedding_dim] += 1.0
            norm = math.sqrt(sum(v * v for v in vec)) or 1.0
            vectors.append([v / norm for v in vec])
        return vectors

    def chat_json(self, system, user):
        self.chat_calls.append((system, user))
        return self.next_reply(system, user) if callable(self.next_reply) else self.next_reply


@pytest.fixture
def llm():
    return FakeLLM()


@pytest.fixture
def reviewers():
    return [("reviewer-a", FakeLLM()), ("reviewer-b", FakeLLM())]


@pytest.fixture
def client(llm, reviewers, tmp_path):
    app = create_app(llm=llm, qdrant=QdrantClient(":memory:"), reviewers=reviewers, data_dir=str(tmp_path))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def uploaded(client):
    with SAMPLE_PDF.open("rb") as f:
        resp = client.post("/api/documents", files={"file": (SAMPLE_PDF.name, f, "application/pdf")})
    assert resp.status_code == 200, resp.text
    return resp.json()
