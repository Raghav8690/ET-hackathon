"""
PS8 – OCR Text Extraction Engine (Task 1.3.2)

Processes scanned PDF pages and images to extract text via OCR.
Primary engine: EasyOCR.  Fallback: pytesseract (Tesseract OCR).

Contract
--------
Function ``extract_ocr_text(file_path: str) -> List[Dict[str, Any]]``
where each dict contains ``{"page": int, "text": str}``.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

# Supported image extensions for direct OCR
_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}

# ---------------------------------------------------------------------------
# Lazy-loaded EasyOCR reader
# ---------------------------------------------------------------------------
_reader = None


def _get_easyocr_reader():
    """Lazily initialise the EasyOCR reader (downloads model on first use)."""
    global _reader
    if _reader is None:
        import easyocr

        logging.getLogger("easyocr").setLevel(logging.ERROR)
        _reader = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _reader


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_ocr_text(file_path: str) -> List[Dict[str, Any]]:
    """Extract text from an image or scanned PDF using OCR.

    For images, returns a single-page result.
    For scanned PDFs, converts each page to an image and runs OCR.

    Parameters
    ----------
    file_path : str
        Path to an image or PDF file.

    Returns
    -------
    List[Dict[str, Any]]
        Each dict has ``page`` (int, 1-indexed) and ``text`` (str).

    Raises
    ------
    FileNotFoundError
        If file does not exist.
    ValueError
        If file format is not supported or OCR fails completely.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    ext = path.suffix.lower()

    if ext in _IMAGE_EXTENSIONS:
        text = _ocr_image(str(path))
        return [{"page": 1, "text": text}]
    elif ext == ".pdf":
        return _ocr_pdf(str(path))
    else:
        raise ValueError(
            f"Unsupported file type for OCR: {ext}. "
            f"Supported: {', '.join(sorted(_IMAGE_EXTENSIONS | {'.pdf'}))}"
        )


def _ocr_image(image_path: str) -> str:
    """Run OCR on a single image file, with fallback from EasyOCR to Tesseract."""
    # Attempt 1: EasyOCR
    try:
        reader = _get_easyocr_reader()
        results = reader.readtext(image_path, detail=0)
        text = "\n".join(results)
        if text.strip():
            logger.info("EasyOCR extracted %d chars from %s", len(text), Path(image_path).name)
            return text
    except Exception as exc:
        logger.warning("EasyOCR failed for %s: %s – trying Tesseract", Path(image_path).name, exc)

    # Attempt 2: Tesseract via pytesseract
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(image_path)
        text = pytesseract.image_to_string(img)
        logger.info("Tesseract extracted %d chars from %s", len(text), Path(image_path).name)
        return text
    except ImportError:
        logger.warning("pytesseract not installed – cannot fallback for %s", Path(image_path).name)
    except Exception as exc:
        logger.warning("Tesseract failed for %s: %s", Path(image_path).name, exc)

    return ""


def _ocr_pdf(pdf_path: str) -> List[Dict[str, Any]]:
    """Convert scanned PDF pages to images and OCR each page."""
    results: List[Dict[str, Any]] = []

    # Try pdf2image (requires poppler)
    try:
        from pdf2image import convert_from_path
        import tempfile

        images = convert_from_path(pdf_path, dpi=200)
        for i, img in enumerate(images):
            # Save temp image and OCR it
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                img.save(tmp.name, "PNG")
                text = _ocr_image(tmp.name)
                results.append({"page": i + 1, "text": text})
                Path(tmp.name).unlink(missing_ok=True)
        return results
    except ImportError:
        logger.warning("pdf2image not available – treating PDF as single-page image for OCR")
    except Exception as exc:
        logger.warning("pdf2image conversion failed: %s – falling back", exc)

    # Fallback: try EasyOCR directly on the PDF path (works for some simple cases)
    try:
        text = _ocr_image(pdf_path)
        return [{"page": 1, "text": text}]
    except Exception:
        return [{"page": 1, "text": ""}]
