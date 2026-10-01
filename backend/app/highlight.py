"""Highlight requirements inside the original PDF so reviewers can see them in context."""

import pymupdf

WINDOW = 6  # words per phrase when the full text is not found verbatim


def _find(page: pymupdf.Page, text: str) -> list:
    rects = page.search_for(text)
    if rects:
        return rects
    # Split or corrected text (e.g. "X must be resolved..." cut from "X must be acknowledged ... and resolved...")
    # only partly matches the source, so fall back to overlapping word windows, always including the tail.
    words = text.split()
    last = max(len(words) - WINDOW, 0)
    found = []
    for i in sorted({*range(0, last + 1, WINDOW // 2), last}):
        found += page.search_for(" ".join(words[i : i + WINDOW]))
    return found


def highlight(pdf_bytes: bytes, requirements: list[dict]) -> tuple[bytes, list[dict]]:
    doc = pymupdf.open(stream=pdf_bytes, filetype="pdf")
    located = []
    for req in requirements:
        # Keep a reference to the page: annotations become invalid once their Page object is collected.
        page = doc[req["page"] - 1] if 1 <= req["page"] <= doc.page_count else None
        rects = _find(page, req["text"]) if page else []
        if rects:
            annot = page.add_highlight_annot(rects)
            annot.set_info(title=req["id"], content=req["text"])
            annot.update()
        located.append({"id": req["id"], "page": req["page"], "found": bool(rects)})
    return doc.tobytes(), located
