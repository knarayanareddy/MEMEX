"""
MEMEX daemon — orchestrates all pillars.

The daemon:
1. Initializes all stores (SQLite, ChromaDB, KuzuDB)
2. Starts all ingestors
3. Runs the worker pool (ThreadPoolExecutor)
4. Starts the API server
5. Runs scheduled maintenance
6. Performs graceful drain-shutdown on SIGTERM/SIGINT
"""

from __future__ import annotations

import signal
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, Future
from typing import Optional

from .config.settings import Settings, get_settings, DocumentStatus
from .db.sqlite import SQLiteDatabase
from .db.chroma import ChromaStore
from .db.kuzu import KuzuGraph
from .ingest.queue import IngestionQueue
from .ingest.filesystem import FilesystemIngestor
from .ingest.browser import BrowserIngestor
from .ingest.terminal import TerminalIngestor
from .ingest.clipboard import ClipboardIngestor
from .parse.dispatcher import ParserDispatcher
from .index.chunker import SmartChunker
from .index.embedder import Embedder
from .index.graph_extractor import GraphExtractor
from .protect.redactor import Redactor
from .protect.purge import PurgeScheduler
from .observability.logging import get_logger, setup_logging, Timer

logger = get_logger("daemon")


class MEMEXDaemon:
    """Main daemon orchestrating all MEMEX components.

    Shutdown lifecycle:
        SIGTERM/SIGINT → stop accepting new work (close ingestors)
                       → drain in-flight pipeline work (worker pool shutdown)
                       → flush pending SQLite writes
                       → stop API server
                       → exit
    """

    def __init__(self, settings: Optional[Settings] = None):
        self._settings = settings or get_settings()
        self._settings.ensure_directories()
        self._running = False
        self._draining = False

        # Setup logging
        setup_logging(
            log_dir=self._settings.log_path,
            log_level=self._settings.log_level,
        )

        # Initialize stores
        self._sqlite = SQLiteDatabase(settings=self._settings)
        self._chroma = ChromaStore(settings=self._settings)
        self._kuzu = KuzuGraph(settings=self._settings)

        # Initialize queue
        self._queue = IngestionQueue()

        # Pipeline components
        self._parser = ParserDispatcher()
        self._chunker = SmartChunker()
        self._embedder = Embedder(settings=self._settings, chroma=self._chroma)
        self._graph_extractor = GraphExtractor(
            settings=self._settings, kuzu=self._kuzu, sqlite=self._sqlite,
        )
        self._redactor = Redactor()
        self._purge_scheduler = PurgeScheduler(
            settings=self._settings, sqlite=self._sqlite,
        )

        # Ingestors
        self._ingestors: list = []

        # FIX: Real worker pool with ThreadPoolExecutor
        self._executor: Optional[ThreadPoolExecutor] = None
        self._in_flight: int = 0
        self._in_flight_lock = threading.Lock()
        self._drain_event = threading.Event()

    def initialize(self) -> None:
        """Run migrations and initialize stores."""
        logger.info("daemon_initializing")

        self._sqlite.run_migrations()

        try:
            self._chroma.initialize()
        except Exception as e:
            logger.warning("chroma_init_warning", error=str(e))

        try:
            self._kuzu.initialize()
        except Exception as e:
            logger.warning("kuzu_init_warning", error=str(e))

        try:
            self._graph_extractor.initialize()
        except Exception as e:
            logger.warning("graph_init_warning", error=str(e))

        # Register embed model if not present
        active_model = self._sqlite.get_active_model()
        if not active_model:
            self._sqlite.register_embed_model(
                model_name=self._settings.embed_model,
                model_version=self._settings.embed_model_version,
                collection_name=self._settings.active_collection,
            )

        logger.info("daemon_initialized")

    def start_ingestors(self) -> None:
        """Start all ingestor threads."""
        ingestor_configs = [
            ("filesystem", FilesystemIngestor),
            ("browser", BrowserIngestor),
            ("terminal", TerminalIngestor),
            ("clipboard", ClipboardIngestor),
        ]

        for name, cls in ingestor_configs:
            try:
                ingestor = cls(self._queue, settings=self._settings)
                self._ingestors.append(ingestor)
            except Exception as e:
                logger.warning("ingestor_init_error", ingestor=name, error=str(e))

        for ingestor in self._ingestors:
            try:
                ingestor.start()
            except Exception as e:
                logger.error("ingestor_start_error", error=str(e))

    def start_workers(self) -> None:
        """FIX: Start a proper ThreadPoolExecutor for pipeline workers."""
        self._executor = ThreadPoolExecutor(
            max_workers=self._settings.worker_count,
            thread_name_prefix="memex-worker",
        )
        logger.info("workers_started", count=self._settings.worker_count)

        # Submit worker loops
        for i in range(self._settings.worker_count):
            self._executor.submit(self._worker_loop)

    def _worker_loop(self) -> None:
        """Worker loop: dequeue → parse → redact → chunk → embed → graph.

        Respects drain mode: stops accepting new items when draining,
        but finishes any in-flight work.
        """
        while self._running:
            doc = self._queue.get(timeout=1.0)
            if doc is None:
                if self._draining:
                    break
                continue

            with self._in_flight_lock:
                self._in_flight += 1

            try:
                self._process_document(doc)
            except Exception as e:
                logger.error(
                    "pipeline_error",
                    source_type=doc.source_type,
                    source_path=doc.source_path[:100],
                    error=str(e),
                )
            finally:
                with self._in_flight_lock:
                    self._in_flight -= 1
                    if self._draining and self._in_flight == 0:
                        self._drain_event.set()

                self._queue.task_done()

    def _process_document(self, raw_doc) -> None:
        """Process a single document through the full pipeline."""
        source_type = raw_doc.source_type
        source_path = raw_doc.source_path
        checksum = raw_doc.checksum

        with self._sqlite.connection() as conn:
            existing = self._sqlite.get_document_by_checksum(checksum, conn=conn)
            if existing:
                if existing.get("status") in (
                    DocumentStatus.INDEXED.value, DocumentStatus.EMBEDDED.value
                ):
                    logger.debug("document_deduped", checksum=checksum[:16])
                    return
                if existing.get("status") in (
                    DocumentStatus.FAILED.value, DocumentStatus.PARSE_FAILED.value
                ):
                    retry_count = existing.get("retry_count", 0)
                    if retry_count >= 5:
                        return
                    self._sqlite.delete_chunks_for_document(existing["id"], conn=conn)
                    doc_id = existing["id"]
                else:
                    doc_id = existing["id"]
            else:
                doc_id = self._sqlite.insert_document(
                    source_type=source_type,
                    source_path=source_path,
                    raw_content=raw_doc.raw_bytes,
                    checksum=checksum,
                    source_metadata=raw_doc.source_metadata,
                    conn=conn,
                )
                if not doc_id:
                    return

        if not doc_id:
            return

        try:
            # PARSE
            with Timer(logger, "parse_step", document_id=doc_id[:16]):
                parsed = self._parser.parse(
                    document_id=doc_id,
                    raw_bytes=raw_doc.raw_bytes,
                    filename=source_path.split("/")[-1] if "/" in source_path else source_path,
                )

            # REDACT
            parsed.clean_content = self._redactor.redact(parsed.clean_content)

            # Persist parsed content
            self._sqlite.update_document_parsed(
                doc_id=doc_id,
                clean_content=parsed.clean_content,
                content_type=parsed.content_type.value,
                word_count=parsed.word_count,
            )

            # CHUNK
            chunks = self._chunker.chunk(doc_id, parsed.clean_content, parsed.content_type)
            chunk_ids = []

            with self._sqlite.connection() as conn:
                for chunk in chunks:
                    chunk_id = self._sqlite.insert_chunk(
                        document_id=doc_id,
                        content=chunk.content,
                        token_count=chunk.token_count,
                        chunk_index=chunk.chunk_index,
                        total_chunks=chunk.total_chunks,
                        start_char=chunk.start_char,
                        end_char=chunk.end_char,
                        conn=conn,
                    )
                    chunk_ids.append(chunk_id)

            # EMBED
            doc = self._sqlite.get_document(doc_id)
            if doc:
                for chunk_id in chunk_ids:
                    chunk_data = self._sqlite.get_chunk_by_id(chunk_id)
                    if chunk_data:
                        success = self._embedder.embed_and_store(
                            chunk_id=chunk_id,
                            document_id=doc_id,
                            content=chunk_data["content"],
                            source_type=doc["source_type"],
                            source_path=doc["source_path"],
                            captured_at=doc["captured_at"],
                            content_type=doc.get("content_type", "plain"),
                            chunk_index=chunk_data["chunk_index"],
                        )
                        if success:
                            self._sqlite.update_chunk_chroma_id(chunk_id, chunk_id)

            self._sqlite.update_document_embedded(doc_id)

            # GRAPH
            try:
                chunk_records = self._sqlite.get_chunks_for_document(doc_id)
                if doc:
                    self._kuzu.add_document_node(
                        doc_id, doc["source_type"], doc["source_path"], doc["captured_at"]
                    )
                self._graph_extractor.process_document(doc_id, chunk_records)
                self._sqlite.update_document_graphed(doc_id)

                with self._sqlite.connection() as conn:
                    conn.execute(
                        "UPDATE documents SET status = ? WHERE id = ?",
                        (DocumentStatus.INDEXED.value, doc_id),
                    )
            except Exception as e:
                logger.error("graph_step_error", document_id=doc_id[:16], error=str(e))

            logger.info(
                "document_indexed",
                document_id=doc_id[:16],
                source_type=source_type,
                chunks=len(chunk_ids),
            )

        except Exception as e:
            logger.error("process_document_error", document_id=doc_id[:16], error=str(e))
            self._sqlite.update_document_status(doc_id, DocumentStatus.FAILED, error=str(e))
            self._sqlite.increment_retry(doc_id, str(e))

    def start_api(self) -> None:
        """Start the FastAPI server."""
        import uvicorn
        from .api.app import create_app

        app = create_app(
            settings=self._settings,
            sqlite=self._sqlite,
            chroma=self._chroma,
            kuzu=self._kuzu,
        )
        app.state.queue = self._queue

        config = uvicorn.Config(
            app,
            host=self._settings.api_host,
            port=self._settings.api_port,
            log_level="warning",
            access_log=False,
        )
        self._server = uvicorn.Server(config)

        api_thread = threading.Thread(target=self._server.run, daemon=True, name="api-server")
        api_thread.start()
        logger.info("api_server_started", host=self._settings.api_host, port=self._settings.api_port)

    def run(self) -> None:
        """Run the full daemon (blocking) with graceful shutdown."""
        self._running = True
        logger.info("daemon_starting", version="2.0.0")

        def _signal_handler(signum, frame):
            logger.info("shutdown_signal_received", signal=signum)
            self._initiate_drain()

        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)

        self.initialize()
        self.start_workers()
        self.start_ingestors()
        self._purge_scheduler.start()
        self.start_api()

        logger.info("daemon_running")

        try:
            while self._running:
                time.sleep(0.5)
        except KeyboardInterrupt:
            pass

        self._initiate_drain()
        self._complete_shutdown()

    def _initiate_drain(self) -> None:
        """FIX: Graceful drain — stop accepting new work, finish in-flight."""
        if self._draining:
            return
        self._draining = True
        self._running = False

        logger.info("drain_started")

        # Phase 1: Stop ingestors (no new items enter the queue)
        for ingestor in self._ingestors:
            try:
                ingestor.stop()
            except Exception:
                pass
        logger.info("ingestors_stopped")

        # Phase 2: Wait for queue to drain or timeout
        with self._in_flight_lock:
            in_flight = self._in_flight

        if in_flight > 0:
            logger.info("draining_in_flight", count=in_flight)
            # Wait up to 30s for in-flight work to complete
            self._drain_event.wait(timeout=30.0)

        with self._in_flight_lock:
            remaining = self._in_flight

        if remaining > 0:
            logger.warning("drain_timeout", remaining_in_flight=remaining)

        # Phase 3: Shutdown thread pool
        if self._executor:
            self._executor.shutdown(wait=False)
            logger.info("worker_pool_shutdown")

        # Phase 4: Stop purge scheduler
        self._purge_scheduler.stop()

        # Phase 5: Stop API server
        if hasattr(self, "_server"):
            self._server.should_exit = True

        logger.info("drain_complete")

    def _complete_shutdown(self) -> None:
        """Final cleanup after drain."""
        logger.info("daemon_shutdown_complete")
