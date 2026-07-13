"""One-shot embedding ingestion for course chunks.

Usage:
    python -m scripts.ingest_embeddings

Env vars:
    EMBEDDING_BACKEND       mock | sentence_transformer  (default: mock)
    EMBEDDING_MODEL_NAME    HF model id (default: MiniLM-L6-v2 for real backend)
    DATABASE_URL            Postgres DSN (default: local dev DB)

The script is idempotent — rerunning it wipes and rewrites chunks per course
so schema tweaks or model swaps replay cleanly.
"""

from __future__ import annotations

from app.db.init_db import init_database
from app.db.session import SessionLocal
from app.ingestion.embed_chunks import ingest_course_embeddings
from app.services.rag.embeddings import get_embedding_client


def main() -> None:
    init_database()
    client = get_embedding_client()

    print(
        f"Ingesting chunks with backend={client.backend_name} "
        f"model={client.model_name} dim={client.dimension}..."
    )

    with SessionLocal() as session:
        report = ingest_course_embeddings(session, client)

    print(
        f"Done. courses_seen={report.courses_seen} "
        f"courses_skipped={report.courses_skipped} "
        f"chunks_written={report.chunks_written} "
        f"started_at_utc={report.started_at_utc.isoformat()} "
        f"completed_at_utc={report.completed_at_utc.isoformat()}"
    )


if __name__ == "__main__":
    main()
