"""Run the golden retrieval eval against the live DB.

Usage:
    python -m scripts.eval_retrieval

Requires:
    - `python -m scripts.init_db` (creates schema + HNSW index)
    - `python -m scripts.ingest_embeddings` (populates course_chunks.embedding)

Env vars:
    EMBEDDING_BACKEND       mock | sentence_transformer (default: mock)
    EMBEDDING_MODEL_NAME    HF model id
    DATABASE_URL            Postgres DSN
"""

from __future__ import annotations

from app.db.session import SessionLocal
from app.services.rag.embeddings import get_embedding_client
from app.services.rag.eval import evaluate, format_report


def main() -> None:
    client = get_embedding_client()
    print(
        f"Evaluating retrieval with backend={client.backend_name} "
        f"model={client.model_name} dim={client.dimension}\n"
    )

    with SessionLocal() as session:
        report = evaluate(session, client)

    print(format_report(report))


if __name__ == "__main__":
    main()
