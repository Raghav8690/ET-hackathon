"""
PS8 – PDF Text Extraction Service (Task 1.3.1)

Extracts text page-by-page from PDF files using pdfplumber.
Falls back to pypdf for files that pdfplumber cannot handle.

Contract
--------
Function ``extract_pdf_text(file_path: str) -> List[Dict[str, Any]]``
where each dict contains ``{"page": int, "text": str}``.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)


def extract_pdf_text(file_path: str) -> List[Dict[str, Any]]:
    """Extract text page-by-page from a PDF file.

    Uses ``pdfplumber`` as the primary extractor. Falls back to ``pypdf``
    if pdfplumber fails to open/parse the file.

    Parameters
    ----------
    file_path : str
        Absolute or relative path to the PDF file.

    Returns
    -------
    List[Dict[str, Any]]
        A list where each dict contains:
        - ``page`` (int): 1-indexed page number.
        - ``text`` (str): Extracted text (may be empty for scanned pages).

    Raises
    ------
    FileNotFoundError
        If *file_path* does not exist.
    ValueError
        If the file is not a PDF or cannot be parsed.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {file_path}")
    if path.suffix.lower() != ".pdf":
        raise ValueError(f"Expected a .pdf file, got: {path.suffix}")

    # --- Attempt 1: pdfplumber (better at tables / complex layouts) --------
    try:
        import pdfplumber

        results: List[Dict[str, Any]] = []
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                text = page.extract_text() or ""
                results.append({"page": i + 1, "text": text})
        if results:
            logger.info("pdfplumber extracted %d pages from %s", len(results), path.name)
            return results
    except Exception as exc:
        logger.warning("pdfplumber failed for %s: %s – falling back to pypdf", path.name, exc)

    # --- Attempt 2: pypdf (more tolerant of broken PDFs) -------------------
    try:
        from pypdf import PdfReader

        reader = PdfReader(file_path)
        results = []
        for i, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            results.append({"page": i + 1, "text": text})
        logger.info("pypdf extracted %d pages from %s", len(results), path.name)
        return results
    except ImportError:
        # pypdf not installed – try PyPDF2 as last resort
        try:
            from PyPDF2 import PdfReader as PdfReader2  # noqa: N811

            reader2 = PdfReader2(file_path)
            results = []
            for i, page in enumerate(reader2.pages):
                text = page.extract_text() or ""
                results.append({"page": i + 1, "text": text})
            logger.info("PyPDF2 extracted %d pages from %s", len(results), path.name)
            return results
        except ImportError:
            raise ValueError(
                "No PDF library available. Install pdfplumber, pypdf, or PyPDF2."
            )
    except Exception as exc:
        raise ValueError(f"Failed to extract text from {path.name}: {exc}") from exc
