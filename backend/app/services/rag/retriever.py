import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Course, CourseChunk
from app.services.rag.normalize import extract_course_ids
from app.services.rag.sample_data import SAMPLE_CHUNKS, SampleChunk


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")
SCOPE_QUERY_STOPWORDS = frozenset(
    {
        "a",
        "about",
        "an",
        "and",
        "are",
        "before",
        "best",
        "between",
        "can",
        "class",
        "classes",
        "compare",
        "course",
        "courses",
        "does",
        "do",
        "evidence",
        "for",
        "give",
        "good",
        "has",
        "have",
        "help",
        "i",
        "information",
        "is",
        "it",
        "learn",
        "list",
        "me",
        "need",
        "of",
        "prerequisite",
        "prerequisites",
        "prior",
        "read",
        "related",
        "relevant",
        "required",
        "show",
        "take",
        "taking",
        "tell",
        "teaches",
        "taught",
        "the",
        "to",
        "what",
        "which",
        "would",
    }
)
DEPARTMENT_TOKENS = frozenset({"cs", "cse", "ece"})


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


def has_catalog_signal(query: str, chunks: list[RetrievedChunk]) -> bool:
    """Return whether evidence shares a non-generic topic token with query.

    Embedding similarity alone can map an out-of-scope question to generic
    catalog text such as ``Prerequisites`` or ``Credit hours``. This small
    lexical check is intentionally conservative and only gates queries that
    lack an explicit course ID; it is not a replacement for semantic ranking.
    """
    query_tokens = tokenize(query) - SCOPE_QUERY_STOPWORDS - DEPARTMENT_TOKENS
    if not query_tokens:
        return False
    return any(
        query_tokens
        & (tokenize(f"{chunk.course_id} {chunk.section_type} {chunk.chunk_text}") - DEPARTMENT_TOKENS)
        for chunk in chunks
    )


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
    if ranked and not query_course_ids and not has_catalog_signal(query, ranked):
        return []
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
        top_chunks = ranked[:top_k]
        if not query_course_ids and not has_catalog_signal(query, top_chunks):
            return []
        return top_chunks
    return search_course_docs(query, course_ids=course_ids, top_k=top_k)


def search_course_chunks_by_keyword(
    session: Session,
    query: str,
    course_ids: list[str] | None = None,
    top_k: int = 5,
) -> list[RetrievedChunk]:
    """Rank persisted RAG chunks with lexical overlap for an evaluation baseline.

    Unlike the legacy course-profile fallback, this uses the same
    ``course_chunks`` corpus and preserves source/section metadata. That makes
    source and section metrics comparable to pgvector retrieval.
    """
    if top_k <= 0:
        return []

    statement = select(CourseChunk)
    if course_ids:
        statement = statement.where(CourseChunk.course_id.in_(course_ids))
    query_tokens = tokenize(query)
    ranked: list[RetrievedChunk] = []
    for stored_chunk in session.scalars(statement).all():
        chunk = RetrievedChunk(
            course_id=stored_chunk.course_id or "",
            source_name=stored_chunk.source_name,
            source_url=stored_chunk.source_url or "",
            section_type=stored_chunk.section_type or "",
            chunk_text=stored_chunk.chunk_text,
            score=0.0,
        )
        score = _score_retrieved_chunk(query_tokens, chunk)
        if score > 0:
            ranked.append(
                RetrievedChunk(
                    course_id=chunk.course_id,
                    source_name=chunk.source_name,
                    source_url=chunk.source_url,
                    section_type=chunk.section_type,
                    chunk_text=chunk.chunk_text,
                    score=round(score, 4),
                )
            )

    ranked.sort(key=lambda chunk: chunk.score, reverse=True)
    top_chunks = ranked[:top_k]
    if top_chunks and not (course_ids or extract_course_ids(query)) and not has_catalog_signal(
        query, top_chunks
    ):
        return []
    return top_chunks


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
