import hashlib, uuid
from datetime import date
from pathlib import Path
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from app.config import MAX_DOCUMENT_SIZE_BYTES
from app.database import get_db
from app.models import Document, DocumentChunk, DocumentStatus, User
from app.security import require
from app.services.audit_service import add_audit
from app.services.blob_service import BlobStorageService
from app.services.embedding_service import EmbeddingService
from app.services.ingestion_service import IngestionService
from app.services.search_service import SearchService
import logging
router=APIRouter(prefix="/documents",tags=["documents"])
ALLOWED_EXTENSIONS={".pdf",".docx"}
def serialize(doc):
    return {"id":doc.id,"policy_code":doc.policy_code,"document_name":doc.document_name,"original_file_name":doc.original_file_name,"version":doc.version,"status":doc.status.value,"is_active":doc.is_active,"effective_from":doc.effective_from,"processing_error":doc.processing_error}
@router.post("",status_code=201)
async def upload_document(policy_code:str=Form(...,min_length=1,max_length=100),document_name:str=Form(...,min_length=1,max_length=255),version:str=Form(...,min_length=1,max_length=50),effective_from:date=Form(...),replaces_document_id:str|None=Form(None),file:UploadFile=File(...),db:Session=Depends(get_db),user:User=Depends(require("admin"))):
    extension=Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS: raise HTTPException(400,"Only PDF and DOCX files are supported")
    content=await file.read(MAX_DOCUMENT_SIZE_BYTES+1)
    if not content: raise HTTPException(400,"Uploaded file is empty")
    if len(content)>MAX_DOCUMENT_SIZE_BYTES: raise HTTPException(413,"File exceeds the configured upload size limit")
    if replaces_document_id:
        old=db.get(Document,replaces_document_id)
        if old is None: raise HTTPException(404,"Document to replace was not found")
        if old.policy_code!=policy_code: raise HTTPException(422,"Replacement documents must use the same policy code")
    doc_id=str(uuid.uuid4()); safe_name=Path(file.filename or "document").name; blob_path=f"policies/{policy_code}/{version}/{doc_id}/{safe_name}"
    try: BlobStorageService().upload_bytes(blob_path,content,file.content_type or "application/octet-stream")
    except Exception: raise HTTPException(503,"Document storage is unavailable") from None
    doc=Document(id=doc_id,policy_code=policy_code,document_name=document_name,original_file_name=safe_name,blob_path=blob_path,file_type=extension,file_size=len(content),version=version,status=DocumentStatus.UPLOADED,is_active=False,effective_from=effective_from,checksum=hashlib.sha256(content).hexdigest(),uploaded_by=user.id,supersedes_document_id=replaces_document_id)
    try:
        db.add(doc); add_audit(db,user.id,"DOCUMENT_UPLOADED",doc.id); db.commit(); db.refresh(doc)
    except IntegrityError:
        db.rollback(); raise HTTPException(409,"This policy version already exists") from None
    return {"document_id":doc.id,"status":doc.status.value}
logger = logging.getLogger(__name__)
@router.post("/{document_id}/process")
def process_document(
    document_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(require("admin"))
):
    try:
        doc = IngestionService().process(document_id, db, user.id)
        return {
            "document_id": doc.id,
            "status": doc.status.value,
            "is_active": doc.is_active
        }
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from None
    except Exception:
        logger.exception(
            "Document processing failed for document_id=%s",
            document_id
        )
        raise HTTPException(
            503,
            "Document processing failed. Check server logs and configuration."
        ) from None
@router.get("")
def list_documents(db:Session=Depends(get_db),user:User=Depends(require("admin","reviewer","adjuster","support_agent"))):
    return [serialize(d) for d in db.query(Document).order_by(Document.uploaded_at.desc()).all()]
@router.get("/{document_id}")
def get_document(document_id:str,db:Session=Depends(get_db),user:User=Depends(require("admin","reviewer","adjuster","support_agent"))):
    doc=db.get(Document,document_id)
    if doc is None: raise HTTPException(404,"Document not found")
    return serialize(doc)
@router.patch("/{document_id}/activation")
def set_activation(document_id:str,active:bool=Form(...),db:Session=Depends(get_db),user:User=Depends(require("admin"))):
    doc=db.get(Document,document_id)
    if doc is None: raise HTTPException(404,"Document not found")
    chunks=db.query(DocumentChunk).filter(DocumentChunk.document_id==doc.id).all()
    if active:
        if doc.status not in {DocumentStatus.DEACTIVATED,DocumentStatus.ACTIVE}: raise HTTPException(409,"Process the document successfully before activating it")
        if not chunks: raise HTTPException(409,"The document has no processed chunks")
        try:
            embed=EmbeddingService(); records=[]
            for c in chunks: records.append({"id":c.id,"document_id":doc.id,"policy_code":doc.policy_code,"document_name":doc.document_name,"version":doc.version,"chunk_number":c.chunk_number,"chunk_text":c.chunk_text,"page_number":c.page_number,"is_active":True,"content_vector":embed.generate_embedding(c.chunk_text)})
            SearchService().upload_chunks(records)
        except Exception: raise HTTPException(503,"Could not reactivate document in search index") from None
        for c in chunks:c.is_active=True
        doc.status=DocumentStatus.ACTIVE; doc.is_active=True; add_audit(db,user.id,"DOCUMENT_REACTIVATED",doc.id)
    else:
        try: SearchService().deactivate_chunks([c.id for c in chunks])
        except Exception: raise HTTPException(503,"Could not deactivate document in search index") from None
        for c in chunks:c.is_active=False
        doc.status=DocumentStatus.DEACTIVATED; doc.is_active=False; add_audit(db,user.id,"DOCUMENT_DEACTIVATED",doc.id)
    db.commit(); db.refresh(doc); return serialize(doc)
