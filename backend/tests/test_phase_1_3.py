"""
PS8 – Phase 1.3 Tests: Preprocessing & Extraction Pipeline

Tests cover:
  - Task 1.3.1: PDF Text Extraction Service (pdfplumber)
  - Task 1.3.2: OCR Text Extraction Engine (EasyOCR)
  - Task 1.3.3: Automatic Metadata and Entity Extractor (Regex)
  - Task 1.3.4: Semantic Text Chunker
"""

import pytest
from unittest.mock import patch, MagicMock

from backend.ingestion.metadata import extract_metadata
from backend.ingestion.chunker import chunk_text
from backend.ingestion.pdf import extract_pdf_text
from backend.ingestion.ocr import extract_ocr_text

# ===================================================================
# Task 1.3.1 – PDF Text Extraction Service
# ===================================================================
@patch("backend.ingestion.pdf.pdfplumber.open")
def test_extract_pdf_text(mock_pdfplumber_open):
    # Mock PDF pages
    mock_page_1 = MagicMock()
    mock_page_1.extract_text.return_value = "Page 1 content."
    mock_page_2 = MagicMock()
    mock_page_2.extract_text.return_value = "Page 2 content."
    
    mock_pdf = MagicMock()
    mock_pdf.pages = [mock_page_1, mock_page_2]
    
    # Setup context manager mock
    mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf
    
    results = extract_pdf_text("dummy.pdf")
    
    assert len(results) == 2
    assert results[0]["page"] == 1
    assert results[0]["text"] == "Page 1 content."
    assert results[1]["page"] == 2
    assert results[1]["text"] == "Page 2 content."

# ===================================================================
# Task 1.3.2 – OCR Text Extraction Engine
# ===================================================================
@patch("backend.ingestion.ocr.get_reader")
def test_extract_ocr_text(mock_get_reader):
    mock_reader = MagicMock()
    # readtext returns a list of text string when detail=0
    mock_reader.readtext.return_value = ["Line 1 of image.", "Line 2 of image."]
    mock_get_reader.return_value = mock_reader
    
    results = extract_ocr_text("dummy.png")
    
    assert len(results) == 1
    assert results[0]["page"] == 1
    assert results[0]["text"] == "Line 1 of image.\nLine 2 of image."

# ===================================================================
# Task 1.3.3 – Automatic Metadata and Entity Extractor
# ===================================================================
def test_extract_metadata_equipment_and_serial():
    text = "This is a maintenance manual for Pump Model P-101 Serial Number SN-883921."
    metadata = extract_metadata(text)
    
    assert metadata["equipment_id"] == "P-101"
    assert metadata["serial_number"] == "SN-883921"
    assert metadata["doc_type"] == "manual"

def test_extract_metadata_report_type():
    text = "Failure log for equipment."
    metadata = extract_metadata(text)
    
    assert metadata["doc_type"] == "report"

def test_extract_metadata_other_type():
    text = "Just some random text."
    metadata = extract_metadata(text)
    
    assert metadata["doc_type"] == "other"

# ===================================================================
# Task 1.3.4 – Semantic Text Chunker
# ===================================================================
def test_chunk_text_basic():
    pages = [
        {
            "page": 1,
            "text": "Paragraph 1\n\nParagraph 2\n\nParagraph 3"
        }
    ]
    
    # Small chunk size to force splitting
    chunks = chunk_text(pages, chunk_size=20, overlap=5)
    
    assert len(chunks) == 3
    assert chunks[0]["page"] == 1
    assert chunks[0]["section_title"] == "General"
    assert "Paragraph 1" in chunks[0]["text"]
    assert "Paragraph 2" in chunks[1]["text"]
    assert "Paragraph 3" in chunks[2]["text"]

def test_chunk_text_multiple_pages():
    pages = [
        {
            "page": 1,
            "text": "Page 1 content."
        },
        {
            "page": 2,
            "text": "Page 2 content."
        }
    ]
    
    chunks = chunk_text(pages, chunk_size=100, overlap=10)
    
    assert len(chunks) == 2
    assert chunks[0]["page"] == 1
    assert chunks[1]["page"] == 2
