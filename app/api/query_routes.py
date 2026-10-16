from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User
from app.schemas import PolicyQueryRequest, PolicyQueryResponse
from app.security import require
from app.services.rag_service import RagService
router=APIRouter(prefix="/ai",tags=["AI / RAG"])
@router.post("/query",response_model=PolicyQueryResponse)
def query_policy(request:PolicyQueryRequest,db:Session=Depends(get_db),user:User=Depends(require("admin","reviewer","adjuster","support_agent"))):
    try:return RagService().answer(request.question,db,user_id=user.id,policy_code=request.policy_code)
    except Exception:raise HTTPException(503,"The policy assistant is temporarily unavailable. Please try again later.") from None
