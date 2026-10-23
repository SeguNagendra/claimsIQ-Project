from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Scan, Subscription, User
from app.schemas.scan import ScanRequest, ScanResponse
from app.services.scan_service import run_scan

router = APIRouter(prefix="/scans", tags=["Scans"])


@router.post("", response_model=ScanResponse, status_code=201)
def create_scan(payload: ScanRequest, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    registered = db.scalar(select(Subscription).where(Subscription.subscription_id == payload.subscription_id, Subscription.is_active.is_(True)))
    if not registered:
        raise HTTPException(status_code=404, detail="Active subscription is not registered in CloudGuard")
    try:
        return run_scan(db, subscription_id=payload.subscription_id, user_id=user.id)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Scan failed: {str(exc)[:500]}")


@router.get("/{scan_id}", response_model=ScanResponse)
def get_scan(scan_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = db.get(Scan, scan_id)
    if not item:
        raise HTTPException(status_code=404, detail="Scan not found")
    return item
