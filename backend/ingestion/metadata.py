"""
PS8 – LLM-Powered Metadata & Entity Extractor

Uses a local Ollama model (configured via OLLAMA_MODEL env var) to extract
comprehensive metadata from document text.  Falls back to regex-only extraction
if Ollama is not configured or unreachable.

Extracted metadata includes:
- Equipment IDs, serial numbers, model numbers, manufacturers
- Document type classification
- Date ranges
- Executive summary of the document
- Key entities (people, organisations, locations)
- Failure modes, root causes, severity
- Cost figures (parts, labour, downtime)
- Compliance / regulatory references
- Technical specifications & measurements
- Action items / recommendations

Contract
--------
Function ``extract_metadata(text: str) -> Dict[str, Any]``
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ollama configuration
# ---------------------------------------------------------------------------
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: Optional[str] = os.getenv("OLLAMA_MODEL")

# Maximum characters of document text sent to the LLM (to fit context window)
_MAX_LLM_INPUT_CHARS = 12_000

# ---------------------------------------------------------------------------
# Regex fallback patterns (kept from original for non-LLM path)
# ---------------------------------------------------------------------------
_EQUIPMENT_PATTERNS = [
    re.compile(
        r"(?:Equipment\s*ID|Model|Asset\s*(?:ID|Tag))\s*[:\-]?\s*([A-Z0-9][\w\-]{1,30})",
        re.IGNORECASE,
    ),
    re.compile(r"\b([A-Z]{1,5}[\-][0-9]{2,6}[A-Z]?)\b"),
]

_SERIAL_PATTERNS = [
    re.compile(
        r"(?:Serial\s*(?:Number|No\.?|#))\s*[:\-]?\s*([A-Z0-9][\w\-]{3,30})",
        re.IGNORECASE,
    ),
    re.compile(r"\b(SN[\-]?[A-Z0-9]{4,20})\b", re.IGNORECASE),
]

_DOC_TYPE_KEYWORDS = {
    "manual": ["manual", "handbook", "specification", "spec sheet", "user guide", "oem"],
    "sop": ["sop", "standard operating procedure", "procedure", "work instruction"],
    "report": ["report", "failure", "incident", "log", "investigation", "analysis"],
    "inspection": ["inspection", "audit", "checklist", "compliance check"],
    "compliance": ["compliance", "regulatory", "osha", "iso", "api standard"],
    "schematic": ["schematic", "diagram", "p&id", "piping", "drawing", "blueprint"],
}

_DATE_PATTERNS = [
    re.compile(r"\b(\d{4}[\-/]\d{1,2}[\-/]\d{1,2})\b"),
    re.compile(r"\b(\d{1,2}[\-/]\d{1,2}[\-/]\d{4})\b"),
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
    "%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y",
    "%m-%d-%Y", "%m/%d/%Y", "%d %B %Y", "%d %b %Y",
    "%B %d, %Y", "%B %d %Y", "%b %d, %Y", "%b %d %Y",
]


# ---------------------------------------------------------------------------
# LLM metadata extraction prompt
# ---------------------------------------------------------------------------
_EXTRACTION_PROMPT = """You are a document analysis expert. Analyse the following document text and extract ALL available metadata.

Return ONLY a valid JSON object (no markdown, no backticks, no commentary) with these exact keys. Use null for fields you cannot determine:

