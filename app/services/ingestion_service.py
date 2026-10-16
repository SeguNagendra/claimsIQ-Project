from datetime import datetime, timezone
from sqlalchemy.orm import Session
from app.models import Document, DocumentChunk, DocumentStatus
from app.services.audit_service import add_audit
from app.services.blob_service import BlobStorageService
from app.services.chunking_service import ChunkingService
from app.services.embedding_service import EmbeddingService
from app.services.extraction_service import TextExtractionService
from app.services.search_service import SearchService
class IngestionService:
    def process(self, document_id: str, db: Session, actor_id: int):
        document=db.get(Document,document_id)
        if document is None: raise ValueError("Document not found")
        if document.status==DocumentStatus.ACTIVE and document.is_active:return document
        document.status=DocumentStatus.PROCESSING; document.processing_error=None
        add_audit(db,actor_id,"DOCUMENT_PROCESSING_STARTED",document.id); db.commit()
        try:
            pages=TextExtractionService().extract(BlobStorageService().download_bytes(document.blob_path),document.file_type)
            if not pages: raise ValueError("No text could be extracted. Scanned PDFs require OCR.")
            raw=ChunkingService().chunk_pages(pages)
            if not raw: raise ValueError("No valid text chunks were created")
            embeddings=EmbeddingService(); rows=[]; records=[]
            for item in raw:
                row=DocumentChunk(document_id=document.id,chunk_number=item["chunk_number"],chunk_text=item["chunk_text"],page_number=item["page_number"],is_active=True)
                db.add(row); db.flush(); rows.append(row)
                records.append({"id":row.id,"document_id":document.id,"policy_code":document.policy_code,"document_name":document.document_name,"version":document.version,"chunk_number":row.chunk_number,"chunk_text":row.chunk_text,"page_number":row.page_number,"is_active":True,"content_vector":embeddings.generate_embedding(row.chunk_text)})
            search=SearchService(); search.upload_chunks(records)
            if document.supersedes_document_id:
                old=db.get(Document,document.supersedes_document_id)
                if old:
                    old_chunks=db.query(DocumentChunk).filter(DocumentChunk.document_id==old.id).all()
                    search.deactivate_chunks([c.id for c in old_chunks])
                    for c in old_chunks:c.is_active=False
                    old.status=DocumentStatus.SUPERSEDED; old.is_active=False; old.effective_to=document.effective_from
                    add_audit(db,actor_id,"DOCUMENT_SUPERSEDED",old.id)
            document.status=DocumentStatus.ACTIVE; document.is_active=True; document.processed_at=datetime.now(timezone.utc)
            add_audit(db,actor_id,"DOCUMENT_ACTIVATED",document.id); db.commit(); db.refresh(document); return document
        except Exception as exc:
            db.rollback(); failed=db.get(Document,document_id)
            if failed:
                failed.status=DocumentStatus.FAILED; failed.is_active=False; failed.processing_error=str(exc)[:2000]
                add_audit(db,actor_id,"DOCUMENT_PROCESSING_FAILED",failed.id); db.commit()
            raise
