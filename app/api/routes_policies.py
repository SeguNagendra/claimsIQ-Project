from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import PolicyRule, User
from app.schemas.policy import PolicyResponse

router = APIRouter(prefix="/policies", tags=["Policies"])


@router.get("", response_model=list[PolicyResponse])
def list_policies(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return list(db.scalars(select(PolicyRule).order_by(PolicyRule.id)).all())


@router.patch("/{policy_id}/enabled")
def set_policy_enabled(policy_id: int, enabled: bool, db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN"))):
    policy = db.get(PolicyRule, policy_id)
    if not policy:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Policy not found")
    policy.enabled = enabled
    db.commit()
    return {"id": policy.id, "code": policy.code, "enabled": policy.enabled}
