"""
PS8 – Ingestion Package

Text extraction, chunking, embedding, and vector storage pipeline.
"""

from backend.ingestion.pdf import extract_pdf_text
from backend.ingestion.ocr import extract_ocr_text
from backend.ingestion.metadata import extract_metadata
from backend.ingestion.chunker import chunk_text
from backend.ingestion.embed import get_embeddings
from backend.ingestion.vector_store import (
    get_chroma_client,
    get_or_create_collection,
    heartbeat,
    collection_count,
)
from backend.ingestion.pipeline import ingest_document

__all__ = [
    "extract_pdf_text",
    "extract_ocr_text",
    "extract_metadata",
    "chunk_text",
    "get_embeddings",
    "get_chroma_client",
    "get_or_create_collection",
    "heartbeat",
    "collection_count",
    "ingest_document",
]