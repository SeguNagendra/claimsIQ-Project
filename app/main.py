import io
import re
import uuid
from collections import Counter

import pandas as pd
from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from pypdf import PdfReader
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import UPLOAD_DIR
from app.db import get_db
from app.models import Audit, Chunk, Claim, Document, Note, Policy, StatusHistory, User
from app.security import current_user, require, token_for, verify_password

app = FastAPI(title="ClaimIQ Pure Local", version="1.0.0")


class PolicyIn(BaseModel):
    number: str = Field(min_length=1, max_length=80)
    holder: str = Field(min_length=1, max_length=150)
    active: bool = True


class ClaimIn(BaseModel):
    policy_id: int
    description: str = Field(min_length=1)
    amount: int = Field(ge=0)


class AssignmentIn(BaseModel):
    user_id: int


class StatusIn(BaseModel):
    status: str
    justification: str | None = None


class NoteIn(BaseModel):
    text: str = Field(min_length=1)


class DocumentState(BaseModel):
    active: bool
    approved: bool


class Question(BaseModel):
    question: str = Field(min_length=1)


def log(db: Session, user: User, action: str, resource: str) -> None:
    # Only action, resource class and actor ID; never user input, credentials or PII.
    db.add(Audit(actor_id=user.id, action=action, resource=resource))


def visible(db: Session, claim_id: int, user: User) -> Claim:
    claim = db.get(Claim, claim_id)
    if claim is None:
        raise HTTPException(404, "Claim not found")
    if user.role == "customer" and claim.owner_id != user.id:
        raise HTTPException(404, "Claim not found")
    if user.role == "adjuster" and claim.assigned_to != user.id:
        raise HTTPException(404, "Claim not found")
    return claim


def claim_out(c: Claim) -> dict:
    return {"id": c.id, "policy_id": c.policy_id, "owner_id": c.owner_id,
            "assigned_to": c.assigned_to, "description": c.description,
            "amount": c.amount, "status": c.status}


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


