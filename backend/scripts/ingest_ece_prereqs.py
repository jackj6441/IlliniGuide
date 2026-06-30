import argparse

from app.db.init_db import init_database
from app.db.session import SessionLocal
from app.ingestion.ece_prereqs import (
    ECE_COURSES_SOURCE_URL,
    fetch_ece_courses_html,
    ingest_ece_prereqs_html,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest ECE course prerequisites.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--source-url", default=ECE_COURSES_SOURCE_URL)
    args = parser.parse_args()

    html_text = fetch_ece_courses_html(args.source_url)
    init_database()
    with SessionLocal() as session:
        result = ingest_ece_prereqs_html(
            session,
            html_text,
            limit=args.limit,
            source_url=args.source_url,
        )

    print(
        "Ingested "
        f"{result.rows_ingested} ECE prerequisite rows from {result.source_url} "
        f"after scanning {result.rows_seen} parsed course rows."
    )


if __name__ == "__main__":
    main()
