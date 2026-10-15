
from collections import Counter
from datetime import datetime, timezone, timedelta

from fastapi import Depends, FastAPI, HTTPException
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Audit, Claim, Note, Policy, StatusHistory, User
from app.schemas import (
    AssignmentCreate,
    ClaimCreate,
    ClaimOut,
    NoteCreate,
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


VALID_STATUSES = {
    "submitted",
    "under_review",
    "approved",
    "denied",
    "closed",
}

TRANSITIONS = {
    "submitted": {"under_review"},
    "under_review": {"approved", "denied"},
    "approved": {"closed"},
    "denied": {"closed"},
    "closed": set(),
}

SLA_TARGET_HOURS = 48


def utc_now() -> datetime:
    """Return the current UTC timestamp."""
    return datetime.now(timezone.utc)


def normalize_datetime(value: datetime | None) -> datetime | None:
    """Make a datetime timezone-aware for safe comparisons."""
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value


def add_audit(
    db: Session,
    user: User,
    action: str,
    resource: str,
) -> None:
    # Avoid storing credentials, claim descriptions, or other user-supplied PII.
    db.add(
        Audit(
            actor_id=user.id,
            action=action,
            resource=resource,
        )
    )


def get_visible_claim(
    db: Session,
    claim_id: int,
    user: User,
) -> Claim:
    claim = db.get(Claim, claim_id)

    if claim is None:
        raise HTTPException(
            status_code=404,
            detail="Claim not found",
        )

    if user.role == "customer" and claim.owner_id != user.id:
        raise HTTPException(
            status_code=404,
            detail="Claim not found",
        )

    if user.role == "adjuster" and claim.assigned_to != user.id:
        raise HTTPException(
            status_code=404,
            detail="Claim not found",
        )

    # Support Agents can look up claims, but mutation endpoints do not
    # grant this role permission to create, assign, or change claim status.
    if user.role == "support_agent":
        return claim

    if user.role not in {"customer", "adjuster", "support_agent", "admin", "reviewer"}:
        raise HTTPException(
            status_code=403,
            detail="Access denied",
        )

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
    user = db.scalar(
        select(User).where(User.username == form.username)
    )

    if (
        user is None
        or not user.active
        or not verify_password(form.password, user.password_hash)
    ):
        raise HTTPException(
            status_code=401,
            detail="Invalid credentials",
        )

    return {
        "access_token": token_for(user),
        "token_type": "bearer",
    }


@app.get("/users/me", tags=["users"])
def get_me(user: User = Depends(current_user)):
    return {
        "id": user.id,
        "username": user.username,
        "role": user.role,
    }


@app.get("/users", tags=["users"])
def list_users(
    db: Session = Depends(get_db),
    user: User = Depends(require("admin", "reviewer")),
):
    return [
        {
            "id": item.id,
            "username": item.username,
            "role": item.role,
            "active": item.active,
        }
        for item in db.scalars(select(User).order_by(User.id))
    ]


@app.get(
    "/policies",
    response_model=list[PolicyOut],
    tags=["policies"],
)
def list_policies(
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return list(db.scalars(select(Policy).order_by(Policy.id)))


@app.post(
    "/claims",
    response_model=ClaimOut,
    status_code=201,
    tags=["claims"],
)
def create_claim(
    data: ClaimCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require("customer", "admin")),
):
    policy = db.get(Policy, data.policy_id)

    if policy is None or not policy.active:
        raise HTTPException(
            status_code=422,
            detail="An active policy is required",
        )

    # Find all active adjusters.
    adjusters = db.scalars(
        select(User)
        .where(
            User.role == "adjuster",
            User.active.is_(True),
        )
        .order_by(User.id)
    ).all()

    if not adjusters:
        raise HTTPException(
            status_code=503,
            detail="No active adjuster is available to assign this claim",
        )

    # Count each adjuster's currently assigned open claims.
    open_statuses = {"submitted", "under_review"}
    claim_counts = {}

    for adjuster in adjusters:
        claim_counts[adjuster.id] = (
            db.scalar(
                select(func.count(Claim.id)).where(
                    Claim.assigned_to == adjuster.id,
                    Claim.status.in_(open_statuses),
                )
            )
            or 0
        )

    # Choose the adjuster with the fewest open claims.
    adjuster = min(
        adjusters,
        key=lambda item: (claim_counts[item.id], item.id),
    )

    # Record submission and initial assignment timestamps.
    now = utc_now()

    claim = Claim(
        policy_id=policy.id,
        owner_id=user.id,
        assigned_to=adjuster.id,
        description=data.description.strip(),
        amount=data.amount,
        status="submitted",
        created_at=now,
        assigned_at=now,
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


@app.get(
    "/claims",
    response_model=list[ClaimOut],
    tags=["claims"],
)
def list_claims(
    policy_number: str | None = None,
    claimant: str | None = None,
    status: str | None = None,
    claim_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    # Join policies so claims can be searched by policy number and holder.
    query = select(Claim).join(Policy, Claim.policy_id == Policy.id)

    # Claim ID is the claim number used for direct lookup.
    if claim_id is not None:
        if claim_id < 1:
            raise HTTPException(
                status_code=422,
                detail="claim_id must be a positive integer",
            )
        query = query.where(Claim.id == claim_id)

    # Preserve the existing customer and adjuster visibility restrictions.
    if user.role == "customer":
        query = query.where(Claim.owner_id == user.id)
    elif user.role == "adjuster":
        query = query.where(Claim.assigned_to == user.id)
    elif user.role not in {"support_agent", "admin", "reviewer"}:
        raise HTTPException(status_code=403, detail="Access denied")

    if policy_number and policy_number.strip():
        query = query.where(
            Policy.number.ilike(f"%{policy_number.strip()}%")
        )

    # The current data model stores the policyholder in Policy.holder.
    # If claimant and policyholder are different people, add claimant_name
    # to Claim and search that field instead.
    if claimant and claimant.strip():
        query = query.where(
            Policy.holder.ilike(f"%{claimant.strip()}%")
        )

    if status and status.strip():
        normalized_status = status.strip().lower()
        if normalized_status not in VALID_STATUSES:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid status. Allowed statuses: {sorted(VALID_STATUSES)}",
            )
        query = query.where(Claim.status == normalized_status)

    query = query.order_by(Claim.id)
    return [claim_response(claim) for claim in db.scalars(query).all()]


@app.get(
    "/claims/{claim_id}",
    response_model=ClaimOut,
    tags=["claims"],
)
def get_claim(
    claim_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    return claim_response(
        get_visible_claim(db, claim_id, user)
    )


@app.post(
    "/claims/{claim_id}/assignment",
    response_model=ClaimOut,
    tags=["assignment"],
)
def assign_claim(
    claim_id: int,
    data: AssignmentCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require("admin", "reviewer")),
):
    claim = get_visible_claim(db, claim_id, user)

    adjuster = db.get(User, data.user_id)

    if (
        adjuster is None
        or not adjuster.active
        or adjuster.role != "adjuster"
    ):
        raise HTTPException(
            status_code=422,
            detail="An active adjuster user is required",
        )

    claim.assigned_to = adjuster.id
    claim.assigned_at = utc_now()

    add_audit(db, user, "assign", "claim")

    db.commit()
    db.refresh(claim)

    return claim_response(claim)


@app.post(
    "/claims/{claim_id}/status",
    response_model=ClaimOut,
    tags=["workflow"],
)
def change_claim_status(
    claim_id: int,
    data: StatusChange,
    db: Session = Depends(get_db),
    user: User = Depends(require("admin", "reviewer", "adjuster")),
):
    claim = get_visible_claim(db, claim_id, user)

    new_status = data.status.strip().lower()

    if new_status not in VALID_STATUSES:
        raise HTTPException(
            status_code=422,
            detail="Unknown claim status",
        )

    override = new_status not in TRANSITIONS.get(
        claim.status,
        set(),
    )

    justification = (data.justification or "").strip()

    if override and (
        user.role != "admin" or not justification
    ):
        raise HTTPException(
            status_code=409,
            detail=(
                "Invalid status transition; an admin override "
                "requires a justification"
            ),
        )

    if (
        new_status in {"approved", "denied"}
        and user.role == "adjuster"
    ):
        raise HTTPException(
            status_code=403,
            detail="Only a reviewer or admin can decide a claim",
        )

    if new_status == claim.status:
        raise HTTPException(
            status_code=409,
            detail="Claim already has this status",
        )

    now = utc_now()
    previous_status = claim.status

    # Record the first decision timestamp.
    if (
        new_status in {"approved", "denied"}
        and claim.decision_at is None
    ):
        claim.decision_at = now

    # Record the first closure timestamp.
    if new_status == "closed" and claim.closed_at is None:
        claim.closed_at = now

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

    add_audit(
        db,
        user,
        "override_status" if override else "change_status",
        "claim",
    )

    db.commit()
    db.refresh(claim)

    return claim_response(claim)


@app.get(
    "/claims/{claim_id}/history",
    tags=["workflow"],
)
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


@app.post(
    "/claims/{claim_id}/notes",
    status_code=201,
    tags=["notes"],
)
def add_claim_note(
    claim_id: int,
    data: NoteCreate,
    db: Session = Depends(get_db),
    user: User = Depends(require("admin", "reviewer", "adjuster")),
):
    get_visible_claim(db, claim_id, user)

    note_text = data.text.strip()

    if not note_text:
        raise HTTPException(
            status_code=422,
            detail="Note cannot be blank",
        )

    note = Note(
        claim_id=claim_id,
        author_id=user.id,
        text=note_text,
    )

    db.add(note)
    add_audit(db, user, "add_note", "claim")

    db.commit()
    db.refresh(note)

    return {
        "id": note.id,
        "claim_id": note.claim_id,
        "author_id": note.author_id,
        "text": note.text,
        "created_at": note.created_at,
    }


@app.get(
    "/claims/{claim_id}/notes",
    tags=["notes"],
)
def list_claim_notes(
    claim_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    get_visible_claim(db, claim_id, user)

    rows = db.scalars(
        select(Note)
        .where(Note.claim_id == claim_id)
        .order_by(Note.id)
    )

    return [
        {
            "id": row.id,
            "claim_id": row.claim_id,
            "author_id": row.author_id,
            "text": row.text,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@app.get(
    "/analytics/summary",
    tags=["analytics"],
)
def analytics_summary(
    db: Session = Depends(get_db),
    user: User = Depends(require("admin", "reviewer")),
):
    claims = list(db.scalars(select(Claim)))
    now = utc_now()
    sla_target = timedelta(hours=SLA_TARGET_HOURS)

    by_status = Counter(claim.status for claim in claims)
    total_amount = sum((claim.amount or 0) for claim in claims)
    assigned_claims = sum(claim.assigned_to is not None for claim in claims)

    claim_tats = []
    adjuster_tats = []
    sla_met = 0
    sla_breached = 0
    overdue_open_claims = 0
    closed_claims = 0
    adjuster_workload = {}

    # Use status history to retain the original decision after a claim is closed.
    # A closed claim may have been either approved or denied.
    decision_by_claim_id = {}
    history_rows = db.scalars(
        select(StatusHistory).order_by(StatusHistory.id)
    ).all()

    for history in history_rows:
        if (
            history.claim_id not in decision_by_claim_id
            and history.new_status in {"approved", "denied"}
        ):
            decision_by_claim_id[history.claim_id] = history.new_status

    # Fallback for existing records that have no decision history.
    for claim in claims:
        if claim.id not in decision_by_claim_id and claim.status in {"approved", "denied"}:
            decision_by_claim_id[claim.id] = claim.status

    approved_claims = sum(
        decision == "approved" for decision in decision_by_claim_id.values()
    )
    rejected_claims = sum(
        decision == "denied" for decision in decision_by_claim_id.values()
    )
    decided_claim_count = approved_claims + rejected_claims

    approval_rate = (
        round(approved_claims / decided_claim_count * 100, 2)
        if decided_claim_count else 0.0
    )
    rejection_rate = (
        round(rejected_claims / decided_claim_count * 100, 2)
        if decided_claim_count else 0.0
    )

    for claim in claims:
        created = normalize_datetime(claim.created_at)
        assigned = normalize_datetime(claim.assigned_at)
        decision = normalize_datetime(claim.decision_at)

        deadline = created + sla_target if created is not None else None

        # Claim TAT and 48-hour SLA: submission -> approval/denial decision.
        if created is not None and decision is not None:
            tat_hours = (decision - created).total_seconds() / 3600
            claim_tats.append(tat_hours)

            if tat_hours <= SLA_TARGET_HOURS:
                sla_met += 1
            else:
                sla_breached += 1

        # Only unresolved claims in these statuses count as overdue.
        elif (
            claim.status in {"submitted", "under_review"}
            and deadline is not None
            and now > deadline
        ):
            overdue_open_claims += 1

        # Adjuster TAT: latest assignment -> approval/denial decision.
        if (
            assigned is not None
            and decision is not None
            and decision >= assigned
        ):
            adjuster_tats.append(
                (decision - assigned).total_seconds() / 3600
            )

        if claim.status == "closed":
            closed_claims += 1

        # Workload per currently assigned adjuster.
        if claim.assigned_to is not None:
            adjuster_id = str(claim.assigned_to)
            stats = adjuster_workload.setdefault(
                adjuster_id,
                {
                    "assigned_claims": 0,
                    "open_claims": 0,
                    "closed_claims": 0,
                },
            )
            stats["assigned_claims"] += 1
            if claim.status == "closed":
                stats["closed_claims"] += 1
            elif claim.status in {"submitted", "under_review", "approved", "denied"}:
                stats["open_claims"] += 1

    return {
        "total_claims": len(claims),
        "by_status": dict(by_status),
        "total_amount": total_amount,
        "average_amount": total_amount / len(claims) if claims else 0.0,
        "assigned_claims": assigned_claims,
        "unassigned_claims": len(claims) - assigned_claims,
        "sla_target_hours": SLA_TARGET_HOURS,
        "closed_claims": closed_claims,
        "decided_claims": decided_claim_count,
        "approved_claims": approved_claims,
        "rejected_claims": rejected_claims,
        "approval_rate_percent": approval_rate,
        "rejection_rate_percent": rejection_rate,
        "sla_met": sla_met,
        "sla_breached": sla_breached,
        "overdue_open_claims": overdue_open_claims,
        "average_claim_tat_hours": (
            round(sum(claim_tats) / len(claim_tats), 2) if claim_tats else None
        ),
        "average_adjuster_tat_hours": (
            round(sum(adjuster_tats) / len(adjuster_tats), 2)
            if adjuster_tats else None
        ),
        "adjuster_workload": adjuster_workload,
    }


@app.get("/audit", tags=["audit"])
def list_audit_logs(
    db: Session = Depends(get_db),
    user: User = Depends(require("admin")),
):
    rows = db.scalars(
        select(Audit)
        .order_by(Audit.id.desc())
        .limit(100)
    )

    return [
        {
            "id": row.id,
            "actor_id": row.actor_id,
            "action": row.action,
            "resource": row.resource,
            "created_at": row.created_at,
        }
        for row in rows
    ]
