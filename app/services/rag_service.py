import re
import time
from app.config import AZURE_OPENAI_CHAT_DEPLOYMENT, RAG_MIN_SEARCH_SCORE
from app.models import ChatQueryLog
from app.prompts.rag_prompt import NO_MATCH, SYSTEM_PROMPT
from app.services.azure_auth import get_openai_client
from app.services.embedding_service import EmbeddingService
from app.services.search_service import SearchService
def redact_sensitive_data(value: str) -> str:
    """Redact common personal identifiers before persisting AI-query logs."""
    value = re.sub(r"\b[0-9]{12}\b", "[REDACTED_ID]", value)  # Aadhaar-like IDs
    value = re.sub(r"(?<!\d)(?:\+?91[- ]?)?[6-9]\d{9}(?!\d)", "[REDACTED_PHONE]", value)
    value = re.sub(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b", "[REDACTED_EMAIL]", value)
    return value

class RagService:
    def answer(self, question, db, user_id: int, policy_code=None):
        started=time.perf_counter(); sources=[]; answer=NO_MATCH; status="NO_MATCH"
        try:
            vector=EmbeddingService().generate_embedding(question)
            matches=SearchService().search(vector,policy_code=policy_code)
            retrieved_matches = list(matches)
            if RAG_MIN_SEARCH_SCORE > 0:
                matches = [m for m in retrieved_matches if float(m.get("search_score") or 0) >= RAG_MIN_SEARCH_SCORE]
                if retrieved_matches and not matches:
                    status = "LOW_CONFIDENCE"
            if matches:
                context=[]
                for m in matches:
                    page=m.get("page_number")
                    context.append(f"Source: {m['document_name']} (version {m['version']}, page {page if page is not None else 'not available'})\nContent: {m['chunk_text']}")
                    sources.append({"document_id":m["document_id"],"document_name":m["document_name"],"version":m["version"],"page_number":page,"chunk_id":m["id"]})
                if not AZURE_OPENAI_CHAT_DEPLOYMENT: raise ValueError("AZURE_OPENAI_CHAT_DEPLOYMENT is missing from .env")
                response=get_openai_client().responses.create(model=AZURE_OPENAI_CHAT_DEPLOYMENT,instructions=SYSTEM_PROMPT,input="POLICY CONTEXT (approved documents only):\n"+"\n\n---\n\n".join(context)+f"\n\nUSER QUESTION:\n{question}")
                answer=(getattr(response,"output_text",None) or "").strip()
                if answer: status="ANSWERED"
                else: answer=NO_MATCH; status="LOW_CONFIDENCE"
        except Exception:
            elapsed=int((time.perf_counter()-started)*1000)
            log=ChatQueryLog(user_id=user_id,question=redact_sensitive_data(question),answer="The policy assistant is temporarily unavailable.",response_time_ms=elapsed,status="ERROR"); log.set_sources([]); db.add(log); db.commit(); raise
        if status == "LOW_CONFIDENCE":
            answer = NO_MATCH
        elapsed=int((time.perf_counter()-started)*1000)
        log=ChatQueryLog(user_id=user_id,question=redact_sensitive_data(question),answer=redact_sensitive_data(answer),response_time_ms=elapsed,status=status); log.set_sources(sources); db.add(log); db.commit()
        return {"answer":answer,"sources":sources,"response_time_ms":elapsed,"status":status}
