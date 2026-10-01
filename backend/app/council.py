"""LLM council: several models independently review extracted requirements, then flagged ones are corrected.

Decision per requirement (strict majority):
  majority "reject" -> rejected   (not a real requirement / unsupported by the source)
  majority "accept" -> accepted   (kept as-is)
  otherwise         -> revised    (the first council model rewrites it using the reviewers' issues;
                                   if the rewrite is identical to the original it is marked accepted)
"""

from collections import Counter

from app.llm import LLM

REVIEW_PROMPT = """You are one reviewer on a council auditing requirements extracted from a business document.
You receive the source pages and a list of requirements, each with an id and the page it came from. Judge each one:
- "accept": a genuine requirement, faithful to the source, complete, stating a single obligation.
- "revise": a genuine requirement, but its own obligation is misstated, or it drops a condition, party, or number
  that applies to that obligation, or it merges several obligations.
- "reject": not a requirement (definition, background, recital) or not supported by the source.
Requirements are deliberately atomic: a source sentence with several obligations is split into one requirement each.
Example: "Data must be encrypted at rest using AES-256 and in transit using TLS 1.2." correctly becomes
"Data must be encrypted at rest using AES-256." and "Data must be encrypted in transit using TLS 1.2." - accept both.
Never ask for split requirements to be combined; omitting a sibling obligation is not an issue.
Respond as JSON: {"reviews": [{"id": string, "verdict": "accept" | "revise" | "reject", "issue": string}]}
"issue" briefly states the problem; use "" when accepting."""

CORRECT_PROMPT = """You fix a requirement extracted from a business document using reviewer feedback.
Rewrite it so it is faithful to the source (copy the source wording verbatim where possible), complete,
and states a single obligation. Never merge in other obligations from the same source sentence (they are separate
requirements), and never add parties, amounts, conditions, or other facts that the source does not state;
if the requirement is already faithful, return it unchanged. Respond as JSON: {"text": string}"""

STATUS = {"accept": "accepted", "revise": "revised", "reject": "rejected"}


def decide(votes: list[dict]) -> str:
    if not votes:
        return "unreviewed"
    counts = Counter(v["verdict"] for v in votes)
    for verdict in ("reject", "accept"):
        if counts[verdict] * 2 > len(votes):
            return STATUS[verdict]
    return "revised"


def review(
    requirements: list[dict], pages: list[str], reviewers: list[tuple[str, LLM]], batch_size: int = 15
) -> list[dict]:
    page_text = lambda p: pages[p - 1] if 1 <= p <= len(pages) else ""  # noqa: E731
    votes: dict[str, list[dict]] = {r["id"]: [] for r in requirements}

    for start in range(0, len(requirements), batch_size):
        batch = requirements[start : start + batch_size]
        source = "\n\n".join(f"--- Page {p} ---\n{page_text(p)}" for p in sorted({r["page"] for r in batch}))
        items = "\n".join(f"{r['id']} (page {r['page']}): {r['text']}" for r in batch)
        for name, llm in reviewers:
            out = llm.chat_json(REVIEW_PROMPT, f"Source pages:\n{source}\n\nRequirements:\n{items}")
            for v in out.get("reviews", []):
                if v.get("id") in votes and v.get("verdict") in STATUS:
                    votes[v["id"]].append({"model": name, "verdict": v["verdict"], "issue": v.get("issue", "")})

    corrector = reviewers[0][1]
    results = []
    for req in requirements:
        status = decide(votes[req["id"]])
        text = req["text"]
        if status == "revised":
            issues = "; ".join(v["issue"] for v in votes[req["id"]] if v["verdict"] != "accept" and v["issue"])
            out = corrector.chat_json(CORRECT_PROMPT, (
                f"Source page {req['page']}:\n{page_text(req['page'])}\n\n"
                f"Requirement: {req['text']}\n\nReviewer issues: {issues or 'reviewers disagreed'}"
            ))
            text = (out.get("text") or "").strip() or text
            if text == req["text"]:
                status = "accepted"  # the corrector found nothing to change
        key = " ".join(text.lower().split())
        duplicate_of = next((r["id"] for r in results if r["status"] != "rejected" and r["_key"] == key), None)
        if duplicate_of and status != "rejected":
            status = "rejected"  # corrections can converge on an existing requirement
            votes[req["id"]].append({"model": "dedupe", "verdict": "reject", "issue": f"duplicate of {duplicate_of}"})
        results.append({**req, "text": text, "original_text": req["text"], "status": status,
                        "votes": votes[req["id"]], "_key": key})
    return [{k: v for k, v in r.items() if k != "_key"} for r in results]
