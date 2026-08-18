"""Deterministic, bounded line-aware source chunking."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    sequence: int
    start_line: int
    end_line: int
    content: str


def chunk_text(
    text: str,
    max_characters: int,
    overlap_lines: int,
) -> list[Chunk]:
    """Split text by lines while bounding pathological single-line content."""

    lines = text.splitlines()
    if not lines:
        return []

    raw_chunks: list[tuple[int, int, str]] = []
    buffer: list[str] = []
    character_count = 0
    start_line = 1

    def flush(end_line: int) -> None:
        nonlocal buffer, character_count
        if buffer:
            raw_chunks.append((start_line, end_line, "\n".join(buffer)))
        buffer = []
        character_count = 0

    for line_number, line in enumerate(lines, 1):
        if len(line) > max_characters:
            flush(line_number - 1)
            for offset in range(0, len(line), max_characters):
                raw_chunks.append(
                    (
                        line_number,
                        line_number,
                        line[offset : offset + max_characters],
                    )
                )
            start_line = line_number + 1
            continue

        added_characters = len(line) + (1 if buffer else 0)
        if buffer and character_count + added_characters > max_characters:
            previous = list(buffer)
            flush(line_number - 1)
            overlap = previous[-overlap_lines:] if overlap_lines else []
            while overlap and len("\n".join([*overlap, line])) > max_characters:
                overlap.pop(0)
            buffer = overlap
            character_count = len("\n".join(buffer))
            start_line = max(1, line_number - len(overlap))

        if not buffer:
            start_line = line_number
        else:
            character_count += 1
        buffer.append(line)
        character_count += len(line)

    flush(len(lines))
    return [
        Chunk(index, start, end, content)
        for index, (start, end, content) in enumerate(raw_chunks)
        if content.strip()
    ]
