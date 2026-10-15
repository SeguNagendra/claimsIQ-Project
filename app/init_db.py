from app.database import Base, SessionLocal, engine
from app import models  # noqa: F401 - registers all SQLAlchemy models
from app.seed import seed_database


def main() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        seed_database(db)
    print("ClaimIQ tables are ready. Demo data was inserted if it was missing.")


if __name__ == "__main__":
    main()
