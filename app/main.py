from collections import Counter

import pandas as pd
from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Audit, Claim, Note, Policy, StatusHistory, User
from app.schemas import (
    AssignmentCreate,
    ClaimCreate,
    ClaimOut,
    NoteCreate,
    PolicyCreate,
    PolicyOut,
    StatusChange,
)
from app.security import current_user, require, token_for, verify_password

app = FastAPI(
    title="ClaimIQ Claims Management API",
    description=(
        "Local API for users, policies, claims, assignment, workflow, notes, "
        "audit and analytics. Document Management and RAG are separate future modules."
    ),
    version="1.0.0",
)

VALID_STATUSES = {"submitted", "under_review", "approved", "denied", "closed"}
TRANSITIONS = {
    "submitted": {"under_review"},
    "under_review": {"approved", "denied"},
    "approved": {"closed"},
    "denied": {"closed"},
    "closed": set(),
}


def add_audit(db: Session, user: User, action: str, resource: str) -> None:
    # Avoid storing credentials, claim descriptions, or other user-supplied PII in the audit record.
    db.add(Audit(actor_id=user.id, action=action, resource=resource))


def get_visible_claim(db: Session, claim_id: int, user: User) -> Claim:
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail="Claim not found")
    if user.role == "customer" and claim.owner_id != user.id:
        raise HTTPException(status_code=404, detail="Claim not found")
    if user.role == "adjuster" and claim.assigned_to != user.id:
        raise HTTPException(status_code=404, detail="Claim not found")
    return claim


def claim_response(claim: Claim) -> dict:
    return {
        "id": claim.id,
        "policy_id": claim.policy_id,
        "owner_id": claim.owner_id,
        "assigned_to": claim.assigned_to,
        "description": claim.description,
        "amount": claim.amount,
        "status": claim.status,
    }


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


@app.post("/auth/token", tags=["authentication"])
def login(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.scalar(select(User).where(User.username == form.username))
    if user is None or not user.active or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    return {"access_token": token_for(user), "token_type": "bearer"}


@app.get("/users/me", tags=["users"])
def get_me(user: User = Depends(current_user)):
    return {"id": user.id, "username": user.username, "role": user.role}


@app.get("/users", tags=["users"])
def list_users(
    db: Session = Depends(get_db),
    user: User = Depends(require("admin", "reviewer")),
):
    return [
        {"id": item.id, "username": item.username, "role": item.role, "active": item.active}
        for item in db.scalars(select(User).order_by(User.id))
    ]


@app.get("/policies", response_model=list[PolicyOut], tags=["policies"])
def list_policies(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return list(db.scalars(select(Policy).order_by(Policy.id)))


@app.post("/policies", response_model=PolicyOut, status_code=201, tags=["policies"])
def create_policy(
    data: PolicyCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require("admin")),
):
    if db.scalar(select(Policy).where(Policy.number == data.number)) is not None:
        raise HTTPException(status_code=409, detail="Policy number already exists")
    policy = Policy(number=data.number.strip(), holder=data.holder.strip(), active=data.active)
    if not policy.number or not policy.holder:
        raise HTTPException(status_code=422, detail="Policy number and holder cannot be blank")
    db.add(policy)
    add_audit(db, user, "create", "policy")
    db.commit()
    db.refresh(policy)
    return policy


@app.post("/claims", response_model=ClaimOut, status_code=201, tags=["claims"])
def create_claim(
    data: ClaimCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require("customer", "admin")),
):
    policy = db.get(Policy, data.policy_id)
    if policy is None or not policy.active:
        raise HTTPException(status_code=422, detail="An active policy is required")
    claim = Claim(
        policy_id=policy.id,
        owner_id=user.id,
        description=data.description.strip(),
        amount=data.amount,
        status="submitted",
    )
    db.add(claim)
    db.flush()
    db.add(
        StatusHistory(
            claim_id=claim.id,
            actor_id=user.id,
            old_status=None,
            new_status="submitted",
            justification="Initial submission",
        )
    )
    add_audit(db, user, "create", "claim")
    db.commit()
    db.refresh(claim)
    return claim_response(claim)


