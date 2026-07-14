from sqlalchemy.orm import Session

from app.services.rag.embeddings import (
    EmbeddingClient,
    get_default_embedding_client,
)
from app.services.rag.normalize import extract_course_ids, normalize_course_id
from app.services.rag.pgvector_retriever import hybrid_search
from app.services.rag.retriever import RetrievedChunk
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
    *,
    embedding_client: EmbeddingClient | None = None,
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

    # The router normally supplies IDs explicitly. Extracting them here keeps
    # the public tool safe for direct callers as well: a query for ECE 999
    # must not silently retrieve evidence for a different course.
    effective_course_ids = normalized_course_ids or extract_course_ids(query)

    client = embedding_client or get_default_embedding_client()
    chunks, retrieval_notes = hybrid_search(
        session,
        query,
        client,
        course_ids=effective_course_ids or None,
        top_k=request.top_k,
    )

    docs = [_chunk_to_doc(chunk) for chunk in chunks]
    notes = retrieval_notes + _build_notes(chunks, effective_course_ids)

    return SearchCourseDocsResult(
        query=query,
        course_ids=effective_course_ids,
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


def _build_notes(chunks: list[RetrievedChunk], course_ids: list[str]) -> list[str]:
    if not chunks:
        if course_ids:
            return [
                f"No evidence found for requested course ID(s): {', '.join(course_ids)}. "
                "The course may be outside the current catalog coverage."
            ]
        return ["No evidence found in course database or sample chunks."]
    if all(chunk.source_name == SAMPLE_FALLBACK_SOURCE_NAME for chunk in chunks):
        return [
            "Fell back to sample chunks; course database has no matching evidence.",
        ]
    return []
