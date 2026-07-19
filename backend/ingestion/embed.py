"""
PS8 – Embedding Generation Wrapper (Task 1.4.2)

Supports (in priority order):
1. **OpenAI** ``text-embedding-3-small`` (1536 dims) – used when a *real* OPENAI_API_KEY is set.
2. **Ollama** local embeddings – used when OLLAMA_MODEL is set. Fast, no auth needed.
3. **Local HuggingFace** ``sentence-transformers/all-MiniLM-L6-v2`` (384 dims) – last resort.

Contract
--------
Function ``get_embeddings(texts: List[str]) -> List[List[float]]``
"""

import logging
import os
from typing import List, Optional

import httpx

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
OPENAI_MODEL = "text-embedding-3-small"
LOCAL_MODEL = "all-MiniLM-L6-v2"

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL: Optional[str] = os.getenv("OLLAMA_MODEL")
# Keep the chat/metadata model separate from the embedding model. Models such
# as gpt-oss support completion but do not expose the embedding capability.
OLLAMA_EMBEDDING_MODEL: Optional[str] = os.getenv("OLLAMA_EMBEDDING_MODEL")

_local_model = None
_embedding_source: Optional[str] = None  # Track which backend is active


def _openai_available() -> bool:
    """Check whether a *real* OpenAI API key is configured.

    Placeholder values like ``your_openai_api_key_here`` are treated as missing.
    """
    key = os.getenv("OPENAI_API_KEY", "").strip()
    if not key:
        return False
    # Reject obvious placeholder values
    placeholders = {"your_openai_api_key_here", "sk-xxx", "your-key-here", ""}
    if key.lower() in placeholders:
        return False
    # Real OpenAI keys start with "sk-"
    if not key.startswith("sk-"):
        return False
    return True


def _ollama_available() -> bool:
    """Check whether Ollama is configured for embeddings."""
    return bool(OLLAMA_EMBEDDING_MODEL and OLLAMA_EMBEDDING_MODEL.strip())


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

    Priority: OpenAI → Ollama → Local HuggingFace.

    Parameters
    ----------
    texts : List[str]
        The texts to embed.

    Returns
    -------
    List[List[float]]
        One embedding vector per input text.

    Raises
    ------
    RuntimeError
        If all embedding backends fail.
    """
    global _embedding_source

    if not texts:
        return []

    # --- Attempt 1: OpenAI ---
    if _openai_available():
        try:
            return _embed_openai(texts)
        except Exception as exc:
            logger.warning("OpenAI embedding failed: %s – trying Ollama", exc)

    # --- Attempt 2: Ollama (local, fast, no auth) ---
    if _ollama_available():
        try:
            return _embed_ollama(texts)
        except Exception as exc:
            logger.warning("Ollama embedding failed: %s – trying local HF model", exc)

    # --- Attempt 3: Local sentence-transformers ---
    try:
        return _embed_local(texts)
    except Exception as exc:
        raise RuntimeError(
            f"All embedding backends failed. Last error: {exc}"
        ) from exc


def get_embedding_dimension() -> int:
    """Return the dimension of the active embedding model.

    Returns 1536 for OpenAI, variable for Ollama, 384 for MiniLM-L6-v2.
    """
    if _openai_available():
        return 1536
    if _ollama_available():
        # Ollama embedding dimensions vary by model, detect at runtime
        try:
            test = _embed_ollama(["test"])
            return len(test[0])
        except Exception:
            pass
    return 384


def get_embedding_source() -> str:
    """Return which embedding backend is active."""
    if _openai_available():
        return f"openai:{OPENAI_MODEL}"
    if _ollama_available():
        return f"ollama:{OLLAMA_EMBEDDING_MODEL}"
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


def _embed_ollama(texts: List[str]) -> List[List[float]]:
    """Generate embeddings via local Ollama API.

    Uses Ollama's current batch ``/api/embed`` endpoint. The legacy
    ``/api/embeddings`` endpoint was removed by newer Ollama versions.
    """
    global _embedding_source

    url_batch = f"{OLLAMA_BASE_URL}/api/embed"

    try:
        with httpx.Client(timeout=120.0) as client:
            response = client.post(
                url_batch,
                json={"model": OLLAMA_EMBEDDING_MODEL, "input": texts},
            )
            response.raise_for_status()
            data = response.json()
            embeddings = data.get("embeddings", [])
            if not embeddings or len(embeddings) != len(texts):
                raise RuntimeError("Ollama returned an incomplete embedding response")

    except httpx.ConnectError:
        raise RuntimeError(f"Cannot connect to Ollama at {OLLAMA_BASE_URL}. Is Ollama running?")
    except Exception as exc:
        raise RuntimeError(f"Ollama embedding failed: {exc}") from exc

    _embedding_source = f"ollama:{OLLAMA_EMBEDDING_MODEL}"
    logger.info(
        "Ollama generated %d embeddings (dim=%d) using %s",
        len(embeddings), len(embeddings[0]), OLLAMA_EMBEDDING_MODEL,
    )
    return embeddings


def _embed_local(texts: List[str]) -> List[List[float]]:
    """Generate embeddings via local sentence-transformers model."""
    global _embedding_source
    model = _get_local_model()

    embeddings = model.encode(texts, show_progress_bar=False, convert_to_numpy=True)
    result = [emb.tolist() for emb in embeddings]

    _embedding_source = f"local:{LOCAL_MODEL}"
    logger.info("Local model generated %d embeddings (dim=%d)", len(result), len(result[0]))
    return result
