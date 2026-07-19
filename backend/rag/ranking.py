"""
PS8 – Ranking & Decay Optimizations (Phase 2.3)

Task 2.3.1 – Temporal Recency Decay Function
Task 2.3.2 – Critical Alert Boosting

Provides post-retrieval reranking functions to adjust scores based on the
age of the document (recent logs are boosted, older decay) and the presence
of critical alerts or high severity markers.
"""

import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import logging

logger = logging.getLogger(__name__)

# Keywords that indicate a critical alert or failure event
_CRITICAL_KEYWORDS = {"alert", "critical", "failure", "emergency", "danger", "melted", "overheating", "broken"}


def apply_recency_decay(
    score: float, 
    doc_date: datetime, 
    halflife_days: float = 365.0, 
    current_date: Optional[datetime] = None
) -> float:
    """Calculate a score multiplier based on the age of the document.

    Uses an exponential decay formula: score * (0.5 ^ (age_days / halflife_days))

    Parameters
    ----------
    score : float
        The base score of the document/chunk.
    doc_date : datetime
        The date the document was created or applies to.
    halflife_days : float
        The number of days for the score to decay to 50% of its original value.
    current_date : datetime, optional
        The reference date (defaults to now in UTC).

    Returns
    -------
    float
        The decayed score.
    """
    if current_date is None:
        current_date = datetime.now(timezone.utc)
        
    if doc_date.tzinfo is None:
        doc_date = doc_date.replace(tzinfo=timezone.utc)
        
    age_delta = current_date - doc_date
    age_days = max(0.0, age_delta.total_seconds() / 86400.0)
    
    decay_factor = math.pow(0.5, age_days / halflife_days)
    return score * decay_factor


def apply_critical_alert_boost(
    chunk: Dict[str, Any], 
    score: float, 
    boost_multiplier: float = 1.5
) -> float:
    """Detect critical terms and apply a score boost.

    Parameters
    ----------
    chunk : Dict
        The retrieved document chunk (must contain ``text`` and ``metadata``).
    score : float
        The base score of the chunk.
    boost_multiplier : float
        The multiplier to apply if critical terms/severity are found.

    Returns
    -------
    float
        The boosted score.
    """
    # 1. Check explicit metadata severity
    meta = chunk.get("metadata", {})
    severity = meta.get("severity", "").upper()
    if severity in {"HIGH", "CRITICAL"}:
        return score * boost_multiplier
        
    # 2. Check text for critical keywords
    text = chunk.get("text", "").lower()
    if any(kw in text for kw in _CRITICAL_KEYWORDS):
        return score * boost_multiplier
        
    return score


def rerank_results(
    results: List[Dict[str, Any]], 
    current_date: Optional[datetime] = None
) -> List[Dict[str, Any]]:
    """Apply recency decay and critical alert boosting, then re-sort.

    Parameters
    ----------
    results : List[Dict]
        The list of fused search results (containing ``rrf_score``).
    current_date : datetime, optional
        Reference date for recency decay.

    Returns
    -------
    List[Dict]
        The results sorted by ``final_score`` descending.
    """
    for res in results:
        # Base score is the RRF score, fallback to 0.0
        score = res.get("rrf_score", 0.0)
        
        # 1. Apply Critical Alert Boosting
        score = apply_critical_alert_boost(res, score)
        
        # 2. Apply Temporal Recency Decay
        meta = res.get("metadata", {})
        # Look for a date in metadata
        doc_date_str = meta.get("date_range_start") or meta.get("date_range_end")
        
        if doc_date_str:
            try:
                # The pipeline usually writes YYYY-MM-DD or full ISO format
                if isinstance(doc_date_str, str):
                    if "T" in doc_date_str:
                        doc_date = datetime.fromisoformat(doc_date_str.replace("Z", "+00:00"))
                    else:
                        doc_date = datetime.strptime(doc_date_str[:10], "%Y-%m-%d").replace(tzinfo=timezone.utc)
                else:
                    doc_date = doc_date_str  # In case it's already a datetime object
                    
                score = apply_recency_decay(score, doc_date, current_date=current_date)
            except Exception as exc:
                logger.debug("Failed to parse date %s for recency decay: %s", doc_date_str, exc)
                pass
                
        res["final_score"] = score

    # Re-sort by final_score descending
    sorted_results = sorted(results, key=lambda x: x.get("final_score", 0.0), reverse=True)
    return sorted_results
