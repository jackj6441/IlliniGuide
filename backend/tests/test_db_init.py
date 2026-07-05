from unittest.mock import Mock, patch

from sqlalchemy import text

from app.db.init_db import HNSW_INDEX_NAME, init_database


def _fresh_mock_engine() -> tuple[Mock, Mock]:
    mock_connection = Mock()
    mock_context = Mock()
    mock_context.__enter__ = Mock(return_value=mock_connection)
    mock_context.__exit__ = Mock(return_value=None)
    mock_engine = Mock()
    mock_engine.begin.return_value = mock_context
    return mock_engine, mock_connection


def _stringify_call(call) -> str:
    return str(call.args[0])


def test_init_database_creates_vector_extension_before_tables() -> None:
    mock_engine, mock_connection = _fresh_mock_engine()
    # Column already at vector(384) so no ALTER is issued.
    mock_connection.execute.return_value.scalar_one_or_none.return_value = (
        "vector(384)"
    )

    with patch("app.db.init_db.Base.metadata.create_all") as create_all:
        init_database(mock_engine)

    executed = [_stringify_call(c) for c in mock_connection.execute.call_args_list]

    # Ordering matters: extension must precede table + column probing.
    assert executed[0] == str(text("CREATE EXTENSION IF NOT EXISTS vector"))
    create_all.assert_called_once_with(bind=mock_connection)

    # No ALTER when the column is already the right dimension.
    assert not any("alter table course_chunks" in s.lower() for s in executed)
    # HNSW index is always ensured.
    assert any(HNSW_INDEX_NAME in s for s in executed)


def test_init_database_alters_embedding_column_when_dimension_mismatched() -> None:
    mock_engine, mock_connection = _fresh_mock_engine()
    # Column was created before D3 with no fixed dimension.
    mock_connection.execute.return_value.scalar_one_or_none.return_value = (
        "vector"
    )

    with patch("app.db.init_db.Base.metadata.create_all"):
        init_database(mock_engine)

    executed = [_stringify_call(c) for c in mock_connection.execute.call_args_list]
    assert any(
        "alter table course_chunks" in s.lower() and "vector(384)" in s.lower()
        for s in executed
    )
