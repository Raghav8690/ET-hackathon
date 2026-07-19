"""
PS8 – BM25 Lexical Retriever (Task 2.1.2)

Instantiates a BM25 index over all document chunks stored in the SQL database
(via ``DocumentChunk``) to fetch exact keyword matches.

Contract
--------
Class ``BM25Index`` supporting:
    ``.build(db: Session)``  — load chunks from DB and build the index.
    ``.build_from_chunks(chunks: List[Dict])``  — build from pre-loaded data.
    ``.search(query_str: str, k: int, filters: Dict) -> List[Dict]``

Each result dict:
    ``{"text": "...", "metadata": {"page": int, "doc_id": "...", ...}, "score": float}``

Dependencies: Task 1.3.4 (chunks exist in DB)
"""

import logging
import math
import re
from collections import Counter
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Text preprocessing
# ---------------------------------------------------------------------------
_STOP_WORDS = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to", "for",
    "of", "with", "by", "from", "is", "it", "as", "was", "are", "were",
    "be", "been", "being", "have", "has", "had", "do", "does", "did",
    "will", "would", "shall", "should", "may", "might", "can", "could",
    "not", "no", "this", "that", "these", "those", "i", "we", "you",
    "he", "she", "they", "me", "him", "her", "us", "them", "my", "your",
    "his", "its", "our", "their", "what", "which", "who", "whom",
    "so", "if", "then", "than", "too", "very", "just", "about",
})

_TOKEN_RE = re.compile(r"[a-zA-Z0-9][\w\-]*")


def _tokenize(text: str) -> List[str]:
    """Lowercase tokenize, removing stop words."""
    tokens = _TOKEN_RE.findall(text.lower())
    return [t for t in tokens if t not in _STOP_WORDS]


