"""Retrieval-augmented answering and requirement extraction."""

from app.llm import LLM
from app.store import VectorStore

ANSWER_PROMPT = """You answer questions about business documents using ONLY the numbered context excerpts provided.
Cite supporting excerpts inline with their number in brackets, e.g. "Invoices are due in 30 days [2]."
If the excerpts do not contain the answer, say "I don't know based on the provided documents." and cite nothing.
Respond as JSON: {"answer": string, "citations": [int]}"""

EXTRACT_PROMPT = """You extract requirements from business documents such as contracts, RFPs, and policies.
A requirement is a statement that a party must, shall, should, will, or may do something, or a condition that must hold.
Use only what is stated in the numbered excerpts. Copy each requirement's wording verbatim from the source.
Each requirement must state exactly one obligation: when a sentence contains several (joined by "and", or listing
separate deadlines or conditions), split it into separate requirements, repeating the subject so each stands alone.
"section" is the nearest clause number or heading the requirement falls under (e.g. "4. Availability"), or "" if none.
Respond as JSON: {"requirements": [{"text": string, "excerpt": int, "section": string,
"category": "functional" | "compliance" | "security" | "reporting" | "financial" | "operational" | "other",
"priority": "must" | "should" | "may"}]}"""

INSIGHTS_PROMPT = """You analyse a business document given as numbered excerpts, each labelled with its page.
Use only what the excerpts state. Every "page" field must be the page of the excerpt the fact came from.
Respond as JSON: {"document_type": string, "summary": string (3-5 sentences),
"parties": [{"name": string, "role": string}],
"key_dates": [{"date": string, "description": string, "page": int}],
"obligations": [{"party": string, "description": string, "page": int}],
"risks": [{"description": string, "page": int}]}"""

# Roughly 60k characters keeps insights within a single, affordable call.
INSIGHTS_CHAR_BUDGET = 60_000


def _format_context(chunks: list[dict]) -> str:
    return "\n\n".join(f"[{i}] ({c['doc_name']}, page {c['page']})\n{c['text']}" for i, c in enumerate(chunks, 1))


def answer(question: str, llm: LLM, store: VectorStore, top_k: int, doc_id: str | None = None) -> dict:
    hits = store.search(llm.embed([question])[0], top_k, doc_id)
    if not hits:
        return {"answer": "No documents have been indexed yet.", "sources": []}
    out = llm.chat_json(ANSWER_PROMPT, f"Context:\n{_format_context(hits)}\n\nQuestion: {question}")
    cited = {int(i) for i in out.get("citations", [])}
    sources = [{**h, "ref": i, "cited": i in cited} for i, h in enumerate(hits, 1)]
    return {"answer": out.get("answer", ""), "sources": sources}


def extract_requirements(doc_id: str, llm: LLM, store: VectorStore, batch_size: int = 8) -> list[dict]:
    chunks = store.chunks_for(doc_id)
    seen: set[str] = set()
    requirements: list[dict] = []
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start : start + batch_size]
        out = llm.chat_json(EXTRACT_PROMPT, _format_context(batch))
        for req in out.get("requirements", []):
            ref = int(req.get("excerpt", 0))
            key = " ".join(req.get("text", "").lower().split())
            # Chunk overlap means the same sentence can be extracted twice.
            if not key or key in seen or not 1 <= ref <= len(batch):
                continue
            seen.add(key)
            requirements.append({
                "id": f"REQ-{len(requirements) + 1:03d}",
                "text": req["text"].strip(),
                "page": batch[ref - 1]["page"],
                "section": req.get("section", ""),
                "category": req.get("category", "other"),
                "priority": req.get("priority", "must"),
            })
    return requirements


def insights(doc_id: str, llm: LLM, store: VectorStore) -> dict:
    chunks, used = [], 0
    for chunk in store.chunks_for(doc_id):
        used += len(chunk["text"])
        if used > INSIGHTS_CHAR_BUDGET:
            break
        chunks.append(chunk)
    return llm.chat_json(INSIGHTS_PROMPT, _format_context(chunks))
