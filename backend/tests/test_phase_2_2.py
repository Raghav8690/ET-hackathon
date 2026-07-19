"""
Phase 2.2 Tests – Hybrid Search & Fusion Engine

Task 2.2.1: Reciprocal Rank Fusion (RRF) tests
Task 2.2.2: Hybrid Search Orchestrator with metadata filtering tests

Tests RRF in isolation with mock data, and the hybrid search orchestrator
with mocked embedding + retriever backends.
"""

import os
import shutil
import tempfile
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Ensure Chroma uses a temporary directory for tests
# ---------------------------------------------------------------------------
_TEST_CHROMA_DIR = tempfile.mkdtemp(prefix="ps8_test_chroma_2_2_")
os.environ["CHROMA_DB_DIR"] = _TEST_CHROMA_DIR

import backend.ingestion.vector_store as vs

vs.CHROMA_DB_DIR = _TEST_CHROMA_DIR
vs._client = None


# ===========================================================================
# TASK 2.2.1 – Reciprocal Rank Fusion Tests
# ===========================================================================
from backend.rag.hybrid_search import fuse_results


class TestFuseResults:
    """Unit tests for Reciprocal Rank Fusion."""

    # ---------------------------------------------------------------
    # Basic functionality
    # ---------------------------------------------------------------
    def test_empty_both_lists(self):
        """Both empty lists should produce empty output."""
        result = fuse_results([], [])
        assert result == []

    def test_empty_vector_results(self):
        """Only BM25 results should still fuse correctly."""
        bm25 = [
            {"text": "chunk A", "metadata": {"doc_id": "1"}, "score": 3.5, "chunk_id": "a"},
            {"text": "chunk B", "metadata": {"doc_id": "2"}, "score": 2.0, "chunk_id": "b"},
        ]
        result = fuse_results([], bm25, k_constant=60)
        assert len(result) == 2
        # Should be ordered by RRF score descending (rank 1 > rank 2)
        assert result[0]["rrf_score"] > result[1]["rrf_score"]
        assert result[0]["sources"] == ["bm25"]

    def test_empty_bm25_results(self):
        """Only vector results should still fuse correctly."""
        vector = [
            {"text": "chunk A", "metadata": {}, "score": 0.1, "chunk_id": "a"},
        ]
        result = fuse_results(vector, [], k_constant=60)
        assert len(result) == 1
        assert result[0]["sources"] == ["vector"]

    # ---------------------------------------------------------------
    # RRF score computation
    # ---------------------------------------------------------------
    def test_rrf_score_single_source(self):
        """RRF score for rank-1 item with k=60 should be 1/(60+1)."""
        vector = [
            {"text": "chunk A", "metadata": {}, "score": 0.1, "chunk_id": "a"},
        ]
        result = fuse_results(vector, [], k_constant=60)
        expected_score = 1.0 / (60 + 1)
        assert abs(result[0]["rrf_score"] - expected_score) < 1e-9

    def test_rrf_score_both_sources_rank_1(self):
        """Document appearing at rank 1 in both lists gets 2/(k+1)."""
        vector = [{"text": "same", "metadata": {}, "score": 0.1, "chunk_id": "x"}]
        bm25 = [{"text": "same", "metadata": {}, "score": 5.0, "chunk_id": "x"}]

        result = fuse_results(vector, bm25, k_constant=60)
        assert len(result) == 1
        expected = 2.0 / (60 + 1)
        assert abs(result[0]["rrf_score"] - expected) < 1e-9
        assert sorted(result[0]["sources"]) == ["bm25", "vector"]

    def test_rrf_score_different_ranks(self):
        """Document at rank 1 in vector and rank 3 in BM25."""
        vector = [
            {"text": "A", "metadata": {}, "chunk_id": "a"},
        ]
        bm25 = [
            {"text": "X", "metadata": {}, "chunk_id": "x"},
            {"text": "Y", "metadata": {}, "chunk_id": "y"},
            {"text": "A", "metadata": {}, "chunk_id": "a"},
        ]
        result = fuse_results(vector, bm25, k_constant=60)

        # Find the fused entry for "a"
        # Actually let's find by checking all entries
        fused_a = None
        for r in result:
            # Check text content
            if r["text"] == "A":
                fused_a = r
                break
        assert fused_a is not None
        # 1/(60+1) from vector + 1/(60+3) from bm25
        expected = 1.0 / 61 + 1.0 / 63
        assert abs(fused_a["rrf_score"] - expected) < 1e-9

    # ---------------------------------------------------------------
    # Deduplication
    # ---------------------------------------------------------------
    def test_deduplication_by_chunk_id(self):
        """Same chunk_id in both lists should be merged into one entry."""
        vector = [
            {"text": "Bearing failure", "metadata": {"page": 1}, "score": 0.2, "chunk_id": "c1"},
            {"text": "Valve leak", "metadata": {"page": 2}, "score": 0.5, "chunk_id": "c2"},
        ]
        bm25 = [
            {"text": "Bearing failure", "metadata": {"page": 1}, "score": 4.0, "chunk_id": "c1"},
            {"text": "Compressor noise", "metadata": {"page": 3}, "score": 2.0, "chunk_id": "c3"},
        ]
        result = fuse_results(vector, bm25)
        # c1 merged, c2 vector only, c3 bm25 only -> 3 unique
        assert len(result) == 3

        # Find merged entry
        merged = next(r for r in result if r["text"] == "Bearing failure")
        assert sorted(merged["sources"]) == ["bm25", "vector"]

    def test_deduplication_by_vector_id_in_metadata(self):
        """If chunk_id is missing, fall back to metadata.vector_id for dedup."""
        vector = [
            {"text": "chunk A", "metadata": {"vector_id": "v1"}, "score": 0.1},
        ]
        bm25 = [
            {"text": "chunk A", "metadata": {"vector_id": "v1"}, "score": 3.0},
        ]
        result = fuse_results(vector, bm25)
        assert len(result) == 1
        assert sorted(result[0]["sources"]) == ["bm25", "vector"]

    def test_deduplication_by_text_fallback(self):
        """If no chunk_id or vector_id, deduplicate by text content."""
        vector = [
            {"text": "Same text content", "metadata": {}, "score": 0.1},
        ]
        bm25 = [
            {"text": "Same text content", "metadata": {}, "score": 3.0},
        ]
        result = fuse_results(vector, bm25)
        assert len(result) == 1

    # ---------------------------------------------------------------
    # Ordering / ranking
    # ---------------------------------------------------------------
    def test_common_element_ranks_higher(self):
        """A document appearing in both lists should outrank one in only one list."""
        vector = [
            {"text": "common", "metadata": {}, "chunk_id": "common"},
            {"text": "vector_only", "metadata": {}, "chunk_id": "vo"},
        ]
        bm25 = [
            {"text": "common", "metadata": {}, "chunk_id": "common"},
            {"text": "bm25_only", "metadata": {}, "chunk_id": "bo"},
        ]
        result = fuse_results(vector, bm25, k_constant=60)
        assert result[0]["text"] == "common"
        assert len(result[0]["sources"]) == 2

    def test_ordering_with_differing_ranks(self):
        """Documents with overlapping ranks should be properly ordered."""
        vector = [
            {"text": "A", "chunk_id": "a", "metadata": {}},
            {"text": "B", "chunk_id": "b", "metadata": {}},
            {"text": "C", "chunk_id": "c", "metadata": {}},
        ]
        bm25 = [
            {"text": "C", "chunk_id": "c", "metadata": {}},
            {"text": "A", "chunk_id": "a", "metadata": {}},
            {"text": "D", "chunk_id": "d", "metadata": {}},
        ]
        result = fuse_results(vector, bm25, k_constant=60)

        # A: 1/(61) + 1/(62) = ~0.03267
        # C: 1/(63) + 1/(61) = ~0.03227
        # So A should rank higher than C
        scores = {r["text"]: r["rrf_score"] for r in result}
        assert scores["A"] > scores["C"]

        # All 4 unique documents should be present
        assert len(result) == 4

    # ---------------------------------------------------------------
    # Result structure
    # ---------------------------------------------------------------
    def test_result_structure(self):
        """Each fused result should have the required fields."""
        vector = [{"text": "test", "metadata": {"page": 1}, "chunk_id": "t1", "score": 0.3}]
        result = fuse_results(vector, [])
        r = result[0]
        assert "text" in r
        assert "metadata" in r
        assert "rrf_score" in r
        assert "sources" in r
        assert isinstance(r["rrf_score"], float)
        assert isinstance(r["sources"], list)

    def test_preserves_metadata(self):
        """Metadata from the first occurrence should be preserved."""
        vector = [
            {
                "text": "Pump failure",
                "metadata": {"equipment_id": "P-101", "page": 3, "doc_type": "REPORT"},
                "chunk_id": "c1",
                "score": 0.1,
            },
        ]
        result = fuse_results(vector, [])
        assert result[0]["metadata"]["equipment_id"] == "P-101"
        assert result[0]["metadata"]["page"] == 3

    # ---------------------------------------------------------------
    # Edge cases
    # ---------------------------------------------------------------
    def test_k_constant_validation(self):
        """k_constant must be positive."""
        with pytest.raises(ValueError, match="positive"):
            fuse_results([], [], k_constant=0)
        with pytest.raises(ValueError, match="positive"):
            fuse_results([], [], k_constant=-5)

    def test_small_k_constant(self):
        """Small k_constant should give more weight to top-ranked items."""
        vector = [
            {"text": "A", "chunk_id": "a", "metadata": {}},
            {"text": "B", "chunk_id": "b", "metadata": {}},
        ]
        result_k1 = fuse_results(vector, [], k_constant=1)
        result_k100 = fuse_results(vector, [], k_constant=100)
        # With k=1: rank-1 score = 1/2 = 0.5, rank-2 score = 1/3 = 0.333
        # Ratio: 0.5/0.333 = 1.5
        # With k=100: rank-1 score = 1/101, rank-2 score = 1/102
        # Ratio: 102/101 ≈ 1.01
        ratio_k1 = result_k1[0]["rrf_score"] / result_k1[1]["rrf_score"]
        ratio_k100 = result_k100[0]["rrf_score"] / result_k100[1]["rrf_score"]
        assert ratio_k1 > ratio_k100  # Small k differentiates ranks more

    def test_large_result_sets(self):
        """Handles large result sets correctly."""
        vector = [
            {"text": f"v{i}", "chunk_id": f"v{i}", "metadata": {}} for i in range(100)
        ]
        bm25 = [
            {"text": f"b{i}", "chunk_id": f"b{i}", "metadata": {}} for i in range(100)
        ]
        result = fuse_results(vector, bm25)
        assert len(result) == 200  # All unique

    def test_identical_result_lists(self):
        """When both lists contain the exact same items, all merge."""
        items = [
            {"text": f"item{i}", "chunk_id": f"c{i}", "metadata": {}} for i in range(5)
        ]
        result = fuse_results(items, items, k_constant=60)
        assert len(result) == 5
        for r in result:
            assert sorted(r["sources"]) == ["bm25", "vector"]


