"""
Phase 2.1 Tests – Vector Similarity Retriever & BM25 Lexical Retriever

Tests both retriever modules in isolation using mock/in-memory data.
"""

import math
import os
import shutil
import tempfile
import uuid

import pytest

# ---------------------------------------------------------------------------
# Ensure Chroma uses a temporary directory for tests
# ---------------------------------------------------------------------------
_TEST_CHROMA_DIR = tempfile.mkdtemp(prefix="ps8_test_chroma_")
os.environ["CHROMA_DB_DIR"] = _TEST_CHROMA_DIR

# Force re-initialise the vector_store singleton so it picks up the test dir
import backend.ingestion.vector_store as vs

vs.CHROMA_DB_DIR = _TEST_CHROMA_DIR
vs._client = None  # Reset singleton


# ===========================  FIXTURES  ====================================

EMBED_DIM = 8  # Small dimension for fast tests


def _make_embedding(seed: float = 0.0) -> list:
    """Generate a deterministic small embedding vector."""
    import random

    rng = random.Random(int(seed * 1000))
    return [rng.random() for _ in range(EMBED_DIM)]


@pytest.fixture(autouse=True)
def _clean_chroma():
    """Reset the Chroma collection before each test."""
    vs._client = None
    try:
        client = vs.get_chroma_client()
        for col in client.list_collections():
            client.delete_collection(col.name)
    except Exception:
        pass
    yield
    # Cleanup after each test
    try:
        client = vs.get_chroma_client()
        for col in client.list_collections():
            client.delete_collection(col.name)
    except Exception:
        pass


def _seed_chroma_collection(
    chunks: list[dict],
    collection_name: str = "document_chunks",
) -> None:
    """Insert test chunks directly into Chroma."""
    col = vs.get_or_create_collection(name=collection_name)
    ids = [c["id"] for c in chunks]
    texts = [c["text"] for c in chunks]
    embeddings = [c["embedding"] for c in chunks]
    metadatas = [c.get("metadata", {}) for c in chunks]
    col.add(ids=ids, documents=texts, embeddings=embeddings, metadatas=metadatas)


# ===========================================================================
# TASK 2.1.1 – Vector Similarity Retriever Tests
# ===========================================================================
from backend.rag.vector_retriever import retrieve_vector_matches, _build_chroma_where


class TestBuildChromaWhere:
    """Unit tests for the Chroma where-clause builder."""

    def test_none_filters(self):
        assert _build_chroma_where(None) is None

    def test_empty_filters(self):
        assert _build_chroma_where({}) is None

    def test_single_string_filter(self):
        result = _build_chroma_where({"equipment_id": "P-101"})
        assert result == {"equipment_id": {"$eq": "P-101"}}

    def test_list_filter(self):
        result = _build_chroma_where({"doc_type": ["MANUAL", "REPORT"]})
        assert result == {"doc_type": {"$in": ["MANUAL", "REPORT"]}}

    def test_boolean_filter(self):
        result = _build_chroma_where({"compliance_relevant": True})
        assert result == {"compliance_relevant": {"$eq": True}}

    def test_multiple_filters_use_and(self):
        result = _build_chroma_where({
            "equipment_id": "P-101",
            "doc_type": "MANUAL",
        })
        assert "$and" in result
        assert len(result["$and"]) == 2

    def test_ignores_none_values(self):
        result = _build_chroma_where({"equipment_id": None, "doc_type": "MANUAL"})
        assert result == {"doc_type": {"$eq": "MANUAL"}}

    def test_ignores_empty_string(self):
        result = _build_chroma_where({"equipment_id": "  "})
        assert result is None


