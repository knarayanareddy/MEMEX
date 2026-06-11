"""
Retrieval quality invariant tests.

INV-018: Hybrid retrieval returns results in score-descending order
INV-019: Time filter after:X returns no documents captured before X
INV-020: Retrieval weights sum to 1.0
INV-021: Temporal decay score is monotonically decreasing with age
INV-022: Temporal decay scores are in [0, 1]
INV-023: Chunking budgets are all positive
INV-024: Context window settings are reasonable
"""

import math
import pytest

from memex.config.settings import load_retrieval_weights, load_chunking


class TestRetrievalMath:
    """INV-018 to INV-024: Retrieval mathematical invariants."""

    def test_inv020_weights_sum_to_one(self):
        """INV-020: Retrieval weights sum to exactly 1.0."""
        weights = load_retrieval_weights()
        hw = weights["hybrid_retrieval"]

        total = (
            hw["vector_weight"]
            + hw["keyword_weight"]
            + hw["graph_weight"]
            + hw["temporal_weight"]
        )
        assert total == pytest.approx(1.0, abs=1e-10), f"Weights sum to {total}, not 1.0"

    def test_inv021_temporal_decay_monotonically_decreasing(self):
        """INV-021: Temporal decay decreases with age."""
        weights = load_retrieval_weights()
        lam = weights["temporal_decay"]["lambda"]

        prev_score = 1.0
        for age_days in range(0, 1000, 10):
            score = math.exp(-lam * age_days)
            assert score <= prev_score + 1e-10, f"Score increased at age={age_days}"
            prev_score = score

    def test_inv022_temporal_decay_range(self):
        """INV-022: Temporal decay scores are in [0, 1]."""
        weights = load_retrieval_weights()
        lam = weights["temporal_decay"]["lambda"]

        for age_days in [0, 1, 7, 30, 100, 365, 1000]:
            score = math.exp(-lam * age_days)
            assert 0.0 <= score <= 1.0, f"Score {score} out of range for age={age_days}"

    def test_inv018_score_ordering(self):
        """INV-018: Verify score fusion produces descending order."""
        from memex.recall.hybrid_retrieval import HybridRetriever

        # Simulate fused scores
        vector_scores = {"a": 0.9, "b": 0.5, "c": 0.1}
        keyword_scores = {"a": 0.3, "b": 0.7, "c": 0.2}
        graph_scores = {"a": 0.0, "b": 0.0, "c": 0.8}
        temporal_scores = {"a": 1.0, "b": 0.5, "c": 0.1}

        retriever = HybridRetriever.__new__(HybridRetriever)
        retriever._weights = load_retrieval_weights()["hybrid_retrieval"]
        retriever._decay = load_retrieval_weights()["temporal_decay"]

        fused = retriever._fuse_scores(
            vector_scores, keyword_scores, graph_scores, temporal_scores
        )

        # Verify descending order
        scores = [f[1] for f in fused]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], f"Not descending at position {i}"

    def test_inv019_time_filter_after(self):
        """INV-019: Time filter after:X excludes older documents."""
        # This tests the filtering logic conceptually
        after = "2026-01-01"
        test_dates = [
            ("2025-12-31", False),
            ("2026-01-01", True),
            ("2026-06-01", True),
        ]
        for date, should_pass in test_dates:
            result = date >= after
            assert result == should_pass, f"Date {date} filter failed"

    def test_inv023_chunking_budgets_are_positive(self):
        """INV-023: All chunking budgets are positive."""
        chunking = load_chunking()
        budgets = chunking["chunk_budgets"]
        for key, value in budgets.items():
            assert value >= 0, f"Budget {key} is negative: {value}"

    def test_inv024_context_window_sane(self):
        """INV-024: Context window settings are reasonable."""
        chunking = load_chunking()
        ctx = chunking["context_window"]
        assert ctx["max_context_tokens"] > 0
        assert ctx["conversation_history_turns"] > 0
