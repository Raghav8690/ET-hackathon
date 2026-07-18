"""
PS8 – Embedding Generation Wrapper (Task 1.4.2)

Supports:
1. **OpenAI** ``text-embedding-3-small`` (1536 dims) – used when OPENAI_API_KEY is set.
2. **Local HuggingFace** ``sentence-transformers/all-MiniLM-L6-v2`` (384 dims) – free fallback.

Contract
--------
Function ``get_embeddings(texts: List[str]) -> List[List[float]]``
"""

import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OPENAI_MODEL = "text-embedding-3-small"
LOCAL_MODEL = "all-MiniLM-L6-v2"

_local_model = None
_embedding_source: Optional[str] = None  # Track which backend is active


def _openai_available() -> bool:
    """Check whether an OpenAI API key is configured."""
    return bool(os.getenv("OPENAI_API_KEY", "").strip())


def _get_local_model():
    """Lazily load the sentence-transformers model."""
    global _local_model
    if _local_model is None:
        from sentence_transformers import SentenceTransformer

        _local_model = SentenceTransformer(LOCAL_MODEL)
        logger.info("Loaded local embedding model: %s", LOCAL_MODEL)
    return _local_model


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_embeddings(texts: List[str]) -> List[List[float]]:
    """Generate embeddings for a list of text strings.

    Tries OpenAI first (if API key is set), then falls back to a local
    sentence-transformers model.

    Parameters
    ----------
    texts : List[str]
        The texts to embed.  Each should be ≤8191 tokens for OpenAI.

    Returns
    -------
    List[List[float]]
        One embedding vector per input text.

    Raises
    ------
    RuntimeError
        If both OpenAI and local model fail.
    """
    global _embedding_source

    if not texts:
        return []

    # --- Attempt 1: OpenAI ---
    if _openai_available():
        try:
            return _embed_openai(texts)
        except Exception as exc:
            logger.warning("OpenAI embedding failed: %s – falling back to local model", exc)

    # --- Attempt 2: Local sentence-transformers ---
    try:
        return _embed_local(texts)
    except Exception as exc:
        raise RuntimeError(
            f"All embedding backends failed. Last error: {exc}"
        ) from exc


def get_embedding_dimension() -> int:
    """Return the dimension of the active embedding model.

    Returns 1536 for OpenAI text-embedding-3-small, 384 for MiniLM-L6-v2.
    """
    if _openai_available():
        return 1536
    return 384


def get_embedding_source() -> str:
    """Return which embedding backend is active."""
    if _openai_available():
        return f"openai:{OPENAI_MODEL}"
    return f"local:{LOCAL_MODEL}"


# ---------------------------------------------------------------------------
# Backend implementations
# ---------------------------------------------------------------------------

def _embed_openai(texts: List[str]) -> List[List[float]]:
    """Generate embeddings via OpenAI API."""
    global _embedding_source
    from openai import OpenAI

    client = OpenAI()  # Uses OPENAI_API_KEY env var

    # OpenAI batch limit: 2048 inputs at once
    batch_size = 2048
    all_embeddings: List[List[float]] = []

    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = client.embeddings.create(
            model=OPENAI_MODEL,
            input=batch,
        )
        batch_embeddings = [item.embedding for item in response.data]
        all_embeddings.extend(batch_embeddings)

    _embedding_source = f"openai:{OPENAI_MODEL}"
    logger.info("OpenAI generated %d embeddings (dim=%d)", len(all_embeddings), len(all_embeddings[0]))
    return all_embeddings


def _embed_local(texts: List[str]) -> List[List[float]]:
    """Generate embeddings via local sentence-transformers model."""
    global _embedding_source
    model = _get_local_model()

    embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    result = [emb.tolist() for emb in embeddings]

    _embedding_source = f"local:{LOCAL_MODEL}"
    logger.info("Local model generated %d embeddings (dim=%d)", len(result), len(result[0]))
    return result
