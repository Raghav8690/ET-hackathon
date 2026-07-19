"""
PS8 – Phase 1.2 Tests: Document Upload & Local File Handler

Tests cover:
  - Task 1.2.1: Local Document Storage (save, delete, exists)
  - Task 1.2.2: FastAPI Upload Endpoint (POST, GET /list, GET /{id}, DELETE)
"""

import io
import os
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so imports resolve cleanly
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parents[2]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))


# ===================================================================
# Task 1.2.1 – File Storage Service Tests
# ===================================================================
class TestFileStorageService:
    """Validate the local file storage helper from backend.services.file_storage."""

    def test_upload_dir_exists(self):
        """get_upload_dir() should create and return the uploads directory."""
        from backend.services.file_storage import get_upload_dir

        upload_dir = get_upload_dir()
        assert upload_dir.exists(), "Uploads directory should exist"
        assert upload_dir.is_dir(), "Uploads path should be a directory"

    def test_save_upload_creates_file(self):
        """save_upload() should write a file to disk and return metadata."""
        from backend.services.file_storage import save_upload, file_exists, delete_upload

        content = b"Hello, this is a test PDF content"
        stream = io.BytesIO(content)

        result = save_upload("test_document.pdf", stream, use_date_subdir=False)

        assert "filepath" in result
        assert "filename" in result
        assert "file_size_bytes" in result
        assert result["file_size_bytes"] == len(content)
        assert file_exists(result["filepath"])

        # Cleanup
        delete_upload(result["filepath"])

    def test_save_upload_unique_filenames(self):
        """Two uploads with the same name should produce different filenames."""
        from backend.services.file_storage import save_upload, delete_upload

        s1 = io.BytesIO(b"content1")
        s2 = io.BytesIO(b"content2")

        r1 = save_upload("same_name.pdf", s1, use_date_subdir=False)
        r2 = save_upload("same_name.pdf", s2, use_date_subdir=False)

        assert r1["filepath"] != r2["filepath"], "Filenames should be unique"

        # Cleanup
        delete_upload(r1["filepath"])
        delete_upload(r2["filepath"])

    def test_save_upload_with_date_subdir(self):
        """save_upload with use_date_subdir=True should create YYYY/MM/DD folder."""
        from backend.services.file_storage import save_upload, delete_upload

        stream = io.BytesIO(b"test content")
        result = save_upload("dated.pdf", stream, use_date_subdir=True)

        # Filepath should contain a date path component
        filepath = result["filepath"]
        assert os.path.exists(filepath)

        # Cleanup
        delete_upload(filepath)

    def test_delete_upload_removes_file(self):
        """delete_upload() should remove the file and return True."""
        from backend.services.file_storage import save_upload, delete_upload, file_exists

        stream = io.BytesIO(b"delete me")
        result = save_upload("to_delete.pdf", stream, use_date_subdir=False)

        assert file_exists(result["filepath"])
        assert delete_upload(result["filepath"]) is True
        assert not file_exists(result["filepath"])

    def test_delete_nonexistent_file_returns_false(self):
        """delete_upload() on a missing file should return False."""
        from backend.services.file_storage import delete_upload

        assert delete_upload("/tmp/nonexistent_file_xyz.pdf") is False

    def test_file_exists_checks_correctly(self):
        """file_exists() should return True for existing files, False otherwise."""
        from backend.services.file_storage import file_exists

        assert file_exists(__file__) is True  # This test file exists
        assert file_exists("/no/such/path/abc.txt") is False


