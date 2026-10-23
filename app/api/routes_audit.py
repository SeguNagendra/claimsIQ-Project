from fastapi import APIRouter, Depends
from sqlalchemy import select, desc
from sqlalchemy.orm import Session
from app.api.deps import require_roles
from app.db.session import get_db
from app.models import AuditLog, User

router = APIRouter(prefix="/audit-logs", tags=["Audit"])


@router.get("")
def list_audit_logs(limit: int = 100, db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN"))):
    safe_limit = max(1, min(limit, 500))
    rows = db.scalars(select(AuditLog).order_by(desc(AuditLog.id)).limit(safe_limit)).all()
    return [
        {
            "id": row.id, "actor_user_id": row.actor_user_id, "actor_type": row.actor_type,
            "action": row.action, "entity_type": row.entity_type, "entity_id": row.entity_id,
            "details": row.details, "previous_hash": row.previous_hash,
            "entry_hash": row.entry_hash, "created_at": row.created_at,
        } for row in rows
    ]
