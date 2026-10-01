from app.ingest import chunk_pages


def test_chunks_stay_within_page_and_size():
    pages = ["word " * 500, "short page", ""]
    chunks = chunk_pages(pages, "d1", "doc.pdf", size=200, overlap=40)

    assert {c.page for c in chunks} == {1, 2}
    assert all(len(c.text) <= 200 for c in chunks)
    assert [c.index for c in chunks] == list(range(len(chunks)))
    assert chunks[-1].text == "short page"


def test_chunks_overlap_and_cut_on_word_boundaries():
    text = " ".join(f"w{i}" for i in range(300))
    chunks = chunk_pages([text], "d1", "doc.pdf", size=100, overlap=30)

    for a, b in zip(chunks, chunks[1:]):
        assert a.text.split()[-1] in b.text  # overlap carries context forward
    assert all(tok.startswith("w") for c in chunks for tok in c.text.split())
