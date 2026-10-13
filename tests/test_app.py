from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker

from app.config import TEST_DATABASE_URL
from app.db import get_db
from app.main import app as api_app
from app.models import Policy, User
from app.security import hash_password


def test_openapi_and_health():
    client = TestClient(api_app)
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    assert client.get("/redoc").status_code == 200
    assert "/rag/ask" in client.get("/openapi.json").json()["paths"]


def test_hash():
    from app.security import verify_password
    assert verify_password("test", hash_password("test"))
    assert not verify_password("wrong", hash_password("test"))


@pytest.fixture
def database():
    from app.db import Base

    parsed = urlsplit(TEST_DATABASE_URL)
    # Hard fail before any write. Overrides cannot point tests at the development database.
    if parsed.path != "/claimiq_test" or parsed.query or parsed.scheme not in {"postgresql", "postgresql+psycopg2"}:
        pytest.fail("Test-database safety guard: only PostgreSQL claimiq_test is permitted")
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with engine.connect():
            pass
    except OperationalError:
        pytest.skip("PostgreSQL claimiq_test unavailable; integration test not executed")
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)
    def override():
        with session() as db:
            yield db
    api_app.dependency_overrides[get_db] = override
    with session.begin() as db:
        for role in ("admin", "reviewer", "adjuster", "customer"):
            db.add(User(username=role, role=role, password_hash=hash_password("demo123")))
        db.flush()
        db.add(Policy(number="T-01", holder="Synthetic", active=True))
    yield session
    api_app.dependency_overrides.clear()
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_workflow(database, tmp_path, monkeypatch):
    monkeypatch.setattr("app.main.UPLOAD_DIR", tmp_path)
    client = TestClient(api_app)
    def auth(role):
        response = client.post("/auth/token", data={"username": role, "password": "demo123"})
        assert response.status_code == 200
        return {"Authorization": "Bearer " + response.json()["access_token"]}
    headers = {role: auth(role) for role in ("admin", "reviewer", "adjuster", "customer")}
    assert client.get("/users/me", headers=headers["customer"]).json()["role"] == "customer"
    assert client.get("/users", headers=headers["customer"]).status_code == 403
    claim = client.post("/claims", headers=headers["customer"], json={"policy_id": 1, "description": "Test damage", "amount": 100}).json()
    cid = claim["id"]
    assert client.get("/claims", headers=headers["adjuster"]).json() == []
    assert client.post(f"/claims/{cid}/status", headers=headers["adjuster"], json={"status": "under_review"}).status_code == 404
    users = client.get("/users", headers=headers["admin"]).json()
    adjuster_id = next(u["id"] for u in users if u["role"] == "adjuster")
    assert client.post(f"/claims/{cid}/assignment", headers=headers["admin"], json={"user_id": adjuster_id}).status_code == 200
    assert client.post(f"/claims/{cid}/status", headers=headers["adjuster"], json={"status": "under_review"}).status_code == 200
    assert client.post(f"/claims/{cid}/status", headers=headers["adjuster"], json={"status": "approved"}).status_code == 403
    assert client.post(f"/claims/{cid}/status", headers=headers["reviewer"], json={"status": "approved"}).status_code == 200
    assert client.post(f"/claims/{cid}/status", headers=headers["admin"], json={"status": "submitted"}).status_code == 409
    assert client.post(f"/claims/{cid}/status", headers=headers["admin"], json={"status": "submitted", "justification": "Correction"}).status_code == 200
    assert len(client.get(f"/claims/{cid}/history", headers=headers["customer"]).json()) == 3
    assert client.post(f"/claims/{cid}/notes", headers=headers["adjuster"], json={"text": "Checked"}).status_code == 200
    assert client.post("/documents", headers=headers["reviewer"], files={"file": ("policy.txt", b"Covered water damage has a deductible of 500 dollars.")}).status_code == 200
    assert client.post("/rag/ask", headers=headers["customer"], json={"question": "water deductible"}).json()["citations"] == []
    did = client.get("/documents", headers=headers["reviewer"]).json()[0]["id"]
    client.patch(f"/documents/{did}", headers=headers["reviewer"], json={"active": True, "approved": True})
    assert client.post("/rag/ask", headers=headers["customer"], json={"question": "water deductible"}).json()["citations"]
    assert not client.post("/rag/ask", headers=headers["customer"], json={"question": "galactic platypus"}).json()["citations"]
    assert client.get("/analytics/summary", headers=headers["admin"]).json()["total_claims"] == 1
    assert client.get("/audit", headers=headers["admin"]).status_code == 200
    assert client.get("/audit", headers=headers["customer"]).status_code == 403
