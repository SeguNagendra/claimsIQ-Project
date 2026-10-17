from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.database import Base, engine, SessionLocal
from app import models  # noqa: F401 - ensure all models are registered
from app.models import Claim, Policy, StatusHistory, User, utc_now
from app.security import hash_password


DEMO_USERS = {
    "admin": "admin",
    "reviewer": "reviewer",
    "customer": "customer",
    "adjuster1": "adjuster",
    "adjuster2": "adjuster",
    "adjuster3": "adjuster",
    "adjuster4": "adjuster",
    "adjuster5": "adjuster",
    "support_agent": "support_agent",
    **{f"customer{i}": "customer" for i in range(2, 51)},
}


def customer_username_for_policy(policy_number_index: int) -> str:
    return "customer" if policy_number_index == 1 else f"customer{policy_number_index}"


def seed_database(db: Session) -> None:
    """Insert demo users, owned policies, and one workflow-consistent claim."""
    for username, role in DEMO_USERS.items():
        existing_user = db.scalar(select(User).where(User.username == username))
        if existing_user is None:
            db.add(
                User(
                    username=username,
                    role=role,
                    password_hash=hash_password("demo123"),
                    active=True,
                )
            )
    db.flush()

    # Preserve the earlier demo policy number when upgrading an existing local DB.
    old_demo_policy = db.scalar(select(Policy).where(Policy.number == "DEMO-001"))
    first_policy = db.scalar(select(Policy).where(Policy.number == "POL-0001"))
    if first_policy is None and old_demo_policy is not None:
        old_demo_policy.number = "POL-0001"
        old_demo_policy.holder = "Sample Customer 001"
        first_policy = old_demo_policy
        # SessionLocal disables autoflush, so persist the rename before querying
        # for POL-0001 in the loop below.
        db.flush()

    # Create the sample policies and explicitly associate each with its customer.
    for i in range(1, 51):
        policy_number = f"POL-{i:04d}"
        customer_username = customer_username_for_policy(i)
        owner = db.scalar(select(User).where(User.username == customer_username))
        policy = db.scalar(select(Policy).where(Policy.number == policy_number))

        if policy is None:
            policy = Policy(
                number=policy_number,
                holder=f"Sample Customer {i:03d}",
                owner_id=owner.id if owner else None,
                active=True,
            )
            db.add(policy)
        elif policy.owner_id is None and owner is not None:
            # Only backfill known demo policies; do not guess ownership for
            # arbitrary legacy policies.
            policy.owner_id = owner.id
    db.flush()

    first_policy = db.scalar(select(Policy).where(Policy.number == "POL-0001"))
    customer = db.scalar(select(User).where(User.username == "customer"))
    if first_policy is None or customer is None:
        return

    existing_claim = db.scalar(
        select(Claim).where(
            Claim.policy_id == first_policy.id,
            Claim.owner_id == customer.id,
        )
    )
    if existing_claim is not None:
        return

    adjusters = db.scalars(
        select(User)
        .where(User.role == "adjuster", User.active.is_(True))
        .order_by(User.id)
    ).all()
    if not adjusters:
        # Leave the sample claim uncreated if no adjuster exists. API submission
        # itself returns 503 when there is nobody available to assign a claim.
        return

    open_statuses = ("submitted", "under_review")
    counts = {}
    for adjuster in adjusters:
        counts[adjuster.id] = db.scalar(
            select(func.count(Claim.id)).where(
                Claim.assigned_to == adjuster.id,
                Claim.status.in_(open_statuses),
            )
        ) or 0
    adjuster = min(adjusters, key=lambda item: (counts[item.id], item.id))
    now = utc_now()
    claim = Claim(
        policy_id=first_policy.id,
        owner_id=customer.id,
        assigned_to=adjuster.id,
        description="Synthetic water damage",
        amount=1200,
        status="submitted",
        created_at=now,
        assigned_at=now,
    )
    db.add(claim)
    db.flush()
    db.add(
        StatusHistory(
            claim_id=claim.id,
            actor_id=customer.id,
            old_status=None,
            new_status="submitted",
            justification="Initial submission (seed data)",
        )
    )


def seed() -> None:
    Base.metadata.create_all(bind=engine)
    with SessionLocal.begin() as db:
        seed_database(db)


if __name__ == "__main__":
    seed()
    print("ClaimIQ seed completed successfully.")
