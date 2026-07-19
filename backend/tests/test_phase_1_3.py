"""
PS8 – Phase 1.3 Tests: Preprocessing & Extraction Pipeline

Tests cover:
  - Task 1.3.1: PDF Text Extraction Service
  - Task 1.3.2: OCR Text Extraction Engine
  - Task 1.3.3: Automatic Metadata and Entity Extractor
  - Task 1.3.4: Semantic Text Chunker
"""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from backend.ingestion.metadata import extract_metadata
from backend.ingestion.chunker import chunk_text


# ===================================================================
# Task 1.3.1 – PDF Text Extraction Service
# ===================================================================
class TestPDFExtraction:
    """Tests for backend.ingestion.pdf.extract_pdf_text"""

    def test_file_not_found_raises(self):
        from backend.ingestion.pdf import extract_pdf_text
        with pytest.raises(FileNotFoundError):
            extract_pdf_text("/nonexistent/path/file.pdf")

    def test_non_pdf_raises_value_error(self):
        from backend.ingestion.pdf import extract_pdf_text
        # Create a temp .txt file
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"hello")
            path = f.name
        try:
            with pytest.raises(ValueError, match="Expected a .pdf"):
                extract_pdf_text(path)
        finally:
            os.unlink(path)

    @patch("pdfplumber.open")
    def test_extract_pdf_text_with_pdfplumber(self, mock_pdfplumber_open):
        """Mock pdfplumber to verify contract output format."""
        mock_page_1 = MagicMock()
        mock_page_1.extract_text.return_value = "Page 1 content."
        mock_page_2 = MagicMock()
        mock_page_2.extract_text.return_value = "Page 2 content."

        mock_pdf = MagicMock()
        mock_pdf.pages = [mock_page_1, mock_page_2]
        mock_pdfplumber_open.return_value.__enter__.return_value = mock_pdf

        # Create a temp .pdf file so the file-exists check passes
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
            f.write(b"%PDF-1.4 fake")
            path = f.name

        try:
            from backend.ingestion.pdf import extract_pdf_text
            results = extract_pdf_text(path)

            assert len(results) == 2
            assert results[0]["page"] == 1
            assert results[0]["text"] == "Page 1 content."
            assert results[1]["page"] == 2
            assert results[1]["text"] == "Page 2 content."
        finally:
            os.unlink(path)


# ===================================================================
# Task 1.3.2 – OCR Text Extraction Engine
# ===================================================================
class TestOCRExtraction:
    """Tests for backend.ingestion.ocr.extract_ocr_text"""

    def test_file_not_found_raises(self):
        from backend.ingestion.ocr import extract_ocr_text
        with pytest.raises(FileNotFoundError):
            extract_ocr_text("/nonexistent/image.png")

    def test_unsupported_extension_raises(self):
        from backend.ingestion.ocr import extract_ocr_text
        with tempfile.NamedTemporaryFile(suffix=".xyz", delete=False) as f:
            f.write(b"data")
            path = f.name
        try:
            with pytest.raises(ValueError, match="Unsupported file type"):
                extract_ocr_text(path)
        finally:
            os.unlink(path)

    @patch("backend.ingestion.ocr._get_easyocr_reader")
    def test_ocr_image_returns_correct_format(self, mock_reader_func):
        """Mock EasyOCR to verify output format for image files."""
        mock_reader = MagicMock()
        mock_reader.readtext.return_value = ["Line 1 of image.", "Line 2 of image."]
        mock_reader_func.return_value = mock_reader

        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            f.write(b"\x89PNG\r\n")
            path = f.name

        try:
            from backend.ingestion.ocr import extract_ocr_text
            results = extract_ocr_text(path)

            assert len(results) == 1
            assert results[0]["page"] == 1
            assert "Line 1 of image." in results[0]["text"]
            assert "Line 2 of image." in results[0]["text"]
        finally:
            os.unlink(path)


