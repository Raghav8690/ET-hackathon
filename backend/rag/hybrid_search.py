"""
PS8 – Hybrid Search & Fusion Engine (Phase 2.2)

Task 2.2.1 – Reciprocal Rank Fusion (RRF) Implementation
Task 2.2.2 – Metadata Filtering Interface / Hybrid Search Orchestrator

Merges results from the Vector Similarity Retriever (Task 2.1.1) and the
BM25 Lexical Retriever (Task 2.1.2) using Reciprocal Rank Fusion, then
exposes a unified ``search_hybrid`` function that handles query embedding,
dual retrieval, fusion, and metadata filtering in one call.

Contracts
---------
``fuse_results(vector_results, bm25_results, k_constant=60) -> List[Dict]``
``search_hybrid(query_str, k=10, filters=None, bm25_index=None, ...) -> List[Dict]``

Dependencies: Tasks 2.1.1, 2.1.2, 1.4.2 (embedding generation)
"""

import logging
from typing import Any, Dict, List, Optional

from backend.ingestion.embed import get_embeddings
from backend.rag.vector_retriever import retrieve_vector_matches

logger = logging.getLogger(__name__)


# ===========================================================================
# Task 2.2.1 – Reciprocal Rank Fusion
# ===========================================================================

def fuse_results(
    vector_results: List[Dict[str, Any]],
    bm25_results: List[Dict[str, Any]],
    k_constant: int = 60,
) -> List[Dict[str, Any]]:
    """Merge vector-search and BM25-search results using Reciprocal Rank Fusion.

    The RRF score for each document is computed as::

        RRF(d) = Σ  1 / (k + rank_i(d))

    where ``k`` is the constant (default 60) and ``rank_i(d)`` is the 1-based
    rank of document ``d`` in result list ``i``.  Documents appearing in both
    lists accumulate score from both.

    Parameters
    ----------
    vector_results : List[Dict]
        Results from the vector similarity retriever.  Each dict must
        contain at least ``"text"`` and ``"metadata"``.  An optional
        ``"chunk_id"`` key is used for deduplication; if absent, the
        ``"text"`` content is used as the identity key.
    bm25_results : List[Dict]
        Results from the BM25 lexical retriever (same dict structure).
    k_constant : int
        Smoothing constant for RRF (default 60).  Higher values give
        more weight to lower-ranked results.

    Returns
    -------
    List[Dict[str, Any]]
        Fused results sorted by descending RRF score.  Each dict contains:
        ``{"text", "metadata", "rrf_score", "sources"}``

        ``sources`` is a list of strings indicating provenance, e.g.
        ``["vector", "bm25"]`` for documents found in both lists.

    Raises
    ------
    ValueError
        If ``k_constant`` is non-positive.
    """
    if k_constant <= 0:
        raise ValueError("k_constant must be a positive integer")

    # Accumulator: identity_key -> merged record
    fused: Dict[str, Dict[str, Any]] = {}

    def _identity(result: Dict) -> str:
        """Choose a stable identity key for deduplication."""
        # Prefer chunk_id, then vector_id in metadata, then text hash
        if result.get("chunk_id"):
            return str(result["chunk_id"])
        meta = result.get("metadata", {})
        if meta.get("vector_id"):
            return str(meta["vector_id"])
        # Fallback: use the text content itself (truncated for speed)
        return result.get("text", "")[:200]

    # --- Score vector results ---
    for rank_0, res in enumerate(vector_results):
        key = _identity(res)
        rank = rank_0 + 1  # 1-based
        rrf_score = 1.0 / (k_constant + rank)

        if key in fused:
            fused[key]["rrf_score"] += rrf_score
            if "vector" not in fused[key]["sources"]:
                fused[key]["sources"].append("vector")
        else:
            fused[key] = {
                "text": res.get("text", ""),
                "metadata": res.get("metadata", {}),
                "rrf_score": rrf_score,
                "sources": ["vector"],
                # Preserve original scores for debugging
                "_vector_score": res.get("score"),
            }

    # --- Score BM25 results ---
    for rank_0, res in enumerate(bm25_results):
        key = _identity(res)
        rank = rank_0 + 1
        rrf_score = 1.0 / (k_constant + rank)

        if key in fused:
            fused[key]["rrf_score"] += rrf_score
            if "bm25" not in fused[key]["sources"]:
                fused[key]["sources"].append("bm25")
            # Keep BM25 score for debugging
            if fused[key].get("_bm25_score") is None:
                fused[key]["_bm25_score"] = res.get("score")
        else:
            fused[key] = {
                "text": res.get("text", ""),
                "metadata": res.get("metadata", {}),
                "rrf_score": rrf_score,
                "sources": ["bm25"],
                "_bm25_score": res.get("score"),
            }

    # Sort by RRF score descending
    sorted_results = sorted(fused.values(), key=lambda x: x["rrf_score"], reverse=True)

    logger.info(
        "RRF fusion: %d vector + %d bm25 -> %d unique results",
        len(vector_results),
        len(bm25_results),
        len(sorted_results),
    )
    return sorted_results


