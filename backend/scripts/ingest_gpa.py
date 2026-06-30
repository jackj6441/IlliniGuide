import argparse

from app.db.init_db import init_database
from app.db.session import SessionLocal
from app.ingestion.gpa import WAF_GPA_SOURCE_URL, fetch_waf_gpa_csv, ingest_waf_gpa_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest WAF UIUC GPA records.")
    parser.add_argument("--limit", type=int, default=20)
    parser.add_argument("--source-url", default=WAF_GPA_SOURCE_URL)
    args = parser.parse_args()

    csv_text = fetch_waf_gpa_csv(args.source_url)
    init_database()
    with SessionLocal() as session:
        result = ingest_waf_gpa_csv(
            session,
            csv_text,
            limit=args.limit,
            source_url=args.source_url,
        )

    print(
        "Ingested "
        f"{result.rows_ingested} GPA rows from {result.source_url} "
        f"after scanning {result.rows_seen} CSV rows."
    )


if __name__ == "__main__":
    main()
