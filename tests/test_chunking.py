from __future__ import annotations

from source_recall.chunking import chunk_text


def test_empty_text_has_no_chunks() -> None:
    assert chunk_text("", 100, 2) == []


def test_chunks_preserve_line_provenance_and_overlap() -> None:
    chunks = chunk_text("one\ntwo\nthree\nfour\n", 10, 1)

    assert [(item.start_line, item.end_line) for item in chunks] == [
        (1, 2),
        (2, 3),
        (3, 4),
    ]
    assert chunks[1].content == "two\nthree"


def test_pathological_single_line_is_bounded() -> None:
    chunks = chunk_text("x" * 25, 10, 0)

    assert [len(item.content) for item in chunks] == [10, 10, 5]
    assert all(item.start_line == item.end_line == 1 for item in chunks)


def test_overlap_never_exceeds_the_character_bound() -> None:
    chunks = chunk_text("1234\n5678\n90\n", 10, 2)

    assert all(len(item.content) <= 10 for item in chunks)
    assert chunks[-1].content == "5678\n90"
