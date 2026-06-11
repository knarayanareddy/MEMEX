"""
Hybrid retrieval engine for MEMEX.

Fuses four independent signals:
1. Vector similarity (ChromaDB cosine)
2. Keyword search (SQLite FTS5 BM25)
3. Graph traversal (KuzuDB entity neighborhood)
4. Temporal decay (exponential recency)

Weights are loaded from Addendum A.
"""

from __future__ import annotations

import math
from datetime import datetime
from typing import Any, Optional

from ..config.settings import (
    RetrievalResult,
    Settings,
    get_settings,
    load_retrieval_weights,
)
from ..db.chroma import ChromaStore
from ..db.kuzu import KuzuGraph
from ..db.sqlite import SQLiteDatabase
from ..index.embedder import Embedder
from ..observability.logging import get_logger
from ..observability.metrics import get_metrics
from ..observability.slos import SLOTimer

logger = get_logger("recall.hybrid")
metrics = get_metrics()


class HybridRetriever:
    """Four-signal hybrid retrieval engine."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        sqlite: Optional[SQLiteDatabase] = None,
        chroma: Optional[ChromaStore] = None,
        kuzu: Optional[KuzuGraph] = None,
        embedder: Optional[Embedder] = None,
    ):
        self._settings = settings or get_settings()
        self._sqlite = sqlite
        self._chroma = chroma
        self._kuzu = kuzu
        self._embedder = embedder

        weights_config = load_retrieval_weights()
        self._weights = weights_config.get("hybrid_retrieval", {})
        self._decay = weights_config.get("temporal_decay", {})
        self._limits = weights_config.get("retrieval_limits", {})

    # ------------------------------------------------------------------
    # Signal extraction
    # ------------------------------------------------------------------

    def _vector_signal(self, query_embedding: list[float], top_k: int) -> dict[str, float]:
        """Get vector similarity scores from ChromaDB."""
        scores: dict[str, float] = {}

        if not self._chroma or not query_embedding:
            return scores

        with SLOTimer("vector_search_ms"):
            try:
                results = self._chroma.query_vectors(
                    query_embedding=query_embedding,
                    n_results=top_k,
                )

                ids = results.get("ids", [[]])[0]
                distances = results.get("distances", [[]])[0]

                for chunk_id, distance in zip(ids, distances):
                    # Convert cosine distance to similarity score [0, 1]
                    similarity = max(0.0, 1.0 - distance)
                    scores[chunk_id] = similarity

            except Exception as e:
                logger.error("vector_signal_error", error=str(e))

        return scores

    def _keyword_signal(self, query: str, top_k: int) -> dict[str, float]:
        """Get BM25 keyword scores from SQLite FTS5."""
        scores: dict[str, float] = {}

        if not self._sqlite:
            return scores

        with SLOTimer("fts_search_ms"):
            try:
                results = self._sqlite.fts_search(query, limit=top_k)
                if not results:
                    return scores

                # Normalize BM25 scores to [0, 1]
                min_rank = min(r["rank"] for r in results)
                max_rank = max(r["rank"] for r in results)
                rank_range = max_rank - min_rank if max_rank != min_rank else 1.0

                for r in results:
                    # BM25 rank is negative (lower = better)
                    normalized = (r["rank"] - min_rank) / rank_range if rank_range != 0 else 1.0
                    # Invert so higher = better
                    scores[r["chunk_id"]] = 1.0 - normalized

            except Exception as e:
                logger.error("keyword_signal_error", error=str(e))

        return scores

    def _graph_signal(self, query: str) -> dict[str, float]:
        """Get graph-based scores from entity neighborhood traversal."""
        scores: dict[str, float] = {}

        if not self._kuzu or not self._sqlite:
            return scores

        try:
            # Extract entities from query using simple NER
            entity_names = self._extract_query_entities(query)
            if not entity_names:
                return scores

            # Get documents connected to these entities
            docs = self._kuzu.get_entity_neighbors(entity_names)

            for doc in docs:
                doc_id = doc["doc_id"]
                # Get chunks for this document
                chunks = self._sqlite.get_chunks_for_document(doc_id)
                for chunk in chunks:
                    # Score based on hop distance (all 1-hop here)
                    scores[chunk["id"]] = 0.8

        except Exception as e:
            logger.error("graph_signal_error", error=str(e))

        return scores

    def _temporal_signal(self, chunk_ids: list[str]) -> dict[str, float]:
        """Compute temporal decay scores for chunks."""
        scores: dict[str, float] = {}

        if not self._sqlite:
            return scores

        lam = self._decay.get("lambda", 0.005)
        now = datetime.utcnow()

        for chunk_id in chunk_ids:
            try:
                chunk = self._sqlite.get_chunk_by_id(chunk_id)
                if not chunk:
                    continue

                # Get document capture time
                doc = self._sqlite.get_document(chunk["document_id"])
                if not doc:
                    continue

                captured_at_str = doc.get("captured_at", "")
                if captured_at_str:
                    try:
                        captured_at = datetime.fromisoformat(captured_at_str)
                        age_days = (now - captured_at).total_seconds() / 86400
                        scores[chunk_id] = math.exp(-lam * age_days)
                    except (ValueError, TypeError):
                        scores[chunk_id] = 0.5  # Neutral score
                else:
                    scores[chunk_id] = 0.5

            except Exception:
                scores[chunk_id] = 0.5

        return scores

    @staticmethod
    def _extract_query_entities(query: str) -> list[str]:
        """Simple entity extraction from query text."""
        import re
        # Capitalized multi-word phrases (basic heuristic)
        entities = re.findall(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+\b', query)
        # Also extract capitalized single words
        entities.extend(re.findall(r'\b[A-Z][a-z]+\b', query))
        return list(set(entities))

    # ------------------------------------------------------------------
    # Score fusion
    # ------------------------------------------------------------------

    def _fuse_scores(
        self,
        vector_scores: dict[str, float],
        keyword_scores: dict[str, float],
        graph_scores: dict[str, float],
        temporal_scores: dict[str, float],
    ) -> list[tuple[str, float, float, float, float, float]]:
        """Fuse scores from all four signals.

        Returns list of (chunk_id, combined, vector, keyword, graph, temporal).
        """
        w_vec = self._weights.get("vector_weight", 0.40)
        w_kw = self._weights.get("keyword_weight", 0.30)
        w_graph = self._weights.get("graph_weight", 0.20)
        w_time = self._weights.get("temporal_weight", 0.10)

        # Gather all candidate chunk IDs
        all_ids = set(vector_scores) | set(keyword_scores) | set(graph_scores) | set(temporal_scores)

        results = []
        for chunk_id in all_ids:
            v = vector_scores.get(chunk_id, 0.0)
            k = keyword_scores.get(chunk_id, 0.0)
            g = graph_scores.get(chunk_id, 0.0)
            t = temporal_scores.get(chunk_id, 0.0)

            combined = (w_vec * v) + (w_kw * k) + (w_graph * g) + (w_time * t)
            results.append((chunk_id, combined, v, k, g, t))

        # Sort by combined score descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    # ------------------------------------------------------------------
    # Main retrieval
    # ------------------------------------------------------------------

    def retrieve(
        self,
        query: str,
        top_k: Optional[int] = None,
        after: Optional[str] = None,
        before: Optional[str] = None,
        source_type: Optional[str] = None,
    ) -> list[RetrievalResult]:
        """Execute hybrid retrieval.

        Args:
            query: Search query.
            top_k: Number of results (default from Addendum A).
            after: Only results captured after this date.
            before: Only results captured before this date.
            source_type: Filter by source type.

        Returns:
            List of RetrievalResult sorted by combined score.
        """
        top_k = min(top_k or self._limits.get("default_top_k", 20),
                    self._limits.get("max_top_k", 50))

        with SLOTimer("hybrid_retrieval_ms"):
            # Generate query embedding
            query_embedding = None
            if self._embedder:
                query_embedding = self._embedder.embed_text(query)

            # Extract all four signals
            vector_scores = self._vector_signal(query_embedding, top_k) if query_embedding else {}
            keyword_scores = self._keyword_signal(query, top_k)
            graph_scores = self._graph_signal(query)

            # Gather all chunk IDs for temporal scoring
            all_chunk_ids = list(
                set(vector_scores) | set(keyword_scores) | set(graph_scores)
            )
            temporal_scores = self._temporal_signal(all_chunk_ids)

            # Fuse scores
            fused = self._fuse_scores(vector_scores, keyword_scores, graph_scores, temporal_scores)

            # Build results
            results: list[RetrievalResult] = []
            for chunk_id, combined, vec, kw, graph, temporal in fused[:top_k]:
                if not self._sqlite:
                    continue

                chunk = self._sqlite.get_chunk_by_id(chunk_id)
                if not chunk:
                    continue

                doc = self._sqlite.get_document(chunk["document_id"])
                if not doc:
                    continue

                # Apply filters
                if source_type and doc["source_type"] != source_type:
                    continue
                if after and doc.get("captured_at", "") < after:
                    continue
                if before and doc.get("captured_at", "") > before:
                    continue

                try:
                    captured_at = datetime.fromisoformat(doc["captured_at"])
                except (ValueError, TypeError):
                    captured_at = datetime.utcnow()

                results.append(RetrievalResult(
                    chunk_id=chunk_id,
                    document_id=chunk["document_id"],
                    content=chunk["content"],
                    combined_score=combined,
                    vector_score=vec,
                    keyword_score=kw,
                    graph_score=graph,
                    temporal_score=temporal,
                    source_type=doc["source_type"],
                    source_path=doc["source_path"],
                    captured_at=captured_at,
                ))

            # Assign citation indices (1-based)
            for i, result in enumerate(results, 1):
                result.citation_index = i

        logger.info(
            "retrieval_complete",
            query=query[:50],
            result_count=len(results),
        )

        return results

    def search(self, query: str, limit: int = 20, **kwargs: Any) -> list[dict]:
        """Simple search returning dictionaries (for API use)."""
        results = self.retrieve(query, top_k=limit, **kwargs)
        return [
            {
                "chunk_id": r.chunk_id,
                "document_id": r.document_id,
                "content": r.content,
                "score": round(r.combined_score, 4),
                "source_type": r.source_type,
                "source_path": r.source_path,
                "captured_at": r.captured_at.isoformat(),
            }
            for r in results
        ]
