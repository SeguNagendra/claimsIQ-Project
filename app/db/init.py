import hashlib
import json
from sqlalchemy import select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
import psycopg
from psycopg import sql as psycopg_sql

from app.db.base import Base
from app.db.session import engine
from app.core.config import settings
from app.core.security import hash_password
from app.models import User, PolicyRule, AuditLog


def ensure_database_exists() -> None:
    """Create the configured PostgreSQL database if it does not already exist.

    The configured DB user must have CREATEDB permission. The Docker Compose
    PostgreSQL image creates the database on first initialization, so this is
    normally an idempotent safety check for this project.
    """
    url = make_url(settings.database_url)
    if not url.drivername.startswith("postgresql"):
        raise RuntimeError("DATABASE_URL must point to PostgreSQL.")
    database_name = url.database
    if not database_name:
        raise RuntimeError("DATABASE_URL must include a database name.")

    connect_kwargs = {
        "host": url.host or "localhost",
        "port": url.port or 5432,
        "user": url.username,
        "password": url.password,
        "dbname": "postgres",
        "connect_timeout": 5,
    }
    with psycopg.connect(**connect_kwargs, autocommit=True) as conn:
        exists = conn.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            (database_name,),
        ).fetchone()
        if not exists:
            conn.execute(
                psycopg_sql.SQL("CREATE DATABASE {}").format(
                    psycopg_sql.Identifier(database_name)
                )
            )


def create_tables() -> None:
    # Idempotent: creates only tables that do not exist.
    Base.metadata.create_all(bind=engine)


def seed_initial_data(db: Session) -> None:
    users = [
        (settings.seed_admin_username, settings.seed_admin_password, "ADMIN"),
        (settings.seed_engineer_username, settings.seed_engineer_password, "CLOUD_ENGINEER"),
        (settings.seed_security_username, settings.seed_security_password, "SECURITY_OFFICER"),
    ]
    for username, password, role in users:
        existing = db.scalar(select(User).where(User.username == username))
        if not existing:
            db.add(User(username=username, password_hash=hash_password(password), role=role, is_active=True))

    policies = [
        {
            "code": "VM_REQUIRED_ENVIRONMENT_TAG",
            "name": "Require Environment tag on VMs",
            "description": "Every scanned VM must have the Environment tag. Missing tags are set to Environment=dev.",
            "resource_type": "Microsoft.Compute/virtualMachines",
            "severity": "LOW",
            "config": {"required_tag": "Environment", "default_value": "dev", "auto_remediate": True},
        },
        {
            "code": "NSG_INBOUND_ANY_IPV4",
            "name": "Detect NSG inbound rules open to all IPv4",
            "description": "Detect enabled inbound NSG rules whose source address prefix is 0.0.0.0/0.",
            "resource_type": "Microsoft.Network/networkSecurityGroups",
            "severity": "HIGH",
            "config": {"source_prefix": "0.0.0.0/0", "require_approval": True},
        },
    ]
    for policy in policies:
        if not db.scalar(select(PolicyRule).where(PolicyRule.code == policy["code"])):
            db.add(PolicyRule(**policy, enabled=True))

    db.commit()


def initialize_database() -> None:
    # One startup path: create the DB if missing, create tables if missing,
    # then seed initial users and policies.
    ensure_database_exists()
    create_tables()
    from app.db.session import SessionLocal
    db = SessionLocal()
    try:
        seed_initial_data(db)
    finally:
        db.close()
