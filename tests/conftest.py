import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import Base, get_db
from app.main import app
from app.models import Policy, User
from app.security import hash_password


@pytest.fixture()
def client():
    # A private in-memory database per test fixture. This cannot touch PostgreSQL.
    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    with TestingSessionLocal.begin() as db:
        for role in ("admin", "reviewer", "adjuster", "customer", "customer2"):
            db.add(User(username=role, role="customer" if role == "customer2" else role,
                        password_hash=hash_password("demo123"), active=True))
        db.flush()
        db.add(Policy(number="TEST-001", holder="Test Policy Holder", active=True))
        db.add(Policy(number="INACTIVE-001", holder="Inactive Holder", active=False))

    def override_get_db():
        with TestingSessionLocal() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


@pytest.fixture()
def auth_headers(client):
    def login_as(username: str) -> dict[str, str]:
        response = client.post(
            "/auth/token",
            data={"username": username, "password": "demo123"},
        )
        assert response.status_code == 200, response.text
        return {"Authorization": f"Bearer {response.json()['access_token']}"}
    return login_as
