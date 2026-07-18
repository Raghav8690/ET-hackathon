"""
PS8 – Automatic Metadata and Entity Extractor (Task 1.3.3)

Regex and keyword-based matching modules to extract:
- Equipment ID / Model number
- Serial Numbers
- Document Type (SOP, Manual, Failure Log, Report, etc.)
- Date ranges mentioned in the text

Contract
--------
Function ``extract_metadata(text: str) -> Dict[str, Any]``

Example
-------
>>> extract_metadata("Pump Model P-101 Serial Number SN-883921")
{"equipment_id": "P-101", "serial_number": "SN-883921", "doc_type": "manual"}
"""

import re
from datetime import datetime
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Equipment & Serial patterns
# ---------------------------------------------------------------------------
_EQUIPMENT_PATTERNS = [
    # "Equipment ID: P-101" or "Model: P-101" or "Equipment ID P-101"
    re.compile(r"(?:Equipment\s*ID|Model|Asset\s*(?:ID|Tag))\s*[:\-]?\s*([A-Z0-9][\w\-]{1,30})", re.IGNORECASE),
    # Standalone equipment codes like "PUMP-101", "C-302", "V-401"
    re.compile(r"\b([A-Z]{1,5}[\-][0-9]{2,6}[A-Z]?)\b"),
]

_SERIAL_PATTERNS = [
    re.compile(r"(?:Serial\s*(?:Number|No\.?|#))\s*[:\-]?\s*([A-Z0-9][\w\-]{3,30})", re.IGNORECASE),
    re.compile(r"\b(SN[\-]?[A-Z0-9]{4,20})\b", re.IGNORECASE),
]

# ---------------------------------------------------------------------------
# Document type classification keywords
# ---------------------------------------------------------------------------
_DOC_TYPE_KEYWORDS = {
    "manual": ["manual", "handbook", "specification", "spec sheet", "user guide", "oem"],
    "sop": ["sop", "standard operating procedure", "procedure", "work instruction"],
    "report": ["report", "failure", "incident", "log", "investigation", "analysis"],
    "inspection": ["inspection", "audit", "checklist", "compliance check"],
    "compliance": ["compliance", "regulatory", "osha", "iso", "api standard"],
    "schematic": ["schematic", "diagram", "p&id", "piping", "drawing", "blueprint"],
}

# ---------------------------------------------------------------------------
# Date patterns
# ---------------------------------------------------------------------------
_DATE_PATTERNS = [
    # ISO: 2025-08-14
    re.compile(r"\b(\d{4}[\-/]\d{1,2}[\-/]\d{1,2})\b"),
    # DD/MM/YYYY or MM/DD/YYYY
    re.compile(r"\b(\d{1,2}[\-/]\d{1,2}[\-/]\d{4})\b"),
    # "14th Aug 2025", "Aug 14, 2025", "August 2025"
    re.compile(
        r"\b(\d{1,2}(?:st|nd|rd|th)?\s+"
        r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+\d{4})\b",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b((?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|"
        r"Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
        r"\s+\d{1,2},?\s+\d{4})\b",
        re.IGNORECASE,
    ),
]

_DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%m-%d-%Y",
    "%m/%d/%Y",
    "%d %B %Y",
    "%d %b %Y",
    "%B %d, %Y",
    "%B %d %Y",
    "%b %d, %Y",
    "%b %d %Y",
]


def _parse_date(date_str: str) -> Optional[datetime]:
    """Try to parse a date string using multiple formats."""
    # Remove ordinal suffixes (1st, 2nd, 3rd, 4th)
    cleaned = re.sub(r"(\d+)(?:st|nd|rd|th)", r"\1", date_str)
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(cleaned.strip(), fmt)
        except ValueError:
            continue
    return None


def _extract_dates(text: str) -> List[datetime]:
    """Extract all recognisable dates from text."""
    dates = []
    for pattern in _DATE_PATTERNS:
        for match in pattern.finditer(text):
            parsed = _parse_date(match.group(1))
            if parsed:
                dates.append(parsed)
    return sorted(set(dates))


def extract_metadata(text: str) -> Dict[str, Any]:
    """Extract structured metadata from raw document text.

    Returns
    -------
    Dict[str, Any]
        Keys may include:
        - ``equipment_id`` (str | None)
        - ``serial_number`` (str | None)
        - ``doc_type`` (str) – one of: manual, sop, report, inspection, compliance, schematic, other
        - ``dates`` (List[str]) – ISO-formatted dates found in text
        - ``date_range_start`` (str | None) – earliest date found
        - ``date_range_end`` (str | None) – latest date found
    """
    metadata: Dict[str, Any] = {}

    # --- Equipment ID ---
    for pattern in _EQUIPMENT_PATTERNS:
        match = pattern.search(text)
        if match:
            metadata["equipment_id"] = match.group(1).upper()
            break

    # --- Serial Number ---
    for pattern in _SERIAL_PATTERNS:
        match = pattern.search(text)
        if match:
            metadata["serial_number"] = match.group(1).upper()
            break

    # --- Document Type ---
    text_lower = text.lower()
    doc_type = "other"
    best_score = 0
    for dtype, keywords in _DOC_TYPE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > best_score:
            best_score = score
            doc_type = dtype
    metadata["doc_type"] = doc_type

    # --- Dates ---
    dates = _extract_dates(text)
    if dates:
        metadata["dates"] = [d.strftime("%Y-%m-%d") for d in dates]
        metadata["date_range_start"] = dates[0].strftime("%Y-%m-%d")
        metadata["date_range_end"] = dates[-1].strftime("%Y-%m-%d")

    return metadata