# ===========================================================================
# TASK 2.2.2 – Hybrid Search Orchestrator Tests
# ===========================================================================
from backend.rag.hybrid_search import search_hybrid


MOCK_EMBED_DIM = 8


def _mock_embedding(*args, **kwargs):
    """Return a mock embedding vector."""
    texts = args[0] if args else kwargs.get("texts", [""])
    return [[0.1] * MOCK_EMBED_DIM for _ in texts]


class TestSearchHybrid:
    """Tests for the hybrid search orchestrator."""

    # ---------------------------------------------------------------
    # Input validation
    # ---------------------------------------------------------------
    def test_empty_query_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            search_hybrid("")

    def test_whitespace_query_raises(self):
        with pytest.raises(ValueError, match="non-empty"):
            search_hybrid("   ")

    # ---------------------------------------------------------------
    # Integration with mocked retrievers
    # ---------------------------------------------------------------
    @patch("backend.rag.hybrid_search.get_embeddings", side_effect=_mock_embedding)
    @patch("backend.rag.hybrid_search.retrieve_vector_matches")
    def test_hybrid_with_only_vector(self, mock_vector, mock_embed):
        """When no BM25 index is provided and DB is unavailable, only vector results return."""
        mock_vector.return_value = [
            {"text": "Pump overheating", "metadata": {"equipment_id": "P-101"}, "score": 0.2, "chunk_id": "c1"},
            {"text": "Valve leak", "metadata": {"equipment_id": "V-201"}, "score": 0.5, "chunk_id": "c2"},
        ]

        # Pass a dummy bm25_index that returns empty
        mock_bm25 = MagicMock()
        mock_bm25.search.return_value = []

        results = search_hybrid("pump failure", k=5, bm25_index=mock_bm25)
        assert len(results) == 2
        assert results[0]["sources"] == ["vector"]
        mock_embed.assert_called_once_with(["pump failure"])
        mock_vector.assert_called_once()

    @patch("backend.rag.hybrid_search.get_embeddings", side_effect=_mock_embedding)
    @patch("backend.rag.hybrid_search.retrieve_vector_matches")
    def test_hybrid_with_both_retrievers(self, mock_vector, mock_embed):
        """Both retrievers contribute and results are fused."""
        mock_vector.return_value = [
            {"text": "Bearing overheating", "metadata": {"equipment_id": "P-101"}, "score": 0.1, "chunk_id": "c1"},
            {"text": "Motor vibration", "metadata": {"equipment_id": "M-501"}, "score": 0.3, "chunk_id": "c2"},
        ]

        mock_bm25 = MagicMock()
        mock_bm25.search.return_value = [
            {"text": "Bearing overheating", "metadata": {"equipment_id": "P-101"}, "score": 5.0, "chunk_id": "c1"},
            {"text": "Compressor noise", "metadata": {"equipment_id": "C-302"}, "score": 3.0, "chunk_id": "c3"},
        ]

        results = search_hybrid("bearing failure", k=10, bm25_index=mock_bm25)

        # c1 appears in both -> should rank first
        assert results[0]["text"] == "Bearing overheating"
        assert sorted(results[0]["sources"]) == ["bm25", "vector"]

        # 3 unique results total
        assert len(results) == 3

    @patch("backend.rag.hybrid_search.get_embeddings", side_effect=_mock_embedding)
    @patch("backend.rag.hybrid_search.retrieve_vector_matches")
    def test_hybrid_filters_passed_to_vector(self, mock_vector, mock_embed):
        """Filters are forwarded to the vector retriever."""
        mock_vector.return_value = []
        mock_bm25 = MagicMock()
        mock_bm25.search.return_value = []

        filters = {"equipment_id": "PUMP-101"}
        search_hybrid("bearing failure", filters=filters, bm25_index=mock_bm25)

        # Check that vector retriever received the filters
        _, kwargs = mock_vector.call_args
        assert kwargs["filters"] == {"equipment_id": "PUMP-101"}

    @patch("backend.rag.hybrid_search.get_embeddings", side_effect=_mock_embedding)
    @patch("backend.rag.hybrid_search.retrieve_vector_matches")
    def test_hybrid_filters_passed_to_bm25(self, mock_vector, mock_embed):
        """Filters are forwarded to the BM25 retriever."""
        mock_vector.return_value = []
        mock_bm25 = MagicMock()
        mock_bm25.search.return_value = []

        filters = {"equipment_id": "PUMP-101", "doc_type": "REPORT"}
        search_hybrid("failure analysis", filters=filters, bm25_index=mock_bm25)

        # Check that BM25 index received the filters
        _, kwargs = mock_bm25.search.call_args
        assert kwargs["filters"] == filters

    @patch("backend.rag.hybrid_search.get_embeddings", side_effect=_mock_embedding)
    @patch("backend.rag.hybrid_search.retrieve_vector_matches")
    def test_hybrid_respects_k(self, mock_vector, mock_embed):
        """Final result count should not exceed k."""
        mock_vector.return_value = [
            {"text": f"v{i}", "metadata": {}, "score": 0.1 * i, "chunk_id": f"v{i}"}
            for i in range(15)
        ]
        mock_bm25 = MagicMock()
        mock_bm25.search.return_value = [
            {"text": f"b{i}", "metadata": {}, "score": 5.0 - i, "chunk_id": f"b{i}"}
            for i in range(15)
        ]

        results = search_hybrid("test query", k=5, bm25_index=mock_bm25)
        assert len(results) <= 5

    @patch("backend.rag.hybrid_search.get_embeddings", side_effect=_mock_embedding)
    @patch("backend.rag.hybrid_search.retrieve_vector_matches")
    def test_hybrid_no_results(self, mock_vector, mock_embed):
        """When both retrievers return nothing, result is empty."""
        mock_vector.return_value = []
        mock_bm25 = MagicMock()
        mock_bm25.search.return_value = []

        results = search_hybrid("nonexistent query", bm25_index=mock_bm25)
        assert results == []

    # ---------------------------------------------------------------
    # Graceful degradation
    # ---------------------------------------------------------------
    @patch("backend.rag.hybrid_search.get_embeddings", side_effect=_mock_embedding)
    @patch("backend.rag.hybrid_search.retrieve_vector_matches", side_effect=Exception("Chroma down"))
    def test_hybrid_vector_failure_fallback_to_bm25(self, mock_vector, mock_embed):
        """If vector retrieval fails, BM25 results should still be returned."""
        mock_bm25 = MagicMock()
        mock_bm25.search.return_value = [
            {"text": "BM25 result", "metadata": {}, "score": 3.0, "chunk_id": "b1"},
        ]

        results = search_hybrid("test", bm25_index=mock_bm25)
        assert len(results) == 1
        assert results[0]["sources"] == ["bm25"]

    @patch("backend.rag.hybrid_search.get_embeddings", side_effect=_mock_embedding)
    @patch("backend.rag.hybrid_search.retrieve_vector_matches")
    def test_hybrid_bm25_failure_fallback_to_vector(self, mock_vector, mock_embed):
        """If BM25 fails, vector results should still be returned."""
        mock_vector.return_value = [
            {"text": "Vector result", "metadata": {}, "score": 0.1, "chunk_id": "v1"},
        ]
        mock_bm25 = MagicMock()
        mock_bm25.search.side_effect = RuntimeError("BM25 crash")

        results = search_hybrid("test", bm25_index=mock_bm25)
        assert len(results) == 1
        assert results[0]["sources"] == ["vector"]

    # ---------------------------------------------------------------
    # Metadata filter integration
    # ---------------------------------------------------------------
    @patch("backend.rag.hybrid_search.get_embeddings", side_effect=_mock_embedding)
    @patch("backend.rag.hybrid_search.retrieve_vector_matches")
    def test_hybrid_filter_no_other_equipment(self, mock_vector, mock_embed):
        """Filtering by equipment_id should exclude results from other equipment.

        This tests the contract from the checklist: search_hybrid("bearing failure",
        filters={"equipment_id": "PUMP-101"}) should not return records from other pumps.
        """
        # Vector retriever already applies filters, so it only returns PUMP-101 results
        mock_vector.return_value = [
            {"text": "PUMP-101 bearing failure", "metadata": {"equipment_id": "PUMP-101"}, "score": 0.1, "chunk_id": "c1"},
        ]

        # BM25 with pre-built index that applies filters
        mock_bm25 = MagicMock()
        mock_bm25.search.return_value = [
            {"text": "PUMP-101 bearing analysis", "metadata": {"equipment_id": "PUMP-101"}, "score": 4.0, "chunk_id": "c2"},
        ]

        results = search_hybrid(
            "bearing failure",
            filters={"equipment_id": "PUMP-101"},
            bm25_index=mock_bm25,
        )

        # All results should be for PUMP-101
        for r in results:
            assert r["metadata"].get("equipment_id") == "PUMP-101"

        # Verify filters were passed to both retrievers
        _, vkw = mock_vector.call_args
        assert vkw["filters"] == {"equipment_id": "PUMP-101"}
        _, bkw = mock_bm25.search.call_args
        assert bkw["filters"] == {"equipment_id": "PUMP-101"}

    # ---------------------------------------------------------------
    # Custom parameters
    # ---------------------------------------------------------------
    @patch("backend.rag.hybrid_search.get_embeddings", side_effect=_mock_embedding)
    @patch("backend.rag.hybrid_search.retrieve_vector_matches")
    def test_hybrid_custom_vector_k_and_bm25_k(self, mock_vector, mock_embed):
        """Custom vector_k and bm25_k are forwarded to retrievers."""
        mock_vector.return_value = []
        mock_bm25 = MagicMock()
        mock_bm25.search.return_value = []

        search_hybrid("test", vector_k=50, bm25_k=30, bm25_index=mock_bm25)

        _, vkw = mock_vector.call_args
        assert vkw["k"] == 50
        _, bkw = mock_bm25.search.call_args
        assert bkw["k"] == 30

    @patch("backend.rag.hybrid_search.get_embeddings", side_effect=_mock_embedding)
    @patch("backend.rag.hybrid_search.retrieve_vector_matches")
    def test_hybrid_custom_k_constant(self, mock_vector, mock_embed):
        """Custom k_constant affects the RRF fusion."""
        mock_vector.return_value = [
            {"text": "A", "metadata": {}, "chunk_id": "a", "score": 0.1},
        ]
        mock_bm25 = MagicMock()
        mock_bm25.search.return_value = []

        results_k10 = search_hybrid("test", k_constant=10, bm25_index=mock_bm25)
        # Reset mock
        mock_vector.return_value = [
            {"text": "A", "metadata": {}, "chunk_id": "a", "score": 0.1},
        ]
        results_k100 = search_hybrid("test", k_constant=100, bm25_index=mock_bm25)

        # k=10: score = 1/11 ≈ 0.0909
        # k=100: score = 1/101 ≈ 0.0099
        assert results_k10[0]["rrf_score"] > results_k100[0]["rrf_score"]


