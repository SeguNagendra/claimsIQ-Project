from sqlalchemy import select

from app.db import SessionLocal
from app.models import Claim, Policy, User
from app.security import hash_password

DEMO = {"admin": "admin", "adjuster": "adjuster", "reviewer": "reviewer", "customer": "customer"}


def seed() -> None:
    with SessionLocal.begin() as db:
        for username, role in DEMO.items():
            if not db.scalar(select(User).where(User.username == username)):
                db.add(User(username=username, role=role, password_hash=hash_password("demo123")))
        db.flush()
        policy = db.scalar(select(Policy).where(Policy.number == "DEMO-001"))
        if policy is None:
            policy = Policy(number="DEMO-001", holder="Synthetic Customer", active=True)
            db.add(policy)
            db.flush()
        owner = db.scalar(select(User).where(User.username == "customer"))
        if owner is not None and not db.scalar(select(Claim).where(Claim.policy_id == policy.id)):
            db.add(Claim(policy_id=policy.id, owner_id=owner.id, description="Synthetic water damage", amount=1200))


if __name__ == "__main__":
    seed()
    print("Demo data seeded (idempotent)")