@app.get("/claims", response_model=list[ClaimOut], tags=["claims"])
def list_claims(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    query = select(Claim).order_by(Claim.id)
    if user.role == "customer":
        query = query.where(Claim.owner_id == user.id)
    elif user.role == "adjuster":
        query = query.where(Claim.assigned_to == user.id)
    return [claim_response(claim) for claim in db.scalars(query)]


@app.get("/claims/{claim_id}", response_model=ClaimOut, tags=["claims"])
def get_claim(
    claim_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return claim_response(get_visible_claim(db, claim_id, user))


@app.post("/claims/{claim_id}/assignment", response_model=ClaimOut, tags=["assignment"])
def assign_claim(
    claim_id: int,
    data: AssignmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require("admin", "reviewer")),
):
    claim = get_visible_claim(db, claim_id, user)
    adjuster = db.get(User, data.user_id)
    if adjuster is None or not adjuster.active or adjuster.role != "adjuster":
        raise HTTPException(status_code=422, detail="An active adjuster user is required")
    claim.assigned_to = adjuster.id
    add_audit(db, user, "assign", "claim")
    db.commit()
    db.refresh(claim)
    return claim_response(claim)


@app.post("/claims/{claim_id}/status", response_model=ClaimOut, tags=["workflow"])
def change_claim_status(
    claim_id: int,
    data: StatusChange,
    db: Session = Depends(get_db),
    user: User = Depends(require("admin", "reviewer", "adjuster")),
):
    claim = get_visible_claim(db, claim_id, user)
    new_status = data.status.strip().lower()
    if new_status not in VALID_STATUSES:
        raise HTTPException(status_code=422, detail="Unknown claim status")

    override = new_status not in TRANSITIONS.get(claim.status, set())
    justification = (data.justification or "").strip()
    if override and (user.role != "admin" or not justification):
        raise HTTPException(
            status_code=409,
            detail="Invalid status transition; an admin override requires a justification",
        )
    if new_status in {"approved", "denied"} and user.role == "adjuster":
        raise HTTPException(status_code=403, detail="Only a reviewer or admin can decide a claim")
    if new_status == claim.status:
        raise HTTPException(status_code=409, detail="Claim already has this status")

    previous_status = claim.status
    claim.status = new_status
    db.add(
        StatusHistory(
            claim_id=claim.id,
            actor_id=user.id,
            old_status=previous_status,
            new_status=new_status,
            justification=justification if override else None,
        )
    )
    add_audit(db, user, "override_status" if override else "change_status", "claim")
    db.commit()
    db.refresh(claim)
    return claim_response(claim)


@app.get("/claims/{claim_id}/history", tags=["workflow"])
def get_claim_history(
    claim_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    get_visible_claim(db, claim_id, user)
    rows = db.scalars(
        select(StatusHistory)
        .where(StatusHistory.claim_id == claim_id)
        .order_by(StatusHistory.id)
    )
    return [
        {
            "id": row.id,
            "old_status": row.old_status,
            "new_status": row.new_status,
            "justification": row.justification,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@app.post("/claims/{claim_id}/notes", status_code=201, tags=["notes"])
def add_claim_note(
    claim_id: int,
    data: NoteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require("admin", "reviewer", "adjuster")),
):
    get_visible_claim(db, claim_id, user)
    note_text = data.text.strip()
    if not note_text:
        raise HTTPException(status_code=422, detail="Note cannot be blank")
    note = Note(claim_id=claim_id, author_id=user.id, text=note_text)
    db.add(note)
    add_audit(db, user, "add_note", "claim")
    db.commit()
    db.refresh(note)
    return {"id": note.id, "claim_id": note.claim_id, "author_id": note.author_id,
            "text": note.text, "created_at": note.created_at}


@app.get("/claims/{claim_id}/notes", tags=["notes"])
def list_claim_notes(
    claim_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    get_visible_claim(db, claim_id, user)
    rows = db.scalars(
        select(Note).where(Note.claim_id == claim_id).order_by(Note.id)
    )
    return [
        {"id": row.id, "claim_id": row.claim_id, "author_id": row.author_id,
         "text": row.text, "created_at": row.created_at}
        for row in rows
    ]


@app.get("/analytics/summary", tags=["analytics"])
def analytics_summary(
    db: Session = Depends(get_db),
    user: User = Depends(require("admin", "reviewer")),
):
    claims = list(db.scalars(select(Claim)))
    if not claims:
        return {
            "total_claims": 0,
            "by_status": {},
            "total_amount": 0,
            "average_amount": 0.0,
            "assigned_claims": 0,
            "unassigned_claims": 0,
        }

    frame = pd.DataFrame(
        [{"status": claim.status, "amount": claim.amount, "assigned": claim.assigned_to is not None}
         for claim in claims]
    )
    status_counts = {str(k): int(v) for k, v in Counter(frame["status"]).items()}
    return {
        "total_claims": int(len(frame)),
        "by_status": status_counts,
        "total_amount": int(frame["amount"].sum()),
        "average_amount": float(frame["amount"].mean()),
        "assigned_claims": int(frame["assigned"].sum()),
        "unassigned_claims": int((~frame["assigned"]).sum()),
    }


@app.get("/audit", tags=["audit"])
def list_audit_logs(
    db: Session = Depends(get_db),
    user: User = Depends(require("admin")),
):
    rows = db.scalars(select(Audit).order_by(Audit.id.desc()).limit(100))
    return [
        {"id": row.id, "actor_id": row.actor_id, "action": row.action,
         "resource": row.resource, "created_at": row.created_at}
        for row in rows
    ]