# ===================================================================
# Task 1.2.2 – FastAPI Document Upload Endpoint Tests
# ===================================================================
class TestDocumentUploadEndpoint:
    """Validate the /api/documents/* endpoints via FastAPI TestClient."""

    @pytest.fixture(autouse=True)
    def setup_client(self):
        """Create a fresh test client and database for each test."""
        from backend.main import app
        from backend.db.session import init_db, drop_db

        # Reinitialise tables for a clean slate
        init_db()
        self.client = TestClient(app)
        yield
        # Optional: leave tables intact for inspection; drop in CI if needed

    def _upload_test_file(self, filename="test_upload.pdf", content=b"%PDF-1.4 test content", auto_ingest=False):
        """Helper to upload a file and return the response JSON."""
        response = self.client.post(
            "/api/documents/upload",
            files={"file": (filename, io.BytesIO(content), "application/pdf")},
            params={"doc_type": "MANUAL", "auto_ingest": auto_ingest},
        )
        return response

    def test_upload_returns_201_or_200(self):
        """POST /api/documents/upload should return success."""
        resp = self._upload_test_file()
        assert resp.status_code == 200, f"Upload failed: {resp.text}"

    def test_upload_returns_document_id(self):
        """Response must include document_id, filename, and status."""
        resp = self._upload_test_file()
        data = resp.json()

        assert "document_id" in data, "Response missing document_id"
        assert "filename" in data, "Response missing filename"
        assert "status" in data, "Response missing status"
        assert data["status"] == "PENDING", f"Expected PENDING, got {data['status']}"
        assert data["filename"] == "test_upload.pdf"

    def test_upload_file_saved_to_disk(self):
        """The uploaded file should physically exist on disk."""
        from backend.services.file_storage import file_exists

        resp = self._upload_test_file()
        data = resp.json()
        assert file_exists(data["filepath"]), "File should exist on disk after upload"

    def test_list_documents(self):
        """GET /api/documents/list should return uploaded documents."""
        self._upload_test_file("doc_a.pdf")
        self._upload_test_file("doc_b.pdf")

        resp = self.client.get("/api/documents/list")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        assert len(data["documents"]) >= 2

    def test_list_documents_filter_by_status(self):
        """Filtering by status should only return matching docs."""
        self._upload_test_file()
        resp = self.client.get("/api/documents/list", params={"status": "PENDING"})
        data = resp.json()
        for doc in data["documents"]:
            assert doc["status"] == "PENDING"

    def test_get_document_by_id(self):
        """GET /api/documents/{id} should return the correct document."""
        upload_resp = self._upload_test_file()
        doc_id = upload_resp.json()["document_id"]

        resp = self.client.get(f"/api/documents/{doc_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == doc_id
        assert data["status"] == "PENDING"

    def test_get_document_not_found(self):
        """GET /api/documents/{id} with a bad ID should return 404."""
        resp = self.client.get("/api/documents/nonexistent-uuid")
        assert resp.status_code == 404

    def test_delete_document(self):
        """DELETE /api/documents/{id} should remove doc and file."""
        upload_resp = self._upload_test_file()
        doc_id = upload_resp.json()["document_id"]

        del_resp = self.client.delete(f"/api/documents/{doc_id}")
        assert del_resp.status_code == 200

        # Confirm it's gone
        get_resp = self.client.get(f"/api/documents/{doc_id}")
        assert get_resp.status_code == 404

    def test_upload_no_file_returns_error(self):
        """POST /api/documents/upload with no file should return 422."""
        resp = self.client.post("/api/documents/upload")
        assert resp.status_code == 422


class TestDocumentEquipmentResponse:
    def test_exposes_asset_tag_and_registry_uuid_separately(self):
        from backend.routes.documents import _document_equipment_fields

        fields = _document_equipment_fields(SimpleNamespace(
            metadata_json='{"equipment_id": "P-101", "equipment_name": "Pump A"}',
            equipment_id="679e8c7d-5150-4ebd-9cda-8790a8352543",
        ))

        assert fields["equipment_id"] == "P-101"
        assert fields["equipment_name"] == "Pump A"
        assert fields["equipment_registry_id"] == "679e8c7d-5150-4ebd-9cda-8790a8352543"
        assert fields["metadata"]["equipment_id"] == "P-101"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