# ===========================================================================
# BM25 + RRF Integration Test (no mocks for BM25)
# ===========================================================================
from backend.rag.bm25_retriever import BM25Index


class TestRRFWithRealBM25:
    """Integration tests combining real BM25 with RRF fusion."""

    @pytest.fixture
    def bm25_index(self):
        chunks = [
            {
                "text": "CRITICAL ALERT: bearing overheating detected in pump P-101 during operation",
                "metadata": {"equipment_id": "P-101", "doc_type": "REPORT", "document_id": "doc-1"},
            },
            {
                "text": "Standard valve maintenance procedure for V-201 lubrication schedule",
                "metadata": {"equipment_id": "V-201", "doc_type": "SOP", "document_id": "doc-2"},
            },
            {
                "text": "Bearing replacement specifications for industrial centrifugal pumps",
                "metadata": {"equipment_id": "P-101", "doc_type": "MANUAL", "document_id": "doc-3"},
            },
            {
                "text": "Compressor C-302 vibration analysis and bearing wear report",
                "metadata": {"equipment_id": "C-302", "doc_type": "REPORT", "document_id": "doc-4"},
            },
        ]
        return BM25Index().build_from_chunks(chunks)

    def test_rrf_with_real_bm25_and_mock_vector(self, bm25_index):
        """RRF fusion with real BM25 results and mock vector results."""
        bm25_results = bm25_index.search("bearing overheating", k=4)

        # Mock vector results with one overlapping chunk
        vector_results = [
            {"text": "CRITICAL ALERT: bearing overheating detected in pump P-101 during operation",
             "metadata": {"equipment_id": "P-101"}, "score": 0.1, "chunk_id": "c0"},
            {"text": "Thermal analysis of pump bearings",
             "metadata": {"equipment_id": "P-101"}, "score": 0.3, "chunk_id": "c_extra"},
        ]
        # Add chunk_id to bm25 results to match (the first bm25 result should match c0 by text)
        for r in bm25_results:
            if "CRITICAL ALERT" in r["text"]:
                r["chunk_id"] = "c0"

        fused = fuse_results(vector_results, bm25_results, k_constant=60)

        # The CRITICAL ALERT chunk should rank highest (appears in both)
        assert "CRITICAL ALERT" in fused[0]["text"]
        assert len(fused[0]["sources"]) == 2

    def test_bm25_filter_then_fuse(self, bm25_index):
        """BM25 with equipment filter + RRF should only return matching equipment."""
        bm25_results = bm25_index.search(
            "bearing", k=5, filters={"equipment_id": "P-101"}
        )
        vector_results = [
            {"text": "P-101 bearing specs", "metadata": {"equipment_id": "P-101"}, "chunk_id": "v1", "score": 0.1},
        ]

        fused = fuse_results(vector_results, bm25_results)

        # All results should be for P-101
        for r in fused:
            assert r["metadata"].get("equipment_id") == "P-101"


# ===========================================================================
# Cleanup
# ===========================================================================
@pytest.fixture(autouse=True, scope="session")
def _cleanup_test_chroma():
    yield
    try:
        shutil.rmtree(_TEST_CHROMA_DIR, ignore_errors=True)
    except Exception:
        pass
