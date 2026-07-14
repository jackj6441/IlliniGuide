"""Semantic top-k retrieval over `course_chunks` via pgvector.

Uses pgvector's cosine distance operator (`<=>`) with the HNSW index created
in D3. Embeddings are unit-normalized at embed time, so cosine distance falls
in [0, 1] for related content and `similarity = 1 - distance` is directly
interpretable as a confidence score for the D5 threshold fallback.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import CourseChunk
from app.services.rag.embeddings import EmbeddingClient
from app.services.rag.normalize import extract_course_ids
from app.services.rag.retriever import (
    RetrievedChunk,
    has_catalog_signal,
    search_course_docs_from_db,
)


LOW_CONFIDENCE_THRESHOLD = 0.35


def semantic_search(
    session: Session,
    query: str,
    embedding_client: EmbeddingClient,
    *,
    course_ids: list[str] | None = None,
    top_k: int = 5,
) -> list[RetrievedChunk]:
    """Return the top-k chunks most similar to `query`.

    Passing `course_ids` restricts retrieval to a fixed set — used by the
    compare/prereq tools where the query already knows which courses matter.
    Chunks with a NULL embedding (never ingested) are filtered so pgvector's
    distance operator never sees a NULL operand.
    """
    if top_k <= 0:
        return []

    query_vec = embedding_client.embed([query])[0]

    distance = CourseChunk.embedding.cosine_distance(query_vec)
    statement = (
        select(CourseChunk, distance.label("distance"))
        .where(CourseChunk.embedding.is_not(None))
        .order_by(distance)
        .limit(top_k)
    )
    if course_ids:
        statement = statement.where(CourseChunk.course_id.in_(course_ids))

    rows = session.execute(statement).all()

    retrieved = [_row_to_chunk(chunk, dist) for chunk, dist in rows]
    if retrieved and not (course_ids or extract_course_ids(query)):
        if not has_catalog_signal(query, retrieved):
            return []
    return retrieved


def _row_to_chunk(chunk: CourseChunk, distance: float) -> RetrievedChunk:
    similarity = max(0.0, min(1.0, 1.0 - float(distance)))
    return RetrievedChunk(
        course_id=chunk.course_id or "",
        source_name=chunk.source_name,
        source_url=chunk.source_url or "",
        section_type=chunk.section_type or "",
        chunk_text=chunk.chunk_text,
        score=round(similarity, 4),
    )


def hybrid_search(
    session: Session,
    query: str,
    embedding_client: EmbeddingClient,
    *,
    course_ids: list[str] | None = None,
    top_k: int = 5,
) -> tuple[list[RetrievedChunk], list[str]]:
    """Semantic-first retrieval with a keyword safety net.

    Behaviour:
    - Run ``semantic_search`` first.
    - If it returns any chunks and the top similarity is below
      ``LOW_CONFIDENCE_THRESHOLD``, append an explicit "low confidence" note so
      the LLM knows not to over-index on the evidence.
    - If it returns *no* chunks (e.g. the DB has not been ingested yet or the
      query is far from anything embedded), silently fall back to the legacy
      keyword retriever so dev environments without a running ingestion job
      still work. No note is added for the silent fallback because it would
      be noisy; the caller's normal "no evidence" logic still applies when the
      keyword path is also empty.
    """
    semantic = semantic_search(
        session,
        query,
        embedding_client,
        course_ids=course_ids,
        top_k=top_k,
    )
    notes: list[str] = []
    if semantic:
        top_score = semantic[0].score
        if top_score < LOW_CONFIDENCE_THRESHOLD:
            notes.append(
                f"Retrieval confidence low (top similarity={top_score:.2f}). "
                "Response may not be well-grounded in course data."
            )
        return semantic, notes

    keyword = search_course_docs_from_db(
        session,
        query,
        course_ids=course_ids,
        top_k=top_k,
    )
    return keyword, notes


__all__ = ["semantic_search", "hybrid_search", "LOW_CONFIDENCE_THRESHOLD"]
