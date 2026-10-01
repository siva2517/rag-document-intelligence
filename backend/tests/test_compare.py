import io

import pytest
from openpyxl import Workbook

from app.compare import compare, load_ground_truth
from tests.conftest import FakeLLM


def test_load_csv_picks_requirement_column():
    data = "ID,Requirement,Owner\n1,Encrypt data at rest,IT\n2,,IT\n3,Report monthly,Ops\n".encode()
    assert load_ground_truth("gt.csv", data) == ["Encrypt data at rest", "Report monthly"]


def test_load_xlsx_falls_back_to_first_column():
    wb = Workbook()
    wb.active.append(["Obligation"])
    wb.active.append(["Notify breaches within 24 hours"])
    buf = io.BytesIO()
    wb.save(buf)
    assert load_ground_truth("gt.xlsx", buf.getvalue()) == ["Notify breaches within 24 hours"]


def test_load_rejects_other_formats():
    with pytest.raises(ValueError):
        load_ground_truth("gt.txt", b"x")


def test_compare_matches_one_to_one_and_scores():
    generated = [
        {"id": "REQ-001", "text": "Customer data must be encrypted at rest using AES-256", "page": 3},
        {"id": "REQ-002", "text": "Customer data must be encrypted at rest using AES-256", "page": 3},
        {"id": "REQ-003", "text": "Provide a monthly service report", "page": 2},
    ]
    truth = ["Customer data must be encrypted at rest using AES-256", "Invoices payable within thirty days"]

    result = compare(generated, truth, FakeLLM(), threshold=0.9)

    s = result["summary"]
    assert (s["matched"], s["precision"], s["recall"]) == (1, 0.333, 0.5)
    assert result["matches"][0]["id"] == "REQ-001"  # each truth item matches at most one generated item
    assert result["missed"] == ["Invoices payable within thirty days"]
    assert [e["id"] for e in result["extra"]] == ["REQ-002", "REQ-003"]


def test_compare_handles_empty_inputs():
    assert compare([], ["x"], FakeLLM(), 0.7)["summary"]["recall"] == 0.0
