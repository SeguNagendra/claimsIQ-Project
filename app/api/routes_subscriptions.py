from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models import Subscription, User
from app.schemas.subscription import SubscriptionCreate, SubscriptionResponse
from app.services.audit_service import record_audit

router = APIRouter(prefix="/subscriptions", tags=["Subscriptions"])


@router.get("", response_model=list[SubscriptionResponse])
def list_subscriptions(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return list(db.scalars(select(Subscription).order_by(Subscription.id)).all())


@router.post("", response_model=SubscriptionResponse, status_code=201)
def create_subscription(payload: SubscriptionCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("ADMIN"))):
    existing = db.scalar(select(Subscription).where(Subscription.subscription_id == payload.subscription_id))
    if existing:
        raise HTTPException(status_code=409, detail="Subscription already registered")
    item = Subscription(name=payload.name, subscription_id=payload.subscription_id)
    db.add(item)
    db.flush()
    record_audit(db, actor_user_id=user.id, action="SUBSCRIPTION_REGISTERED", entity_type="Subscription", entity_id=str(item.id), details={"subscription_id": item.subscription_id})
    db.commit()
    db.refresh(item)
    return item
