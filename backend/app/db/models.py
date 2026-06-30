from datetime import datetime
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Float, ForeignKey, Integer, Text, func
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    department: Mapped[str] = mapped_column(Text, nullable=False)
    course_number: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    credit_hours: Mapped[str | None] = mapped_column(Text)
    prerequisites: Mapped[str | None] = mapped_column(Text)
    source_url: Mapped[str | None] = mapped_column(Text)
    career_tags: Mapped[list[str] | None] = mapped_column(ARRAY(Text))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())

    chunks: Mapped[list["CourseChunk"]] = relationship(
        back_populates="course",
        primaryjoin="Course.course_id == foreign(CourseChunk.course_id)",
    )


class Instructor(Base):
    __tablename__ = "instructors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)


class GPAStat(Base):
    __tablename__ = "gpa_stats"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[str] = mapped_column(Text, nullable=False)
    instructor_name: Mapped[str | None] = mapped_column(Text)
    term: Mapped[str | None] = mapped_column(Text)
    average_gpa: Mapped[float | None] = mapped_column(Float)
    grade_distribution: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    source_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class CourseChunk(Base):
    __tablename__ = "course_chunks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    course_id: Mapped[str | None] = mapped_column(Text)
    source_name: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text)
    section_type: Mapped[str | None] = mapped_column(Text)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_: Mapped[dict[str, Any] | None] = mapped_column("metadata", JSONB)
    embedding: Mapped[list[float] | None] = mapped_column(Vector)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    course: Mapped[Course | None] = relationship(
        back_populates="chunks",
        primaryjoin="foreign(CourseChunk.course_id) == Course.course_id",
    )


class EvalRun(Base):
    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_name: Mapped[str] = mapped_column(Text, nullable=False)
    model_name: Mapped[str | None] = mapped_column(Text)
    retriever_config: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    results: Mapped[list["EvalResult"]] = relationship(back_populates="run")


class EvalResult(Base):
    __tablename__ = "eval_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    run_id: Mapped[int | None] = mapped_column(ForeignKey("eval_runs.id"))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text)
    expected_evidence: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    retrieved_chunks: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    latency_ms: Mapped[int | None] = mapped_column(Integer)
    correctness_score: Mapped[float | None] = mapped_column(Float)
    citation_score: Mapped[float | None] = mapped_column(Float)
    notes: Mapped[str | None] = mapped_column(Text)

    run: Mapped[EvalRun | None] = relationship(back_populates="results")


__all__ = [
    "Base",
    "Course",
    "Instructor",
    "GPAStat",
    "CourseChunk",
    "EvalRun",
    "EvalResult",
]
