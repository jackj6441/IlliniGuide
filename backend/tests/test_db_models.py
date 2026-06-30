from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql

from app.db.models import Base, Course, CourseChunk, EvalResult


def test_expected_tables_are_registered() -> None:
    assert set(Base.metadata.tables) == {
        "courses",
        "instructors",
        "gpa_stats",
        "course_chunks",
        "eval_runs",
        "eval_results",
    }


def test_courses_table_has_core_columns() -> None:
    columns = Course.__table__.columns

    assert columns["course_id"].unique is True
    assert columns["course_id"].nullable is False
    assert columns["department"].nullable is False
    assert columns["course_number"].nullable is False
    assert columns["title"].nullable is False
    assert "career_tags" in columns
    assert "created_at" in columns
    assert "updated_at" in columns


def test_course_chunks_compile_with_pgvector_column() -> None:
    ddl = str(
        CreateTable(CourseChunk.__table__).compile(dialect=postgresql.dialect())
    )

    assert "CREATE TABLE course_chunks" in ddl
    assert "embedding VECTOR" in ddl
    assert "metadata JSONB" in ddl


def test_eval_results_references_eval_runs() -> None:
    foreign_keys = list(EvalResult.__table__.columns["run_id"].foreign_keys)

    assert len(foreign_keys) == 1
    assert foreign_keys[0].target_fullname == "eval_runs.id"
