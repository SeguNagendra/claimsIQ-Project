from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Claim, Policy, StatusHistory, User
from app.security import hash_password

DEMO_USERS = {
    "admin": "admin",
    "reviewer": "reviewer",
    "adjuster": "adjuster",
    "customer": "customer",
}


def seed_database(db: Session) -> None:
    for username, role in DEMO_USERS.items():
        if db.scalar(select(User).where(User.username == username)) is None:
            db.add(User(username=username, role=role, password_hash=hash_password("demo123"), active=True))
    db.flush()

    policy = db.scalar(select(Policy).where(Policy.number == "DEMO-001"))
    if policy is None:
        policy = Policy(number="DEMO-001", holder="Synthetic Customer", active=True)
        db.add(policy)
        db.flush()

    customer = db.scalar(select(User).where(User.username == "customer"))
    claim = db.scalar(select(Claim).where(Claim.description == "Synthetic water damage"))
    if customer is not None and claim is None:
        claim = Claim(
            policy_id=policy.id,
            owner_id=customer.id,
            description="Synthetic water damage",
            amount=1200,
            status="submitted",
        )
        db.add(claim)
        db.flush()
        db.add(
            StatusHistory(
                claim_id=claim.id,
                actor_id=customer.id,
                old_status=None,
                new_status="submitted",
                justification="Initial submission",
            )
        )
    db.commit()