# ---------------------------------------------------------------------------
# BM25 Implementation (Okapi BM25)
# ---------------------------------------------------------------------------
class BM25Index:
    """In-memory BM25 lexical index over document chunks.

    Parameters
    ----------
    k1 : float
        Term frequency saturation parameter (default 1.5).
    b : float
        Length normalisation parameter (default 0.75).
    """

    def __init__(self, k1: float = 1.5, b: float = 0.75):
        self.k1 = k1
        self.b = b

        # Internal storage
        self._corpus_tokens: List[List[str]] = []
        self._chunks: List[Dict[str, Any]] = []  # Original chunk data
        self._doc_count = 0
        self._avg_dl = 0.0
        self._doc_freqs: Counter = Counter()  # term -> number of docs containing term
        self._built = False

    # ------------------------------------------------------------------
    # Building the index
    # ------------------------------------------------------------------
    def build(self, db) -> "BM25Index":
        """Build the index from all document chunks in the database.

        Parameters
        ----------
        db : sqlalchemy.orm.Session
            Active database session.

        Returns
        -------
        self
        """
        from backend.db.models import DocumentChunk, Document

        rows = (
            db.query(DocumentChunk, Document)
            .join(Document, DocumentChunk.document_id == Document.id)
            .filter(Document.status == "INGESTED")
            .all()
        )

        chunks = []
        for chunk_row, doc_row in rows:
            meta = {
                "document_id": chunk_row.document_id,
                "page": chunk_row.page_number or 1,
                "section_title": chunk_row.section_title or "General",
                "chunk_index": chunk_row.chunk_index,
                "vector_id": chunk_row.vector_id,
                "filename": doc_row.filename,
                "doc_type": doc_row.doc_type,
            }
            # Extract equipment_id from document if available
            if doc_row.equipment_id:
                meta["equipment_id"] = doc_row.equipment_id
            # Extract equipment_id tag from metadata_json if available
            if doc_row.metadata_json:
                import json
                try:
                    parsed = json.loads(doc_row.metadata_json)
                    if parsed.get("equipment_id"):
                        meta["equipment_id_tag"] = parsed["equipment_id"]
                except (json.JSONDecodeError, TypeError):
                    pass

            chunks.append({
                "text": chunk_row.text,
                "metadata": meta,
            })

        return self.build_from_chunks(chunks)

    def build_from_chunks(self, chunks: List[Dict[str, Any]]) -> "BM25Index":
        """Build the BM25 index from pre-loaded chunk dicts.

        Parameters
        ----------
        chunks : List[Dict]
            Each dict must have ``"text"`` (str) and ``"metadata"`` (Dict).

        Returns
        -------
        self
        """
        self._chunks = chunks
        self._corpus_tokens = []
        self._doc_freqs = Counter()

        total_len = 0
        for chunk in chunks:
            tokens = _tokenize(chunk.get("text", ""))
            self._corpus_tokens.append(tokens)
            total_len += len(tokens)

            # Document frequency: count each term once per document
            unique_terms = set(tokens)
            for term in unique_terms:
                self._doc_freqs[term] += 1

        self._doc_count = len(chunks)
        self._avg_dl = total_len / self._doc_count if self._doc_count > 0 else 0.0
        self._built = True

        logger.info(
            "BM25 index built: %d chunks, %d unique terms, avg_dl=%.1f",
            self._doc_count,
            len(self._doc_freqs),
            self._avg_dl,
        )
        return self

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------
    def _idf(self, term: str) -> float:
        """Inverse document frequency with smoothing."""
        df = self._doc_freqs.get(term, 0)
        # Standard BM25 IDF formula
        return math.log(
            (self._doc_count - df + 0.5) / (df + 0.5) + 1.0
        )

    def _score_document(self, query_tokens: List[str], doc_idx: int) -> float:
        """Compute BM25 score for a single document given query tokens."""
        doc_tokens = self._corpus_tokens[doc_idx]
        dl = len(doc_tokens)
        tf_counter = Counter(doc_tokens)

        score = 0.0
        for qt in query_tokens:
            tf = tf_counter.get(qt, 0)
            if tf == 0:
                continue
            idf = self._idf(qt)
            # Okapi BM25 TF component
            numerator = tf * (self.k1 + 1)
            denominator = tf + self.k1 * (1 - self.b + self.b * (dl / self._avg_dl))
            score += idf * (numerator / denominator)

        return score

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------
    def search(
        self,
        query_str: str,
        k: int = 5,
        filters: Optional[Dict[str, Any]] = None,
    ) -> List[Dict[str, Any]]:
        """Search the BM25 index for the query string.

        Parameters
        ----------
        query_str : str
            Natural language query.
        k : int
            Number of top results to return.
        filters : Dict, optional
            Metadata filters. Supported keys:
            - ``equipment_id`` : exact match
            - ``doc_type`` : exact match or list
            - ``document_id`` : exact match

        Returns
        -------
        List[Dict[str, Any]]
            Each entry:
            ``{"text": str, "metadata": Dict, "score": float}``
            Results sorted by BM25 score descending (highest = best match).

        Raises
        ------
        RuntimeError
            If the index has not been built yet.
        ValueError
            If ``k`` is non-positive.
        """
        if not self._built:
            raise RuntimeError("BM25 index has not been built. Call build() or build_from_chunks() first.")
        if k <= 0:
            raise ValueError("k must be a positive integer")

        query_tokens = _tokenize(query_str)
        if not query_tokens:
            return []

        # Score all documents
        scored: List[tuple] = []
        for idx in range(self._doc_count):
            # Apply metadata filters before scoring (skip filtered docs)
            if filters and not self._matches_filters(idx, filters):
                continue
            score = self._score_document(query_tokens, idx)
            if score > 0:
                scored.append((idx, score))

        # Sort by score descending
        scored.sort(key=lambda x: x[1], reverse=True)

        # Take top-k
        results: List[Dict[str, Any]] = []
        for idx, score in scored[:k]:
            chunk = self._chunks[idx]
            results.append({
                "text": chunk.get("text", ""),
                "metadata": chunk.get("metadata", {}),
                "score": score,
            })

        logger.info(
            "BM25 search: query=%r, %d results (k=%d, filters=%s)",
            query_str[:50],
            len(results),
            k,
            filters,
        )
        return results

    # ------------------------------------------------------------------
    # Filter helpers
    # ------------------------------------------------------------------
    def _matches_filters(self, doc_idx: int, filters: Dict[str, Any]) -> bool:
        """Check if a chunk's metadata matches all specified filters."""
        meta = self._chunks[doc_idx].get("metadata", {})

        for key, expected in filters.items():
            actual = meta.get(key)
            if actual is None:
                # Also check the equipment_id_tag field for equipment_id filters
                if key == "equipment_id":
                    actual = meta.get("equipment_id_tag")
                if actual is None:
                    return False

            if isinstance(expected, list):
                if actual not in expected:
                    return False
            elif actual != expected:
                return False

        return True

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    @property
    def is_built(self) -> bool:
        """Whether the index has been built."""
        return self._built

    @property
    def document_count(self) -> int:
        """Number of chunks in the index."""
        return self._doc_count

    def get_stats(self) -> Dict[str, Any]:
        """Return index statistics."""
        return {
            "document_count": self._doc_count,
            "unique_terms": len(self._doc_freqs),
            "avg_document_length": round(self._avg_dl, 1),
            "k1": self.k1,
            "b": self.b,
            "is_built": self._built,
        }
