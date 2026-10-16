
from sqlalchemy import inspect, text

from app.database import Base, SessionLocal, engine
from app import models  # noqa: F401 - registers all SQLAlchemy models
from app.seed import seed_database
from scripts.create_search_index import main as create_search_index


def migrate_legacy_policy_owner_column() -> None:
    """Add the policy owner column to an existing local database if needed."""
    inspector = inspect(engine)
    if "policies" not in inspector.get_table_names():
        return

    columns = {
        column["name"] for column in inspector.get_columns("policies")
    }

    if "owner_id" not in columns:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "ALTER TABLE policies ADD COLUMN owner_id INTEGER "
                    "REFERENCES users(id)"
                )
            )


def main() -> None:
    migrate_legacy_policy_owner_column()

    Base.metadata.create_all(bind=engine)

    with SessionLocal.begin() as db:
        seed_database(db)

    print("ClaimIQ tables are ready. Demo data was inserted if it was missing.")

    # Ensure the Azure AI Search index exists.
    create_search_index()


if __name__ == "__main__":
    main()
