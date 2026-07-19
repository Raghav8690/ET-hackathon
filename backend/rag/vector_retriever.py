"""
PS8 – Vector Similarity Retriever (Task 2.1.1)

Queries the Chroma index with a pre-computed query embedding and returns
the top-k most similar document chunks, optionally filtered by metadata.

Contract
--------
Function ``retrieve_vector_matches(query_vector, k, filters) -> List[Dict]``

Each returned dict contains:
    ``{"text": "...", "metadata": {"page": int, "doc_id": "...", ...}, "score": float}``

Dependencies: Task 1.4.1 (Chroma Vector Database Connection)
"""

import logging
from typing import Any, Dict, List, Optional

from backend.ingestion.vector_store import (
    COLLECTION_NAME,
    get_or_create_collection,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Filter builder
# ---------------------------------------------------------------------------
def _build_chroma_where(filters: Optional[Dict[str, Any]]) -> Optional[Dict]:
    """Convert user-facing filter dict into a Chroma ``where`` clause.

    Supported filter keys
    ---------------------
    - ``equipment_id``   : exact match (str)
    - ``doc_type``       : exact match or list of acceptable types
    - ``document_id``    : exact match (str)
    - ``severity``       : exact match (str)
    - ``compliance_relevant`` : boolean

    All conditions are combined with ``$and``.
    """
    if not filters:
        return None

    conditions: List[Dict] = []

    # Simple equality filters
    _SIMPLE_KEYS = (
        "equipment_id",
        "doc_type",
        "document_id",
        "severity",
        "equipment_name",
        "equipment_type",
        "serial_number",
        "manufacturer",
    )
    for key in _SIMPLE_KEYS:
        val = filters.get(key)
        if val is None:
            continue
        if isinstance(val, list):
            # Chroma supports $in operator for lists
            conditions.append({key: {"$in": val}})
        elif isinstance(val, str) and val.strip():
            conditions.append({key: {"$eq": val}})

    # Boolean filter
    if filters.get("compliance_relevant") is not None:
        conditions.append(
            {"compliance_relevant": {"$eq": bool(filters["compliance_relevant"])}}
        )

    if not conditions:
        return None
    if len(conditions) == 1:
        return conditions[0]
    return {"$and": conditions}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def retrieve_vector_matches(
    query_vector: List[float],
    k: int = 5,
    filters: Optional[Dict[str, Any]] = None,
    collection_name: str = COLLECTION_NAME,
) -> List[Dict[str, Any]]:
    """Query Chroma with a dense vector and return top-k matching chunks.

    Parameters
    ----------
    query_vector : List[float]
        The embedding of the user's query.
    k : int
        Number of top results to return (default 5).
    filters : Dict, optional
        Metadata filters to narrow results (e.g. ``{"equipment_id": "P-101"}``).
    collection_name : str
        Chroma collection to search (default ``document_chunks``).

    Returns
    -------
    List[Dict[str, Any]]
        Each entry:
        ``{"text": str, "metadata": Dict, "score": float, "chunk_id": str}``

        ``score`` is the Chroma *distance* — lower is more similar.
        Results are sorted from most similar (lowest distance) to least.

    Raises
    ------
    ValueError
        If ``query_vector`` is empty or ``k`` is non-positive.
    """
    if not query_vector:
        raise ValueError("query_vector must be a non-empty list of floats")
    if k <= 0:
        raise ValueError("k must be a positive integer")

    collection = get_or_create_collection(name=collection_name)

    # Clamp k to the collection size to avoid Chroma errors
    doc_count = collection.count()
    effective_k = min(k, doc_count) if doc_count > 0 else k

    if doc_count == 0:
        logger.warning("Collection '%s' is empty – returning no results", collection_name)
        return []

    where_clause = _build_chroma_where(filters)

    query_kwargs: Dict[str, Any] = {
        "query_embeddings": [query_vector],
        "n_results": effective_k,
        "include": ["documents", "metadatas", "distances"],
    }
    if where_clause is not None:
        query_kwargs["where"] = where_clause

    try:
        results = collection.query(**query_kwargs)
    except Exception as exc:
        logger.error("Chroma query failed: %s", exc)
        raise

    # Unpack Chroma's nested list structure
    ids_list = results.get("ids", [[]])[0]
    docs_list = results.get("documents", [[]])[0]
    metas_list = results.get("metadatas", [[]])[0]
    dists_list = results.get("distances", [[]])[0]

    output: List[Dict[str, Any]] = []
    for chunk_id, text, meta, dist in zip(ids_list, docs_list, metas_list, dists_list):
        output.append(
            {
                "chunk_id": chunk_id,
                "text": text or "",
                "metadata": meta or {},
                "score": dist,
            }
        )

    logger.info(
        "Vector retrieval: %d results from '%s' (k=%d, filters=%s)",
        len(output),
        collection_name,
        k,
        filters,
    )
    return output
