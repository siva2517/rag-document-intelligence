import json
from pathlib import Path

from qdrant_client import QdrantClient

from app.config import settings
from app.store import VectorStore
from eval.run_eval import evaluate
from tests.conftest import SAMPLE_PDF, FakeLLM

DATASET = Path(__file__).parents[1] / "eval" / "dataset.jsonl"


def test_evaluate_on_sample_dataset():
    llm = FakeLLM()
    llm.next_reply = {"answer": "stub", "citations": [1], "faithful": 1, "correct": 1}
    dataset = [json.loads(line) for line in DATASET.read_text().splitlines() if line.strip()]
    store = VectorStore(QdrantClient(":memory:"), "eval", settings.embedding_dim)

    report = evaluate([SAMPLE_PDF], dataset, llm, store, top_k=3)

    summary = report["summary"]
    assert summary["questions"] == len(dataset)
    # Even bag-of-words retrieval should find the right page for most labelled questions.
    assert summary["hit@3"] >= 0.8
    assert 0 < summary["mrr"] <= 1
    refusal = next(r for r in report["rows"] if not r["expected_pages"])
    assert refusal["hit"] is None and refusal["reciprocal_rank"] is None
