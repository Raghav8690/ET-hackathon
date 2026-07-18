import easyocr
from typing import List, Dict, Any
import logging

# Initialize reader globally or lazily
_reader = None

def get_reader():
    global _reader
    if _reader is None:
        # Load English language model (disable verbose logging)
        logging.getLogger("easyocr").setLevel(logging.ERROR)
        _reader = easyocr.Reader(['en'], gpu=False)
    return _reader

def extract_ocr_text(file_path: str) -> List[Dict[str, Any]]:
    """
    Extract text from an image file using EasyOCR.
    
    Returns:
        List[Dict[str, Any]]: A list representing a single page containing all extracted text.
    """
    r = get_reader()
    result = r.readtext(file_path, detail=0)
    text = "\n".join(result)
    return [{"page": 1, "text": text}]
