"""Enrich ECE and CS records with official catalog descriptions and credits."""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import distinct, func, select
from sqlalchemy.orm import Session

from app.db.init_db import init_database
from app.db.models import Course
from app.db.session import SessionLocal
from app.ingestion.catalog_details import (
    CS_CATALOG_DETAILS_SOURCE_URL,
    ECE_CATALOG_DETAILS_SOURCE_URL,
    fetch_catalog_details_html,
    ingest_catalog_details_html,
)
from app.ingestion.course_catalog import CourseIngestionResult, utc_now, write_ingestion_manifest


def enrich_catalog_details_html(
    session: Session,
    ece_html: str,
    cs_html: str,
    *,
    ece_source_url: str = ECE_CATALOG_DETAILS_SOURCE_URL,
    cs_source_url: str = CS_CATALOG_DETAILS_SOURCE_URL,
    ece_limit: int | None = None,
    cs_limit: int | None = None,
) -> tuple[CourseIngestionResult, CourseIngestionResult, int]:
    """Atomically upsert detail fields and return the active ECE/CS corpus size."""
    try:
        ece_result = ingest_catalog_details_html(
            session,
            ece_html,
            department="ECE",
            source_url=ece_source_url,
            limit=ece_limit,
            commit=False,
        )
        cs_result = ingest_catalog_details_html(
            session,
            cs_html,
            department="CS",
            source_url=cs_source_url,
            limit=cs_limit,
            commit=False,
        )
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
        description="Enrich ECE and CS courses with official catalog descriptions and credits."
    )
    parser.add_argument("--ece-source-url", default=ECE_CATALOG_DETAILS_SOURCE_URL)
    parser.add_argument("--cs-source-url", default=CS_CATALOG_DETAILS_SOURCE_URL)
    parser.add_argument("--ece-limit", type=int)
    parser.add_argument("--cs-limit", type=int)
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/catalog_details"))
    parser.add_argument("--run-id")
    args = parser.parse_args()

    ece_html = fetch_catalog_details_html(args.ece_source_url)
    cs_html = fetch_catalog_details_html(args.cs_source_url)
    fetched_at = utc_now()
    init_database()
    with SessionLocal() as session:
        ece_result, cs_result, total_distinct_course_count = enrich_catalog_details_html(
            session,
            ece_html,
            cs_html,
            ece_source_url=args.ece_source_url,
            cs_source_url=args.cs_source_url,
            ece_limit=args.ece_limit,
            cs_limit=args.cs_limit,
        )

    manifest_path = write_ingestion_manifest(
        args.artifacts_dir,
        [ece_result, cs_result],
        fetched_at=fetched_at,
        run_id=args.run_id,
        total_distinct_course_count=total_distinct_course_count,
    )
    print(f"Enriched catalog details for {total_distinct_course_count} distinct ECE/CS courses.")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
