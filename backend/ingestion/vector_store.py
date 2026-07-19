"""
PS8 – Chroma Vector Database Connection (Task 1.4.1)

Instantiates and configures a local Chroma PersistentClient.

Contract
--------
Module initialisation checking if database folder is ready.
Provides ``get_chroma_client()``, ``get_or_create_collection()``, and
``heartbeat()`` functions.
"""

import logging
import os
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
_project_root = Path(__file__).resolve().parents[2]
_default_chroma_dir = _project_root / "data" / "chroma"

CHROMA_DB_DIR = os.getenv("CHROMA_DB_DIR", str(_default_chroma_dir))

# ---------------------------------------------------------------------------
# Singleton client
# ---------------------------------------------------------------------------
_client: Optional[chromadb.ClientAPI] = None

# Collection name for document chunks
COLLECTION_NAME = "document_chunks"


def get_chroma_client() -> chromadb.ClientAPI:
    """Return a singleton Chroma PersistentClient.

    Creates the storage directory if it doesn't exist.
    """
    global _client
    if _client is None:
        db_path = Path(CHROMA_DB_DIR)
        db_path.mkdir(parents=True, exist_ok=True)

        _client = chromadb.PersistentClient(
            path=str(db_path),
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True,
            ),
        )
        logger.info("Chroma PersistentClient initialised at %s", db_path)
    return _client


def get_or_create_collection(
    name: str = COLLECTION_NAME,
    embedding_function=None,
) -> chromadb.Collection:
    """Get or create a Chroma collection.

    Parameters
    ----------
    name : str
        Collection name (default ``document_chunks``).
    embedding_function : optional
        Custom embedding function.  If ``None``, Chroma uses its default.

    Returns
    -------
    chromadb.Collection
    """
    client = get_chroma_client()
    kwargs = {"name": name}
    if embedding_function is not None:
        kwargs["embedding_function"] = embedding_function
    collection = client.get_or_create_collection(**kwargs)
    logger.info("Collection '%s' ready – %d documents", name, collection.count())
    return collection


def heartbeat() -> int:
    """Check that the Chroma client is responsive.

    Returns
    -------
    int
        Heartbeat timestamp (nanoseconds since epoch) from Chroma.
    """
    client = get_chroma_client()
    hb = client.heartbeat()
    logger.info("Chroma heartbeat: %s", hb)
    return hb


def collection_count(name: str = COLLECTION_NAME) -> int:
    """Return the number of records in a collection (0 if it doesn't exist)."""
    try:
        client = get_chroma_client()
        coll = client.get_collection(name)
        return coll.count()
    except Exception:
        return 0


def reset_collection(name: str = COLLECTION_NAME) -> chromadb.Collection:
    """Delete and recreate a collection. Returns the fresh collection."""
    client = get_chroma_client()
    try:
        client.delete_collection(name)
        logger.info("Deleted collection '%s'", name)
    except Exception as exc:
        logger.warning("Could not delete collection '%s' (may not exist): %s", name, exc)
    coll = client.get_or_create_collection(name=name)
    logger.info("Recreated collection '%s'", name)
    return coll