{
  "summary": "A 2-3 sentence executive summary of the document content and purpose",
  "doc_type": "One of: manual, sop, report, inspection, compliance, schematic, memo, letter, invoice, datasheet, other",
  "language": "Primary language of the document",
  "equipment_id": "Primary equipment identifier like PUMP-101, C-302, V-401, or any alphanumeric equipment code",
  "equipment_name": "Full equipment name like Centrifugal Pump A",
  "equipment_type": "Equipment category like pump, compressor, valve, motor, conveyor, turbine, boiler",
  "serial_number": "Serial number if found",
  "model_number": "Model or part number if found",
  "manufacturer": "Manufacturer or OEM name if mentioned",
  "key_entities": ["Important named entities: people, organisations, departments, systems"],
  "locations": ["Physical locations: plants, buildings, areas, bays"],
  "people_and_roles": ["People with their role, e.g. John Smith (Inspector)"],
  "dates_mentioned": ["Dates in YYYY-MM-DD format"],
  "date_range_start": "Earliest date YYYY-MM-DD or null",
  "date_range_end": "Latest date YYYY-MM-DD or null",
  "failure_modes": ["Failure modes or problems described"],
  "root_causes": ["Root causes identified or suspected"],
  "severity": "LOW, MEDIUM, HIGH, or CRITICAL if mentioned, else null",
  "costs_mentioned": ["Cost figures like $500 parts, $3000 repair"],
  "downtime_hours": "Total downtime hours mentioned or null",
  "compliance_references": ["Regulatory standards: OSHA, ISO, API etc."],
  "compliance_relevant": false,
  "technical_specs": ["Technical specifications: measurements, ratings, pressures, temperatures"],
  "action_items": ["Recommendations or required actions"],
  "tags": ["5-10 keyword tags for search"]
}

CRITICAL RULES:
- Extract equipment_id even if it is an informal name like "Pump A" or "Motor 3" — use whatever identifier is present.
- Do NOT fabricate information, only extract what is present.
- Convert dates to YYYY-MM-DD format when possible.
- Return ONLY the raw JSON object. No explanations, no markdown fences.

