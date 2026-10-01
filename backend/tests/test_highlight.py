import pymupdf

from app.highlight import highlight
from tests.conftest import SAMPLE_PDF


def test_highlights_verbatim_paraphrased_and_reports_missing():
    reqs = [
        # Wraps across lines in the PDF.
        {"id": "REQ-001", "page": 3, "text": "All Customer data must be encrypted at rest using AES-256 and in transit using TLS 1.2 or higher."},
        # Council-style rewrite: not verbatim, but shares long phrases with the source.
        {"id": "REQ-002", "page": 3, "text": "The Provider shall notify the Customer of any confirmed security breach within one day."},
        # Split from a compound sentence: only the tail matches the source.
        {"id": "REQ-005", "page": 2, "text": "Severity 1 incidents must be resolved or mitigated within 4 hours."},
        {"id": "REQ-003", "page": 1, "text": "Unicorns must be fed twice daily."},
        {"id": "REQ-004", "page": 99, "text": "Page out of range."},
    ]

    pdf, located = highlight(SAMPLE_PDF.read_bytes(), reqs)

    assert [r["found"] for r in located] == [True, True, True, False, False]
    doc = pymupdf.open(stream=pdf, filetype="pdf")
    titles = [a.info["title"] for a in doc[2].annots()]
    assert titles == ["REQ-001", "REQ-002"]
    assert [a.info["title"] for a in doc[1].annots()] == ["REQ-005"]
    assert list(doc[0].annots()) == []
