import hashlib
import json
from sqlalchemy import select, desc
from sqlalchemy.orm import Session
from app.models import AuditLog


def record_audit(
    db: Session, *, actor_user_id: int | None, actor_type: str = "USER",
    action: str, entity_type: str, entity_id: str | None = None, details: dict | None = None
) -> AuditLog:
    previous = db.scalar(select(AuditLog).order_by(desc(AuditLog.id)).limit(1))
    previous_hash = previous.entry_hash if previous else None
    payload = {
        "actor_user_id": actor_user_id, "actor_type": actor_type, "action": action,
        "entity_type": entity_type, "entity_id": entity_id, "details": details or {},
    }
    canonical = json.dumps({"previous_hash": previous_hash, **payload}, sort_keys=True, default=str)
    entry_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    item = AuditLog(**payload, previous_hash=previous_hash, entry_hash=entry_hash)
    db.add(item)
    db.flush()
    return item