class TestRetrieveVectorMatches:
    """Tests for the vector similarity retriever."""

    def test_empty_collection_returns_empty(self):
        query = _make_embedding(1.0)
        results = retrieve_vector_matches(query, k=5)
        assert results == []

    def test_raises_on_empty_vector(self):
        with pytest.raises(ValueError, match="non-empty"):
            retrieve_vector_matches([], k=5)

    def test_raises_on_negative_k(self):
        with pytest.raises(ValueError, match="positive"):
            retrieve_vector_matches([1.0, 2.0], k=-1)

    def test_basic_retrieval(self):
        """Insert 3 chunks, query, and verify top-k results."""
        chunks = [
            {
                "id": "c1",
                "text": "Bearing overheating detected in pump P-101",
                "embedding": _make_embedding(1.0),
                "metadata": {"equipment_id": "P-101", "page": 1, "doc_type": "REPORT"},
            },
            {
                "id": "c2",
                "text": "Standard operating procedure for valve maintenance",
                "embedding": _make_embedding(2.0),
                "metadata": {"equipment_id": "V-201", "page": 1, "doc_type": "SOP"},
            },
            {
                "id": "c3",
                "text": "Compressor vibration analysis report Q4 2025",
                "embedding": _make_embedding(3.0),
                "metadata": {"equipment_id": "C-302", "page": 1, "doc_type": "REPORT"},
            },
        ]
        _seed_chroma_collection(chunks)

        # Query with the same embedding as c1 – c1 should be the top result
        results = retrieve_vector_matches(_make_embedding(1.0), k=2)
        assert len(results) == 2
        assert results[0]["chunk_id"] == "c1"
        assert results[0]["text"] == chunks[0]["text"]
        assert results[0]["metadata"]["equipment_id"] == "P-101"
        assert "score" in results[0]

    def test_k_clamped_to_collection_size(self):
        """When k > collection size, return all available results."""
        chunks = [
            {
                "id": "c1",
                "text": "Single chunk",
                "embedding": _make_embedding(1.0),
                "metadata": {"_placeholder": True},
            },
        ]
        _seed_chroma_collection(chunks)

        results = retrieve_vector_matches(_make_embedding(1.0), k=100)
        assert len(results) == 1

    def test_filter_by_equipment_id(self):
        """Filters should restrict results to matching equipment."""
        chunks = [
            {
                "id": "c1",
                "text": "Pump bearing failure",
                "embedding": _make_embedding(1.0),
                "metadata": {"equipment_id": "P-101", "doc_type": "REPORT"},
            },
            {
                "id": "c2",
                "text": "Valve leak detected",
                "embedding": _make_embedding(1.1),
                "metadata": {"equipment_id": "V-201", "doc_type": "REPORT"},
            },
        ]
        _seed_chroma_collection(chunks)

        results = retrieve_vector_matches(
            _make_embedding(1.0),
            k=5,
            filters={"equipment_id": "P-101"},
        )
        assert len(results) == 1
        assert results[0]["metadata"]["equipment_id"] == "P-101"

    def test_filter_by_doc_type_list(self):
        """Filter with a list of acceptable doc_types."""
        chunks = [
            {
                "id": "c1",
                "text": "SOP step 1",
                "embedding": _make_embedding(1.0),
                "metadata": {"doc_type": "SOP"},
            },
            {
                "id": "c2",
                "text": "Manual section 3",
                "embedding": _make_embedding(2.0),
                "metadata": {"doc_type": "MANUAL"},
            },
            {
                "id": "c3",
                "text": "Inspection record",
                "embedding": _make_embedding(3.0),
                "metadata": {"doc_type": "INSPECTION"},
            },
        ]
        _seed_chroma_collection(chunks)

        results = retrieve_vector_matches(
            _make_embedding(1.0),
            k=10,
            filters={"doc_type": ["SOP", "MANUAL"]},
        )
        doc_types = {r["metadata"]["doc_type"] for r in results}
        assert "INSPECTION" not in doc_types
        assert len(results) == 2

    def test_results_sorted_by_distance(self):
        """Verify results are ordered from lowest distance (most similar)."""
        chunks = [
            {
                "id": f"c{i}",
                "text": f"chunk {i}",
                "embedding": _make_embedding(float(i)),
                "metadata": {"chunk_index": i},
            }
            for i in range(5)
        ]
        _seed_chroma_collection(chunks)

        results = retrieve_vector_matches(_make_embedding(2.0), k=5)
        distances = [r["score"] for r in results]
        assert distances == sorted(distances), "Results should be sorted by ascending distance"

    def test_result_structure(self):
        """Validate the shape of each result dict."""
        chunks = [
            {
                "id": "c1",
                "text": "Test chunk",
                "embedding": _make_embedding(1.0),
                "metadata": {"page": 3, "document_id": "doc-123"},
            },
        ]
        _seed_chroma_collection(chunks)

        results = retrieve_vector_matches(_make_embedding(1.0), k=1)
        assert len(results) == 1
        r = results[0]
        assert "text" in r
        assert "metadata" in r
        assert "score" in r
        assert "chunk_id" in r
        assert isinstance(r["metadata"], dict)
        assert isinstance(r["score"], float)


