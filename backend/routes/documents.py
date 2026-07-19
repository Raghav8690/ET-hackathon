"""
PS8 – Document Management API Routes

Endpoints
---------
POST   /api/documents/upload    – Upload a document file.
POST   /api/documents/{id}/ingest – Trigger ingestion pipeline for a document.
GET    /api/documents/list      – List all uploaded documents.
GET    /api/documents/{id}      – Retrieve a single document record.
DELETE /api/documents/{id}      – Delete a document and its file.
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.orm import Session

from backend.db.models import Document
from backend.db.session import get_db
from backend.services.file_storage import delete_upload, save_upload

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/documents", tags=["Documents"])


def _document_equipment_fields(doc: Document) -> dict:
    """Expose the extracted asset tag separately from the registry UUID.

    ``Document.equipment_id`` is a foreign key to ``Equipment.id`` and is
    therefore intentionally a UUID. Returning it as the public equipment ID
    made clients appear to receive a randomly extracted tag.
    """
    try:
        metadata = json.loads(doc.metadata_json or "{}")
    except (TypeError, json.JSONDecodeError):
        metadata = {}

    return {
        "equipment_id": metadata.get("equipment_id"),
        "equipment_name": metadata.get("equipment_name"),
        "equipment_registry_id": doc.equipment_id,
        # Provide parsed metadata dict for API clients and analytics services.
        "metadata": metadata,
    }


# ---------------------------------------------------------------------------
# POST /api/documents/upload
# ---------------------------------------------------------------------------
@router.post("/upload")
def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Query("OTHER", description="Document type (SOP, MANUAL, REPORT, etc.)"),
    auto_ingest: bool = Query(True, description="Automatically trigger ingestion after upload"),
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    """Accept a file upload, store it on disk, and create a database record.

    Returns
    -------
    JSON with ``document_id``, ``filename``, and ``status``.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided.")

    # 1. Save raw file to disk via storage service (Task 1.2.1)
    storage_result = save_upload(
        original_filename=file.filename,
        file_stream=file.file,
    )

    # 2. Create a database record with status PENDING
    doc = Document(
        filename=file.filename,
        filepath=storage_result["filepath"],
        file_size_bytes=storage_result["file_size_bytes"],
        doc_type=doc_type.upper(),
        status="PENDING",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    # 3. Optionally trigger ingestion in the background
    if auto_ingest:
        background_tasks.add_task(_run_ingestion_background, doc.id)

    return {
        "document_id": doc.id,
        "filename": doc.filename,
        "status": doc.status,
        "file_size_bytes": doc.file_size_bytes,
        "filepath": doc.filepath,
        "auto_ingest": auto_ingest,
    }


# ---------------------------------------------------------------------------
# POST /api/documents/{document_id}/ingest
# ---------------------------------------------------------------------------
@router.post("/{document_id}/ingest")
def trigger_ingestion(
    document_id: str,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
):
    """Manually trigger the ingestion pipeline for a document.

    Use this to re-ingest a document or to process a document that was
    uploaded with ``auto_ingest=false``.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    if doc.status == "PROCESSING":
        raise HTTPException(status_code=409, detail="Document is already being processed.")

    # Reset status
    doc.status = "PENDING"
    db.commit()

    background_tasks.add_task(_run_ingestion_background, document_id)

    return {
        "message": "Ingestion triggered.",
        "document_id": document_id,
        "status": "PENDING",
    }


# ---------------------------------------------------------------------------
# GET /api/documents/list
# ---------------------------------------------------------------------------
@router.get("/list")
def list_documents(
    status: Optional[str] = Query(None, description="Filter by status"),
    doc_type: Optional[str] = Query(None, description="Filter by document type"),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """Return a paginated list of uploaded documents."""
    query = db.query(Document)
    if status:
        query = query.filter(Document.status == status.upper())
    if doc_type:
        query = query.filter(Document.doc_type == doc_type.upper())

    total = query.count()
    docs = query.order_by(Document.upload_date.desc()).offset(offset).limit(limit).all()

    return {
        "total": total,
        "offset": offset,
        "limit": limit,
        "documents": [
            {
                "id": d.id,
                "filename": d.filename,
                "doc_type": d.doc_type,
                "status": d.status,
                "file_size_bytes": d.file_size_bytes,
                "upload_date": d.upload_date.isoformat() if d.upload_date else None,
                **_document_equipment_fields(d),
            }
            for d in docs
        ],
    }


# ---------------------------------------------------------------------------
# GET /api/documents/{document_id}
# ---------------------------------------------------------------------------
@router.get("/{document_id}")
def get_document(document_id: str, db: Session = Depends(get_db)):
    """Retrieve a single document record by ID."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    return {
        "id": doc.id,
        "filename": doc.filename,
        "filepath": doc.filepath,
        "doc_type": doc.doc_type,
        "status": doc.status,
        "file_size_bytes": doc.file_size_bytes,
        "upload_date": doc.upload_date.isoformat() if doc.upload_date else None,
        "processed_date": doc.processed_date.isoformat() if doc.processed_date else None,
        "error_message": doc.error_message,
        **_document_equipment_fields(doc),
    }


# ---------------------------------------------------------------------------
# DELETE /api/documents/{document_id}
# ---------------------------------------------------------------------------
@router.delete("/{document_id}")
def delete_document(document_id: str, db: Session = Depends(get_db)):
    """Delete a document record and its file from disk."""
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found.")

    # Remove file from disk
    delete_upload(doc.filepath)

    # Remove from database (cascades to chunks via relationship)
    db.delete(doc)
    db.commit()

    return {"message": "Document deleted.", "document_id": document_id}


# ---------------------------------------------------------------------------
# Background task helper
# ---------------------------------------------------------------------------
def _run_ingestion_background(document_id: str) -> None:
    """Run the ingestion pipeline in a background thread.

    Creates its own database session since background tasks run outside
    the request lifecycle.
    """
    from backend.db.session import SessionLocal
    from backend.ingestion.pipeline import ingest_document

    db = SessionLocal()
    try:
        success = ingest_document(document_id, db)
        if success:
            logger.info("Background ingestion completed for %s", document_id)
        else:
            logger.error("Background ingestion failed for %s", document_id)
    except Exception as exc:
        logger.exception("Background ingestion error for %s: %s", document_id, exc)
    finally:
        db.close()
