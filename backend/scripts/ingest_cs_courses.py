import argparse
from pathlib import Path

from app.db.init_db import init_database
from app.db.session import SessionLocal
from app.ingestion.course_catalog import utc_now, write_ingestion_manifest
from app.ingestion.cs_catalog import (
    CS_COURSES_SOURCE_URL,
    fetch_cs_courses_html,
    ingest_cs_courses_html,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest official UIUC CS course catalog records.")
    parser.add_argument("--limit", type=int, help="Maximum unique courses; omit for all parsed rows.")
    parser.add_argument("--source-url", default=CS_COURSES_SOURCE_URL)
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts/ingestion"))
    parser.add_argument("--run-id", help="Optional deterministic artifact directory name.")
    args = parser.parse_args()

    html_text = fetch_cs_courses_html(args.source_url)
    fetched_at = utc_now()
    init_database()
    with SessionLocal() as session:
        result = ingest_cs_courses_html(
            session,
            html_text,
            limit=args.limit,
            source_url=args.source_url,
        )

    manifest_path = write_ingestion_manifest(
        args.artifacts_dir,
        [result],
        fetched_at=fetched_at,
        run_id=args.run_id,
    )
    print(
        "Ingested "
        f"{result.rows_ingested} CS catalog rows from {result.source_url} "
        f"after parsing {result.rows_seen} course rows."
    )
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
