"""
PS8 – Phase 1.4 Tests: Vector Storage Pipeline

Tests cover:
  - Task 1.4.1: Chroma Vector Database Connection
  - Task 1.4.2: Embedding Generation Wrapper
  - Task 1.4.3: Ingestion Pipeline Orchestrator
"""

import json
import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock, PropertyMock
from datetime import datetime, timezone

# ===================================================================
# Task 1.4.1 – Chroma Vector Database Connection
# ===================================================================
class TestVectorStore:
    """Tests for backend.ingestion.vector_store"""

    @patch("backend.ingestion.vector_store.chromadb.PersistentClient")
    def test_get_chroma_client_returns_client(self, mock_persistent_client, tmp_path):
        """Verify we can create a Chroma client."""
        # Setup mock
        mock_client_instance = MagicMock()
        mock_client_instance.heartbeat.return_value = 123456789
        mock_persistent_client.return_value = mock_client_instance

        # Reset singleton
        import backend.ingestion.vector_store as vs
        vs._client = None
        vs.CHROMA_DB_DIR = str(tmp_path / "chroma")

        client = vs.get_chroma_client()
        assert client is not None
        mock_persistent_client.assert_called_once()

        # Heartbeat should return a positive number
        hb = vs.heartbeat()
        assert hb == 123456789

        # Cleanup
        vs._client = None

    @patch("backend.ingestion.vector_store.chromadb.PersistentClient")
    def test_get_or_create_collection(self, mock_persistent_client, tmp_path):
        """Verify collection creation and retrieval."""
        mock_client_instance = MagicMock()
        mock_coll = MagicMock()
        mock_coll.count.return_value = 0
        mock_coll.name = "test_collection"
        mock_client_instance.get_or_create_collection.return_value = mock_coll
        mock_persistent_client.return_value = mock_client_instance

        import backend.ingestion.vector_store as vs
        vs._client = None
        vs.CHROMA_DB_DIR = str(tmp_path / "chroma")

        coll = vs.get_or_create_collection("test_collection")
        assert coll is not None
        assert coll.count() == 0

        # Second call should return same collection
        coll2 = vs.get_or_create_collection("test_collection")
        assert coll2.name == coll.name

        vs._client = None

    @patch("backend.ingestion.vector_store.chromadb.PersistentClient")
    def test_collection_count(self, mock_persistent_client):
        """collection_count returns 0 for non-existent collection."""
        mock_client_instance = MagicMock()
        mock_client_instance.get_collection.side_effect = Exception("Not found")
        mock_persistent_client.return_value = mock_client_instance

        import backend.ingestion.vector_store as vs
        vs._client = None

        count = vs.collection_count("nonexistent")
        assert count == 0

        vs._client = None


# ===================================================================
# Task 1.4.2 – Embedding Generation Wrapper
# ===================================================================
class TestEmbeddings:
    """Tests for backend.ingestion.embed"""

    def test_empty_input_returns_empty(self):
        from backend.ingestion.embed import get_embeddings
        result = get_embeddings([])
        assert result == []

    @patch("backend.ingestion.embed._openai_available", return_value=False)
    def test_local_embeddings_dimension(self, _):
        """Verify local model returns correct dimension (384 for MiniLM)."""
        from backend.ingestion.embed import get_embedding_dimension
        dim = get_embedding_dimension()
        assert dim == 384

    @patch("backend.ingestion.embed._openai_available", return_value=True)
    def test_openai_dimension(self, _):
        from backend.ingestion.embed import get_embedding_dimension
        dim = get_embedding_dimension()
        assert dim == 1536

    def test_get_embedding_source_without_openai(self):
        from backend.ingestion.embed import get_embedding_source
        with patch.dict(os.environ, {"OPENAI_API_KEY": ""}):
            source = get_embedding_source()
            assert "local" in source or "MiniLM" in source

    @patch("backend.ingestion.embed._embed_local")
    @patch("backend.ingestion.embed._openai_available", return_value=False)
    def test_get_embeddings_falls_back_to_local(self, _, mock_local):
        """When OpenAI not available, should use local model."""
        mock_local.return_value = [[0.1, 0.2, 0.3]]
        from backend.ingestion.embed import get_embeddings
        result = get_embeddings(["test text"])
        mock_local.assert_called_once()
        assert len(result) == 1
        assert len(result[0]) == 3

    @patch("backend.ingestion.embed.httpx.Client")
    @patch("backend.ingestion.embed.OLLAMA_EMBEDDING_MODEL", "embeddinggemma")
    def test_ollama_uses_current_batch_endpoint_and_embedding_model(self, mock_client_cls):
        from backend.ingestion.embed import _embed_ollama

        response = MagicMock()
        response.json.return_value = {"embeddings": [[0.1, 0.2]]}
        mock_client = mock_client_cls.return_value.__enter__.return_value
        mock_client.post.return_value = response

        assert _embed_ollama(["test"]) == [[0.1, 0.2]]
        mock_client.post.assert_called_once_with(
            "http://localhost:11434/api/embed",
            json={"model": "embeddinggemma", "input": ["test"]},
        )


