"""
PS8 – Semantic Text Chunker (Task 1.3.4)

Splits extracted text into semantic paragraphs/chunks that are suitable for
embedding and vector search.  Chunks retain page number, detected section
title, and metadata.

Contract
--------
Function ``chunk_text(pages_content, chunk_size, overlap) -> List[Dict]``
Chunks retain page number, header title, and metadata.
No chunk should exceed ``chunk_size`` characters.
"""

import re
from typing import Any, Dict, List

# Regex to detect markdown-style headers or ALL-CAPS section titles
_HEADER_PATTERN = re.compile(
    r"^(?:"
    r"#{1,6}\s+.+"          # Markdown headers: # Title, ## Subtitle
    r"|[A-Z][A-Z0-9 &\-]{4,80}$"  # ALL-CAPS SECTION TITLES
    r"|(?:\d+\.)+\s+.+"    # Numbered headers: 1.2.3 Title
    r")",
    re.MULTILINE,
)


def _detect_section_title(text: str) -> str:
    """Try to detect a section heading from the beginning of a chunk."""
    lines = text.strip().split("\n")
    for line in lines[:3]:  # Check first 3 lines
        line = line.strip()
        if _HEADER_PATTERN.match(line):
            # Clean up markdown formatting
            clean = re.sub(r"^#+\s*", "", line).strip()
            if clean:
                return clean[:128]  # Cap length
    return "General"


def _split_into_paragraphs(text: str) -> List[str]:
    """Split text into meaningful segments using double newlines, headers, etc."""
    # Split on double newlines first
    segments = re.split(r"\n\s*\n", text)
    
    result = []
    for segment in segments:
        segment = segment.strip()
        if not segment:
            continue
        # Further split very long segments at header boundaries
        if len(segment) > 2000:
            sub_segments = _HEADER_PATTERN.split(segment)
            result.extend(s.strip() for s in sub_segments if s.strip())
        else:
            result.append(segment)
    return result


def chunk_text(
    pages_content: List[Dict[str, Any]],
    chunk_size: int = 1000,
    overlap: int = 200,
) -> List[Dict[str, Any]]:
    """Split extracted text into semantic chunks.

    Parameters
    ----------
    pages_content : List[Dict]
        Output from ``extract_pdf_text`` or ``extract_ocr_text``.
        Each dict must have ``page`` (int) and ``text`` (str).
    chunk_size : int
        Maximum character length of each chunk (default 1000).
    overlap : int
        Number of characters to overlap between consecutive chunks
        for context continuity (default 200).

    Returns
    -------
    List[Dict[str, Any]]
        Each dict contains:
        - ``page`` (int): Source page number (1-indexed).
        - ``text`` (str): The chunk text.
        - ``section_title`` (str): Detected or default section header.
        - ``chunk_index`` (int): Global index of the chunk (0-based).
        - ``char_count`` (int): Character count of the chunk text.

    Guarantees
    ----------
    - No chunk text exceeds ``chunk_size`` characters.
    - Consecutive chunks share approximately ``overlap`` characters.
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size must be positive")
    if overlap < 0:
        raise ValueError("overlap must be non-negative")
    if overlap >= chunk_size:
        raise ValueError("overlap must be less than chunk_size")

    chunks: List[Dict[str, Any]] = []
    global_index = 0

    for page_data in pages_content:
        page_num = page_data.get("page", 1)
        text = page_data.get("text", "")

        if not text.strip():
            continue

        paragraphs = _split_into_paragraphs(text)
        current_chunk = ""
        current_title = "General"

        for para in paragraphs:
            # Detect header for this paragraph
            detected = _detect_section_title(para)
            if detected != "General":
                current_title = detected

            # Would adding this paragraph exceed chunk_size?
            if current_chunk and (len(current_chunk) + len(para) + 2) > chunk_size:
                # Emit the current chunk
                chunks.append({
                    "page": page_num,
                    "text": current_chunk.strip(),
                    "section_title": current_title,
                    "chunk_index": global_index,
                    "char_count": len(current_chunk.strip()),
                })
                global_index += 1

                # Overlap: carry the tail of the current chunk forward
                if overlap > 0 and len(current_chunk) > overlap:
                    current_chunk = current_chunk[-overlap:] + "\n\n" + para
                else:
                    current_chunk = para
            else:
                if current_chunk:
                    current_chunk += "\n\n" + para
                else:
                    current_chunk = para

            # Handle very long single paragraphs (force-split)
            while len(current_chunk) > chunk_size:
                split_point = current_chunk.rfind(" ", 0, chunk_size)
                if split_point <= 0:
                    split_point = chunk_size  # Hard break if no space found

                chunks.append({
                    "page": page_num,
                    "text": current_chunk[:split_point].strip(),
                    "section_title": current_title,
                    "chunk_index": global_index,
                    "char_count": len(current_chunk[:split_point].strip()),
                })
                global_index += 1

                # Carry overlap forward
                if overlap > 0:
                    carry_start = max(0, split_point - overlap)
                    current_chunk = current_chunk[carry_start:]
                else:
                    current_chunk = current_chunk[split_point:]

        # Flush remaining text for this page
        if current_chunk.strip():
            chunks.append({
                "page": page_num,
                "text": current_chunk.strip(),
                "section_title": current_title,
                "chunk_index": global_index,
                "char_count": len(current_chunk.strip()),
            })
            global_index += 1

    return chunks