# ===========================================================================
# Task 2.2.2 – Hybrid Search Orchestrator with Metadata Filtering
# ===========================================================================

def search_hybrid(
    query_str: str,
    k: int = 10,
    filters: Optional[Dict[str, Any]] = None,
    bm25_index: Optional[Any] = None,
    vector_k: int = 20,
    bm25_k: int = 20,
    k_constant: int = 60,
    vector_weight: float = 1.0,
    bm25_weight: float = 1.0,
) -> List[Dict[str, Any]]:
    """Execute a hybrid search combining vector similarity and BM25 lexical retrieval.

    This is the main entry point for Phase 2 search.  It:

    1. Embeds the query string into a dense vector.
    2. Runs the **Vector Similarity Retriever** (Task 2.1.1) with filters.
    3. Runs the **BM25 Lexical Retriever** (Task 2.1.2) with the same filters.
    4. Fuses results using **Reciprocal Rank Fusion** (Task 2.2.1).
    5. Returns the top-k fused results.

    Parameters
    ----------
    query_str : str
        Natural language query.
    k : int
        Final number of results to return after fusion (default 10).
    filters : Dict, optional
        Metadata filters applied to both retrievers.  Supported keys:
        ``equipment_id``, ``doc_type``, ``document_id``, ``severity``,
        ``compliance_relevant``, ``date_range_start``, ``date_range_end``.
    bm25_index : BM25Index, optional
        Pre-built BM25 index.  If ``None``, a new index is built from the
        database (requires an active DB session via ``get_db``).
    vector_k : int
        Number of candidates to retrieve from the vector store (default 20).
    bm25_k : int
        Number of candidates to retrieve from BM25 (default 20).
    k_constant : int
        RRF smoothing constant (default 60).
    vector_weight : float
        Not yet implemented — reserved for weighted RRF variants.
    bm25_weight : float
        Not yet implemented — reserved for weighted RRF variants.

    Returns
    -------
    List[Dict[str, Any]]
        Top-k fused results.  Each dict:
        ``{"text", "metadata", "rrf_score", "sources"}``

    Raises
    ------
    ValueError
        If ``query_str`` is empty.
    RuntimeError
        If embedding generation fails.
    """
    if not query_str or not query_str.strip():
        raise ValueError("query_str must be a non-empty string")

    # --- 1. Embed the query ---
    query_vectors = get_embeddings([query_str])
    if not query_vectors or not query_vectors[0]:
        raise RuntimeError("Failed to generate query embedding")
    query_vector = query_vectors[0]

    # --- 2. Vector retrieval ---
    try:
        vector_results = retrieve_vector_matches(
            query_vector=query_vector,
            k=vector_k,
            filters=filters,
        )
    except Exception as exc:
        logger.warning("Vector retrieval failed: %s — continuing with BM25 only", exc)
        vector_results = []

    # --- 3. BM25 retrieval ---
    bm25_results = []
    if bm25_index is not None:
        try:
            bm25_results = bm25_index.search(
                query_str=query_str,
                k=bm25_k,
                filters=filters,
            )
        except Exception as exc:
            logger.warning("BM25 retrieval failed: %s — continuing with vector only", exc)
    else:
        # Auto-build from database
        try:
            bm25_results = _bm25_search_from_db(query_str, bm25_k, filters)
        except Exception as exc:
            logger.warning("BM25 DB retrieval failed: %s — continuing with vector only", exc)

    # --- 4. Fuse results ---
    if not vector_results and not bm25_results:
        logger.info("Hybrid search: no results from either retriever")
        return []

    fused = fuse_results(
        vector_results=vector_results,
        bm25_results=bm25_results,
        k_constant=k_constant,
    )

    # --- 4.5. Apply Ranking Optimizations (Phase 2.3) ---
    from backend.rag.ranking import rerank_results
    fused = rerank_results(fused)

    # --- 5. Return top-k ---
    top_k = fused[:k]

    logger.info(
        "Hybrid search: query=%r, %d vector + %d bm25 -> %d fused -> %d returned",
        query_str[:50],
        len(vector_results),
        len(bm25_results),
        len(fused),
        len(top_k),
    )
    return top_k


def _bm25_search_from_db(
    query_str: str,
    k: int,
    filters: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Build a BM25 index from the database and search it.

    This is a convenience path for when no pre-built index is provided.
    For production use, the BM25 index should be built once and reused.
    """
    from backend.db.session import get_db
    from backend.rag.bm25_retriever import BM25Index

    db = next(get_db())
    try:
        index = BM25Index().build(db)
        return index.search(query_str=query_str, k=k, filters=filters)
    finally:
        db.close()