# ===================================================================
# Task 1.3.3 – Automatic Metadata and Entity Extractor
# ===================================================================
class TestMetadataExtraction:
    """Tests for backend.ingestion.metadata.extract_metadata"""

    def test_equipment_id_and_serial(self):
        text = "This is a maintenance manual for Pump Model P-101 Serial Number SN-883921."
        metadata = extract_metadata(text)

        assert metadata.get("equipment_id") == "P-101"
        assert metadata.get("serial_number") == "SN-883921"
        assert metadata.get("doc_type") == "manual"

    def test_report_type_detection(self):
        text = "Failure investigation report for pump bearing overheating incident."
        metadata = extract_metadata(text)
        assert metadata["doc_type"] == "report"

    def test_sop_type_detection(self):
        text = "Standard Operating Procedure for valve maintenance."
        metadata = extract_metadata(text)
        assert metadata["doc_type"] == "sop"

    def test_inspection_type_detection(self):
        text = "Annual inspection audit checklist for compressor unit."
        metadata = extract_metadata(text)
        assert metadata["doc_type"] == "inspection"

    def test_other_type_fallback(self):
        text = "Just some random text with no keywords."
        metadata = extract_metadata(text)
        assert metadata["doc_type"] == "other"

    def test_date_extraction_iso(self):
        text = "Serviced on 2025-08-14 by technician."
        metadata = extract_metadata(text)
        assert "dates" in metadata
        assert "2025-08-14" in metadata["dates"]
        assert metadata["date_range_start"] == "2025-08-14"

    def test_date_extraction_natural(self):
        text = "Serviced on 14th Aug 2025 and again 20th September 2025."
        metadata = extract_metadata(text)
        assert "dates" in metadata
        assert len(metadata["dates"]) >= 1

    def test_standalone_equipment_code(self):
        """Test that standalone codes like C-302 are picked up."""
        text = "Compressor C-302 showed vibration anomaly."
        metadata = extract_metadata(text)
        assert metadata.get("equipment_id") == "C-302"

    @patch("backend.ingestion.metadata._call_ollama", return_value='{"equipment_id": "C-999", "doc_type": "report"}')
    @patch("backend.ingestion.metadata._ollama_is_configured", return_value=True)
    def test_explicit_equipment_tag_overrides_llm_guess(self, _, __):
        """The LLM must not replace an asset tag explicitly found in source text."""
        metadata = extract_metadata("Failure report for Pump A (P-101).")
        assert metadata["equipment_id"] == "P-101"

    @patch("backend.ingestion.metadata._call_ollama", return_value='{"equipment_id": "C-999", "doc_type": "report"}')
    @patch("backend.ingestion.metadata._ollama_is_configured", return_value=True)
    def test_hallucinated_equipment_tag_is_discarded(self, _, __):
        metadata = extract_metadata("Failure report for Pump A.")
        assert "equipment_id" not in metadata

    @patch("backend.ingestion.metadata._call_ollama", return_value='{"serial_number": "SN-000000", "doc_type": "report"}')
    @patch("backend.ingestion.metadata._ollama_is_configured", return_value=True)
    def test_explicit_serial_number_overrides_llm_guess(self, _, __):
        metadata = extract_metadata("Pump P-101 serial number SN-883921 failed.")
        assert metadata["serial_number"] == "SN-883921"

    def test_analytics_metadata_is_normalised_from_source(self):
        text = (
            "Failure report: Pump A (P-101) and Compressor C-302 failed on 2026-07-15. "
            "The inspection was non-compliant. Annual downtime impact is $50,000/year. "
            "Root cause: cooling system failure caused bearing overheating."
        )
        with patch("backend.ingestion.metadata._ollama_is_configured", return_value=False):
            metadata = extract_metadata(text)

        assert {item["equipment_id"] for item in metadata["equipment_mentions"]} == {"P-101", "C-302"}
        assert metadata["structured_costs"] == [{
            "amount": 50000.0, "currency": "USD", "cost_type": "annual_impact",
            "period": "yearly", "evidence": "$50,000/year",
        }]
        assert metadata["inspection_status"] == "NON_COMPLIANT"
        assert metadata["event_dates"][0]["event_type"] == "inspection"
        assert metadata["metadata_schema_version"] == "2.0"

    def test_empty_text(self):
        metadata = extract_metadata("")
        assert metadata["doc_type"] == "other"
        assert "dates" not in metadata


# ===================================================================
# Task 1.3.4 – Semantic Text Chunker
# ===================================================================
class TestChunker:
    """Tests for backend.ingestion.chunker.chunk_text"""

    def test_basic_chunking(self):
        pages = [{"page": 1, "text": "Paragraph 1\n\nParagraph 2\n\nParagraph 3"}]
        chunks = chunk_text(pages, chunk_size=30, overlap=5)

        assert len(chunks) >= 2
        assert all(c["page"] == 1 for c in chunks)
        assert all("section_title" in c for c in chunks)
        assert all("chunk_index" in c for c in chunks)
        assert all("char_count" in c for c in chunks)

    def test_no_chunk_exceeds_size(self):
        long_text = "word " * 500  # ~2500 chars
        pages = [{"page": 1, "text": long_text}]
        chunk_size = 200
        chunks = chunk_text(pages, chunk_size=chunk_size, overlap=50)

        for chunk in chunks:
            assert chunk["char_count"] <= chunk_size + 50  # small tolerance for edge cases

    def test_multiple_pages(self):
        pages = [
            {"page": 1, "text": "Page 1 content."},
            {"page": 2, "text": "Page 2 content."},
        ]
        chunks = chunk_text(pages, chunk_size=100, overlap=10)

        assert len(chunks) == 2
        assert chunks[0]["page"] == 1
        assert chunks[1]["page"] == 2

    def test_empty_text_produces_no_chunks(self):
        pages = [{"page": 1, "text": ""}]
        chunks = chunk_text(pages, chunk_size=100, overlap=10)
        assert len(chunks) == 0

    def test_chunk_index_sequential(self):
        pages = [
            {"page": 1, "text": "A\n\nB\n\nC\n\nD"},
            {"page": 2, "text": "E\n\nF"},
        ]
        chunks = chunk_text(pages, chunk_size=5, overlap=0)
        indices = [c["chunk_index"] for c in chunks]
        assert indices == list(range(len(chunks)))

    def test_invalid_params(self):
        with pytest.raises(ValueError):
            chunk_text([], chunk_size=0, overlap=0)
        with pytest.raises(ValueError):
            chunk_text([], chunk_size=100, overlap=-1)
        with pytest.raises(ValueError):
            chunk_text([], chunk_size=100, overlap=100)

    def test_header_detection(self):
        text = "## Section Title\n\nSome content here about equipment."
        pages = [{"page": 1, "text": text}]
        chunks = chunk_text(pages, chunk_size=500, overlap=50)
        assert len(chunks) >= 1
        assert chunks[0]["section_title"] == "Section Title"
