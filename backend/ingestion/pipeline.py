"""
PS8 – Ingestion Pipeline Orchestrator (Task 1.4.3)

Combines the full document processing workflow:
1. Text extraction (PDF / OCR)
2. Semantic chunking
3. Metadata extraction
4. Embedding generation
5. Chroma vector insertion
6. Database status updates

Contract
--------
Function ``ingest_document(document_id: str, db: Session) -> bool``
Updates database status to ``INGESTED`` or ``FAILED``.
"""

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from backend.db.models import Document, DocumentChunk
from backend.ingestion.chunker import chunk_text
from backend.ingestion.embed import get_embeddings
from backend.ingestion.metadata import extract_metadata
from backend.ingestion.pdf import extract_pdf_text
from backend.ingestion.ocr import extract_ocr_text
from backend.ingestion.vector_store import get_or_create_collection

logger = logging.getLogger(__name__)

# File extensions that should be processed via OCR
_OCR_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}
_PDF_EXTENSION = ".pdf"


def ingest_document(document_id: str, db: Session) -> bool:
    """Run the full ingestion pipeline for a single document.

    Steps
    -----
    1. Load document record from DB.
    2. Extract text (PDF or OCR based on file type).
    3. Chunk extracted text into semantic segments.
    4. Extract metadata from the full text.
    5. Generate embeddings for all chunks.
    6. Insert chunks + embeddings into Chroma.
    7. Save chunk metadata to SQL database.
    8. Update document status to INGESTED.

    Parameters
    ----------
    document_id : str
        UUID of the document record in the ``documents`` table.
    db : Session
        Active SQLAlchemy session.

    Returns
    -------
    bool
        ``True`` if ingestion succeeded, ``False`` if it failed.
        On failure, the document status is set to ``FAILED`` with error details.
    """
    # --- 1. Load document record ---
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        logger.error("Document %s not found in database", document_id)
        return False

    try:
        # Mark as processing and clear any previous errors
        doc.status = "PROCESSING"
        doc.error_message = None
        db.commit()

        file_path = doc.filepath
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"File not found on disk: {file_path}")

        ext = path.suffix.lower()

        # --- 2. Extract text ---
        pages_content = _extract_text(file_path, ext)
        full_text = "\n\n".join(p["text"] for p in pages_content if p.get("text"))

        if not full_text.strip():
            logger.warning("No text extracted from %s – marking as INGESTED (empty)", doc.filename)
            doc.status = "INGESTED"
            doc.processed_date = datetime.now(timezone.utc)
            doc.metadata_json = json.dumps({"warning": "No text could be extracted"})
            db.commit()
            return True

        # --- 3. Chunk text ---
        chunks = chunk_text(pages_content, chunk_size=1000, overlap=200)
        logger.info("Generated %d chunks from %s", len(chunks), doc.filename)

        if not chunks:
            doc.status = "INGESTED"
            doc.processed_date = datetime.now(timezone.utc)
            doc.metadata_json = json.dumps({"warning": "Text extracted but no chunks generated"})
            db.commit()
            return True

        # --- 4. Extract metadata ---
        metadata = extract_metadata(full_text)
        doc.metadata_json = json.dumps(metadata)

        # Link to equipment if detected
        if metadata.get("equipment_id"):
            _maybe_link_equipment(doc, metadata["equipment_id"], db)

        # Set date range if detected
        if metadata.get("date_range_start"):
            try:
                doc.date_range_start = datetime.strptime(
                    metadata["date_range_start"], "%Y-%m-%d"
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        if metadata.get("date_range_end"):
            try:
                doc.date_range_end = datetime.strptime(
                    metadata["date_range_end"], "%Y-%m-%d"
                ).replace(tzinfo=timezone.utc)
            except ValueError:
                pass

        # --- 5. Generate embeddings ---
        chunk_texts = [c["text"] for c in chunks]
        embeddings = get_embeddings(chunk_texts)

        # --- 6. Insert into Chroma ---
        collection = get_or_create_collection()
        chunk_ids = []
        chunk_metadatas = []
        
        for i, chunk in enumerate(chunks):
            chunk_id = f"{document_id}_chunk_{i}"
            chunk_ids.append(chunk_id)
            chunk_metadatas.append({
                "document_id": document_id,
                "filename": doc.filename,
                "page": chunk.get("page", 1),
                "section_title": chunk.get("section_title", "General"),
                "chunk_index": i,
                "doc_type": metadata.get("doc_type", "other"),
                "equipment_id": metadata.get("equipment_id", ""),
            })

        # Chroma upsert (handles both insert and update)
        collection.upsert(
            ids=chunk_ids,
            documents=chunk_texts,
            embeddings=embeddings,
            metadatas=chunk_metadatas,
        )
        logger.info("Upserted %d vectors into Chroma for %s", len(chunk_ids), doc.filename)

        # --- 7. Save chunks to SQL ---
        # Remove any existing chunks for this document (re-ingestion support)
        db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document_id
        ).delete()

        for i, chunk in enumerate(chunks):
            db_chunk = DocumentChunk(
                document_id=document_id,
                chunk_index=i,
                text=chunk["text"],
                page_number=chunk.get("page"),
                section_title=chunk.get("section_title", "General"),
                token_count=len(chunk["text"].split()),  # Approximate word count
                vector_id=f"{document_id}_chunk_{i}",
            )
            db.add(db_chunk)

        # --- 8. Mark as INGESTED ---
        doc.status = "INGESTED"
        doc.processed_date = datetime.now(timezone.utc)
        db.commit()

        logger.info(
            "✅ Successfully ingested %s: %d chunks, %d vectors",
            doc.filename,
            len(chunks),
            len(embeddings),
        )
        return True

    except Exception as exc:
        logger.exception("❌ Ingestion failed for document %s: %s", document_id, exc)
        try:
            db.rollback()
            doc.status = "FAILED"
            doc.error_message = str(exc)[:2000]
            doc.processed_date = datetime.now(timezone.utc)
            db.commit()
        except Exception:
            logger.exception("Failed to update document status after error")
        return False


