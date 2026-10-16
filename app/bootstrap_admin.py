import os

from sqlalchemy import select

from app import models  # noqa: F401 - register SQLAlchemy models
from app.database import Base, SessionLocal, engine
from app.models import User
from app.security import hash_password


def main() -> None:
    username = os.environ.get("CLAIMIQ_ADMIN_USERNAME", "").strip()
    password = os.environ.get("CLAIMIQ_ADMIN_PASSWORD", "")
    if not username or not password:
        raise RuntimeError(
            "CLAIMIQ_ADMIN_USERNAME and CLAIMIQ_ADMIN_PASSWORD must be set"
        )

    Base.metadata.create_all(bind=engine)
    with SessionLocal.begin() as db:
        existing_user = db.scalar(select(User).where(User.username == username))
        if existing_user is not None:
            if existing_user.role != "admin":
                raise RuntimeError(
                    f"Bootstrap username {username!r} already exists "
                    "and is not an admin"
                )
            print(f"Admin user {username!r} already exists; keeping its password.")
            return

        db.add(
            User(
                username=username,
                password_hash=hash_password(password),
                role="admin",
                active=True,
            )
        )
    print(f"Created initial admin user {username!r}.")


if __name__ == "__main__":
    main()
