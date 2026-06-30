from sqlalchemy import Engine, text

from app.db.models import Base
from app.db.session import create_db_engine


def init_database(engine: Engine | None = None) -> None:
    db_engine = engine or create_db_engine()

    with db_engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        Base.metadata.create_all(bind=connection)
