"""Ingest the official ECE and CS catalogs in one auditable run."""

import argparse
from pathlib import Path

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.db.init_db import init_database
from app.db.models import Course
from app.db.session import SessionLocal
from app.ingestion.course_catalog import (
    CourseIngestionResult,
    utc_now,
    write_ingestion_manifest,
)
from app.ingestion.cs_catalog import (
    CS_COURSES_SOURCE_URL,
    fetch_cs_courses_html,
    ingest_cs_courses_html,
)
from app.ingestion.ece_prereqs import (
    ECE_COURSES_SOURCE_URL,
    fetch_ece_courses_html,
    ingest_ece_prereqs_html,
)


def ingest_course_catalogs_html(
    session: Session,
    ece_html: str,
    cs_html: str,
    *,
    ece_limit: int | None = None,
    cs_limit: int | None = None,
    ece_source_url: str = ECE_COURSES_SOURCE_URL,
    cs_source_url: str = CS_COURSES_SOURCE_URL,
) -> tuple[CourseIngestionResult, CourseIngestionResult, int]:
    """Upsert both official sources and count distinct ECE/CS courses afterward."""
    try:
        ece_result = ingest_ece_prereqs_html(
            session,
            ece_html,
            limit=ece_limit,
            source_url=ece_source_url,
            commit=False,
        )
        cs_result = ingest_cs_courses_html(
            session,
            cs_html,
            limit=cs_limit,
            source_url=cs_source_url,
            commit=False,
        )
        # SessionLocal disables autoflush. Flush the two staged catalog batches
        # before counting them, while keeping the final commit atomic.
        session.flush()
        total_distinct_course_count = session.scalar(
            select(func.count(distinct(Course.course_id))).where(Course.department.in_(("ECE", "CS")))
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return ece_result, cs_result, int(total_distinct_course_count or 0)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Ingest official UIUC ECE and CS catalogs in one auditable run."
    )
    parser.add_argument("--ece-limit", type=int, help="Maximum unique ECE courses; omit for all.")
    parser.add_argument("--cs-limit", type=int, help="Maximum unique CS courses; omit for all.")
    parser.add_argument("--ece-source-url", default=ECE_COURSES_SOURCE_URL)
    parser.add_argument("--cs-source-url", default=CS_COURSES_SOURCE_URL)
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/ingestion"))
    parser.add_argument("--run-id", help="Optional deterministic artifact directory name.")
    parser.add_argument(
        "--require-minimum-distinct",
        type=int,
        help="Fail after writing the manifest unless ECE+CS distinct courses meet this count.",
    )
    args = parser.parse_args()

    ece_html = fetch_ece_courses_html(args.ece_source_url)
    cs_html = fetch_cs_courses_html(args.cs_source_url)
    fetched_at = utc_now()
    init_database()
    with SessionLocal() as session:
        ece_result, cs_result, total_distinct_course_count = ingest_course_catalogs_html(
            session,
            ece_html,
            cs_html,
            ece_limit=args.ece_limit,
            cs_limit=args.cs_limit,
            ece_source_url=args.ece_source_url,
            cs_source_url=args.cs_source_url,
        )

    manifest_path = write_ingestion_manifest(
        args.artifacts_dir,
        [ece_result, cs_result],
        fetched_at=fetched_at,
        run_id=args.run_id,
        total_distinct_course_count=total_distinct_course_count,
    )
    print(
        "Ingested ECE and CS catalog sources; "
        f"database now contains {total_distinct_course_count} distinct ECE/CS courses."
    )
    print(f"Manifest: {manifest_path}")

    if (
        args.require_minimum_distinct is not None
        and total_distinct_course_count < args.require_minimum_distinct
    ):
        raise SystemExit(
            "Distinct ECE/CS course count below required minimum: "
            f"{total_distinct_course_count} < {args.require_minimum_distinct}"
        )


if __name__ == "__main__":
    main()
