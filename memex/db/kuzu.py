"""
KuzuDB graph store management for MEMEX.

Handles:
- Graph schema initialization
- Entity/relation insertion
- Cypher queries for graph traversal
- Delete propagation
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from ..config.settings import Settings, get_settings
from ..observability.logging import get_logger

logger = get_logger(__name__)

_SCHEMA_SQL = """
CREATE NODE TABLE IF NOT EXISTS Document (
    id STRING, source_type STRING, source_path STRING,
    captured_at STRING, PRIMARY KEY (id)
);
CREATE NODE TABLE IF NOT EXISTS Entity (
    id STRING, canonical_name STRING, entity_type STRING,
    PRIMARY KEY (id)
);
CREATE NODE TABLE IF NOT EXISTS Chunk (
    id STRING, document_id STRING, chunk_index INT64,
    PRIMARY KEY (id)
);
CREATE REL TABLE IF NOT EXISTS MENTIONED_IN (
    FROM Entity TO Document, confidence DOUBLE, mention_text STRING
);
CREATE REL TABLE IF NOT EXISTS MENTIONED_IN_CHUNK (
    FROM Entity TO Chunk, confidence DOUBLE
);
CREATE REL TABLE IF NOT EXISTS RELATED_TO (
    FROM Entity TO Entity, predicate STRING,
    confidence DOUBLE, evidence STRING, document_id STRING
);
CREATE REL TABLE IF NOT EXISTS CONTAINS (
    FROM Document TO Chunk
);
"""


class KuzuGraph:
    """KuzuDB embedded graph database wrapper."""

    def __init__(self, kuzu_path: Optional[Path] = None, settings: Optional[Settings] = None):
        self._settings = settings or get_settings()
        self._kuzu_path = kuzu_path or self._settings.kuzu_path
        self._conn = None
        self._db = None

    def initialize(self) -> None:
        """Initialize the KuzuDB database and create schema."""
        import kuzu

        self._kuzu_path.mkdir(parents=True, exist_ok=True)
        self._db = kuzu.Database(str(self._kuzu_path))
        self._conn = kuzu.Connection(self._db)

        # Create schema — each statement separately
        for statement in _SCHEMA_SQL.strip().split(";"):
            stmt = statement.strip()
            if stmt:
                try:
                    self._conn.execute(stmt)
                except Exception as e:
                    # "Table already exists" is fine
                    if "already exists" not in str(e).lower():
                        raise

        logger.info("kuzu_initialized")

    @property
    def connection(self):
        if self._conn is None:
            self.initialize()
        return self._conn

    # ------------------------------------------------------------------
    # Node operations
    # ------------------------------------------------------------------

    def add_document_node(self, doc_id: str, source_type: str, source_path: str, captured_at: str) -> None:
        """Add a Document node."""
        self.connection.execute(
            """MERGE (d:Document {id: $id})
               ON CREATE SET d.source_type = $st, d.source_path = $sp, d.captured_at = $ca""",
            {"id": doc_id, "st": source_type, "sp": source_path, "ca": captured_at},
        )

    def add_entity_node(self, entity_id: str, canonical_name: str, entity_type: str) -> None:
        """Add an Entity node."""
        self.connection.execute(
            """MERGE (e:Entity {id: $id})
               ON CREATE SET e.canonical_name = $name, e.entity_type = $type""",
            {"id": entity_id, "name": canonical_name, "type": entity_type},
        )

    def add_chunk_node(self, chunk_id: str, document_id: str, chunk_index: int) -> None:
        """Add a Chunk node."""
        self.connection.execute(
            """MERGE (c:Chunk {id: $id})
               ON CREATE SET c.document_id = $doc_id, c.chunk_index = $idx""",
            {"id": chunk_id, "doc_id": document_id, "idx": chunk_index},
        )

    # ------------------------------------------------------------------
    # Edge operations
    # ------------------------------------------------------------------

    def add_mentioned_in(
        self, entity_id: str, document_id: str, confidence: float, mention_text: str
    ) -> None:
        """Create MENTIONED_IN edge from Entity to Document."""
        self.connection.execute(
            """MATCH (e:Entity {id: $eid}), (d:Document {id: $did})
               MERGE (e)-[:MENTIONED_IN {confidence: $conf, mention_text: $mt}]->(d)""",
            {"eid": entity_id, "did": document_id, "conf": confidence, "mt": mention_text},
        )

    def add_mentioned_in_chunk(
        self, entity_id: str, chunk_id: str, confidence: float
    ) -> None:
        """Create MENTIONED_IN_CHUNK edge."""
        self.connection.execute(
            """MATCH (e:Entity {id: $eid}), (c:Chunk {id: $cid})
               MERGE (e)-[:MENTIONED_IN_CHUNK {confidence: $conf}]->(c)""",
            {"eid": entity_id, "cid": chunk_id, "conf": confidence},
        )

    def add_related_to(
        self,
        subject_id: str,
        object_id: str,
        predicate: str,
        confidence: float,
        evidence: str,
        document_id: str,
    ) -> None:
        """Create RELATED_TO edge between entities."""
        self.connection.execute(
            """MATCH (s:Entity {id: $sid}), (o:Entity {id: $oid})
               MERGE (s)-[:RELATED_TO {predicate: $pred, confidence: $conf,
                        evidence: $ev, document_id: $did}]->(o)""",
            {
                "sid": subject_id, "oid": object_id, "pred": predicate,
                "conf": confidence, "ev": evidence, "did": document_id,
            },
        )

    def add_contains(self, document_id: str, chunk_id: str) -> None:
        """Create CONTAINS edge from Document to Chunk."""
        self.connection.execute(
            """MATCH (d:Document {id: $did}), (c:Chunk {id: $cid})
               MERGE (d)-[:CONTAINS]->(c)""",
            {"did": document_id, "cid": chunk_id},
        )

    # ------------------------------------------------------------------
    # Query operations
    # ------------------------------------------------------------------

    def get_entity_neighbors(self, entity_names: list[str], hop_distance: int = 2) -> list[dict]:
        """Get documents connected to entities by name, with N-hop expansion."""
        if not entity_names:
            return []

        # Build a Cypher query for entity neighborhood
        names_list = ", ".join([f'"{n}"' for n in entity_names])
        query = f"""
            MATCH (e:Entity)-[:MENTIONED_IN]->(d:Document)
            WHERE e.canonical_name IN [{names_list}]
            RETURN DISTINCT d.id as doc_id, d.source_type as source_type,
                   d.source_path as source_path, d.captured_at as captured_at
        """
        result = self.connection.execute(query)
        docs = []
        while result.has_next():
            row = result.get_next()
            docs.append({
                "doc_id": row[0],
                "source_type": row[1],
                "source_path": row[2],
                "captured_at": row[3],
            })
        return docs

    def get_entity_with_neighbors(self, entity_id: str) -> dict[str, Any]:
        """Get entity details and connected nodes."""
        result = self.connection.execute(
            "MATCH (e:Entity {id: $id}) RETURN e.id, e.canonical_name, e.entity_type",
            {"id": entity_id},
        )
        if not result.has_next():
            return {}
        row = result.get_next()
        entity = {"id": row[0], "canonical_name": row[1], "entity_type": row[2]}

        # Get related documents
        doc_result = self.connection.execute(
            """MATCH (e:Entity {id: $id})-[:MENTIONED_IN]->(d:Document)
               RETURN d.id, d.source_path""",
            {"id": entity_id},
        )
        docs = []
        while doc_result.has_next():
            d = doc_result.get_next()
            docs.append({"id": d[0], "source_path": d[1]})

        return {"entity": entity, "connected_documents": docs}

    # ------------------------------------------------------------------
    # Delete operations
    # ------------------------------------------------------------------

    def delete_mentions_for_document(self, document_id: str) -> int:
        """Delete all MENTIONED_IN edges and orphan entity nodes for a document."""
        count = 0
        try:
            # Delete edges pointing to this document
            self.connection.execute(
                """MATCH (e:Entity)-[r:MENTIONED_IN]->(d:Document {id: $did})
                   DELETE r""",
                {"did": document_id},
            )
            count += 1

            self.connection.execute(
                """MATCH (e:Entity)-[r:MENTIONED_IN_CHUNK]->(c:Chunk)
                   WHERE c.document_id = $did
                   DELETE r""",
                {"did": document_id},
            )
            count += 1

            # Delete RELATED_TO edges for this document
            self.connection.execute(
                """MATCH (e1:Entity)-[r:RELATED_TO]->(e2:Entity)
                   WHERE r.document_id = $did
                   DELETE r""",
                {"did": document_id},
            )
            count += 1

            # Delete chunk and document nodes
            self.connection.execute(
                """MATCH (c:Chunk {document_id: $did}) DELETE c""",
                {"did": document_id},
            )
            self.connection.execute(
                """MATCH (d:Document {id: $did}) DELETE d""",
                {"did": document_id},
            )

            logger.info("graph_mentions_deleted", document_id=document_id)
        except Exception as e:
            logger.error("graph_delete_failed", document_id=document_id, error=str(e))
        return count

    def verify_no_mentions_for_document(self, document_id: str) -> bool:
        """Verify no graph data exists for a document."""
        result = self.connection.execute(
            "MATCH (d:Document {id: $id}) RETURN count(d)",
            {"id": document_id},
        )
        if result.has_next():
            return result.get_next()[0] == 0
        return True

    # ------------------------------------------------------------------
    # Stats
    # ------------------------------------------------------------------

    def get_stats(self) -> dict[str, Any]:
        """Get graph store statistics."""
        try:
            node_result = self.connection.execute(
                "MATCH (n) RETURN count(n)"
            )
            nodes = node_result.get_next()[0] if node_result.has_next() else 0

            edge_result = self.connection.execute(
                "MATCH ()-[r]->() RETURN count(r)"
            )
            edges = edge_result.get_next()[0] if edge_result.has_next() else 0

            return {
                "status": "ok",
                "total_nodes": nodes,
                "total_edges": edges,
            }
        except Exception as e:
            return {"status": "error", "error": str(e)}

    def health_check(self) -> dict[str, Any]:
        """Quick health check."""
        try:
            return self.get_stats()
        except Exception as e:
            return {"status": "error", "error": str(e)}
