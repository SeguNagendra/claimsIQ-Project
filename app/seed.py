
from sqlalchemy import select

from app.db import SessionLocal
from app.models import Claim, Policy, User
from app.security import hash_password
from app.database import Base, engine
from app import models

# Create tables from all registered SQLAlchemy models
Base.metadata.create_all(bind=engine)

DEMO_USERS = {
    "admin": "admin",
    "reviewer": "reviewer",
    "customer": "customer",
    "adjuster1": "adjuster",
    "adjuster2": "adjuster",
    "adjuster3": "adjuster",
    "adjuster4": "adjuster",
    "adjuster5": "adjuster",
    "support_agent": "support_agent"
}


def seed() -> None:
    with SessionLocal.begin() as db:

        # 1. Create demo users if they do not already exist.
        for username, role in DEMO_USERS.items():
            existing_user = db.scalar(
                select(User).where(User.username == username)
            )

            if existing_user is None:
                db.add(
                    User(
                        username=username,
                        role=role,
                        password_hash=hash_password("demo123"),
                    )
                )

        db.flush()

        # 2. Keep an existing demo policy as POL-0001 when possible.
        old_demo_policy = db.scalar(
            select(Policy).where(Policy.number == "DEMO-001")
        )
        first_policy = db.scalar(
            select(Policy).where(Policy.number == "POL-0001")
        )

        if first_policy is None and old_demo_policy is not None:
            old_demo_policy.number = "POL-0001"
            old_demo_policy.holder = "Sample Customer 001"
            old_demo_policy.active = True

        # 3. Create 50 sample policies without duplicating them.
        for i in range(1, 51):
            policy_number = f"POL-{i:04d}"

            existing_policy = db.scalar(
                select(Policy).where(Policy.number == policy_number)
            )

            if existing_policy is None:
                db.add(
                    Policy(
                        number=policy_number,
                        holder=f"Sample Customer {i:03d}",
                        active=True,
                    )
                )

        db.flush()

        # 4. Get the first sample policy and demo customer.
        first_policy = db.scalar(
            select(Policy).where(Policy.number == "POL-0001")
        )

        customer = db.scalar(
            select(User).where(User.username == "customer")
        )

        # 5. Create a demo claim if one does not already exist
        # for this customer and policy.
        if first_policy is not None and customer is not None:
            existing_claim = db.scalar(
                select(Claim).where(
                    Claim.policy_id == first_policy.id,
                    Claim.owner_id == customer.id,
                )
            )

            if existing_claim is None:
                db.add(
                    Claim(
                        policy_id=first_policy.id,
                        owner_id=customer.id,
                        description="Synthetic water damage",
                        amount=1200,
                    )
                )


if __name__ == "__main__":
    seed()
    print("ClaimIQ seed completed successfully.")
