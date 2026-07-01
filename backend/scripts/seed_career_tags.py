from app.db.init_db import init_database
from app.db.session import SessionLocal
from app.ingestion.career_tags import seed_core_career_tags


def main() -> None:
    init_database()
    with SessionLocal() as session:
        result = seed_core_career_tags(session)

    print(
        "Seeded career tags for "
        f"{result.rows_updated}/{result.rows_seen} configured courses. "
        f"Missing courses: {', '.join(result.missing_course_ids) or 'none'}."
    )


if __name__ == "__main__":
    main()
