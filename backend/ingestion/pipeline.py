"""
PS8 – Ingestion Pipeline Orchestrator

Combines the full document processing workflow:
1. Text extraction (PDF / OCR / plain text)
2. Semantic chunking
3. LLM-powered metadata extraction (via local Ollama)
4. Embedding generation
5. Chroma vector insertion with rich metadata
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
    4. Extract metadata from the full text (LLM-powered via Ollama).
    5. Generate embeddings for all chunks.
    6. Insert chunks + embeddings into Chroma with rich metadata.
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

        # --- 4. Extract metadata (LLM-powered via Ollama or regex fallback) ---
        metadata = extract_metadata(full_text)
        doc.metadata_json = json.dumps(metadata)

        logger.info(
            "Metadata extraction method: %s | doc_type: %s | equipment: %s",
            metadata.get("_extraction_method", "unknown"),
            metadata.get("doc_type", "other"),
            metadata.get("equipment_id", "none"),
        )

        # Link to equipment if detected (auto-creates if not found)
        equipment_id_str = metadata.get("equipment_id")
        if equipment_id_str:
            _link_or_create_equipment(doc, metadata, db)

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

        # Set compliance flag if detected
        if metadata.get("compliance_relevant"):
            doc.compliance_relevant = True

        # --- 5. Generate embeddings ---
        chunk_texts = [c["text"] for c in chunks]
        embeddings = get_embeddings(chunk_texts)

        # --- 6. Insert into Chroma with rich metadata ---
        collection = get_or_create_collection()
        chunk_ids = []
        chunk_metadatas = []

        # Build rich per-chunk metadata for vector search filtering
        doc_level_meta = _build_doc_level_chroma_meta(metadata, doc)

        for i, chunk in enumerate(chunks):
            chunk_id = f"{document_id}_chunk_{i}"
            chunk_ids.append(chunk_id)

            # Per-chunk metadata (merge doc-level + chunk-specific)
            chunk_meta = {
                **doc_level_meta,
                "chunk_index": i,
                "page": chunk.get("page", 1),
                "section_title": chunk.get("section_title", "General"),
            }
            chunk_metadatas.append(chunk_meta)

        # Chroma upsert (handles both insert and update)
        try:
            collection.upsert(
                ids=chunk_ids,
                documents=chunk_texts,
                embeddings=embeddings,
                metadatas=chunk_metadatas,
            )
        except Exception as exc:
            err_msg = str(exc)
            if "expecting embedding with dimension" in err_msg or "dimension" in err_msg.lower():
                logger.warning(
                    "Chroma embedding dimension mismatch (%s). Resetting collection and retrying upsert...",
                    err_msg,
                )
                from backend.ingestion.vector_store import reset_collection
                collection = reset_collection()
                collection.upsert(
                    ids=chunk_ids,
                    documents=chunk_texts,
                    embeddings=embeddings,
                    metadatas=chunk_metadatas,
                )
            else:
                raise
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
            "✅ Successfully ingested %s: %d chunks, %d vectors, method=%s",
            doc.filename,
            len(chunks),
            len(embeddings),
            metadata.get("_extraction_method", "unknown"),
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
    elif ext == ".docx":
        from backend.ingestion.docx_parser import extract_docx_text
        return extract_docx_text(file_path)
    elif ext == ".doc":
        from backend.ingestion.docx_parser import extract_doc_text
        return extract_doc_text(file_path)
    elif ext in {".xls", ".xlsx", ".ppt", ".pptx", ".zip", ".tar", ".gz", ".rar", ".7z"}:
        raise ValueError(f"Binary file type {ext} cannot be read as plain text.")
    else:
        # For other text-like files, try reading as plain text
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                text = f.read()
            return [{"page": 1, "text": text}]
        except Exception:
            raise ValueError(f"Unsupported file type: {ext}")


def _build_doc_level_chroma_meta(
    metadata: Dict[str, Any], doc: "Document"
) -> Dict[str, Any]:
    """Build a flat metadata dict suitable for Chroma (strings/ints/floats/bools only).

    Chroma metadata values must be str, int, float, or bool.
    Lists are joined as comma-separated strings.
    """
    meta: Dict[str, Any] = {
        "document_id": doc.id,
        "filename": doc.filename,
        "doc_type": metadata.get("doc_type", "other"),
    }

    # String fields
    for key in (
        "equipment_id", "equipment_name", "equipment_type",
        "serial_number", "model_number", "manufacturer",
        "severity", "summary", "language",
        "date_range_start", "date_range_end",
    ):
        val = metadata.get(key)
        if val and isinstance(val, str):
            # Chroma has metadata value size limits, truncate long strings
            meta[key] = val[:500]

    # List fields → comma-separated strings
    for key in (
        "failure_modes", "root_causes", "tags",
        "compliance_references", "locations",
        "technical_specs", "action_items",
        "costs_mentioned", "key_entities",
        "equipment_mentions",
    ):
        val = metadata.get(key)
        if isinstance(val, list) and val:
            meta[key] = ", ".join(str(v) for v in val[:20])[:1000]

    # Boolean fields
    if metadata.get("compliance_relevant") is not None:
        meta["compliance_relevant"] = bool(metadata["compliance_relevant"])

    # Extraction method for debugging
    meta["extraction_method"] = metadata.get("_extraction_method", "unknown")

    return meta


def _link_or_create_equipment(
    doc: Document, metadata: Dict[str, Any], db: Session
) -> None:
    """Link document to an existing equipment record, or auto-create one.

    Searches by equipment_id, equipment_name, serial_number, and model_number.
    If no match is found, creates a new Equipment record using the
    LLM-extracted metadata.
    """
    from backend.db.models import Equipment

    equipment_id_str = metadata.get("equipment_id", "")
    equipment_name = metadata.get("equipment_name", "")
    serial_number = metadata.get("serial_number")
    model_number = metadata.get("model_number")

    # --- Try to find existing equipment ---
    search_terms = [t for t in [equipment_id_str, equipment_name] if t]

    for term in search_terms:
        equip = (
            db.query(Equipment)
            .filter(
                (Equipment.name.ilike(f"%{term}%"))
                | (Equipment.model.ilike(f"%{term}%"))
                | (Equipment.serial_number.ilike(f"%{term}%"))
            )
            .first()
        )
        if equip:
            doc.equipment_id = equip.id
            logger.info("Linked document to existing equipment: %s (%s)", equip.name, equip.id)
            return

    # Also try serial number if available
    if serial_number:
        equip = (
            db.query(Equipment)
            .filter(Equipment.serial_number.ilike(f"%{serial_number}%"))
            .first()
        )
        if equip:
            doc.equipment_id = equip.id
            logger.info("Linked document to equipment by serial: %s (%s)", equip.name, equip.id)
            return

    # --- No match found: auto-create equipment ---
    # Build a name: prefer equipment_name, fall back to equipment_id
    name = equipment_name or equipment_id_str or "Unknown Equipment"

    new_equip = Equipment(
        name=name,
        serial_number=serial_number,
        model=model_number or equipment_id_str,
        manufacturer=metadata.get("manufacturer"),
        status="OPERATIONAL",
    )
    db.add(new_equip)
    db.flush()  # Get the generated ID without committing

    doc.equipment_id = new_equip.id
    logger.info(
        "Auto-created equipment '%s' (id=%s, serial=%s, model=%s) and linked to document",
        name, new_equip.id, serial_number, model_number,
    )
