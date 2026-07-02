from sqlalchemy.orm import Session

from app.services.rag.normalize import normalize_course_id
from app.services.rag.retriever import RetrievedChunk, search_course_docs_from_db
from app.services.tools.schemas import (
    RetrievedDoc,
    SearchCourseDocsRequest,
    SearchCourseDocsResult,
)


MIN_TOP_K = 1
MAX_TOP_K = 20
SAMPLE_FALLBACK_SOURCE_NAME = "Mock Course Dataset"


def search_course_docs(
    session: Session,
    request: SearchCourseDocsRequest,
) -> SearchCourseDocsResult:
    query = request.query.strip()
    if not query:
        raise ValueError("query must be a non-empty string")

    if not (MIN_TOP_K <= request.top_k <= MAX_TOP_K):
        raise ValueError(
            f"top_k must be between {MIN_TOP_K} and {MAX_TOP_K}, got {request.top_k}"
        )

    normalized_course_ids: list[str] = []
    if request.course_ids:
        seen: set[str] = set()
        for raw_course_id in request.course_ids:
            normalized = normalize_course_id(raw_course_id)
            if normalized not in seen:
                seen.add(normalized)
                normalized_course_ids.append(normalized)

    chunks = search_course_docs_from_db(
        session,
        query,
        course_ids=normalized_course_ids or None,
        top_k=request.top_k,
    )

    docs = [_chunk_to_doc(chunk) for chunk in chunks]
    notes = _build_notes(chunks)

    return SearchCourseDocsResult(
        query=query,
        course_ids=normalized_course_ids,
        docs=docs,
        notes=notes,
    )


def _chunk_to_doc(chunk: RetrievedChunk) -> RetrievedDoc:
    return RetrievedDoc(
        course_id=chunk.course_id,
        source_name=chunk.source_name,
        source_url=chunk.source_url,
        section_type=chunk.section_type,
        snippet=chunk.chunk_text,
        score=chunk.score,
    )


def _build_notes(chunks: list[RetrievedChunk]) -> list[str]:
    if not chunks:
        return ["No evidence found in course database or sample chunks."]
    if all(chunk.source_name == SAMPLE_FALLBACK_SOURCE_NAME for chunk in chunks):
        return [
            "Fell back to sample chunks; course database has no matching evidence.",
        ]
    return []
