"""
Phase 3 Tests – Backend LLM Routing & Conversation Management
"""

import json
from unittest.mock import patch, MagicMock

from backend.services.chat_manager import (
    get_session_history,
    save_message,
    compile_chat_history,
    build_rag_prompt,
    extract_citations,
    generate_completion,
)
from backend.db.models import ChatSession, ChatMessage
from backend.db.session import engine, Base
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

@pytest.fixture
def db():
    # Use in-memory SQLite for tests
    engine_test = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine_test)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()

def test_session_storage(db: Session):
    """Task 3.1.1: Insert session messages and retrieve. Assert list matches exact inserts."""
    session_id = "test-session-1"
    save_message(db, session_id, "user", "Hello")
    save_message(db, session_id, "assistant", "Hi there", [{"document_id": "doc1", "page": 1}])
    
    history = get_session_history(db, session_id)
    assert len(history) == 2
    assert history[0]["role"] == "user"
    assert history[0]["content"] == "Hello"
    assert history[1]["role"] == "assistant"
    assert history[1]["content"] == "Hi there"
    assert history[1]["citations"][0]["document_id"] == "doc1"


def test_context_aware_buffer_generator(db: Session):
    """Task 3.1.2: Insert 10 messages. Retrieve with limit 3, and confirm only last 3 items are returned."""
    session_id = "test-session-2"
    for i in range(10):
        save_message(db, session_id, "user", f"Msg {i}")
        
    buffer = compile_chat_history(db, session_id, limit=3)
    assert len(buffer) == 3
    assert buffer[0]["content"] == "Msg 7"
    assert buffer[1]["content"] == "Msg 8"
    assert buffer[2]["content"] == "Msg 9"


def test_rag_response_prompt_builder():
    """Task 3.2.1 & 3.3.1: Confirm placeholder values (chunks, history, query) and modes are injected."""
    chunks = [{"text": "Pump A specs", "metadata": {"document_id": "doc_pump", "page": 2}}]
    history = [{"role": "user", "content": "Prev question"}]
    query = "Why did it fail?"
    
    prompt = build_rag_prompt(query, chunks, history, mode="manager")
    
    # Check mode persona
    assert "senior plant manager" in prompt
    assert "Cost" in prompt
    # Check injection
    assert "doc_pump" in prompt
    assert "Page 2" in prompt
    assert "Pump A specs" in prompt
    assert "Prev question" in prompt
    assert "Why did it fail?" in prompt


def test_llm_completion_fallback():
    """Task 3.2.2: Mock API failure to trigger fallback block."""
    import os
    os.environ["OPENAI_API_KEY"] = "mock_key_for_test"
    
    # We mock openai to raise an exception
    with patch("openai.Client") as MockClient:
        MockClient.side_effect = Exception("API Timeout")
        response = generate_completion("test prompt")
        assert "Fallback API response" in response
        assert "API Timeout" in response


def test_citation_extractor():
    """Task 3.3.2: Test parser with mock LLM text containing [Source: ManualA, Page 4]."""
    mock_text = "The pump failed due to cavitation [Source: ManualA, Page 4]. Keep an eye on it [Source: ManualB, Page 12]."
    parsed = extract_citations(mock_text)
    
    assert parsed["answer"] == mock_text
    assert len(parsed["citations"]) == 2
    assert parsed["citations"][0]["document_id"] == "ManualA"
    assert parsed["citations"][0]["page"] == 4
    assert parsed["citations"][1]["document_id"] == "ManualB"
    assert parsed["citations"][1]["page"] == 12


from fastapi.testclient import TestClient
from backend.main import app

client = TestClient(app)

@patch("backend.routes.chat.search_hybrid")
@patch("backend.routes.chat.generate_completion")
def test_chat_endpoint(mock_gen, mock_search):
    """Task 3.2.3: Test FastAPI Chat Endpoint /api/chat"""
    mock_search.return_value = [{"text": "Mock chunk", "metadata": {"document_id": "doc1", "page": 1}}]
    mock_gen.return_value = "It failed due to wear. [Source: doc1, Page 1]"
    
    payload = {
        "query": "Why did pump A fail?",
        "session_id": "test-session-api",
        "mode": "technical",
        "filters": {}
    }
    
    resp = client.post("/api/chat", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "It failed due to wear" in data["answer"]
    assert len(data["citations"]) == 1
    assert data["citations"][0]["document_id"] == "doc1"
    assert data["context_used"] == 1
