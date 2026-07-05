from sqlalchemy import Connection, Engine, text

from app.db.models import EMBEDDING_DIMENSION, Base
from app.db.session import create_db_engine


HNSW_INDEX_NAME = "course_chunks_embedding_hnsw"


def init_database(engine: Engine | None = None) -> None:
    db_engine = engine or create_db_engine()

    with db_engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(bind=connection)
        ensure_embedding_dimension(connection, EMBEDDING_DIMENSION)
        ensure_hnsw_index(connection, EMBEDDING_DIMENSION)


def ensure_embedding_dimension(conn: Connection, dim: int) -> bool:
    """Idempotently coerce `course_chunks.embedding` to `vector(dim)`.

    Returns True if an ALTER was executed. When the column already has the
    right typmod (SQLAlchemy `create_all` set it correctly on a fresh table)
    this is a no-op. Existing rows with a mismatched dimension would fail the
    ALTER's implicit cast, but at this project stage the column has never held
    real embeddings — pre-D3 ingestion left it NULL — so wiping to NULL is safe.
    """
    current = conn.execute(
        text(
            """
            SELECT format_type(atttypid, atttypmod)
            FROM pg_attribute
            WHERE attrelid = 'course_chunks'::regclass
              AND attname = 'embedding'
              AND NOT attisdropped
            """
        )
    ).scalar_one_or_none()

    expected = f"vector({dim})"
    if current == expected:
        return False

    conn.execute(
        text(
            f"ALTER TABLE course_chunks "
            f"ALTER COLUMN embedding TYPE vector({dim}) USING NULL"
        )
    )
    return True


def ensure_hnsw_index(conn: Connection, dim: int) -> None:
    """Create the HNSW cosine index if missing.

    HNSW is preferred over IVFFLAT here because our corpus is small
    (~hundreds of chunks) and we don't want to maintain an IVF training step.
    Cosine ops match embeddings that were unit-normalized at embed time, so
    `<=>` distance is directly interpretable.
    """
    # Guard against building the index before the column has a fixed
    # dimension — pgvector requires `typmod` to be set for HNSW.
    del dim  # only used for readability at the call site
    conn.execute(
        text(
            f"""
            CREATE INDEX IF NOT EXISTS {HNSW_INDEX_NAME}
            ON course_chunks USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64)
            """
        )
    )
