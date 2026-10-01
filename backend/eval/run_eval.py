"""Evaluate retrieval and answer quality against a labelled question set.

Metrics
- hit@k:         an expected page appears among the top-k retrieved chunks
- MRR:           1 / rank of the first chunk from an expected page
- faithfulness:  LLM judge: is every claim in the answer supported by the retrieved context?
- correctness:   LLM judge: does the answer agree with the reference answer?

Questions with no expected pages test refusal: they count toward faithfulness and
correctness but not the retrieval metrics.

Usage (from backend/):
    uv run python -m eval.run_eval --pdf ../samples/sample_services_agreement.pdf
"""

import argparse
import json
import uuid
from pathlib import Path

from qdrant_client import QdrantClient

from app import rag
from app.config import settings
from app.ingest import chunk_pages, read_pdf_pages
from app.llm import LLM, OpenAILLM
from app.store import VectorStore

JUDGE_PROMPT = """You grade a question-answering system. Given the retrieved context, the system's answer,
and a reference answer, return JSON: {"faithful": 0 or 1, "correct": 0 or 1, "reason": string}.
faithful = 1 if every factual claim in the answer is supported by the context (a refusal counts as faithful).
correct  = 1 if the answer agrees with the reference answer in substance."""


def evaluate(pdf_paths: list[Path], dataset: list[dict], llm: LLM, store: VectorStore, top_k: int) -> dict:
    for path in pdf_paths:
        chunks = chunk_pages(read_pdf_pages(path.read_bytes()), str(uuid.uuid4()), path.name,
                             settings.chunk_size, settings.chunk_overlap)
        store.upsert(chunks, llm.embed([c.text for c in chunks]))

    rows = []
    for item in dataset:
        result = rag.answer(item["question"], llm, store, top_k)
        pages = [s["page"] for s in result["sources"]]
        expected = set(item.get("expected_pages", []))
        rank = next((i for i, p in enumerate(pages, 1) if p in expected), None)
        context = "\n\n".join(s["text"] for s in result["sources"])
        verdict = llm.chat_json(JUDGE_PROMPT, (
            f"Question: {item['question']}\n\nContext:\n{context}\n\n"
            f"Answer: {result['answer']}\n\nReference answer: {item.get('reference', '')}"
        ))
        rows.append({
            "question": item["question"],
            "answer": result["answer"],
            "retrieved_pages": pages,
            "expected_pages": sorted(expected),
            "hit": rank is not None if expected else None,
            "reciprocal_rank": (1 / rank if rank else 0.0) if expected else None,
            "faithful": int(verdict.get("faithful", 0)),
            "correct": int(verdict.get("correct", 0)),
            "judge_reason": verdict.get("reason", ""),
        })

    retrieval = [r for r in rows if r["hit"] is not None]
    mean = lambda xs: round(sum(xs) / len(xs), 3) if xs else None  # noqa: E731
    summary = {
        "questions": len(rows),
        f"hit@{top_k}": mean([r["hit"] for r in retrieval]),
        "mrr": mean([r["reciprocal_rank"] for r in retrieval]),
        "faithfulness": mean([r["faithful"] for r in rows]),
        "correctness": mean([r["correct"] for r in rows]),
    }
    return {"summary": summary, "rows": rows}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--pdf", type=Path, nargs="+", required=True)
    parser.add_argument("--dataset", type=Path, default=Path(__file__).parent / "dataset.jsonl")
    parser.add_argument("--top-k", type=int, default=settings.top_k)
    parser.add_argument("--out", type=Path, default=Path("eval_report.json"))
    args = parser.parse_args()

    dataset = [json.loads(line) for line in args.dataset.read_text().splitlines() if line.strip()]
    llm = OpenAILLM(settings.openai_api_key, settings.chat_model, settings.embedding_model)
    # In-memory Qdrant keeps eval runs isolated from the app's collection.
    store = VectorStore(QdrantClient(":memory:"), "eval", settings.embedding_dim)

    report = evaluate(args.pdf, dataset, llm, store, args.top_k)
    args.out.write_text(json.dumps(report, indent=2))

    for row in report["rows"]:
        mark = "PASS" if row["correct"] else "FAIL"
        print(f"[{mark}] {row['question']}\n       {row['answer']}")
    print("\nSummary:", json.dumps(report["summary"], indent=2))
    print(f"Full report written to {args.out}")


if __name__ == "__main__":
    main()
