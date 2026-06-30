import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Course
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


def search_course_docs_from_db(
    session: Session,
    query: str,
    course_ids: list[str] | None = None,
    top_k: int = 5,
) -> list[RetrievedChunk]:
    query_course_ids = course_ids or extract_course_ids(query)
    query_tokens = tokenize(query)

    statement = select(Course)
    if query_course_ids:
        statement = statement.where(Course.course_id.in_(query_course_ids))
    courses = list(session.scalars(statement).all())

    ranked: list[RetrievedChunk] = []
    for course in courses:
        chunk = _course_to_chunk(course)
        score = _score_retrieved_chunk(query_tokens, chunk)
        if score > 0 or (query_course_ids and course.course_id in query_course_ids):
            ranked.append(
                RetrievedChunk(
                    course_id=chunk.course_id,
                    source_name=chunk.source_name,
                    source_url=chunk.source_url,
                    section_type=chunk.section_type,
                    chunk_text=chunk.chunk_text,
                    score=round(max(score, 0.0001), 4),
                )
            )

    ranked.sort(key=lambda chunk: chunk.score, reverse=True)
    if ranked:
        return ranked[:top_k]
    return search_course_docs(query, course_ids=course_ids, top_k=top_k)


def _score_chunk(query_tokens: set[str], chunk: SampleChunk) -> float:
    chunk_tokens = tokenize(f"{chunk.course_id} {chunk.section_type} {chunk.chunk_text}")
    if not query_tokens:
        return 0.0
    overlap = query_tokens & chunk_tokens
    return len(overlap) / len(query_tokens)


def _score_retrieved_chunk(query_tokens: set[str], chunk: RetrievedChunk) -> float:
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


def _course_to_chunk(course: Course) -> RetrievedChunk:
    parts = [f"{course.course_id}: {course.title}"]
    if course.description:
        parts.append(course.description)
    if course.prerequisites:
        parts.append(f"Prerequisites: {course.prerequisites}")
    if course.career_tags:
        parts.append(f"Career tags: {', '.join(course.career_tags)}")

    return RetrievedChunk(
        course_id=course.course_id,
        source_name="Course Database",
        source_url=course.source_url or "local://courses",
        section_type="course_profile",
        chunk_text=" ".join(parts),
        score=0.0,
    )