# ===================================================================
# Task 1.4.3 – Ingestion Pipeline Orchestrator
# ===================================================================
class TestIngestionPipeline:
    """Tests for backend.ingestion.pipeline"""

    @patch("backend.ingestion.pipeline.get_or_create_collection")
    @patch("backend.ingestion.pipeline.get_embeddings")
    @patch("backend.ingestion.pipeline.extract_pdf_text")
    def test_ingest_document_success(self, mock_extract, mock_embed, mock_collection):
        """Full pipeline test with mocked dependencies."""
        from backend.ingestion.pipeline import ingest_document
        from backend.db.models import Document, DocumentChunk

        # Mock text extraction
        mock_extract.return_value = [
            {"page": 1, "text": "Pump Model P-101 Serial Number SN-883921. " * 10}
        ]

        # Mock embeddings
        mock_embed.return_value = [[0.1] * 384]

        # Mock Chroma collection
        mock_coll = MagicMock()
        mock_coll.upsert.return_value = None
        mock_collection.return_value = mock_coll

        # Mock DB session
        mock_db = MagicMock()
        mock_doc = MagicMock(spec=Document)
        mock_doc.id = "test-doc-id"
        mock_doc.filename = "test.pdf"
        mock_doc.filepath = __file__  # Use this test file as a proxy (exists on disk)
        mock_doc.status = "PENDING"
        mock_doc.metadata_json = None
        mock_doc.equipment_id = None
        mock_doc.date_range_start = None
        mock_doc.date_range_end = None
        mock_doc.error_message = None
        mock_doc.processed_date = None

        # filepath needs to have .pdf extension for the routing
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 test content")
            mock_doc.filepath = f.name

        # Mock Equipment returned by _maybe_link_equipment
        mock_equip = MagicMock()
        mock_equip.id = "equip-123"
        mock_equip.name = "Pump A"
        mock_equip.model = "P-101"
        mock_equip.serial_number = "SN-883921"
        
        # When querying Document, return mock_doc; when querying Equipment, return mock_equip
        def mock_first():
            from backend.db.models import Document
            if mock_db.query.call_args[0][0] == Document:
                return mock_doc
            return mock_equip

        mock_db.query.return_value.filter.return_value.first.side_effect = mock_first
        mock_db.query.return_value.filter.return_value.delete.return_value = 0

        try:
            result = ingest_document("test-doc-id", mock_db)

            assert result is True
            assert mock_doc.status == "INGESTED"
            assert mock_doc.processed_date is not None
            mock_coll.upsert.assert_called_once()
        finally:
            os.unlink(mock_doc.filepath)

    def test_ingest_document_not_found(self):
        """Pipeline should return False for non-existent document."""
        from backend.ingestion.pipeline import ingest_document

        mock_db = MagicMock()
        mock_db.query.return_value.filter.return_value.first.return_value = None

        result = ingest_document("nonexistent-id", mock_db)
        assert result is False

    @patch("backend.ingestion.pipeline.extract_pdf_text")
    def test_ingest_document_file_missing(self, mock_extract):
        """Pipeline should mark as FAILED when file doesn't exist on disk."""
        from backend.ingestion.pipeline import ingest_document
        from backend.db.models import Document

        mock_extract.side_effect = FileNotFoundError("File not found")

        mock_db = MagicMock()
        mock_doc = MagicMock(spec=Document)
        mock_doc.id = "test-doc-id"
        mock_doc.filename = "missing.pdf"
        mock_doc.filepath = "/nonexistent/path/missing.pdf"
        mock_doc.status = "PENDING"
        mock_doc.error_message = None
        mock_doc.processed_date = None

        mock_db.query.return_value.filter.return_value.first.return_value = mock_doc

        result = ingest_document("test-doc-id", mock_db)
        assert result is False
        assert mock_doc.status == "FAILED"

    @patch("backend.ingestion.vector_store.reset_collection")
    @patch("backend.ingestion.pipeline.get_or_create_collection")
    @patch("backend.ingestion.pipeline.get_embeddings")
    @patch("backend.ingestion.pipeline.extract_pdf_text")
    def test_ingest_document_dimension_mismatch_recovery(
        self, mock_extract, mock_embed, mock_collection, mock_reset
    ):
        """Pipeline automatically resets collection and retries if embedding dimension changes."""
        from backend.ingestion.pipeline import ingest_document
        from backend.db.models import Document

        mock_extract.return_value = [{"page": 1, "text": "Pump P-101 manual content"}]
        mock_embed.return_value = [[0.1] * 768]

        mock_coll_initial = MagicMock()
        mock_coll_initial.upsert.side_effect = Exception("Collection expecting embedding with dimension of 384, got 768")
        mock_collection.return_value = mock_coll_initial

        mock_coll_reset = MagicMock()
        mock_reset.return_value = mock_coll_reset

        mock_db = MagicMock()
        mock_doc = MagicMock(spec=Document)
        mock_doc.id = "dim-test-id"
        mock_doc.filename = "test.pdf"
        mock_doc.status = "PENDING"
        mock_doc.metadata_json = None
        mock_doc.equipment_id = None
        mock_doc.date_range_start = None
        mock_doc.date_range_end = None
        mock_doc.error_message = None
        mock_doc.processed_date = None

        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 content")
            mock_doc.filepath = f.name

        mock_equip = MagicMock()
        mock_equip.id = "equip-123"
        mock_equip.name = "Pump A"

        def mock_first():
            from backend.db.models import Document
            if mock_db.query.call_args[0][0] == Document:
                return mock_doc
            return mock_equip

        mock_db.query.return_value.filter.return_value.first.side_effect = mock_first
        mock_db.query.return_value.filter.return_value.delete.return_value = 0

        try:
            result = ingest_document("dim-test-id", mock_db)

            assert result is True
            assert mock_doc.status == "INGESTED"
            mock_reset.assert_called_once()
            mock_coll_reset.upsert.assert_called_once()
        finally:
            os.unlink(mock_doc.filepath)