--- DOCUMENT TEXT ---
""" # noqa: E501


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _parse_date(date_str: str) -> Optional[datetime]:
    """Try to parse a date string using multiple formats."""
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


def _ollama_is_configured() -> bool:
    """Check if OLLAMA_MODEL is set in environment."""
    return bool(OLLAMA_MODEL and OLLAMA_MODEL.strip())


def _call_ollama(prompt: str) -> Optional[str]:
    """Send a prompt to the local Ollama API and return the response text.

    Returns None if the call fails for any reason.
    """
    if not _ollama_is_configured():
        return None

    url = f"{OLLAMA_BASE_URL}/api/generate"
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "format": "json",  # Force JSON output from Ollama
        "options": {
            "temperature": 0.1,  # Low temperature for factual extraction
            "num_predict": 4096,
        },
    }

    try:
        with httpx.Client(timeout=180.0) as client:
            response = client.post(url, json=payload)
            response.raise_for_status()
            data = response.json()
            return data.get("response", "")
    except httpx.ConnectError:
        logger.error(
            "Cannot connect to Ollama at %s. Is Ollama running?", OLLAMA_BASE_URL
        )
        return None
    except httpx.HTTPStatusError as exc:
        logger.error("Ollama HTTP error: %s", exc)
        return None
    except Exception as exc:
        logger.error("Ollama call failed: %s", exc)
        return None


def _strip_backslashes(text: str) -> str:
    """Remove redundant backslash escapes that some LLMs inject into JSON.

    Handles patterns like:  \\/  →  /   and  \\'  →  '
    Does NOT touch valid JSON escapes like \\n, \\t, \\\", \\\\
    """
    # Replace escaped forward slashes (common LLM artefact)
    text = text.replace("\\/", "/")
    # Replace escaped single quotes (not valid JSON, but LLMs do it)
    text = text.replace("\\'", "'")
    return text


def _parse_llm_json(raw: str) -> Optional[Dict[str, Any]]:
    """Try to parse JSON from LLM output, handling markdown fences and escapes."""
    if not raw:
        return None

    # Strip markdown code fences if present
    text = raw.strip()
    if text.startswith("```"):
        # Remove opening fence (```json or ```)
        text = re.sub(r"^```(?:json)?\s*\n?", "", text)
        # Remove closing fence
        text = re.sub(r"\n?```\s*$", "", text)

    # Clean up redundant backslash escapes
    text = _strip_backslashes(text)

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try to find the first JSON object in the text
    brace_start = text.find("{")
    brace_end = text.rfind("}")
    if brace_start != -1 and brace_end != -1 and brace_end > brace_start:
        json_str = text[brace_start : brace_end + 1]
        try:
            return json.loads(json_str)
        except json.JSONDecodeError:
            # Last resort: try to fix common JSON issues
            # Remove trailing commas before } or ]
            fixed = re.sub(r",\s*([}\]])", r"\1", json_str)
            try:
                return json.loads(fixed)
            except json.JSONDecodeError:
                pass

    logger.warning("Failed to parse LLM output as JSON. Raw (first 500 chars): %s", raw[:500])
    return None


def _clean_string_value(val: Any) -> Optional[str]:
    """Clean a string value: strip whitespace, remove backslashes, reject nullish."""
    if val is None:
        return None
    if not isinstance(val, str):
        val = str(val)
    # Remove stray backslashes that aren't valid escapes
    val = val.replace("\\", "")
    val = val.strip()
    if not val or val.lower() in ("null", "none", "n/a", "na", "undefined"):
        return None
    return val


def _clean_llm_metadata(raw_meta: Dict[str, Any]) -> Dict[str, Any]:
    """Normalise and clean up LLM-extracted metadata."""
    cleaned: Dict[str, Any] = {}

    # --- Strings (normalise empty → skip) ---
    for key in (
        "summary", "doc_type", "language",
        "equipment_id", "equipment_name", "equipment_type",
        "serial_number", "model_number", "manufacturer",
        "date_range_start", "date_range_end",
        "severity", "downtime_hours",
    ):
        val = _clean_string_value(raw_meta.get(key))
        if val:
            cleaned[key] = val

    # --- Lists (filter out empties, clean each value) ---
    for key in (
        "key_entities", "locations", "people_and_roles",
        "dates_mentioned", "failure_modes", "root_causes",
        "costs_mentioned", "compliance_references",
        "technical_specs", "action_items", "tags",
    ):
        val = raw_meta.get(key)
        if isinstance(val, list):
            filtered = []
            for v in val:
                clean_v = _clean_string_value(v)
                if clean_v:
                    filtered.append(clean_v)
            if filtered:
                cleaned[key] = filtered

    # --- Booleans ---
    compliance_val = raw_meta.get("compliance_relevant")
    if isinstance(compliance_val, bool):
        cleaned["compliance_relevant"] = compliance_val
    elif isinstance(compliance_val, str):
        cleaned["compliance_relevant"] = compliance_val.lower() in ("true", "yes", "1")

    # --- Normalise doc_type ---
    valid_doc_types = {
        "manual", "sop", "report", "inspection", "compliance",
        "schematic", "memo", "letter", "invoice", "datasheet", "other",
    }
    if cleaned.get("doc_type", "").lower() not in valid_doc_types:
        cleaned["doc_type"] = "other"
    else:
        cleaned["doc_type"] = cleaned["doc_type"].lower()

    # Mark extraction method
    cleaned["_extraction_method"] = "ollama_llm"

    return cleaned


# ---------------------------------------------------------------------------
# Regex-only fallback (original logic)
# ---------------------------------------------------------------------------
def _extract_metadata_regex(text: str) -> Dict[str, Any]:
    """Regex and keyword-based metadata extraction (no LLM)."""
    metadata: Dict[str, Any] = {}

    # Equipment ID
    for pattern in _EQUIPMENT_PATTERNS:
        match = pattern.search(text)
        if match:
            metadata["equipment_id"] = match.group(1).upper()
            break

    # Serial Number
    for pattern in _SERIAL_PATTERNS:
        match = pattern.search(text)
        if match:
            metadata["serial_number"] = match.group(1).upper()
            break

    # Document Type
    text_lower = text.lower()
    doc_type = "other"
    best_score = 0
    for dtype, keywords in _DOC_TYPE_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > best_score:
            best_score = score
            doc_type = dtype
    metadata["doc_type"] = doc_type

    # Dates
    dates = _extract_dates(text)
    if dates:
        metadata["dates_mentioned"] = [d.strftime("%Y-%m-%d") for d in dates]
        metadata["date_range_start"] = dates[0].strftime("%Y-%m-%d")
        metadata["date_range_end"] = dates[-1].strftime("%Y-%m-%d")

    # Generate a basic summary (first 300 chars)
    summary_text = text[:500].replace("\n", " ").strip()
    if len(summary_text) > 300:
        summary_text = summary_text[:297] + "..."
    metadata["summary"] = summary_text

    metadata["_extraction_method"] = "regex_fallback"

    return metadata


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_metadata(text: str) -> Dict[str, Any]:
    """Extract structured metadata from raw document text.

    Uses a local Ollama LLM model (set via OLLAMA_MODEL env var) for
    comprehensive extraction.  Falls back to regex patterns if Ollama is
    not configured or unreachable.

    Parameters
    ----------
    text : str
        Raw document text to analyse.

    Returns
    -------
    Dict[str, Any]
        Rich metadata dictionary.  Key fields:
        - ``summary`` – executive summary of the document
        - ``doc_type`` – document classification
        - ``equipment_id`` – primary equipment identifier
        - ``serial_number``, ``model_number``, ``manufacturer``
        - ``dates_mentioned``, ``date_range_start``, ``date_range_end``
        - ``failure_modes``, ``root_causes``, ``severity``
        - ``compliance_references``, ``compliance_relevant``
        - ``technical_specs``, ``action_items``, ``tags``
        - ``_extraction_method`` – "ollama_llm" or "regex_fallback"
    """
    if not text or not text.strip():
        return {"doc_type": "other", "summary": "", "_extraction_method": "empty_input"}

    # --- Try LLM extraction first ---
    if _ollama_is_configured():
        logger.info(
            "Attempting LLM metadata extraction via Ollama model '%s'",
            OLLAMA_MODEL,
        )

        # Truncate text to fit context window
        input_text = text[:_MAX_LLM_INPUT_CHARS]
        # Build prompt by simple concatenation (no .format() to avoid brace issues)
        prompt = _EXTRACTION_PROMPT + input_text

        raw_response = _call_ollama(prompt)
        if raw_response:
            parsed = _parse_llm_json(raw_response)
            if parsed:
                metadata = _clean_llm_metadata(parsed)
                logger.info(
                    "LLM metadata extraction successful: %d fields extracted",
                    len(metadata),
                )

                # Also try regex for equipment_id if LLM missed it
                if not metadata.get("equipment_id"):
                    for pattern in _EQUIPMENT_PATTERNS:
                        match = pattern.search(text)
                        if match:
                            metadata["equipment_id"] = match.group(1).upper()
                            logger.info(
                                "Regex supplemented equipment_id: %s",
                                metadata["equipment_id"],
                            )
                            break

                # Supplement with regex date extraction on full text (LLM
                # only sees truncated text, regex can scan the whole thing)
                regex_dates = _extract_dates(text)
                if regex_dates:
                    all_dates = set(metadata.get("dates_mentioned", []))
                    all_dates.update(d.strftime("%Y-%m-%d") for d in regex_dates)
                    metadata["dates_mentioned"] = sorted(all_dates)
                    metadata["date_range_start"] = metadata["dates_mentioned"][0]
                    metadata["date_range_end"] = metadata["dates_mentioned"][-1]

                return metadata
            else:
                logger.warning("LLM returned unparseable output, falling back to regex")
        else:
            logger.warning("LLM call failed, falling back to regex extraction")
    else:
        logger.error(
            "OLLAMA_MODEL not set in environment. "
            "Set OLLAMA_MODEL in your .env file to enable LLM metadata extraction. "
            "Falling back to regex-only extraction."
        )

    # --- Fallback: regex-only ---
    return _extract_metadata_regex(text)
