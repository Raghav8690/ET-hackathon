import logging
from typing import Any, Dict, List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.db.session import get_db
from backend.rag.hybrid_search import search_hybrid
from backend.services.chat_manager import (
    build_rag_prompt,
    compile_chat_history,
    extract_citations,
    generate_completion,
    save_message,
)

logger = logging.getLogger(__name__)

router = APIRouter()

class ChatRequest(BaseModel):
    query: str
    session_id: str
    mode: str = "technical"
    filters: Optional[Dict[str, Any]] = None


@router.post("")
def chat_endpoint(req: ChatRequest, db: Session = Depends(get_db)):
    """
    Task 3.2.3: FastAPI Chat Endpoint /api/chat
    Main query handler, accepting question, filters, session ID, and mode.
    """
    if not req.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")
        
    try:
        # 1. Retrieve relevant contexts (Hybrid Search)
        context_chunks = search_hybrid(
            query_str=req.query,
            k=5,
            filters=req.filters
        )
        
        # 2. Get chat history
        history = compile_chat_history(db, req.session_id, limit=5)
        
        # 3. Build Prompt
        prompt = build_rag_prompt(
            query=req.query,
            context_chunks=context_chunks,
            history=history,
            mode=req.mode
        )
        
        # 4. Generate Completion
        llm_response = generate_completion(prompt)
        
        # 5. Extract Citations
        parsed_response = extract_citations(llm_response)
        
        # 6. Save User Message & AI Response to DB
        save_message(db, req.session_id, "user", req.query)
        ai_msg = save_message(
            db, 
            req.session_id, 
            "assistant", 
            parsed_response["answer"], 
            parsed_response["citations"]
        )
        
        return {
            "id": ai_msg.id,
            "answer": parsed_response["answer"],
            "citations": parsed_response["citations"],
            "context_used": len(context_chunks)
        }
    except Exception as exc:
        logger.exception("Chat endpoint failed")
        raise HTTPException(status_code=500, detail=str(exc))
