from app.schemas import Citation
from app.services.rag.retriever import RetrievedChunk


def citation_from_chunk(chunk: RetrievedChunk, max_snippet_chars: int = 220) -> Citation:
    snippet = chunk.chunk_text
    if len(snippet) > max_snippet_chars:
        snippet = f"{snippet[: max_snippet_chars - 3].rstrip()}..."
    return Citation(
        source_name=chunk.source_name,
        source_url=chunk.source_url,
        course_id=chunk.course_id,
        snippet=snippet,
    )
