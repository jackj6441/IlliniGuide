import re
from dataclasses import dataclass

from app.services.rag.normalize import extract_course_ids
from app.services.rag.sample_data import SAMPLE_CHUNKS, SampleChunk


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


@dataclass(frozen=True)
class RetrievedChunk:
    course_id: str
    source_name: str
    source_url: str
    section_type: str
    chunk_text: str
    score: float


def tokenize(text: str) -> set[str]:
    return set(TOKEN_PATTERN.findall(text.lower()))


def search_course_docs(
    query: str,
    course_ids: list[str] | None = None,
    top_k: int = 5,
) -> list[RetrievedChunk]:
    query_course_ids = course_ids or extract_course_ids(query)
    query_tokens = tokenize(query)

    candidates = list(SAMPLE_CHUNKS)
    if query_course_ids:
        candidates = [chunk for chunk in candidates if chunk.course_id in query_course_ids]

    ranked: list[RetrievedChunk] = []
    for chunk in candidates:
        score = _score_chunk(query_tokens, chunk)
        if score > 0:
            ranked.append(_to_retrieved_chunk(chunk, score))

    ranked.sort(key=lambda chunk: chunk.score, reverse=True)
    return ranked[:top_k]


def _score_chunk(query_tokens: set[str], chunk: SampleChunk) -> float:
    chunk_tokens = tokenize(f"{chunk.course_id} {chunk.section_type} {chunk.chunk_text}")
    if not query_tokens:
        return 0.0
    overlap = query_tokens & chunk_tokens
    return len(overlap) / len(query_tokens)


def _to_retrieved_chunk(chunk: SampleChunk, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        course_id=chunk.course_id,
        source_name=chunk.source_name,
        source_url=chunk.source_url,
        section_type=chunk.section_type,
        chunk_text=chunk.chunk_text,
        score=round(score, 4),
    )
