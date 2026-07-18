import pdfplumber
from typing import List, Dict, Any

def extract_pdf_text(file_path: str) -> List[Dict[str, Any]]:
    """
    Extract text page-by-page from a PDF file.
    
    Returns:
        List[Dict[str, Any]]: A list where each dict contains 'page' (int) and 'text' (str).
    """
    results = []
    with pdfplumber.open(file_path) as pdf:
        for i, page in enumerate(pdf.pages):
            text = page.extract_text() or ""
            results.append({
                "page": i + 1,
                "text": text
            })
    return results
