"""
Graph extraction for MEMEX.

Entity extraction with spaCy NER.
Optional relation extraction via LLM.
Writes to both KuzuDB and SQLite.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Optional

from ..config.settings import Settings, get_settings, load_retrieval_weights
from ..db.kuzu import KuzuGraph
from ..db.sqlite import SQLiteDatabase
from ..observability.logging import get_logger

logger = get_logger("index.graph")

# spaCy entity label mapping
_LABEL_MAP = {
    "PERSON": "PERSON",
    "ORG": "ORG",
    "GPE": "PLACE",
    "LOC": "PLACE",
    "PRODUCT": "CONCEPT",
    "EVENT": "CONCEPT",
    "WORK_OF_ART": "CONCEPT",
    "LAW": "CONCEPT",
    "LANGUAGE": "CONCEPT",
    "DATE": "CONCEPT",
    "TIME": "CONCEPT",
    "MONEY": "CONCEPT",
    "QUANTITY": "CONCEPT",
}


class GraphExtractor:
    """Extract entities and relations from documents."""

    def __init__(
        self,
        settings: Optional[Settings] = None,
        kuzu: Optional[KuzuGraph] = None,
        sqlite: Optional[SQLiteDatabase] = None,
    ):
        self._settings = settings or get_settings()
        self._kuzu = kuzu
        self._sqlite = sqlite
        self._nlp = None

    def initialize(self) -> None:
        """Load spaCy model."""
        try:
            import spacy
            try:
                self._nlp = spacy.load("en_core_web_trf")
            except OSError:
                try:
                    self._nlp = spacy.load("en_core_web_sm")
                except OSError:
                    logger.warning("spacy_model_missing", action="downloading en_core_web_sm")
                    import subprocess
                    result = subprocess.run(
                        ["python", "-m", "spacy", "download", "en_core_web_sm"],
                        capture_output=True, text=True,
                    )
                    if result.returncode == 0:
                        self._nlp = spacy.load("en_core_web_sm")
                    else:
                        logger.error("spacy_download_failed", stderr=result.stderr)
                        return
            logger.info("spacy_loaded", model=self._nlp.meta.get("name", "unknown"))
        except ImportError:
            logger.error("spacy_not_installed")

    def extract_entities(
        self,
        document_id: str,
        chunk_id: str,
        text: str,
    ) -> list[dict[str, Any]]:
        """Extract named entities from text using spaCy NER."""
        if not self._nlp:
            return []

        doc = self._nlp(text)
        entities = []

        for ent in doc.ents:
            entity_type = _LABEL_MAP.get(ent.label_, "CONCEPT")
            entity_data = {
                "text": ent.text,
                "label": entity_type,
                "start_char": ent.start_char,
                "end_char": ent.end_char,
                "confidence": 0.8,
            }
            entities.append(entity_data)
            self._persist_entity(
                document_id=document_id,
                chunk_id=chunk_id,
                entity_data=entity_data,
            )

        if entities:
            logger.debug(
                "entities_extracted",
                document_id=document_id[:16],
                count=len(entities),
            )

        return entities

    def _persist_entity(
        self,
        document_id: str,
        chunk_id: str,
        entity_data: dict[str, Any],
    ) -> None:
        """Persist an entity to SQLite and KuzuDB.

        FIX: Previous version had a scoping bug where entity_id could be
        referenced before assignment in the Kuzu block. Now we always compute
        entity_id from the SQLite upsert first, and use a generated UUID as
        fallback when SQLite is unavailable.
        """
        canonical_name = entity_data["text"].strip()
        entity_type = entity_data["label"]

        # Always resolve entity_id deterministically
        entity_id: Optional[str] = None

        # SQLite — primary source of truth for entity identity
        if self._sqlite:
            try:
                entity_id = self._sqlite.upsert_entity(canonical_name, entity_type)
                self._sqlite.insert_entity_mention(
                    entity_id=entity_id,
                    document_id=document_id,
                    chunk_id=chunk_id,
                    mention_text=entity_data["text"],
                    start_char=entity_data["start_char"],
                    confidence=entity_data["confidence"],
                )
            except Exception as e:
                logger.error("entity_sqlite_error", error=str(e))

        # If SQLite didn't produce an ID (or isn't configured), generate one
        if entity_id is None:
            entity_id = str(uuid.uuid4())

        # KuzuDB — secondary store, uses the entity_id from above
        if self._kuzu:
            try:
                self._kuzu.add_entity_node(entity_id, canonical_name, entity_type)
                self._kuzu.add_mentioned_in(
                    entity_id, document_id,
                    entity_data["confidence"], entity_data["text"],
                )
            except Exception as e:
                logger.error("entity_kuzu_error", error=str(e))

    def extract_relations(
        self,
        document_id: str,
        chunk_id: str,
        text: str,
        entities: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Extract relations between entities using LLM (opt-in)."""
        if not self._settings.extract_relations:
            return []

        weights = load_retrieval_weights()
        threshold = weights.get("relation_extraction", {}).get("confidence_threshold", 0.5)

        entity_names = [e["text"] for e in entities]
        if len(entity_names) < 2:
            return []

        # LLM relation extraction would go here when enabled
        return []

    def process_document(
        self,
        document_id: str,
        chunks: list[dict],
    ) -> int:
        """Process all chunks of a document for entity extraction."""
        total_entities = 0

        for chunk_data in chunks:
            chunk_id = chunk_data["id"]
            content = chunk_data["content"]

            entities = self.extract_entities(document_id, chunk_id, content)
            total_entities += len(entities)

            if self._settings.extract_relations:
                self.extract_relations(document_id, chunk_id, content, entities)

        if self._kuzu and total_entities > 0:
            try:
                for chunk_data in chunks:
                    self._kuzu.add_chunk_node(
                        chunk_data["id"],
                        document_id,
                        chunk_data.get("chunk_index", 0),
                    )
                    self._kuzu.add_contains(document_id, chunk_data["id"])
            except Exception as e:
                logger.error("kuzu_chunk_insert_error", error=str(e))

        logger.info(
            "graph_extracted",
            document_id=document_id[:16],
            entity_count=total_entities,
        )
        return total_entities
