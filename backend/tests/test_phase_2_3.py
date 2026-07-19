"""
Phase 2.3 Tests – Ranking & Decay Optimizations

Task 2.3.1: Temporal Recency Decay Function tests
Task 2.3.2: Critical Alert Boosting tests
"""

from datetime import datetime, timedelta, timezone

from backend.rag.ranking import (
    apply_recency_decay,
    apply_critical_alert_boost,
    rerank_results,
)


class TestRecencyDecay:
    """Unit tests for Temporal Recency Decay Function."""

    def test_apply_recency_decay_exact_halflife(self):
        """At exactly 365 days old, the score should be halved."""
        now = datetime(2026, 7, 19, tzinfo=timezone.utc)
        doc_date = now - timedelta(days=365)
        
        base_score = 10.0
        decayed = apply_recency_decay(base_score, doc_date, halflife_days=365.0, current_date=now)
        
        assert abs(decayed - 5.0) < 1e-6

    def test_apply_recency_decay_now(self):
        """A brand new document should have no decay (score remains same)."""
        now = datetime(2026, 7, 19, tzinfo=timezone.utc)
        
        base_score = 10.0
        decayed = apply_recency_decay(base_score, now, current_date=now)
        
        assert abs(decayed - 10.0) < 1e-6

    def test_apply_recency_decay_future(self):
        """A future document should also have no decay (age capped at 0)."""
        now = datetime(2026, 7, 19, tzinfo=timezone.utc)
        future_date = now + timedelta(days=10)
        
        base_score = 10.0
        decayed = apply_recency_decay(base_score, future_date, current_date=now)
        
        assert abs(decayed - 10.0) < 1e-6

    def test_apply_recency_decay_very_old(self):
        """A document 2 halflives old should be 25% of original score."""
        now = datetime(2026, 7, 19, tzinfo=timezone.utc)
        doc_date = now - timedelta(days=730) # 2 years
        
        base_score = 10.0
        decayed = apply_recency_decay(base_score, doc_date, halflife_days=365.0, current_date=now)
        
        assert abs(decayed - 2.5) < 1e-6


class TestCriticalAlertBoosting:
    """Unit tests for Critical Alert Boosting."""

    def test_boost_via_text_keyword(self):
        """Score should be boosted if text contains a critical keyword."""
        chunk = {"text": "CRITICAL ALERT: bearing melted", "metadata": {}}
        base_score = 10.0
        
        boosted = apply_critical_alert_boost(chunk, base_score, boost_multiplier=1.5)
        assert abs(boosted - 15.0) < 1e-6

    def test_boost_via_metadata_severity(self):
        """Score should be boosted if metadata severity is HIGH/CRITICAL."""
        chunk = {"text": "Just some normal text", "metadata": {"severity": "CRITICAL"}}
        base_score = 10.0
        
        boosted = apply_critical_alert_boost(chunk, base_score, boost_multiplier=1.5)
        assert abs(boosted - 15.0) < 1e-6

    def test_no_boost_if_not_critical(self):
        """Score should not be boosted if no keywords or severity match."""
        chunk = {"text": "Routine maintenance completed", "metadata": {"severity": "LOW"}}
        base_score = 10.0
        
        boosted = apply_critical_alert_boost(chunk, base_score, boost_multiplier=1.5)
        assert abs(boosted - 10.0) < 1e-6


class TestRerankResults:
    """Integration tests for the rerank_results orchestrator."""

    def test_rerank_sorts_correctly_with_mixed_optimizations(self):
        """
        Tests that critical alerts and recent docs outrank older/normal docs.
        """
        now = datetime(2026, 7, 19, tzinfo=timezone.utc)
        one_year_ago = (now - timedelta(days=365)).strftime("%Y-%m-%d")
        today = now.strftime("%Y-%m-%d")

        results = [
            # 1. Normal doc, 1 year old (Score: 10.0 -> decays to 5.0)
            {
                "id": "doc1",
                "text": "Routine maintenance",
                "metadata": {"date_range_start": one_year_ago},
                "rrf_score": 10.0,
            },
            # 2. Critical doc, 1 year old (Score: 10.0 -> boost to 15.0 -> decays to 7.5)
            {
                "id": "doc2",
                "text": "Bearing failure detected",
                "metadata": {"date_range_start": one_year_ago},
                "rrf_score": 10.0,
            },
            # 3. Normal doc, brand new (Score: 10.0 -> no decay -> 10.0)
            {
                "id": "doc3",
                "text": "Routine maintenance",
                "metadata": {"date_range_start": today},
                "rrf_score": 10.0,
            },
            # 4. Critical doc, brand new (Score: 10.0 -> boost to 15.0 -> no decay -> 15.0)
            {
                "id": "doc4",
                "text": "Critical alert: system down",
                "metadata": {"date_range_start": today},
                "rrf_score": 10.0,
            }
        ]

        reranked = rerank_results(results, current_date=now)

        # Expected order: doc4 (15.0), doc3 (10.0), doc2 (7.5), doc1 (5.0)
        assert reranked[0]["id"] == "doc4"
        assert reranked[1]["id"] == "doc3"
        assert reranked[2]["id"] == "doc2"
        assert reranked[3]["id"] == "doc1"

        assert abs(reranked[0]["final_score"] - 15.0) < 1e-6
        assert abs(reranked[1]["final_score"] - 10.0) < 1e-6
        assert abs(reranked[2]["final_score"] - 7.5) < 1e-6
        assert abs(reranked[3]["final_score"] - 5.0) < 1e-6

    def test_rerank_ignores_invalid_dates(self):
        """Invalid date strings should simply bypass the decay function."""
        results = [
            {
                "id": "doc1",
                "text": "Normal text",
                "metadata": {"date_range_start": "invalid-date-string"},
                "rrf_score": 10.0,
            }
        ]
        
        reranked = rerank_results(results)
        assert reranked[0]["final_score"] == 10.0
