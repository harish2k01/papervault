from dataclasses import dataclass

DEFAULT_CHUNK_WORDS = 180
DEFAULT_OVERLAP_WORDS = 30


@dataclass(frozen=True, slots=True)
class TextChunk:
    page_number: int
    chunk_index: int
    content_text: str
    token_count: int


def chunk_page_text(
    page_number: int,
    text: str,
    *,
    chunk_words: int = DEFAULT_CHUNK_WORDS,
    overlap_words: int = DEFAULT_OVERLAP_WORDS,
) -> tuple[TextChunk, ...]:
    if page_number < 1:
        raise ValueError("Page number must be positive")
    if chunk_words < 1:
        raise ValueError("Chunk size must be positive")
    if overlap_words < 0 or overlap_words >= chunk_words:
        raise ValueError("Chunk overlap must be smaller than chunk size")

    words = text.split()
    if not words:
        return ()

    chunks: list[TextChunk] = []
    step = chunk_words - overlap_words
    for chunk_index, start in enumerate(range(0, len(words), step)):
        window = words[start : start + chunk_words]
        if not window:
            break
        chunks.append(
            TextChunk(
                page_number=page_number,
                chunk_index=chunk_index,
                content_text=" ".join(window),
                token_count=len(window),
            )
        )
        if start + chunk_words >= len(words):
            break
    return tuple(chunks)
