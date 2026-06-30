from unittest.mock import Mock, patch

from sqlalchemy import text

from app.db.init_db import init_database


def test_init_database_creates_vector_extension_before_tables() -> None:
    mock_connection = Mock()
    mock_context = Mock()
    mock_context.__enter__ = Mock(return_value=mock_connection)
    mock_context.__exit__ = Mock(return_value=None)
    mock_engine = Mock()
    mock_engine.begin.return_value = mock_context

    with patch("app.db.init_db.Base.metadata.create_all") as create_all:
        init_database(mock_engine)

    mock_connection.execute.assert_called_once()
    executed_statement = mock_connection.execute.call_args.args[0]
    assert str(executed_statement) == str(text("CREATE EXTENSION IF NOT EXISTS vector"))
    create_all.assert_called_once_with(bind=mock_connection)
