from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Finding, User
from app.schemas.finding import FindingResponse

router = APIRouter(prefix="/findings", tags=["Findings"])


@router.get("", response_model=list[FindingResponse])
def list_findings(
    status_filter: str | None = Query(default=None, alias="status"),
    severity: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Finding).order_by(Finding.id.desc())
    if status_filter:
        query = query.where(Finding.status == status_filter.upper())
    if severity:
        query = query.where(Finding.severity == severity.upper())
    return list(db.scalars(query).all())
