import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

import app.bootstrap_admin as bootstrap_admin
from app import models  # noqa: F401 - register SQLAlchemy models
from app.database import Base
from app.models import User
from app.security import verify_password


def test_bootstrap_creates_admin_once(monkeypatch):
    engine = create_engine("sqlite://")
    session_factory = sessionmaker(bind=engine, autoflush=False)
    monkeypatch.setattr(bootstrap_admin, "engine", engine)
    monkeypatch.setattr(bootstrap_admin, "SessionLocal", session_factory)
    monkeypatch.setenv("CLAIMIQ_ADMIN_USERNAME", "initial-admin")
    monkeypatch.setenv("CLAIMIQ_ADMIN_PASSWORD", "first-password")

    bootstrap_admin.main()

    with session_factory() as db:
        user = db.scalar(select(User).where(User.username == "initial-admin"))
        assert user is not None
        assert user.role == "admin"
        assert verify_password("first-password", user.password_hash)

    monkeypatch.setenv("CLAIMIQ_ADMIN_PASSWORD", "replacement-password")
    bootstrap_admin.main()

    with session_factory() as db:
        user = db.scalar(select(User).where(User.username == "initial-admin"))
        assert user is not None
        assert verify_password("first-password", user.password_hash)
        assert not verify_password("replacement-password", user.password_hash)


def test_bootstrap_rejects_existing_non_admin(monkeypatch):
    engine = create_engine("sqlite://")
    session_factory = sessionmaker(bind=engine, autoflush=False)
    Base.metadata.create_all(bind=engine)
    with session_factory.begin() as db:
        db.add(
            User(
                username="existing-user",
                password_hash="unused",
                role="reviewer",
                active=True,
            )
        )
    monkeypatch.setattr(bootstrap_admin, "engine", engine)
    monkeypatch.setattr(bootstrap_admin, "SessionLocal", session_factory)
    monkeypatch.setenv("CLAIMIQ_ADMIN_USERNAME", "existing-user")
    monkeypatch.setenv("CLAIMIQ_ADMIN_PASSWORD", "password")

    with pytest.raises(RuntimeError, match="is not an admin"):
        bootstrap_admin.main()
