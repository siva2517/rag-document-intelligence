from app import rag


def test_upload_and_list(client, uploaded):
    assert uploaded["pages"] == 3
    assert uploaded["chunks"] >= 3
    docs = client.get("/api/documents").json()
    assert docs == [{"doc_id": uploaded["doc_id"], "name": "sample_services_agreement.pdf"}]


def test_rejects_non_pdf(client):
    resp = client.post("/api/documents", files={"file": ("notes.txt", b"hello", "text/plain")})
    assert resp.status_code == 400


def test_ask_retrieves_relevant_page_and_marks_citations(client, llm, uploaded):
    llm.next_reply = {"answer": "Within 24 hours [1].", "citations": [1]}

    resp = client.post("/api/ask", json={"question": "How fast must a security breach be notified?"})

    body = resp.json()
    assert body["answer"] == "Within 24 hours [1]."
    assert body["sources"][0]["page"] == 3
    assert body["sources"][0]["cited"] is True
    assert all(not s["cited"] for s in body["sources"][1:])
    assert "breach" in llm.chat_calls[-1][1]  # retrieved context was sent to the model


def test_ask_with_no_documents(client):
    body = client.post("/api/ask", json={"question": "anything?"}).json()
    assert body["sources"] == []


def test_extract_requirements_maps_pages_and_dedupes(client, llm, uploaded):
    llm.next_reply = {
        "requirements": [
            {"text": "Encrypt data at rest with AES-256.", "excerpt": 1, "category": "security", "priority": "must"},
            {"text": "encrypt data at rest  with AES-256.", "excerpt": 1, "category": "security", "priority": "must"},
            {"text": "Out of range excerpt", "excerpt": 99},
        ]
    }

    reqs = client.post(f"/api/documents/{uploaded['doc_id']}/requirements").json()["requirements"]

    assert len(reqs) == 1
    assert reqs[0]["id"] == "REQ-001"
    assert reqs[0]["page"] == 1  # excerpt 1 of the first batch is the first chunk


def test_delete_document(client, uploaded):
    client.delete(f"/api/documents/{uploaded['doc_id']}")
    assert client.get("/api/documents").json() == []


def test_stage_order_is_enforced(client, uploaded):
    resp = client.post(f"/api/documents/{uploaded['doc_id']}/review")
    assert resp.status_code == 409


def test_invalid_doc_id_is_rejected(client):
    assert client.get("/api/documents/..%2F..%2Fetc/state").status_code in (404, 422)
    assert client.get("/api/documents/not-a-uuid/state").status_code == 422


def test_full_pipeline_persists_and_restores(client, llm, reviewers, uploaded):
    doc_id = uploaded["doc_id"]

    def main_llm(system, user):
        if system == rag.INSIGHTS_PROMPT:
            return {"document_type": "Services agreement", "summary": "MSA.", "parties": [], "key_dates": [],
                    "obligations": [], "risks": []}
        return {"requirements": [
            {"text": "All Customer data must be encrypted at rest using AES-256", "excerpt": 1, "section": "8. Encryption",
             "category": "security", "priority": "must"},
            {"text": "This Master Services Agreement is entered into between Northwind Logistics", "excerpt": 1,
             "section": "1. Parties", "category": "other", "priority": "may"},
        ]}

    def reviewer(system, user):
        return {"reviews": [{"id": "REQ-001", "verdict": "accept", "issue": ""},
                            {"id": "REQ-002", "verdict": "reject", "issue": "recital, not a requirement"}]}

    llm.next_reply = main_llm
    for _, r in reviewers:
        r.next_reply = reviewer

    state = client.post(f"/api/documents/{doc_id}/pipeline").json()

    assert state["insights"]["document_type"] == "Services agreement"
    assert [r["section"] for r in state["requirements"]] == ["8. Encryption", "1. Parties"]
    assert [r["status"] for r in state["review"]] == ["accepted", "rejected"]
    assert [r["id"] for r in state["highlight"]] == ["REQ-001"]  # rejected requirements are not highlighted
    assert {"original.pdf", "pages.json", "insights.json", "requirements.json", "review.json",
            "highlight.json", "highlighted.pdf"} <= set(state["manifest"])

    csv = b"Requirement\nAll Customer data must be encrypted at rest using AES-256\nInvoices are payable within 30 days\n"
    comparison = client.post(f"/api/documents/{doc_id}/ground-truth", files={"file": ("gt.csv", csv, "text/csv")}).json()
    assert comparison["summary"]["matched"] == 1 and comparison["summary"]["recall"] == 0.5

    restored = client.get(f"/api/documents/{doc_id}/state").json()
    assert restored["comparison"] == comparison

    pdf = client.get(f"/api/documents/{doc_id}/files/highlighted.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert client.get(f"/api/documents/{doc_id}/files/pages.json").status_code == 404

    client.delete(f"/api/documents/{doc_id}")
    assert client.get(f"/api/documents/{doc_id}/state").json()["manifest"] == {}