def _extract_text(file_path: str, ext: str) -> List[Dict[str, Any]]:
    """Route to the correct text extraction method based on file extension."""
    if ext == _PDF_EXTENSION:
        # Try PDF text extraction first; if pages come back empty, try OCR
        pages = extract_pdf_text(file_path)
        total_text = sum(len(p.get("text", "")) for p in pages)
        if total_text < 50:
            # Likely a scanned PDF – fall back to OCR
            logger.info("PDF text extraction yielded <50 chars – attempting OCR")
            try:
                ocr_pages = extract_ocr_text(file_path)
                ocr_text = sum(len(p.get("text", "")) for p in ocr_pages)
                if ocr_text > total_text:
                    return ocr_pages
            except Exception as exc:
                logger.warning("OCR fallback failed: %s", exc)
        return pages
    elif ext in _OCR_EXTENSIONS:
        return extract_ocr_text(file_path)
    else:
        # For other text-like files, try reading as plain text
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            return [{"page": 1, "text": text}]
        except Exception:
            raise ValueError(f"Unsupported file type: {ext}")


def _maybe_link_equipment(
    doc: Document, equipment_id_str: str, db: Session
) -> None:
    """Try to link the document to an existing equipment record by name/model."""
    from backend.db.models import Equipment

    equip = (
        db.query(Equipment)
        .filter(
            (Equipment.name.ilike(f"%{equipment_id_str}%"))
            | (Equipment.model.ilike(f"%{equipment_id_str}%"))
            | (Equipment.serial_number.ilike(f"%{equipment_id_str}%"))
        )
        .first()
    )
    if equip:
        doc.equipment_id = equip.id
        logger.info("Linked document to equipment: %s (%s)", equip.name, equip.id)