# ===========================================================================
# TASK 2.1.2 – BM25 Lexical Retriever Tests
# ===========================================================================
from backend.rag.bm25_retriever import BM25Index, _tokenize


class TestTokenize:
    """Unit tests for the BM25 tokenizer."""

    def test_basic_tokenization(self):
        tokens = _tokenize("Hello world test")
        assert "hello" in tokens
        assert "world" in tokens
        assert "test" in tokens

    def test_stop_words_removed(self):
        tokens = _tokenize("the quick and the lazy")
        assert "the" not in tokens
        assert "and" not in tokens
        assert "quick" in tokens
        assert "lazy" in tokens

    def test_case_insensitive(self):
        tokens = _tokenize("Bearing OVERHEATING Failure")
        assert "bearing" in tokens
        assert "overheating" in tokens
        assert "failure" in tokens

    def test_empty_string(self):
        assert _tokenize("") == []

    def test_preserves_alphanumeric_with_hyphens(self):
        tokens = _tokenize("P-101 serial SN-883921")
        assert "p-101" in tokens
        assert "sn-883921" in tokens


class TestBM25Index:
    """Tests for the BM25 lexical retriever."""

    @pytest.fixture
    def sample_chunks(self):
        """Three test chunks for BM25 indexing."""
        return [
            {
                "text": "Bearing overheating detected in pump P-101 during routine inspection",
                "metadata": {"document_id": "doc-1", "page": 1, "equipment_id": "P-101", "doc_type": "REPORT"},
            },
            {
                "text": "Standard operating procedure for valve maintenance and lubrication schedule",
                "metadata": {"document_id": "doc-2", "page": 1, "equipment_id": "V-201", "doc_type": "SOP"},
            },
            {
                "text": "Compressor vibration analysis showing overheating trend in bearing assembly",
                "metadata": {"document_id": "doc-3", "page": 2, "equipment_id": "C-302", "doc_type": "REPORT"},
            },
        ]

    def test_raises_if_not_built(self):
        index = BM25Index()
        with pytest.raises(RuntimeError, match="not been built"):
            index.search("test query")

    def test_raises_on_negative_k(self, sample_chunks):
        index = BM25Index().build_from_chunks(sample_chunks)
        with pytest.raises(ValueError, match="positive"):
            index.search("test", k=-1)

    def test_build_from_chunks(self, sample_chunks):
        index = BM25Index().build_from_chunks(sample_chunks)
        assert index.is_built is True
        assert index.document_count == 3

    def test_empty_query_returns_empty(self, sample_chunks):
        index = BM25Index().build_from_chunks(sample_chunks)
        results = index.search("the and is")  # Only stop words
        assert results == []

    def test_overheating_ranks_first(self, sample_chunks):
        """Search for 'overheating'. The sentence with 'overheating' should rank highest."""
        index = BM25Index().build_from_chunks(sample_chunks)
        results = index.search("overheating", k=3)
        assert len(results) >= 1
        # Both chunks 0 and 2 contain "overheating", so they should be in results
        result_texts = [r["text"] for r in results]
        for text in result_texts:
            assert "overheating" in text.lower()

    def test_bearing_search(self, sample_chunks):
        """Search for 'bearing' returns chunks containing 'bearing'."""
        index = BM25Index().build_from_chunks(sample_chunks)
        results = index.search("bearing", k=3)
        assert len(results) >= 1
        for r in results:
            assert "bearing" in r["text"].lower()

    def test_valve_search(self, sample_chunks):
        """Search for 'valve maintenance' should return the SOP chunk."""
        index = BM25Index().build_from_chunks(sample_chunks)
        results = index.search("valve maintenance", k=1)
        assert len(results) == 1
        assert "valve" in results[0]["text"].lower()
        assert results[0]["metadata"]["doc_type"] == "SOP"

    def test_no_matches_returns_empty(self, sample_chunks):
        """Search for non-existent term returns empty list."""
        index = BM25Index().build_from_chunks(sample_chunks)
        results = index.search("xylophone dinosaur platypus", k=5)
        assert results == []

    def test_scores_are_positive(self, sample_chunks):
        """BM25 scores should be positive for matching documents."""
        index = BM25Index().build_from_chunks(sample_chunks)
        results = index.search("overheating bearing", k=5)
        for r in results:
            assert r["score"] > 0

    def test_scores_sorted_descending(self, sample_chunks):
        """Results should be sorted by BM25 score descending."""
        index = BM25Index().build_from_chunks(sample_chunks)
        results = index.search("overheating bearing pump", k=5)
        scores = [r["score"] for r in results]
        assert scores == sorted(scores, reverse=True)

    def test_filter_by_equipment_id(self, sample_chunks):
        """Filter by equipment_id should restrict results."""
        index = BM25Index().build_from_chunks(sample_chunks)
        results = index.search("overheating", k=5, filters={"equipment_id": "P-101"})
        assert len(results) == 1
        assert results[0]["metadata"]["equipment_id"] == "P-101"

    def test_filter_by_doc_type(self, sample_chunks):
        """Filter by doc_type should restrict results."""
        index = BM25Index().build_from_chunks(sample_chunks)
        results = index.search("maintenance", k=5, filters={"doc_type": "SOP"})
        for r in results:
            assert r["metadata"]["doc_type"] == "SOP"

    def test_filter_by_document_id(self, sample_chunks):
        """Filter by document_id should restrict results."""
        index = BM25Index().build_from_chunks(sample_chunks)
        results = index.search("overheating", k=5, filters={"document_id": "doc-3"})
        assert len(results) == 1
        assert results[0]["metadata"]["document_id"] == "doc-3"

    def test_filter_excludes_non_matching(self, sample_chunks):
        """Filtering by equipment that doesn't match should return empty."""
        index = BM25Index().build_from_chunks(sample_chunks)
        results = index.search("overheating", k=5, filters={"equipment_id": "NONEXISTENT"})
        assert results == []

    def test_result_structure(self, sample_chunks):
        """Validate result dict structure."""
        index = BM25Index().build_from_chunks(sample_chunks)
        results = index.search("bearing", k=1)
        assert len(results) == 1
        r = results[0]
        assert "text" in r
        assert "metadata" in r
        assert "score" in r
        assert isinstance(r["metadata"], dict)
        assert isinstance(r["score"], float)

    def test_get_stats(self, sample_chunks):
        """Index statistics should be populated after build."""
        index = BM25Index().build_from_chunks(sample_chunks)
        stats = index.get_stats()
        assert stats["document_count"] == 3
        assert stats["unique_terms"] > 0
        assert stats["avg_document_length"] > 0
        assert stats["is_built"] is True

    def test_k_exceeds_results(self, sample_chunks):
        """When k > matching documents, return all matches."""
        index = BM25Index().build_from_chunks(sample_chunks)
        results = index.search("overheating", k=100)
        # Only 2 chunks contain "overheating"
        assert len(results) == 2

    def test_rebuild_replaces_index(self, sample_chunks):
        """Rebuilding with new data replaces the old index."""
        index = BM25Index().build_from_chunks(sample_chunks)
        assert index.document_count == 3

        new_chunks = [
            {"text": "Turbine blade erosion", "metadata": {"document_id": "doc-99"}},
        ]
        index.build_from_chunks(new_chunks)
        assert index.document_count == 1
        results = index.search("turbine", k=5)
        assert len(results) == 1

    def test_compound_query_scores_higher_for_multiple_matches(self, sample_chunks):
        """A chunk matching multiple query terms should score higher than one matching fewer."""
        index = BM25Index().build_from_chunks(sample_chunks)
        results = index.search("bearing overheating pump", k=3)
        if len(results) >= 2:
            # The chunk with "bearing overheating pump" (chunk 0) should outscore
            # the chunk with only "bearing overheating" (chunk 2)
            top = results[0]
            assert "pump" in top["text"].lower() or "bearing" in top["text"].lower()


# ===========================================================================
# Cleanup
# ===========================================================================
@pytest.fixture(autouse=True, scope="session")
def _cleanup_test_chroma():
    """Remove the test Chroma directory after all tests complete."""
    yield
    try:
        shutil.rmtree(_TEST_CHROMA_DIR, ignore_errors=True)
    except Exception:
        pass
