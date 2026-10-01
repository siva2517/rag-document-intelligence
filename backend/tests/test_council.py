from app.council import CORRECT_PROMPT, decide, review
from tests.conftest import FakeLLM

REQS = [
    {"id": "REQ-001", "text": "Encrypt data at rest.", "page": 3},
    {"id": "REQ-002", "text": "The agreement is effective January 1, 2026.", "page": 1},
    {"id": "REQ-003", "text": "Acknowledge Severity 1 incidents within 15 minutes.", "page": 2},
]
PAGES = ["page one text", "page two text", "page three text"]


def scripted(verdicts: dict[str, str]):
    def reply(system, user):
        if system == CORRECT_PROMPT:
            return {"text": "All Customer data must be encrypted at rest using AES-256."}
        return {"reviews": [{"id": i, "verdict": v, "issue": f"{v} issue" if v != "accept" else ""} for i, v in verdicts.items()]}
    return reply


def test_decide_uses_strict_majority():
    v = lambda *xs: [{"verdict": x} for x in xs]  # noqa: E731
    assert decide(v("accept", "accept")) == "accepted"
    assert decide(v("reject", "reject", "accept")) == "rejected"
    assert decide(v("accept", "reject")) == "revised"  # disagreement gets a correction pass
    assert decide(v("revise", "accept")) == "revised"
    assert decide([]) == "unreviewed"


def test_review_accepts_revises_and_rejects():
    a, b = FakeLLM(), FakeLLM()
    a.next_reply = scripted({"REQ-001": "revise", "REQ-002": "reject", "REQ-003": "accept"})
    b.next_reply = scripted({"REQ-001": "accept", "REQ-002": "reject", "REQ-003": "accept"})

    out = {r["id"]: r for r in review(REQS, PAGES, [("a", a), ("b", b)])}

    assert out["REQ-001"]["status"] == "revised"
    assert out["REQ-001"]["text"] == "All Customer data must be encrypted at rest using AES-256."
    assert out["REQ-001"]["original_text"] == "Encrypt data at rest."
    assert out["REQ-002"]["status"] == "rejected"
    assert out["REQ-003"]["status"] == "accepted"
    assert [v["model"] for v in out["REQ-003"]["votes"]] == ["a", "b"]
    # The corrector sees the source page and the reviewer's issue.
    correction_input = next(u for s, u in a.chat_calls if s == CORRECT_PROMPT)
    assert "page three text" in correction_input and "revise issue" in correction_input


def test_review_ignores_unknown_ids_and_bad_verdicts():
    a = FakeLLM()
    a.next_reply = {"reviews": [{"id": "REQ-999", "verdict": "accept"}, {"id": "REQ-001", "verdict": "maybe"}]}

    out = review(REQS[:1], PAGES, [("a", a)])

    assert out[0]["status"] == "unreviewed" and out[0]["votes"] == []


def test_unchanged_correction_counts_as_accepted():
    a = FakeLLM()
    a.next_reply = lambda s, u: {"text": REQS[0]["text"]} if s == CORRECT_PROMPT else {
        "reviews": [{"id": "REQ-001", "verdict": "revise", "issue": "maybe vague"}]}

    out = review(REQS[:1], PAGES, [("a", a)])

    assert out[0]["status"] == "accepted"


def test_correction_that_duplicates_an_existing_requirement_is_rejected():
    reqs = [{"id": "REQ-001", "text": "Credits are capped at 50%.", "page": 2},
            {"id": "REQ-002", "text": "Capped at 50%.", "page": 2}]
    a = FakeLLM()
    a.next_reply = lambda s, u: {"text": "Credits are capped at 50%."} if s == CORRECT_PROMPT else {
        "reviews": [{"id": "REQ-001", "verdict": "accept", "issue": ""},
                    {"id": "REQ-002", "verdict": "revise", "issue": "fragment"}]}

    out = review(reqs, PAGES, [("a", a)])

    assert [r["status"] for r in out] == ["accepted", "rejected"]
    assert out[1]["votes"][-1]["issue"] == "duplicate of REQ-001"
    assert "_key" not in out[0]
