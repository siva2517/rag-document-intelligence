"""PDF parsing and page-aware chunking.

Chunks never cross page boundaries, so every chunk maps to exactly one page
and citations can point at a precise location in the source document.
"""

import io
from dataclasses import dataclass

from pypdf import PdfReader


@dataclass
class Chunk:
    doc_id: str
    doc_name: str
    page: int
    index: int
    text: str


def read_pdf_pages(data: bytes) -> list[str]:
    reader = PdfReader(io.BytesIO(data))
    return [page.extract_text() or "" for page in reader.pages]


def chunk_pages(pages: list[str], doc_id: str, doc_name: str, size: int, overlap: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for page_no, raw in enumerate(pages, start=1):
        text = " ".join(raw.split())
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            if end < len(text):
                # Prefer to cut on a word boundary in the back half of the window.
                cut = text.rfind(" ", start + size // 2, end)
                if cut != -1:
                    end = cut
            chunks.append(Chunk(doc_id, doc_name, page_no, len(chunks), text[start:end].strip()))
            if end >= len(text):
                break
            start = max(end - overlap, start + 1)
            # Snap the overlap start forward to the next word so chunks never begin mid-word.
            if text[start - 1] != " ":
                space = text.find(" ", start, end)
                start = space + 1 if space != -1 else end
    return chunks