@app.post("/auth/token", tags=["auth"])
def login(form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.username == form.username))
    if user is None or not user.active or not verify_password(form.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")
    return {"access_token": token_for(user), "token_type": "bearer"}


@app.get("/users/me", tags=["users"])
def me(user: User = Depends(current_user)):
    return {"id": user.id, "username": user.username, "role": user.role}


@app.get("/users", tags=["users"])
def users(db: Session = Depends(get_db), user: User = Depends(require("admin", "reviewer"))):
    return [{"id": u.id, "username": u.username, "role": u.role} for u in db.scalars(select(User))]


@app.get("/policies", tags=["policies"])
def policies(db: Session = Depends(get_db), user: User = Depends(current_user)):
    return [{"id": p.id, "number": p.number, "active": p.active} for p in db.scalars(select(Policy))]


@app.post("/policies", tags=["policies"])
def create_policy(data: PolicyIn, db: Session = Depends(get_db), user: User = Depends(require("admin"))):
    if db.scalar(select(Policy).where(Policy.number == data.number)):
        raise HTTPException(409, "Policy already exists")
    policy = Policy(**data.model_dump())
    db.add(policy)
    log(db, user, "create", "policy")
    db.commit()
    db.refresh(policy)
    return {"id": policy.id}


@app.post("/claims", tags=["claims"])
def create_claim(data: ClaimIn, db: Session = Depends(get_db), user: User = Depends(require("customer", "admin"))):
    policy = db.get(Policy, data.policy_id)
    if policy is None or not policy.active:
        raise HTTPException(422, "Active policy required")
    claim = Claim(**data.model_dump(), owner_id=user.id)
    db.add(claim)
    log(db, user, "create", "claim")
    db.commit()
    db.refresh(claim)
    return claim_out(claim)


@app.get("/claims", tags=["claims"])
def list_claims(db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = select(Claim)
    if user.role == "customer":
        query = query.where(Claim.owner_id == user.id)
    if user.role == "adjuster":
        query = query.where(Claim.assigned_to == user.id)
    return [claim_out(c) for c in db.scalars(query)]


@app.get("/claims/{claim_id}", tags=["claims"])
def get_claim(claim_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    return claim_out(visible(db, claim_id, user))


@app.post("/claims/{claim_id}/assignment", tags=["assignments"])
def assign(claim_id: int, data: AssignmentIn, db: Session = Depends(get_db), user: User = Depends(require("admin", "reviewer"))):
    claim = visible(db, claim_id, user)
    assignee = db.get(User, data.user_id)
    if assignee is None or not assignee.active or assignee.role != "adjuster":
        raise HTTPException(422, "Active adjuster required")
    claim.assigned_to = assignee.id
    log(db, user, "assign", "claim")
    db.commit()
    return claim_out(claim)


TRANSITIONS = {"submitted": {"under_review"}, "under_review": {"approved", "denied"},
               "approved": {"closed"}, "denied": {"closed"}, "closed": set()}


@app.post("/claims/{claim_id}/status", tags=["status"])
def change_status(claim_id: int, data: StatusIn, db: Session = Depends(get_db),
                  user: User = Depends(require("admin", "reviewer", "adjuster"))):
    claim = visible(db, claim_id, user)
    if data.status not in TRANSITIONS:
        raise HTTPException(422, "Unknown status")
    override = data.status not in TRANSITIONS[claim.status]
    if override and (user.role != "admin" or not data.justification or not data.justification.strip()):
        raise HTTPException(409, "Admin override requires justification")
    if data.status in {"approved", "denied"} and user.role == "adjuster":
        raise HTTPException(403, "Decision requires reviewer or admin")
    db.add(StatusHistory(claim_id=claim.id, actor_id=user.id, old_status=claim.status,
                         new_status=data.status, justification=data.justification if override else None))
    claim.status = data.status
    log(db, user, "override_status" if override else "change_status", "claim")
    db.commit()
    return claim_out(claim)


@app.get("/claims/{claim_id}/history", tags=["status"])
def history(claim_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    visible(db, claim_id, user)
    return [{"id": h.id, "old": h.old_status, "new": h.new_status,
             "justification": h.justification} for h in db.scalars(
                 select(StatusHistory).where(StatusHistory.claim_id == claim_id).order_by(StatusHistory.id))]


@app.post("/claims/{claim_id}/notes", tags=["notes"])
def add_note(claim_id: int, data: NoteIn, db: Session = Depends(get_db),
             user: User = Depends(require("admin", "reviewer", "adjuster"))):
    visible(db, claim_id, user)
    note = Note(claim_id=claim_id, author_id=user.id, text=data.text)
    db.add(note)
    log(db, user, "add_note", "claim")
    db.commit()
    db.refresh(note)
    return {"id": note.id, "text": note.text}


@app.get("/claims/{claim_id}/notes", tags=["notes"])
def notes(claim_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    visible(db, claim_id, user)
    return [{"id": n.id, "text": n.text} for n in db.scalars(select(Note).where(Note.claim_id == claim_id))]


@app.post("/documents", tags=["documents"])
def upload(file: UploadFile = File(...), claim_id: int | None = Form(None),
           db: Session = Depends(get_db), user: User = Depends(require("admin", "reviewer", "adjuster"))):
    if claim_id is not None:
        visible(db, claim_id, user)
    name = (file.filename or "").replace("\\", "/").split("/")[-1]
    extension = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    if extension not in {"pdf", "txt"}:
        raise HTTPException(415, "Only PDF and TXT supported")
    content = file.file.read(5_000_001)
    if len(content) > 5_000_000:
        raise HTTPException(413, "File too large")
    if extension == "pdf" and not content.startswith(b"%PDF-"):
        raise HTTPException(422, "Invalid PDF")
    try:
        text = (PdfReader(io.BytesIO(content)).pages if extension == "pdf" else None)
        extracted = "\n".join(page.extract_text() or "" for page in text) if text is not None else content.decode("utf-8")
    except Exception as exc:
        raise HTTPException(422, "Cannot extract document text") from exc
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    storage = uuid.uuid4().hex + "." + extension
    path = UPLOAD_DIR / storage
    try:
        path.write_bytes(content)
        doc = Document(filename=name[:255], storage_name=storage, claim_id=claim_id)
        db.add(doc)
        db.flush()
        for index, start in enumerate(range(0, min(len(extracted), 100_000), 1000)):
            db.add(Chunk(document_id=doc.id, ordinal=index, text=extracted[start:start + 1000]))
        log(db, user, "upload", "document")
        db.commit()
        return {"id": doc.id, "chunks": min((len(extracted) + 999) // 1000, 100)}
    except Exception:
        db.rollback()
        path.unlink(missing_ok=True)
        raise


@app.get("/documents", tags=["documents"])
def documents(db: Session = Depends(get_db), user: User = Depends(require("admin", "reviewer", "adjuster"))):
    rows = []
    for doc in db.scalars(select(Document)):
        claim = db.get(Claim, doc.claim_id) if doc.claim_id is not None else None
        if user.role == "adjuster" and claim is not None and claim.assigned_to != user.id:
            continue
        rows.append({"id": doc.id, "filename": doc.filename, "active": doc.active, "approved": doc.approved})
    return rows


@app.get("/documents/{document_id}/download", tags=["documents"])
def download(document_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)):
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    if doc.claim_id is not None:
        visible(db, doc.claim_id, user)
    elif user.role == "customer":
        raise HTTPException(403, "Not authorized")
    path = UPLOAD_DIR / doc.storage_name
    if not path.is_file():
        raise HTTPException(404, "File missing")
    return FileResponse(path, filename=doc.filename)


@app.patch("/documents/{document_id}", tags=["documents"])
def set_document(document_id: int, data: DocumentState, db: Session = Depends(get_db),
                 user: User = Depends(require("admin", "reviewer"))):
    doc = db.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, "Document not found")
    doc.active, doc.approved = data.active, data.approved
    log(db, user, "set_document", "document")
    db.commit()
    return {"id": doc.id, "active": doc.active, "approved": doc.approved}


STOP = {"what", "where", "which", "with", "from", "this", "that", "about", "does", "have", "the", "and", "for", "are", "can"}


def terms(text: str) -> set[str]:
    return {x for x in re.findall(r"[a-z0-9]{3,}", text.lower()) if x not in STOP}


@app.post("/rag/ask", tags=["rag"])
def ask(data: Question, db: Session = Depends(get_db), user: User = Depends(current_user)):
    query = terms(data.question)
    results = []
    for chunk, doc in db.execute(select(Chunk, Document).join(Document).where(Document.active.is_(True), Document.approved.is_(True))):
        if doc.claim_id is not None:
            try:
                visible(db, doc.claim_id, user)
            except HTTPException:
                continue
        score = len(query & terms(chunk.text))
        if score:
            results.append((score, chunk, doc))
    results.sort(key=lambda row: (-row[0], row[1].id))
    if not results:
        return {"answer": "No matching approved source found.", "citations": []}
    citations = [{"document_id": doc.id, "chunk_id": chunk.id, "filename": doc.filename}
                 for _, chunk, doc in results[:3]]
    answer = " ".join(chunk.text[:400] for _, chunk, _ in results[:3])
    return {"answer": answer + " " + " ".join(f"[document:{c['document_id']}:chunk:{c['chunk_id']}]" for c in citations),
            "citations": citations}


@app.get("/analytics/summary", tags=["analytics"])
def analytics(db: Session = Depends(get_db), user: User = Depends(require("admin", "reviewer"))):
    frame = pd.DataFrame([{"status": c.status, "amount": c.amount, "assigned": c.assigned_to is not None}
                          for c in db.scalars(select(Claim))])
    if frame.empty:
        return {"total_claims": 0, "by_status": {}, "total_amount": 0, "average_amount": 0, "assigned_claims": 0}
    return {"total_claims": int(len(frame)), "by_status": {str(k): int(v) for k, v in Counter(frame.status).items()},
            "total_amount": int(frame.amount.sum()), "average_amount": float(frame.amount.mean()),
            "assigned_claims": int(frame.assigned.sum())}


@app.get("/audit", tags=["audit"])
def audit(db: Session = Depends(get_db), user: User = Depends(require("admin"))):
    return [{"id": a.id, "actor_id": a.actor_id, "action": a.action, "resource": a.resource}
            for a in db.scalars(select(Audit).order_by(Audit.id.desc()).limit(100))]
