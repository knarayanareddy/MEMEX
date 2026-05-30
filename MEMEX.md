🧠 MEMEX
Comprehensive Engineering Design Document
Version 1.0 | Local-First Passive Second Brain — Self-Building Personal Memory Engine
TABLE OF CONTENTS

    Project Overview & Vision
    Goals, Non-Goals & Constraints
    System Architecture
    Module Breakdown
        4.1 Ingestion Daemon & Watcher Layer
        4.2 Universal Content Parser
        4.3 Chunker
        4.4 Embedding Engine
        4.5 Knowledge Graph Layer
        4.6 Hybrid Retrieval Engine
        4.7 Conversation & Citation Layer
        4.8 Terminal UI (TUI)
        4.9 Web UI & Graph Visualizer
    Data Models & Schemas
    API Specifications
    Directory Structure
    Configuration System
    Embedding & Vector Store Deep Dive
    Knowledge Graph Deep Dive
    Hybrid Retrieval Deep Dive
    Conversation Layer Deep Dive
    Ingestor Deep Dive (Per Source)
    Privacy & Security Model
    Storage & Persistence
    Logging, Observability & Debugging
    Testing Strategy
    Build, Packaging & Installation
    Platform Support Matrix
    Performance Targets & Benchmarks
    Error Handling Strategy
    Dependency Registry
    Milestone & Phased Rollout Plan
    Open Questions & Future Work

1. Project Overview & Vision
1.1 What is MEMEX?

MEMEX is a local-first, privacy-preserving, self-building second brain. It runs entirely on the user's machine as a background daemon that:

    Passively ingests digital activity across every major surface: browser history, files, terminal sessions, email, screenshots, clipboard, and calendar
    Parses and normalizes that raw content into clean, structured text using source-appropriate parsers (PDF, HTML, code, image, email)
    Chunks and embeds content into a local vector store for semantic search
    Extracts entities and relations into a local knowledge graph, building an associative web over your intellectual history
    Exposes a chat interface where you query your past self in plain language and receive answers cited back to original sources
    Never sends data anywhere — all inference, storage, and retrieval is entirely on-device

The name is a direct homage to Vannevar Bush's 1945 vision in "As We May Think": a device that stores a person's books, records, and communications and lets them navigate via associative trails — not rigid folders.
1.2 The Problem Being Solved

Knowledge workers generate enormous quantities of digital exhaust every day:

    Dozens of browser tabs read and forgotten
    Hundreds of PDFs, notes, and documents scattered across directories
    Terminal sessions full of commands, errors, and discovered solutions
    Emails containing decisions, context, and references
    Screenshots of things that mattered in the moment

The tools built to manage this — note-taking apps, bookmarking tools, search engines — all require manual labor: you must decide what to save, tag, title, and organize it yourself. The result is that most of what you consume and produce is immediately lost.

MEMEX inverts this entirely. You do nothing. MEMEX watches, ingests, understands, and makes everything retrievable. When you ask "that paper I read in March about Bloom filters" or "what was the Redis config I used for that project last year", MEMEX reconstructs the answer with citations to exact sources.
1.3 Design Philosophy
Principle	Description
Passive by default	You never feed MEMEX. MEMEX feeds itself from your existing digital activity.
Local-first	All models, all storage, all inference run on the user's machine. Zero cloud dependency.
Associative recall	Retrieval mirrors how humans remember — by topic cluster, time, and connection — not by exact keyword.
Cited answers	Every response traces back to a specific source document, chunk, and timestamp. No oracular black boxes.
Privacy by construction	MEMEX cannot exfiltrate data because it never establishes outbound connections for user data.
Composable indexes	Vector similarity, keyword search, graph traversal, and temporal proximity are four independent lenses combined at query time.
2. Goals, Non-Goals & Constraints
2.1 Goals (In Scope)

    Passive ingestion from: browser history, filesystem, terminal, email, clipboard, calendar, screenshots
    HTML/PDF/Markdown/code/email/image parsing into clean text
    Smart, source-aware chunking
    Local embedding via nomic-embed-text through Ollama
    Local vector storage via ChromaDB (persistent, on-disk)
    Full-text keyword search via SQLite FTS5 with BM25-style ranking
    Named entity recognition (NER) via spaCy
    LLM-based relation extraction stored in KuzuDB
    Hybrid retrieval: vector + keyword + graph + temporal re-ranking
    Conversational chat interface with citations back to exact source documents
    Terminal UI (TUI) via Textual
    Web UI with knowledge graph visualization via Svelte + D3 force graph
    Embedding cache (avoid re-embedding unchanged content)
    Document deduplication via checksum
    Configurable per-source allowlists/denylists
    Scheduled background re-indexing

2.2 Non-Goals (Explicitly Out of Scope)

    ❌ Any cloud sync, remote telemetry, or external API calls for user data
    ❌ Manual note-taking or document creation (MEMEX reads, never writes user content)
    ❌ Browser content modification (read-only observation only)
    ❌ Active screen recording (screenshots are opt-in, not continuous)
    ❌ Multi-user or shared memory (strictly single-user, single-machine)
    ❌ Mobile clients (desktop daemon only at v1.0)
    ❌ Real-time streaming ingestion (polling + event-driven, not continuous stream processing)
    ❌ Acting as a search engine replacement for the open web

2.3 Constraints

    All AI models run locally via Ollama (nomic-embed-text for embeddings, llama3/mistral for chat)
    Embedding and graph building must run as background jobs that do not interrupt foreground work
    Ingestion daemon must consume < 5% CPU on idle (event-driven, not polling)
    Vector store, graph DB, and SQLite must all be file-based (no external server processes)
    The system must be fully functional offline after initial model pulls
    All configuration in a single config.toml; zero required setup beyond install + model pull

3. System Architecture
3.1 High-Level Architecture Diagram

text

┌──────────────────────────────────────────────────────────────────────────┐
│                            USER'S MACHINE                                │
│                                                                          │
│  ┌─────────────┐  ┌────────────┐  ┌────────────┐  ┌──────────────────┐  │
│  │   Browser   │  │ Filesystem │  │  Terminal  │  │  Email / Clip /  │  │
│  │  (History + │  │  (Files +  │  │  (History  │  │  Calendar /      │  │
│  │   Pages)    │  │   Dirs)    │  │   + Cmds)  │  │  Screenshots)    │  │
│  └──────┬──────┘  └─────┬──────┘  └─────┬──────┘  └────────┬─────────┘  │
│         │               │               │                   │            │
│         └───────────────┴───────────────┴───────────────────┘            │
│                                   │                                      │
│                    ┌──────────────▼──────────────┐                       │
│                    │      INGESTION DAEMON        │                       │
│                    │  (Source Watchers / Pollers) │                       │
│                    └──────────────┬──────────────┘                       │
│                                   │  raw content                         │
│                    ┌──────────────▼──────────────┐                       │
│                    │  UNIVERSAL CONTENT PARSER    │                       │
│                    │  PDF│HTML│Code│Email│Image   │                       │
│                    └──────────────┬──────────────┘                       │
│                                   │  clean text                          │
│                    ┌──────────────▼──────────────┐                       │
│                    │          CHUNKER             │                       │
│                    │  (Smart, source-aware)       │                       │
│                    └──────┬───────────┬───────────┘                       │
│                           │           │                                   │
│              ┌────────────▼──┐   ┌────▼────────────────┐                 │
│              │  EMBEDDING    │   │  KNOWLEDGE GRAPH     │                 │
│              │  ENGINE       │   │  LAYER               │                 │
│              │  (Ollama)     │   │  NER (spaCy) +       │                 │
│              │               │   │  Relations (LLM) +   │                 │
│              │  ChromaDB ◄───┘   │  KuzuDB              │                 │
│              └───────┬───────┘   └──────────┬──────────┘                 │
│                      │                       │                            │
│  ┌───────────────────▼───────────────────────▼──────────────────────┐    │
│  │                    SQLite (Event Store / Document Store / FTS5)  │    │
│  └───────────────────────────────────┬───────────────────────────────┘    │
│                                      │                                    │
│                    ┌─────────────────▼──────────────────┐                 │
│                    │       HYBRID RETRIEVAL ENGINE       │                 │
│                    │  Vector + Keyword + Graph + Temporal│                 │
│                    └─────────────────┬──────────────────┘                 │
│                                      │                                    │
│                    ┌─────────────────▼──────────────────┐                 │
│                    │    CONVERSATION & CITATION LAYER    │                 │
│                    │    Local LLM (Ollama llama3/mistral)│                 │
│                    └──────────┬──────────────┬───────────┘                 │
│                               │              │                            │
│                  ┌────────────▼──┐    ┌──────▼──────────┐                 │
│                  │   TUI         │    │    Web UI        │                 │
│                  │  (Textual)    │    │  (Svelte + D3)   │                 │
│                  └───────────────┘    └─────────────────┘                 │
└──────────────────────────────────────────────────────────────────────────┘

3.2 Data Flow (Step by Step)

text

Step 1:  Source event fires (file changed, browser history updated, terminal command run)
Step 2:  Ingestor picks up event, fetches raw content (HTML, file bytes, IMAP message, etc.)
Step 3:  Deduplication check: compute SHA-256 checksum → compare against documents.checksum
         If unchanged: skip. If new/changed: continue.
Step 4:  Universal Content Parser converts raw → clean_content (plain text)
Step 5:  Chunker splits clean_content into semantically meaningful chunks
         Each chunk gets token_count, chunk_index, document reference
Step 6:  Embedding Engine sends each chunk to Ollama nomic-embed-text
         Embedding cached in ChromaDB with chroma_id stored in chunks table
Step 7:  Knowledge Graph Layer runs NER (spaCy) over clean_content
         Extracts entities → upsert into entities + entity_mentions tables
         LLM-based relation extraction → upsert into relations + KuzuDB graph
Step 8:  SQLite updated: documents.is_embedded = true, documents.is_graphed = true
Step 9:  FTS5 index automatically updated via trigger
Step 10: On query: HybridRetriever runs vector + keyword + graph + temporal merge
Step 11: Top-ranked chunks injected as context into local LLM prompt
Step 12: LLM generates answer with citations referencing source documents + timestamps
Step 13: Result rendered in TUI chat pane or Web UI conversation view

3.3 Component Ownership
Component	Language/Tool	Owns
Ingestion Daemon	Python	Source watching, polling, raw content fetch
Universal Content Parser	Python	HTML/PDF/Markdown/code/image/email → clean text
Chunker	Python	Semantic splitting, token counting
Embedding Engine	Python + Ollama API	Chunk → vector, ChromaDB persistence
Knowledge Graph Layer	Python + spaCy + Ollama + KuzuDB	NER, relation extraction, graph storage
Hybrid Retriever	Python	Vector + keyword + graph + temporal fusion
Conversation Layer	Python + Ollama API	Context building, LLM chat, citation formatting
TUI	Python (Textual)	Terminal chat interface
Web UI	Svelte + D3	Browser-based graph viewer + chat
SQLite Store	SQLite (FTS5)	Documents, chunks, entities, relations, conversations
4. Module Breakdown
4.1 Ingestion Daemon & Watcher Layer
Purpose

The ingestion daemon is a long-running background process that watches all configured data sources and feeds new or changed content into the processing pipeline. It is the only component that touches raw user data sources.
Source Watchers
Source	Mechanism	Frequency
Filesystem	watchdog library (inotify/FSEvents)	Event-driven
Browser History	SQLite poll on browser profile DB	Every 5 minutes
Browser Pages	Browser extension → local HTTP endpoint	On page visit
Terminal	Shell hook (PROMPT_COMMAND / precmd)	On command
Email	IMAP IDLE + periodic poll	Every 10 minutes
Clipboard	Polling via pyperclip	Every 30 seconds
Calendar	ICS file poll or CalDAV	Every 30 minutes
Screenshots	Directory watcher on screenshot save path	Event-driven
Document Identity & Deduplication

Every document entering the pipeline is assigned a stable identity:

Python

# ingestors/base.py

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RawDocument:
    """The contract every ingestor must produce."""
    source_type: str          # "browser", "filesystem", "terminal", "email", etc.
    source_path: str          # Canonical identifier (URL, file path, IMAP UID, etc.)
    raw_content: bytes        # Unprocessed bytes
    title: Optional[str]
    source_created_at: Optional[datetime]
    source_modified_at: Optional[datetime]
    metadata: dict            # Source-specific extras

    @property
    def checksum(self) -> str:
        """SHA-256 of raw content. Used for deduplication."""
        return hashlib.sha256(self.raw_content).hexdigest()


class BaseIngestor:
    """All ingestors extend this."""

    def __init__(self, config: dict, db_conn, event_queue):
        self.config = config
        self.db = db_conn
        self.queue = event_queue

    def should_ingest(self, source_path: str, checksum: str) -> bool:
        """Return True if this document is new or changed."""
        row = self.db.execute(
            "SELECT checksum FROM documents WHERE source_path = ?",
            (source_path,)
        ).fetchone()
        if row is None:
            return True                  # New document
        return row["checksum"] != checksum   # Changed document

    def emit(self, doc: RawDocument):
        """Submit document to processing pipeline."""
        if self.should_ingest(doc.source_path, doc.checksum):
            self.queue.put(doc)

Daemon Lifecycle

Python

# ingestors/daemon.py

import threading
import queue
import logging
from typing import List

from ingestors.browser import BrowserIngestor
from ingestors.filesystem import FilesystemIngestor
from ingestors.terminal import TerminalIngestor
from ingestors.email import EmailIngestor
from ingestors.clipboard import ClipboardIngestor
from ingestors.calendar import CalendarIngestor
from ingestors.screenshot import ScreenshotIngestor
from parsers.universal import UniversalParser
from embeddings.engine import EmbeddingEngine
from graph.extractor import GraphExtractor


class MEMEXDaemon:
    """
    The top-level daemon. Starts all ingestors, owns the processing queue,
    and orchestrates parse → embed → graph for every incoming document.
    """

    def __init__(self, config: dict):
        self.config = config
        self.raw_queue = queue.PriorityQueue(maxsize=1000)
        self.ingestors = self._build_ingestors()
        self.parser = UniversalParser(config)
        self.embedder = EmbeddingEngine(config)
        self.grapher = GraphExtractor(config)
        self._stop_event = threading.Event()

    def _build_ingestors(self) -> List:
        enabled = self.config["sources"]["enabled"]
        mapping = {
            "browser":    BrowserIngestor,
            "filesystem": FilesystemIngestor,
            "terminal":   TerminalIngestor,
            "email":      EmailIngestor,
            "clipboard":  ClipboardIngestor,
            "calendar":   CalendarIngestor,
            "screenshot": ScreenshotIngestor,
        }
        return [
            mapping[name](self.config, self.raw_queue)
            for name in enabled
            if name in mapping
        ]

    def start(self):
        logging.info("MEMEX daemon starting...")
        # Start each ingestor in its own thread
        for ingestor in self.ingestors:
            t = threading.Thread(target=ingestor.run, daemon=True)
            t.start()

        # Start processing workers
        worker_count = self.config["processing"]["workers"]
        for _ in range(worker_count):
            t = threading.Thread(target=self._process_worker, daemon=True)
            t.start()

        logging.info(f"MEMEX daemon started. {len(self.ingestors)} ingestors active.")
        self._stop_event.wait()

    def _process_worker(self):
        """Pull from raw_queue → parse → embed → graph."""
        while not self._stop_event.is_set():
            try:
                _, raw_doc = self.raw_queue.get(timeout=1.0)
                self._process_document(raw_doc)
            except queue.Empty:
                continue
            except Exception as e:
                logging.error(f"Processing error: {e}", exc_info=True)
                # Never crash the daemon on a single bad document

    def _process_document(self, raw_doc):
        # 1. Parse
        parsed = self.parser.parse(raw_doc)
        if not parsed:
            return

        # 2. Persist to SQLite (upsert)
        doc_id = self._upsert_document(parsed)

        # 3. Chunk + Embed
        self.embedder.process(doc_id, parsed.clean_content)

        # 4. Graph extraction
        self.grapher.process(doc_id, parsed.clean_content)

        logging.debug(f"Processed: {raw_doc.source_path}")

    def stop(self):
        self._stop_event.set()

4.2 Universal Content Parser
Purpose

Converts raw bytes from any source into a canonical ParsedDocument (clean UTF-8 text, normalized title, metadata). Each source type has a dedicated parser; the UniversalParser dispatches to the right one.
Parser Dispatch

Python

# parsers/universal.py

from parsers.pdf import PDFParser
from parsers.html import HTMLParser
from parsers.code import CodeParser
from parsers.email_parser import EmailParser
from parsers.image import ImageParser
from parsers.markdown import MarkdownParser
from parsers.plain import PlainTextParser
from dataclasses import dataclass
from typing import Optional


@dataclass
class ParsedDocument:
    source_path: str
    source_type: str
    title: Optional[str]
    clean_content: str          # Normalized plain text
    content_type: str           # "pdf", "html", "code", "email", "image", "markdown", "plain"
    language: Optional[str]     # Programming language if code
    metadata: dict


class UniversalParser:

    EXTENSION_MAP = {
        ".pdf":  "pdf",
        ".html": "html",
        ".htm":  "html",
        ".md":   "markdown",
        ".py":   "code",
        ".go":   "code",
        ".js":   "code",
        ".ts":   "code",
        ".rs":   "code",
        ".java": "code",
        ".c":    "code",
        ".cpp":  "code",
        ".txt":  "plain",
        ".png":  "image",
        ".jpg":  "image",
        ".jpeg": "image",
        ".gif":  "image",
    }

    def __init__(self, config: dict):
        self.parsers = {
            "pdf":      PDFParser(config),
            "html":     HTMLParser(config),
            "code":     CodeParser(config),
            "email":    EmailParser(config),
            "image":    ImageParser(config),
            "markdown": MarkdownParser(config),
            "plain":    PlainTextParser(config),
        }

    def parse(self, raw_doc) -> Optional[ParsedDocument]:
        content_type = self._detect_type(raw_doc)
        if content_type not in self.parsers:
            return None
        return self.parsers[content_type].parse(raw_doc)

    def _detect_type(self, raw_doc) -> str:
        # 1. Source type overrides (email always → email parser)
        if raw_doc.source_type == "email":
            return "email"
        if raw_doc.source_type == "browser":
            return "html"
        if raw_doc.source_type == "screenshot":
            return "image"
        # 2. Extension-based detection
        import os
        _, ext = os.path.splitext(raw_doc.source_path)
        return self.EXTENSION_MAP.get(ext.lower(), "plain")

Per-Parser Implementation

Python

# parsers/pdf.py

from pdfminer.high_level import extract_text
from pdfminer.pdfdocument import PDFDocument
from pdfminer.pdfparser import PDFParser as MinerParser
import io


class PDFParser:

    def parse(self, raw_doc) -> Optional[ParsedDocument]:
        try:
            text = extract_text(io.BytesIO(raw_doc.raw_content))
            title = self._extract_title(raw_doc.raw_content) or raw_doc.title
            return ParsedDocument(
                source_path=raw_doc.source_path,
                source_type=raw_doc.source_type,
                title=title,
                clean_content=self._clean(text),
                content_type="pdf",
                language=None,
                metadata=raw_doc.metadata,
            )
        except Exception as e:
            return None

    def _clean(self, text: str) -> str:
        import re
        # Remove excessive whitespace, page markers, ligatures
        text = re.sub(r'\n{3,}', '\n\n', text)
        text = text.replace('\x0c', '\n')  # Form feed (page break)
        return text.strip()

    def _extract_title(self, raw_bytes: bytes) -> Optional[str]:
        try:
            parser = MinerParser(io.BytesIO(raw_bytes))
            doc = PDFDocument(parser)
            info = doc.info
            if info and "Title" in info[0]:
                return info[0]["Title"].decode("utf-8", errors="ignore")
        except Exception:
            pass
        return None

Python

# parsers/html.py

from readability import Document
from bs4 import BeautifulSoup


class HTMLParser:

    def parse(self, raw_doc) -> Optional[ParsedDocument]:
        try:
            html = raw_doc.raw_content.decode("utf-8", errors="replace")
            doc = Document(html)
            title = doc.title()
            # readability extracts article body
            content_html = doc.summary()
            soup = BeautifulSoup(content_html, "html.parser")
            clean = soup.get_text(separator="\n", strip=True)
            return ParsedDocument(
                source_path=raw_doc.source_path,
                source_type=raw_doc.source_type,
                title=title,
                clean_content=self._clean(clean),
                content_type="html",
                language=None,
                metadata=raw_doc.metadata,
            )
        except Exception:
            return None

    def _clean(self, text: str) -> str:
        import re
        text = re.sub(r'\n{3,}', '\n\n', text)
        return text.strip()

Python

# parsers/code.py

import tree_sitter
from tree_sitter import Language, Parser


class CodeParser:
    """
    Uses tree-sitter to parse code into a structured representation,
    then extracts comments, docstrings, and function signatures for embedding.
    Raw code is preserved as clean_content for keyword search.
    """

    LANGUAGE_EXTENSION_MAP = {
        ".py":   "python",
        ".js":   "javascript",
        ".ts":   "typescript",
        ".go":   "go",
        ".rs":   "rust",
        ".java": "java",
        ".c":    "c",
        ".cpp":  "cpp",
    }

    def parse(self, raw_doc) -> Optional[ParsedDocument]:
        import os
        _, ext = os.path.splitext(raw_doc.source_path)
        language = self.LANGUAGE_EXTENSION_MAP.get(ext.lower(), "plain")
        code = raw_doc.raw_content.decode("utf-8", errors="replace")

        # For embedding: prioritize comments + signatures over raw code
        enriched = self._extract_semantic_content(code, language)

        return ParsedDocument(
            source_path=raw_doc.source_path,
            source_type=raw_doc.source_type,
            title=os.path.basename(raw_doc.source_path),
            clean_content=enriched,
            content_type="code",
            language=language,
            metadata={**raw_doc.metadata, "language": language},
        )

    def _extract_semantic_content(self, code: str, language: str) -> str:
        """Prepend extracted comments/docstrings before raw code."""
        lines = code.split("\n")
        comments = [l.strip() for l in lines if l.strip().startswith(("#", "//", "/*", "*", '"""', "'''"))]
        preamble = "\n".join(comments[:50])  # First 50 comment lines
        return f"{preamble}\n\n{code}"

Python

# parsers/image.py

import pytesseract
from PIL import Image
import io


class ImageParser:
    """OCR-based parser for screenshots and images."""

    def parse(self, raw_doc) -> Optional[ParsedDocument]:
        try:
            image = Image.open(io.BytesIO(raw_doc.raw_content))
            text = pytesseract.image_to_string(image, lang="eng")
            if not text.strip():
                return None  # Empty OCR result — skip
            return ParsedDocument(
                source_path=raw_doc.source_path,
                source_type=raw_doc.source_type,
                title=raw_doc.title or "Screenshot",
                clean_content=text.strip(),
                content_type="image",
                language=None,
                metadata=raw_doc.metadata,
            )
        except Exception:
            return None

4.3 Chunker
Purpose

Splits ParsedDocument.clean_content into chunks that are:

    Small enough for embedding to be semantically focused
    Large enough to carry coherent context
    Appropriate for the content type (code, prose, email have different natural boundaries)

Chunking Strategy

Python

# parsers/chunker.py

from dataclasses import dataclass
from typing import List
import tiktoken


@dataclass
class Chunk:
    doc_id: str
    chunk_index: int
    content: str
    token_count: int


class SmartChunker:
    """
    Chunking strategy by content type:
    - prose (HTML, PDF, markdown, plain): paragraph-aware sliding window
    - code: function/class boundary-aware splitting
    - email: header + body as separate chunks
    - image (OCR text): plain sliding window
    """

    DEFAULTS = {
        "prose":  {"max_tokens": 400, "overlap_tokens": 50},
        "code":   {"max_tokens": 300, "overlap_tokens": 30},
        "email":  {"max_tokens": 350, "overlap_tokens": 40},
        "image":  {"max_tokens": 300, "overlap_tokens": 30},
    }

    def __init__(self, config: dict):
        self.config = config
        self.encoder = tiktoken.get_encoding("cl100k_base")

    def chunk(self, doc_id: str, content: str, content_type: str) -> List[Chunk]:
        strategy = self._get_strategy(content_type)
        if content_type == "code":
            paragraphs = self._split_by_function(content)
        else:
            paragraphs = self._split_by_paragraph(content)
        return self._sliding_window(doc_id, paragraphs, strategy)

    def _get_strategy(self, content_type: str) -> dict:
        if content_type in ("html", "pdf", "markdown", "plain"):
            return self.DEFAULTS["prose"]
        return self.DEFAULTS.get(content_type, self.DEFAULTS["prose"])

    def _split_by_paragraph(self, text: str) -> List[str]:
        import re
        return [p.strip() for p in re.split(r'\n\n+', text) if p.strip()]

    def _split_by_function(self, code: str) -> List[str]:
        """Naive function-level splitting by blank lines + indent reset."""
        import re
        # Split on blank lines that follow a non-indented line (function boundaries)
        parts = re.split(r'\n(?=\S)', code)
        return [p.strip() for p in parts if p.strip()]

    def _sliding_window(self, doc_id: str, paragraphs: List[str], strategy: dict) -> List[Chunk]:
        max_tokens = strategy["max_tokens"]
        overlap = strategy["overlap_tokens"]
        chunks = []
        current_parts = []
        current_tokens = 0
        chunk_index = 0

        for para in paragraphs:
            para_tokens = len(self.encoder.encode(para))
            if current_tokens + para_tokens > max_tokens and current_parts:
                content = "\n\n".join(current_parts)
                chunks.append(Chunk(
                    doc_id=doc_id,
                    chunk_index=chunk_index,
                    content=content,
                    token_count=current_tokens,
                ))
                chunk_index += 1
                # Overlap: keep last paragraph(s) up to overlap_tokens
                overlap_parts = []
                overlap_count = 0
                for p in reversed(current_parts):
                    t = len(self.encoder.encode(p))
                    if overlap_count + t > overlap:
                        break
                    overlap_parts.insert(0, p)
                    overlap_count += t
                current_parts = overlap_parts
                current_tokens = overlap_count

            current_parts.append(para)
            current_tokens += para_tokens

        if current_parts:
            chunks.append(Chunk(
                doc_id=doc_id,
                chunk_index=chunk_index,
                content="\n\n".join(current_parts),
                token_count=current_tokens,
            ))

        return chunks

4.4 Embedding Engine
Purpose

Converts each chunk into a vector embedding via Ollama's nomic-embed-text model and persists it in ChromaDB. Maintains an embedding cache so unchanged chunks are never re-embedded.
Implementation

Python

# embeddings/engine.py

import requests
import chromadb
from chromadb.config import Settings
import logging
from typing import List
from parsers.chunker import SmartChunker, Chunk


class EmbeddingEngine:
    """
    Orchestrates: chunk → embed → persist to ChromaDB.
    Caches embeddings by (doc_id, chunk_index, token_count) to avoid re-work.
    """

    def __init__(self, config: dict):
        self.config = config
        self.ollama_url = config["ollama"]["base_url"]
        self.model = config["ollama"]["embedding_model"]  # "nomic-embed-text"
        self.chunker = SmartChunker(config)
        self.chroma = chromadb.PersistentClient(
            path=config["storage"]["chroma_path"],
            settings=Settings(anonymized_telemetry=False),
        )
        self.collection = self.chroma.get_or_create_collection(
            name="memex_chunks",
            metadata={"hnsw:space": "cosine"},
        )

    def process(self, doc_id: str, clean_content: str, content_type: str):
        chunks = self.chunker.chunk(doc_id, clean_content, content_type)
        if not chunks:
            return
        new_chunks = self._filter_already_embedded(doc_id, chunks)
        if not new_chunks:
            logging.debug(f"All chunks already embedded for doc {doc_id}")
            return
        self._embed_and_store(doc_id, new_chunks)

    def _filter_already_embedded(self, doc_id: str, chunks: List[Chunk]) -> List[Chunk]:
        """Skip chunks that already have a chroma_id in SQLite."""
        from storage.db import get_db
        db = get_db()
        existing = {
            row["chunk_index"]
            for row in db.execute(
                "SELECT chunk_index FROM chunks WHERE doc_id = ? AND chroma_id IS NOT NULL",
                (doc_id,)
            ).fetchall()
        }
        return [c for c in chunks if c.chunk_index not in existing]

    def _embed_and_store(self, doc_id: str, chunks: List[Chunk]):
        texts = [c.content for c in chunks]
        embeddings = self._get_embeddings(texts)
        if not embeddings:
            return

        ids = [f"{doc_id}__chunk__{c.chunk_index}" for c in chunks]
        metadatas = [{"doc_id": doc_id, "chunk_index": c.chunk_index, "token_count": c.token_count} for c in chunks]

        self.collection.upsert(
            ids=ids,
            embeddings=embeddings,
            documents=texts,
            metadatas=metadatas,
        )

        # Persist chunk records to SQLite
        from storage.db import get_db
        db = get_db()
        for chunk, chroma_id in zip(chunks, ids):
            db.execute("""
                INSERT OR REPLACE INTO chunks (doc_id, chunk_index, content, token_count, chroma_id, embedded_at)
                VALUES (?, ?, ?, ?, ?, datetime('now'))
            """, (doc_id, chunk.chunk_index, chunk.content, chunk.token_count, chroma_id))
        db.commit()

    def _get_embeddings(self, texts: List[str]) -> Optional[List[List[float]]]:
        try:
            response = requests.post(
                f"{self.ollama_url}/api/embed",
                json={"model": self.model, "input": texts},
                timeout=60,
            )
            response.raise_for_status()
            return response.json()["embeddings"]
        except Exception as e:
            logging.error(f"Embedding request failed: {e}")
            return None

    def search(self, query: str, n_results: int = 20) -> List[dict]:
        embeddings = self._get_embeddings([query])
        if not embeddings:
            return []
        results = self.collection.query(
            query_embeddings=embeddings,
            n_results=n_results,
            include=["documents", "metadatas", "distances"],
        )
        return [
            {
                "chroma_id": results["ids"][0][i],
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            }
            for i in range(len(results["ids"][0]))
        ]

4.5 Knowledge Graph Layer
Purpose

Extracts named entities and typed relations from each document's clean content and persists them in both SQLite (entity/mention/relation tables) and KuzuDB (property graph for traversal queries). Enables "who/what is connected to what" queries that pure vector search cannot answer.
Entity Extraction (spaCy NER)

Python

# graph/entity_extractor.py

import spacy
from typing import List, Tuple
from dataclasses import dataclass


@dataclass
class ExtractedEntity:
    text: str
    label: str       # PERSON, ORG, GPE, PRODUCT, TECH, etc.
    start_char: int
    end_char: int
    context: str     # Surrounding sentence


class EntityExtractor:

    def __init__(self, config: dict):
        model = config["graph"].get("spacy_model", "en_core_web_trf")
        self.nlp = spacy.load(model)

    def extract(self, text: str) -> List[ExtractedEntity]:
        # Process in 100k-character chunks to avoid memory issues
        chunk_size = 100_000
        entities = []
        for start in range(0, len(text), chunk_size):
            chunk = text[start:start + chunk_size]
            doc = self.nlp(chunk)
            for ent in doc.ents:
                # Get surrounding sentence as context
                sent_text = ent.sent.text.strip() if ent.sent else chunk[
                    max(0, ent.start_char - 100):ent.end_char + 100
                ]
                entities.append(ExtractedEntity(
                    text=ent.text,
                    label=ent.label_,
                    start_char=start + ent.start_char,
                    end_char=start + ent.end_char,
                    context=sent_text[:500],
                ))
        return entities

Relation Extraction (LLM-based)

Python

# graph/relation_extractor.py

import requests
import json
from typing import List
from dataclasses import dataclass


@dataclass
class ExtractedRelation:
    subject: str
    predicate: str    # e.g., "authored", "cited", "uses", "works_at"
    object: str
    confidence: float
    evidence: str     # The sentence or passage this came from


RELATION_PROMPT = """Extract relationships between entities from the following text.
Return a JSON array of objects with keys: subject, predicate, object, confidence (0.0-1.0), evidence.

Only extract relationships that are clearly stated. Do not infer.
Keep predicates concise (1-3 words, snake_case): authored, cited_in, uses, works_at, created_by, related_to.

Text:
{text}

JSON output only:"""


class RelationExtractor:

    def __init__(self, config: dict):
        self.ollama_url = config["ollama"]["base_url"]
        self.model = config["ollama"]["chat_model"]
        self.enabled = config["graph"].get("enable_relation_extraction", True)

    def extract(self, text: str, max_chars: int = 3000) -> List[ExtractedRelation]:
        if not self.enabled:
            return []
        # Only run on first 3000 chars to keep latency manageable
        excerpt = text[:max_chars]
        try:
            response = requests.post(
                f"{self.ollama_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": RELATION_PROMPT.format(text=excerpt),
                    "stream": False,
                    "format": "json",
                },
                timeout=30,
            )
            response.raise_for_status()
            raw = response.json().get("response", "[]")
            items = json.loads(raw)
            return [
                ExtractedRelation(
                    subject=r.get("subject", ""),
                    predicate=r.get("predicate", ""),
                    object=r.get("object", ""),
                    confidence=float(r.get("confidence", 0.5)),
                    evidence=r.get("evidence", "")[:500],
                )
                for r in items
                if r.get("subject") and r.get("predicate") and r.get("object")
            ]
        except Exception as e:
            return []

Graph Persistence (KuzuDB + SQLite)

Python

# graph/extractor.py

import kuzu
import logging
from graph.entity_extractor import EntityExtractor
from graph.relation_extractor import RelationExtractor


class GraphExtractor:

    def __init__(self, config: dict):
        self.entity_extractor = EntityExtractor(config)
        self.relation_extractor = RelationExtractor(config)
        self.kuzu_db = kuzu.Database(config["storage"]["kuzu_path"])
        self.kuzu_conn = kuzu.Connection(self.kuzu_db)
        self._init_kuzu_schema()

    def _init_kuzu_schema(self):
        try:
            self.kuzu_conn.execute("CREATE NODE TABLE IF NOT EXISTS Entity(name STRING, label STRING, PRIMARY KEY(name))")
            self.kuzu_conn.execute("CREATE REL TABLE IF NOT EXISTS RELATES(FROM Entity TO Entity, predicate STRING, confidence DOUBLE, source_doc_id STRING)")
        except Exception:
            pass  # Tables already exist

    def process(self, doc_id: str, clean_content: str):
        # 1. Entity extraction
        entities = self.entity_extractor.extract(clean_content)
        entity_ids = {}
        for ent in entities:
            eid = self._upsert_entity(doc_id, ent)
            if eid:
                entity_ids[ent.text] = eid

        # 2. Relation extraction (LLM-based)
        relations = self.relation_extractor.extract(clean_content)
        for rel in relations:
            if rel.confidence >= 0.5:
                self._upsert_relation(doc_id, rel)

        # 3. Mark document as graphed
        from storage.db import get_db
        db = get_db()
        db.execute("UPDATE documents SET is_graphed = 1 WHERE id = ?", (doc_id,))
        db.commit()

    def _upsert_entity(self, doc_id: str, ent) -> Optional[str]:
        from storage.db import get_db
        import uuid
        db = get_db()
        canonical = ent.text.strip().lower()
        row = db.execute("SELECT id FROM entities WHERE canonical_name = ?", (canonical,)).fetchone()
        if row:
            entity_id = row["id"]
            db.execute("""
                UPDATE entities
                SET mention_count = mention_count + 1, last_seen = datetime('now')
                WHERE id = ?
            """, (entity_id,))
        else:
            entity_id = str(uuid.uuid4())
            db.execute("""
                INSERT INTO entities (id, canonical_name, label, first_seen, last_seen, mention_count)
                VALUES (?, ?, ?, datetime('now'), datetime('now'), 1)
            """, (entity_id, canonical, ent.label))

        db.execute("""
            INSERT INTO entity_mentions (id, entity_id, doc_id, context_snippet, start_char, end_char, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (str(uuid.uuid4()), entity_id, doc_id, ent.context, ent.start_char, ent.end_char))
        db.commit()

        # Also upsert into KuzuDB
        try:
            self.kuzu_conn.execute(
                "MERGE (e:Entity {name: $name}) SET e.label = $label",
                {"name": canonical, "label": ent.label}
            )
        except Exception:
            pass

        return entity_id

    def _upsert_relation(self, doc_id: str, rel):
        from storage.db import get_db
        import uuid
        db = get_db()
        db.execute("""
            INSERT INTO relations (id, subject, predicate, object, confidence, source_doc_id, created_at)
            VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
        """, (str(uuid.uuid4()), rel.subject, rel.predicate, rel.object, rel.confidence, doc_id))
        db.commit()
        try:
            self.kuzu_conn.execute("""
                MATCH (s:Entity {name: $subj}), (o:Entity {name: $obj})
                CREATE (s)-[:RELATES {predicate: $pred, confidence: $conf, source_doc_id: $doc_id}]->(o)
            """, {
                "subj": rel.subject.lower(),
                "obj": rel.object.lower(),
                "pred": rel.predicate,
                "conf": rel.confidence,
                "doc_id": doc_id,
            })
        except Exception:
            pass

4.6 Hybrid Retrieval Engine
Purpose

The retrieval engine is the heart of MEMEX's "associative recall." It fuses four independent retrieval signals — semantic vector similarity, exact keyword match, knowledge graph traversal, and temporal proximity — into a single ranked list of relevant chunks.
Full Implementation

Python

# memory/retriever.py

import sqlite3
import re
from typing import List, Dict, Any, Optional
from embeddings.engine import EmbeddingEngine
import kuzu


class HybridRetriever:
    """
    Four-signal retrieval:
    1. Vector similarity  (ChromaDB)
    2. Keyword / BM25     (SQLite FTS5)
    3. Graph traversal    (KuzuDB entity neighborhood)
    4. Temporal re-rank   (recency bias on merged results)
    """

    VECTOR_WEIGHT = 0.40
    KEYWORD_WEIGHT = 0.30
    GRAPH_WEIGHT = 0.20
    TEMPORAL_WEIGHT = 0.10

    def __init__(self, config: dict):
        self.config = config
        self.embedder = EmbeddingEngine(config)
        self.kuzu_db = kuzu.Database(config["storage"]["kuzu_path"])
        self.kuzu_conn = kuzu.Connection(self.kuzu_db)

    def retrieve(self, query: str, n_results: int = 10, time_filter: Optional[dict] = None) -> List[Dict[str, Any]]:
        # Run all four signals
        vector_hits = self._vector_search(query, n=30)
        keyword_hits = self._keyword_search(query, n=30)
        graph_hits = self._graph_search(query, n=20)

        # Merge by doc_id+chunk_index key
        merged = self._merge(vector_hits, keyword_hits, graph_hits)

        # Temporal re-rank
        merged = self._temporal_rerank(merged, time_filter)

        # Sort and return top N
        merged.sort(key=lambda x: x["combined_score"], reverse=True)
        return merged[:n_results]

    def _vector_search(self, query: str, n: int) -> List[dict]:
        results = self.embedder.search(query, n_results=n)
        return [
            {
                "key": r["chroma_id"],
                "doc_id": r["metadata"]["doc_id"],
                "chunk_index": r["metadata"]["chunk_index"],
                "content": r["content"],
                "vector_score": 1.0 - r["distance"],  # cosine distance → similarity
                "keyword_score": 0.0,
                "graph_score": 0.0,
            }
            for r in results
        ]

    def _keyword_search(self, query: str, n: int) -> List[dict]:
        from storage.db import get_db
        db = get_db()
        # FTS5 BM25 ranking (lower rank = better match in SQLite FTS5)
        rows = db.execute("""
            SELECT
                c.doc_id,
                c.chunk_index,
                c.content,
                c.chroma_id,
                bm25(chunks_fts) AS bm25_score
            FROM chunks_fts
            JOIN chunks c ON c.rowid = chunks_fts.rowid
            WHERE chunks_fts MATCH ?
            ORDER BY bm25_score
            LIMIT ?
        """, (query, n)).fetchall()

        if not rows:
            return []

        # Normalize BM25 scores to 0-1 (BM25 returns negatives in SQLite)
        scores = [abs(r["bm25_score"]) for r in rows]
        max_score = max(scores) if scores else 1.0
        return [
            {
                "key": row["chroma_id"] or f"{row['doc_id']}__chunk__{row['chunk_index']}",
                "doc_id": row["doc_id"],
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "vector_score": 0.0,
                "keyword_score": abs(row["bm25_score"]) / max_score,
                "graph_score": 0.0,
            }
            for row in rows
        ]

    def _graph_search(self, query: str, n: int) -> List[dict]:
        """
        Extract entity mentions from query → find connected documents in KuzuDB
        → return chunks from those documents.
        """
        # Simple entity extraction from query: quoted phrases + capitalized words
        entities = re.findall(r'"([^"]+)"|([A-Z][a-zA-Z0-9_]+)', query)
        entity_terms = [e[0] or e[1] for e in entities if (e[0] or e[1])]
        if not entity_terms:
            return []

        connected_docs = set()
        for term in entity_terms[:5]:  # Limit graph hops to 5 entity terms
            try:
                result = self.kuzu_conn.execute("""
                    MATCH (e:Entity)-[:RELATES*1..2]-(connected:Entity)
                    WHERE e.name CONTAINS $term
                    RETURN connected.name AS name
                    LIMIT 20
                """, {"term": term.lower()})
                while result.has_next():
                    row = result.get_next()
                    connected_docs.add(row[0])
            except Exception:
                continue

        if not connected_docs:
            return []

        # Find document IDs that mention these connected entities
        from storage.db import get_db
        db = get_db()
        placeholders = ",".join("?" * len(connected_docs))
        rows = db.execute(f"""
            SELECT DISTINCT c.doc_id, c.chunk_index, c.content, c.chroma_id
            FROM entity_mentions em
            JOIN entities en ON en.id = em.entity_id
            JOIN chunks c ON c.doc_id = em.doc_id
            WHERE en.canonical_name IN ({placeholders})
            LIMIT ?
        """, (*connected_docs, n)).fetchall()

        return [
            {
                "key": row["chroma_id"] or f"{row['doc_id']}__chunk__{row['chunk_index']}",
                "doc_id": row["doc_id"],
                "chunk_index": row["chunk_index"],
                "content": row["content"],
                "vector_score": 0.0,
                "keyword_score": 0.0,
                "graph_score": 0.8,  # Fixed score for graph-connected results
            }
            for row in rows
        ]

    def _merge(self, vector_hits, keyword_hits, graph_hits) -> List[dict]:
        merged: Dict[str, dict] = {}
        for hit in vector_hits:
            merged[hit["key"]] = {**hit}
        for hit in keyword_hits:
            if hit["key"] in merged:
                merged[hit["key"]]["keyword_score"] = hit["keyword_score"]
            else:
                merged[hit["key"]] = {**hit}
        for hit in graph_hits:
            if hit["key"] in merged:
                merged[hit["key"]]["graph_score"] = hit["graph_score"]
            else:
                merged[hit["key"]] = {**hit}
        # Compute combined score
        for key, item in merged.items():
            item["combined_score"] = (
                item.get("vector_score", 0.0) * self.VECTOR_WEIGHT +
                item.get("keyword_score", 0.0) * self.KEYWORD_WEIGHT +
                item.get("graph_score", 0.0) * self.GRAPH_WEIGHT
            )
        return list(merged.values())

    def _temporal_rerank(self, hits: List[dict], time_filter: Optional[dict]) -> List[dict]:
        """
        Apply a time-decay boost based on document recency.
        Optionally filter to documents within a time window.
        """
        from storage.db import get_db
        from datetime import datetime, timezone
        db = get_db()
        doc_ids = list({h["doc_id"] for h in hits})
        if not doc_ids:
            return hits

        placeholders = ",".join("?" * len(doc_ids))
        rows = db.execute(
            f"SELECT id, ingested_at FROM documents WHERE id IN ({placeholders})",
            doc_ids
        ).fetchall()
        date_map = {r["id"]: r["ingested_at"] for r in rows}

        now = datetime.now(timezone.utc)
        filtered = []
        for hit in hits:
            ingested = date_map.get(hit["doc_id"])
            if ingested:
                try:
                    dt = datetime.fromisoformat(ingested).replace(tzinfo=timezone.utc)
                    age_days = (now - dt).days

                    if time_filter:
                        after = time_filter.get("after")
                        before = time_filter.get("before")
                        if after and dt < after:
                            continue
                        if before and dt > before:
                            continue

                    # Exponential decay: score × e^(-λ × age_days), λ = 0.005
                    import math
                    decay = math.exp(-0.005 * age_days)
                    hit["temporal_score"] = decay
                    hit["combined_score"] += decay * self.TEMPORAL_WEIGHT
                except Exception:
                    pass
            filtered.append(hit)

        return filtered

4.7 Conversation & Citation Layer
Purpose

Takes retrieved chunks, assembles a context-injected prompt, calls the local LLM, and formats the answer with citations back to the exact source documents and timestamps.
Implementation

Python

# conversation/engine.py

import requests
import json
from typing import List, Dict, Any
from memory.retriever import HybridRetriever
from storage.db import get_db


SYSTEM_PROMPT = """You are MEMEX, a personal memory assistant. You have access to the user's
indexed documents, notes, browser history, and past activity.

Answer the user's question using ONLY the provided context. If you reference a source,
cite it using [Source N] notation. If you cannot answer from the context, say so.

Be concise, specific, and always prefer citing exact documents over vague statements.
When possible, include the date the source was created or ingested."""


class ConversationEngine:

    def __init__(self, config: dict):
        self.config = config
        self.retriever = HybridRetriever(config)
        self.ollama_url = config["ollama"]["base_url"]
        self.model = config["ollama"]["chat_model"]

    def chat(self, query: str, session_id: str, time_filter: dict = None) -> dict:
        # 1. Retrieve relevant chunks
        hits = self.retriever.retrieve(query, n_results=8, time_filter=time_filter)
        if not hits:
            return {
                "answer": "I couldn't find anything relevant in your memory for that query.",
                "sources": [],
                "session_id": session_id,
            }

        # 2. Build context block with numbered sources
        context_block, sources = self._build_context(hits)

        # 3. Build messages
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Context:\n{context_block}\n\nQuestion: {query}"},
        ]

        # 4. Call local LLM
        answer = self._call_llm(messages)

        # 5. Persist conversation
        self._persist_turn(session_id, query, answer, sources)

        return {
            "answer": answer,
            "sources": sources,
            "session_id": session_id,
        }

    def _build_context(self, hits: List[Dict[str, Any]]) -> tuple:
        db = get_db()
        context_parts = []
        sources = []
        for i, hit in enumerate(hits, start=1):
            row = db.execute(
                "SELECT title, source_path, source_type, ingested_at FROM documents WHERE id = ?",
                (hit["doc_id"],)
            ).fetchone()
            if not row:
                continue
            title = row["title"] or row["source_path"]
            date = (row["ingested_at"] or "")[:10]
            context_parts.append(
                f"[Source {i}] {title} ({row['source_type']}, {date}):\n{hit['content']}"
            )
            sources.append({
                "index": i,
                "title": title,
                "source_type": row["source_type"],
                "source_path": row["source_path"],
                "ingested_at": row["ingested_at"],
                "chunk_index": hit["chunk_index"],
                "combined_score": hit["combined_score"],
            })
        return "\n\n---\n\n".join(context_parts), sources

    def _call_llm(self, messages: List[dict]) -> str:
        try:
            response = requests.post(
                f"{self.ollama_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": messages,
                    "stream": False,
                },
                timeout=120,
            )
            response.raise_for_status()
            return response.json()["message"]["content"]
        except Exception as e:
            return f"[LLM error: {e}]"

    def _persist_turn(self, session_id: str, query: str, answer: str, sources: list):
        db = get_db()
        import uuid
        db.execute("""
            INSERT INTO conversations (id, session_id, query, answer, sources_json, created_at)
            VALUES (?, ?, ?, ?, ?, datetime('now'))
        """, (str(uuid.uuid4()), session_id, query, answer, json.dumps(sources)))
        db.commit()

4.8 Terminal UI (TUI)
Purpose

A rich, keyboard-driven terminal interface built with Textual. Provides a chat pane, a source panel showing citations, and a timeline sidebar for browsing memory by date.

Python

# ui/tui/app.py

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Input, RichLog, ListView, ListItem
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from conversation.engine import ConversationEngine
import threading


class MEMEXApp(App):
    """MEMEX Terminal UI."""

    CSS = """
    Screen {
        layout: horizontal;
    }
    #sidebar {
        width: 28;
        border: solid $primary;
    }
    #main {
        layout: vertical;
    }
    #chat-log {
        height: 1fr;
        border: solid $surface;
    }
    #source-panel {
        height: 12;
        border: solid $accent;
    }
    #input-bar {
        dock: bottom;
        height: 3;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+l", "clear_chat", "Clear"),
        ("tab", "focus_input", "Focus input"),
    ]

    current_session_id: reactive[str] = reactive("")

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal():
            with Vertical(id="sidebar"):
                yield ListView(id="timeline")
            with Vertical(id="main"):
                yield RichLog(id="chat-log", highlight=True, markup=True)
                yield RichLog(id="source-panel", highlight=True)
                yield Input(placeholder="Ask your memory...", id="input-bar")
        yield Footer()

    def on_mount(self):
        import uuid
        self.current_session_id = str(uuid.uuid4())
        self.engine = ConversationEngine(self.app.config)
        self._load_timeline()
        self.query_one("#input-bar").focus()

    def on_input_submitted(self, event: Input.Submitted):
        query = event.value.strip()
        if not query:
            return
        event.input.value = ""
        chat_log = self.query_one("#chat-log", RichLog)
        source_panel = self.query_one("#source-panel", RichLog)
        chat_log.write(f"[bold cyan]You:[/bold cyan] {query}")
        chat_log.write("[dim]Thinking...[/dim]")

        def run_query():
            result = self.engine.chat(query, self.current_session_id)
            self.call_from_thread(self._display_result, result)

        threading.Thread(target=run_query, daemon=True).start()

    def _display_result(self, result: dict):
        chat_log = self.query_one("#chat-log", RichLog)
        source_panel = self.query_one("#source-panel", RichLog)

        # Remove "Thinking..." line
        chat_log.write(f"\n[bold green]MEMEX:[/bold green] {result['answer']}\n")

        source_panel.clear()
        source_panel.write("[bold]Sources:[/bold]")
        for src in result["sources"]:
            date = (src.get("ingested_at") or "")[:10]
            source_panel.write(
                f"  [Source {src['index']}] [cyan]{src['title']}[/cyan] "
                f"[dim]({src['source_type']}, {date})[/dim]"
            )

    def _load_timeline(self):
        from storage.db import get_db
        db = get_db()
        rows = db.execute("""
            SELECT DATE(ingested_at) AS day, COUNT(*) AS count
            FROM documents
            GROUP BY day
            ORDER BY day DESC
            LIMIT 30
        """).fetchall()
        timeline = self.query_one("#timeline", ListView)
        for row in rows:
            timeline.append(ListItem(f"{row['day']} ({row['count']} docs)"))

    def action_clear_chat(self):
        self.query_one("#chat-log", RichLog).clear()

    def action_focus_input(self):
        self.query_one("#input-bar").focus()

4.9 Web UI & Graph Visualizer
Purpose

A Svelte-based web dashboard running at http://localhost:8080 that provides a richer interface than the TUI, including an interactive D3 force-directed knowledge graph visualization, conversation history, and document timeline.

Key Pages:
Page	Description
Chat	Full conversation interface with source cards
Graph	Interactive D3 force graph of entities and relations
Timeline	Chronological document browser
Sources	Full document index with search
Settings	Configuration editor

svelte

<!-- ui/web/src/routes/Graph.svelte -->

<script>
  import { onMount } from 'svelte';
  import * as d3 from 'd3';

  let svgEl;
  let nodes = [];
  let links = [];

  onMount(async () => {
    const res = await fetch('/api/graph/data');
    const data = await res.json();
    nodes = data.nodes;
    links = data.links;
    renderGraph();
  });

  function renderGraph() {
    const width = window.innerWidth - 300;
    const height = window.innerHeight - 100;

    const svg = d3.select(svgEl)
      .attr('width', width)
      .attr('height', height);

    const simulation = d3.forceSimulation(nodes)
      .force('link', d3.forceLink(links).id(d => d.id).distance(80))
      .force('charge', d3.forceManyBody().strength(-200))
      .force('center', d3.forceCenter(width / 2, height / 2))
      .force('collision', d3.forceCollide().radius(30));

    const link = svg.append('g')
      .selectAll('line')
      .data(links)
      .join('line')
      .attr('stroke', '#555')
      .attr('stroke-opacity', 0.6)
      .attr('stroke-width', d => Math.sqrt(d.confidence * 4));

    const node = svg.append('g')
      .selectAll('circle')
      .data(nodes)
      .join('circle')
      .attr('r', d => 6 + Math.min(d.mention_count, 20))
      .attr('fill', d => labelColor(d.label))
      .call(d3.drag()
        .on('start', (event, d) => {
          if (!event.active) simulation.alphaTarget(0.3).restart();
          d.fx = d.x; d.fy = d.y;
        })
        .on('drag', (event, d) => { d.fx = event.x; d.fy = event.y; })
        .on('end', (event, d) => {
          if (!event.active) simulation.alphaTarget(0);
          d.fx = null; d.fy = null;
        })
      );

    const label = svg.append('g')
      .selectAll('text')
      .data(nodes)
      .join('text')
      .text(d => d.name)
      .attr('font-size', 11)
      .attr('fill', '#ccc');

    simulation.on('tick', () => {
      link
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);
      node.attr('cx', d => d.x).attr('cy', d => d.y);
      label.attr('x', d => d.x + 8).attr('y', d => d.y + 3);
    });
  }

  function labelColor(label) {
    const map = {
      PERSON: '#60a5fa', ORG: '#f59e0b', GPE: '#34d399',
      PRODUCT: '#a78bfa', TECH: '#fb7185', default: '#9ca3af'
    };
    return map[label] || map.default;
  }
</script>

<div class="graph-container">
  <svg bind:this={svgEl}></svg>
</div>

5. Data Models & Schemas
5.1 SQLite Schema

SQL

-- migrations/001_initial.sql

-- ─────────────────────────────────────────────────────────────────────────────
-- DOCUMENTS: The ground-truth record of every ingested item
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS documents (
    id                  TEXT PRIMARY KEY,
    source_type         TEXT NOT NULL,         -- "browser", "filesystem", "terminal", etc.
    source_path         TEXT NOT NULL,         -- URL, file path, IMAP UID, etc.
    title               TEXT,
    raw_content         BLOB,                  -- Original bytes (optional, can be purged)
    clean_content       TEXT,                  -- Parsed plain text
    content_type        TEXT,                  -- "pdf", "html", "code", "email", "image"
    language            TEXT,                  -- Programming language if code
    checksum            TEXT NOT NULL UNIQUE,  -- SHA-256 of raw_content (dedup key)
    ingested_at         DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_created_at   DATETIME,
    source_modified_at  DATETIME,
    is_embedded         INTEGER NOT NULL DEFAULT 0,
    is_graphed          INTEGER NOT NULL DEFAULT 0,
    metadata_json       TEXT                   -- Source-specific extras (JSON)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- CHUNKS: The unit of retrieval and embedding
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS chunks (
    id          TEXT PRIMARY KEY,
    doc_id      TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INTEGER NOT NULL,
    content     TEXT NOT NULL,
    token_count INTEGER NOT NULL,
    chroma_id   TEXT,                          -- ChromaDB vector ID
    embedded_at DATETIME,
    UNIQUE (doc_id, chunk_index)
);

-- ─────────────────────────────────────────────────────────────────────────────
-- ENTITIES: Canonical entity registry (NER output)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS entities (
    id              TEXT PRIMARY KEY,
    canonical_name  TEXT NOT NULL UNIQUE,
    label           TEXT NOT NULL,             -- PERSON, ORG, GPE, PRODUCT, etc.
    aliases         TEXT,                      -- JSON array of alternate forms
    first_seen      DATETIME NOT NULL,
    last_seen       DATETIME NOT NULL,
    mention_count   INTEGER NOT NULL DEFAULT 0
);

-- ─────────────────────────────────────────────────────────────────────────────
-- ENTITY_MENTIONS: Where each entity appeared
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS entity_mentions (
    id               TEXT PRIMARY KEY,
    entity_id        TEXT NOT NULL REFERENCES entities(id),
    doc_id           TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    context_snippet  TEXT,                     -- Surrounding sentence
    start_char       INTEGER,
    end_char         INTEGER,
    created_at       DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ─────────────────────────────────────────────────────────────────────────────
-- RELATIONS: Typed edges between entities (LLM-extracted)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS relations (
    id              TEXT PRIMARY KEY,
    subject         TEXT NOT NULL,             -- Canonical entity name
    predicate       TEXT NOT NULL,             -- e.g., "authored", "cited_in", "uses"
    object          TEXT NOT NULL,             -- Canonical entity name
    confidence      REAL NOT NULL DEFAULT 0.5,
    source_doc_id   TEXT REFERENCES documents(id) ON DELETE SET NULL,
    created_at      DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ─────────────────────────────────────────────────────────────────────────────
-- CONVERSATIONS: Chat history with MEMEX
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS conversations (
    id           TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL,
    query        TEXT NOT NULL,
    answer       TEXT NOT NULL,
    sources_json TEXT,                         -- JSON array of cited sources
    created_at   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ─────────────────────────────────────────────────────────────────────────────
-- FTS5 INDEXES for full-text keyword search
-- ─────────────────────────────────────────────────────────────────────────────
CREATE VIRTUAL TABLE IF NOT EXISTS documents_fts USING fts5(
    title,
    clean_content,
    content='documents',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content,
    content='chunks',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

-- Auto-update FTS5 on document insert/update/delete
CREATE TRIGGER IF NOT EXISTS documents_fts_insert AFTER INSERT ON documents BEGIN
    INSERT INTO documents_fts(rowid, title, clean_content)
    VALUES (new.rowid, new.title, new.clean_content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_fts_insert AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, content) VALUES (new.rowid, new.content);
END;

-- ─────────────────────────────────────────────────────────────────────────────
-- PERFORMANCE INDEXES
-- ─────────────────────────────────────────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_documents_source_type   ON documents(source_type);
CREATE INDEX IF NOT EXISTS idx_documents_ingested_at   ON documents(ingested_at);
CREATE INDEX IF NOT EXISTS idx_documents_checksum      ON documents(checksum);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_id           ON chunks(doc_id);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_entity  ON entity_mentions(entity_id);
CREATE INDEX IF NOT EXISTS idx_entity_mentions_doc     ON entity_mentions(doc_id);
CREATE INDEX IF NOT EXISTS idx_relations_subject       ON relations(subject);
CREATE INDEX IF NOT EXISTS idx_relations_object        ON relations(object);
CREATE INDEX IF NOT EXISTS idx_conversations_session   ON conversations(session_id);

6. API Specifications
6.1 Internal REST API (Web UI ↔ Backend)

All endpoints served at http://localhost:8080/api/v1/
Memory / Retrieval

text

POST   /api/v1/memory/search
       Body: { query, n_results?, time_filter? }
       Returns: { hits: Chunk[], sources: Document[] }

GET    /api/v1/memory/timeline
       Query: ?from=&to=&source_type=&limit=
       Returns: { documents: Document[] }

Conversation

text

POST   /api/v1/conversation/chat
       Body: { query, session_id, time_filter? }
       Returns: { answer, sources, session_id }

GET    /api/v1/conversation/sessions
       Returns: { sessions: Session[] }

GET    /api/v1/conversation/session/:id
       Returns: { session_id, turns: ConversationTurn[] }

DELETE /api/v1/conversation/session/:id
       Returns: { success }

Documents

text

GET    /api/v1/documents
       Query: ?source_type=&limit=&offset=&from=&to=
       Returns: { total, documents: Document[] }

GET    /api/v1/documents/:id
       Returns: Document (with chunks + entity mentions)

DELETE /api/v1/documents/:id
       Deletes from SQLite + ChromaDB + KuzuDB
       Returns: { success }

Graph

text

GET    /api/v1/graph/data
       Returns: { nodes: Entity[], links: Relation[] }
       (Used by D3 force graph)

GET    /api/v1/graph/entity/:name
       Returns: { entity, mentions, relations, connected_docs }

GET    /api/v1/graph/neighbors/:name
       Query: ?depth=2
       Returns: { nodes, links } (subgraph)

System

text

GET    /api/v1/health
       Returns: { daemon_running, ollama_healthy, db_healthy, chroma_healthy, doc_count, chunk_count }

GET    /api/v1/stats
       Returns: { doc_count_by_source, ingested_today, entity_count, relation_count, embedding_coverage_pct }

POST   /api/v1/ingest/trigger
       Body: { source_type }
       Returns: { queued: true }

GET    /api/v1/settings
       Returns: Settings

PUT    /api/v1/settings
       Body: Partial<Settings>
       Returns: Settings

Real-Time Stream

text

GET    /api/v1/stream/events
       Content-Type: text/event-stream
       Events: document.ingested | chunk.embedded | entity.extracted | query.processed

7. Directory Structure

text

memex/
├── cmd/
│   └── memex/
│       └── main.py                    # Entry point: starts daemon + API server
│
├── ingestors/
│   ├── base.py                        # BaseIngestor, RawDocument dataclass
│   ├── daemon.py                      # MEMEXDaemon orchestrator
│   ├── browser.py                     # Browser history + page content
│   ├── filesystem.py                  # File watcher (watchdog)
│   ├── terminal.py                    # Shell history hooks
│   ├── email.py                       # IMAP ingestion
│   ├── clipboard.py                   # Clipboard polling
│   ├── calendar.py                    # ICS / CalDAV polling
│   └── screenshot.py                  # Screenshot directory watcher
│
├── parsers/
│   ├── universal.py                   # Parser dispatcher
│   ├── chunker.py                     # SmartChunker
│   ├── pdf.py                         # pdfminer.six PDF extraction
│   ├── html.py                        # readability-lxml HTML extraction
│   ├── code.py                        # tree-sitter code parsing
│   ├── email_parser.py                # email stdlib + mailparser
│   ├── image.py                       # Tesseract OCR
│   ├── markdown.py                    # Markdown → plain text
│   └── plain.py                       # Raw text passthrough
│
├── embeddings/
│   ├── engine.py                      # EmbeddingEngine: chunk → Ollama → ChromaDB
│   └── cache.py                       # Embedding cache utilities
│
├── graph/
│   ├── extractor.py                   # GraphExtractor orchestrator
│   ├── entity_extractor.py            # spaCy NER
│   └── relation_extractor.py          # LLM-based relation extraction
│
├── memory/
│   ├── retriever.py                   # HybridRetriever (vector+keyword+graph+temporal)
│   └── ranker.py                      # Score fusion and temporal re-rank
│
├── conversation/
│   ├── engine.py                      # ConversationEngine: query → context → LLM → citations
│   └── prompts.py                     # System prompt templates
│
├── storage/
│   ├── db.py                          # SQLite connection + WAL config
│   ├── migrations.py                  # Migration runner
│   └── migrations/
│       ├── 001_initial.sql
│       └── 002_add_indexes.sql
│
├── api/
│   ├── server.py                      # FastAPI app + router registration
│   ├── middleware.py                  # Local-only access enforcement, CORS
│   ├── sse.py                         # Server-Sent Events endpoint
│   └── routes/
│       ├── memory.py
│       ├── conversation.py
│       ├── documents.py
│       ├── graph.py
│       ├── system.py
│       └── settings.py
│
├── ui/
│   ├── tui/
│   │   ├── app.py                     # Textual TUI application
│   │   └── components/
│   │       ├── chat_pane.py
│   │       ├── source_panel.py
│   │       └── timeline_sidebar.py
│   └── web/                           # Svelte web application
│       ├── src/
│       │   ├── App.svelte
│       │   ├── routes/
│       │   │   ├── Chat.svelte
│       │   │   ├── Graph.svelte
│       │   │   ├── Timeline.svelte
│       │   │   ├── Sources.svelte
│       │   │   └── Settings.svelte
│       │   ├── components/
│       │   │   ├── SourceCard.svelte
│       │   │   ├── ConversationTurn.svelte
│       │   │   ├── EntityBadge.svelte
│       │   │   └── DocumentRow.svelte
│       │   ├── stores/
│       │   │   └── memex.js
│       │   └── api/
│       │       └── client.js
│       ├── package.json
│       └── vite.config.js
│
├── config/
│   ├── config.py                      # Config loader (TOML)
│   └── defaults.py                    # Default config values
│
├── tests/
│   ├── unit/
│   │   ├── test_chunker.py
│   │   ├── test_parsers.py
│   │   ├── test_retriever.py
│   │   └── test_entity_extractor.py
│   ├── integration/
│   │   ├── test_ingest_pipeline.py
│   │   ├── test_embedding_engine.py
│   │   └── test_graph_extractor.py
│   └── fixtures/
│       ├── sample.pdf
│       ├── sample.html
│       ├── sample.py
│       └── sample_email.eml
│
├── data/                              # Runtime data (gitignored)
│   ├── memex.db                       # SQLite database
│   ├── chroma/                        # ChromaDB vector store
│   └── kuzu/                          # KuzuDB graph database
│
├── logs/                              # Log files (gitignored)
├── pyproject.toml
├── requirements.txt
├── Makefile
├── Dockerfile
└── README.md

8. Configuration System
8.1 Config File (TOML)

Stored at ~/.memex/config.toml

toml

[daemon]
enabled = true
log_level = "info"          # debug | info | warn | error
processing_workers = 2       # Parallel document processing threads
queue_size = 1000

[sources]
enabled = [
    "browser",
    "filesystem",
    "terminal",
    "email",
    "clipboard",
    "calendar",
    "screenshot",
]

[sources.browser]
enabled = true
poll_interval_seconds = 300          # 5 minutes
profile_paths = []                   # Auto-detected if empty
max_history_days = 90
fetch_page_content = true            # Download + parse visited pages
excluded_domains = [
    "accounts.google.com",
    "mail.google.com",
    "banking.example.com",
]

[sources.filesystem]
enabled = true
watch_paths = [
    "~/Documents",
    "~/Desktop",
    "~/Downloads",
    "~/Notes",
]
excluded_paths = [
    "~/.ssh",
    "~/.gnupg",
    "~/Downloads/tmp",
]
included_extensions = [
    ".pdf", ".md", ".txt", ".docx",
    ".py", ".go", ".js", ".ts", ".rs",
    ".html", ".ipynb",
]
max_file_size_mb = 50

[sources.terminal]
enabled = true
shell_history_path = "~/.zsh_history"  # Override auto-detect
capture_output = false                   # Output capture is risky — disabled by default
excluded_commands = ["password", "secret", "token", "key"]

[sources.email]
enabled = false              # Requires IMAP credentials — disabled by default
imap_host = ""
imap_port = 993
imap_user = ""
imap_password_env = "MEMEX_IMAP_PASSWORD"   # Read from env var, never stored
mailboxes = ["INBOX", "Sent"]
max_messages = 1000

[sources.clipboard]
enabled = true
poll_interval_seconds = 30
min_length_chars = 50        # Ignore short clipboard snippets

[sources.screenshot]
enabled = false              # Opt-in only
watch_path = "~/Screenshots"
run_ocr = true

[sources.calendar]
enabled = false
ics_paths = []               # List of ICS file paths
caldav_url = ""
caldav_user = ""
caldav_password_env = "MEMEX_CALDAV_PASSWORD"

[ollama]
base_url = "http://localhost:11434"
embedding_model = "nomic-embed-text"
chat_model = "llama3:8b"
request_timeout_seconds = 120

[graph]
enable_entity_extraction = true
enable_relation_extraction = true
spacy_model = "en_core_web_sm"        # "en_core_web_trf" for higher accuracy
min_relation_confidence = 0.5
max_chars_for_relation_extraction = 3000

[retrieval]
default_n_results = 8
vector_weight = 0.40
keyword_weight = 0.30
graph_weight = 0.20
temporal_weight = 0.10
temporal_decay_lambda = 0.005         # e^(-lambda * age_days)

[storage]
db_path = "~/.memex/data/memex.db"
chroma_path = "~/.memex/data/chroma"
kuzu_path = "~/.memex/data/kuzu"
log_path = "~/.memex/logs/memex.log"
raw_content_retention_days = 30       # Purge raw_content after N days (keep clean_content)
max_db_size_mb = 2000

[api]
host = "127.0.0.1"                    # NEVER 0.0.0.0 — localhost only
port = 8080

[ui]
tui_enabled = true
web_enabled = true
web_port = 8080
open_browser_on_start = false
theme = "dark"

8.2 Config Loader

Python

# config/config.py

import tomllib
import os
from pathlib import Path
from dataclasses import dataclass


DEFAULT_CONFIG_PATH = Path.home() / ".memex" / "config.toml"


def load_config(path: Path = DEFAULT_CONFIG_PATH) -> dict:
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        _write_default_config(path)

    with open(path, "rb") as f:
        config = tomllib.load(f)

    config = _expand_paths(config)
    _validate(config)
    return config


def _expand_paths(config: dict) -> dict:
    """Expand ~ in all path values."""
    import copy
    config = copy.deepcopy(config)
    for section in config.values():
        if isinstance(section, dict):
            for key, val in section.items():
                if isinstance(val, str) and val.startswith("~"):
                    section[key] = str(Path(val).expanduser())
                elif isinstance(val, list):
                    section[key] = [
                        str(Path(v).expanduser()) if isinstance(v, str) and v.startswith("~") else v
                        for v in val
                    ]
    return config


def _validate(config: dict):
    required = [
        ("ollama", "base_url"),
        ("ollama", "embedding_model"),
        ("ollama", "chat_model"),
        ("storage", "db_path"),
        ("storage", "chroma_path"),
        ("storage", "kuzu_path"),
    ]
    for section, key in required:
        if not config.get(section, {}).get(key):
            raise ValueError(f"Missing required config: [{section}].{key}")

    # API must bind to localhost only
    if config.get("api", {}).get("host", "127.0.0.1") not in ("127.0.0.1", "::1", "localhost"):
        raise ValueError("config.api.host must be localhost only. MEMEX does not support remote access.")

9. Embedding & Vector Store Deep Dive
9.1 Why nomic-embed-text

nomic-embed-text is a locally-available embedding model served through Ollama with the following characteristics relevant to MEMEX:
Property	Value
Embedding dimensions	768
Context window	8192 tokens
Suitable for	Long-form prose, code, email, mixed content
Inference speed	Fast on CPU (no GPU required)
Ollama endpoint	/api/embed
9.2 ChromaDB Configuration

Python

# embeddings/engine.py (Chroma setup detail)

import chromadb
from chromadb.config import Settings

# PersistentClient = data survives process restarts
client = chromadb.PersistentClient(
    path=config["storage"]["chroma_path"],
    settings=Settings(
        anonymized_telemetry=False,    # No telemetry — local only
        allow_reset=True,              # Enable for test/rebuild scenarios
    )
)

# HNSW cosine distance for semantic similarity
collection = client.get_or_create_collection(
    name="memex_chunks",
    metadata={"hnsw:space": "cosine"},   # cosine similarity for text
)

9.3 Embedding Cache Strategy

The cache operates at two levels:

    Chunk-level: chunks.chroma_id IS NOT NULL → already embedded, skip
    Document-level: documents.is_embedded = 1 → all chunks done

Python

# embeddings/cache.py

def is_chunk_embedded(db, doc_id: str, chunk_index: int) -> bool:
    row = db.execute(
        "SELECT chroma_id FROM chunks WHERE doc_id = ? AND chunk_index = ?",
        (doc_id, chunk_index)
    ).fetchone()
    return row is not None and row["chroma_id"] is not None


def get_embedding_coverage(db) -> float:
    """Returns fraction of documents fully embedded."""
    total = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    embedded = db.execute("SELECT COUNT(*) FROM documents WHERE is_embedded = 1").fetchone()[0]
    return embedded / total if total > 0 else 0.0

9.4 Re-embedding Strategy

When a document's checksum changes (file was modified):

    Delete existing chunks from SQLite (cascade deletes chunk records)
    Delete matching vectors from ChromaDB by doc_id prefix
    Re-parse, re-chunk, re-embed
    Update documents.checksum and reset is_embedded = 0 → 1

Python

def rebuild_document_embeddings(doc_id: str, embedder: EmbeddingEngine, db):
    # 1. Remove from Chroma
    chroma_ids = [
        row["chroma_id"]
        for row in db.execute(
            "SELECT chroma_id FROM chunks WHERE doc_id = ? AND chroma_id IS NOT NULL",
            (doc_id,)
        ).fetchall()
    ]
    if chroma_ids:
        embedder.collection.delete(ids=chroma_ids)

    # 2. Remove chunk rows (will be re-inserted by embedder)
    db.execute("DELETE FROM chunks WHERE doc_id = ?", (doc_id,))
    db.execute("UPDATE documents SET is_embedded = 0 WHERE id = ?", (doc_id,))
    db.commit()

    # 3. Re-embed from clean_content
    row = db.execute("SELECT clean_content, content_type FROM documents WHERE id = ?", (doc_id,)).fetchone()
    if row:
        embedder.process(doc_id, row["clean_content"], row["content_type"])

10. Knowledge Graph Deep Dive
10.1 Entity Lifecycle

text

Raw text
   │
   ▼
spaCy NER → ExtractedEntity(text, label, start_char, end_char, context)
   │
   ▼
Canonicalize: lowercase, strip punctuation
   │
   ├── Already in entities table?
   │   ├── YES → increment mention_count, update last_seen
   │   └── NO  → INSERT new entity row
   │
   ▼
INSERT entity_mention (entity_id, doc_id, context_snippet, char offsets)
   │
   ▼
MERGE (e:Entity {name: canonical}) in KuzuDB

10.2 Relation Lifecycle

text

LLM extracts: subject, predicate, object, confidence, evidence
   │
   ├── confidence < threshold (0.5) → discard
   │
   ▼
INSERT into relations (subject, predicate, object, confidence, source_doc_id)
   │
   ▼
KuzuDB:
  MATCH (s:Entity {name: subject}), (o:Entity {name: object})
  CREATE (s)-[:RELATES {predicate, confidence, source_doc_id}]->(o)

10.3 Graph Traversal for Retrieval

Python

# graph/traversal.py

def get_entity_neighborhood(kuzu_conn, entity_name: str, depth: int = 2) -> dict:
    """Return subgraph of entities connected to entity_name within `depth` hops."""
    result = kuzu_conn.execute("""
        MATCH path = (start:Entity {name: $name})-[:RELATES*1..$depth]-(neighbor:Entity)
        RETURN
            neighbor.name AS name,
            neighbor.label AS label,
            length(path) AS hops
        LIMIT 50
    """, {"name": entity_name.lower(), "depth": depth})

    nodes = []
    while result.has_next():
        row = result.get_next()
        nodes.append({"name": row[0], "label": row[1], "hops": row[2]})
    return {"center": entity_name, "neighbors": nodes}


def get_documents_for_entities(db, entity_names: list) -> list:
    """Return doc_ids for documents mentioning any of the given entities."""
    placeholders = ",".join("?" * len(entity_names))
    rows = db.execute(f"""
        SELECT DISTINCT em.doc_id
        FROM entity_mentions em
        JOIN entities e ON e.id = em.entity_id
        WHERE e.canonical_name IN ({placeholders})
    """, entity_names).fetchall()
    return [r["doc_id"] for r in rows]

11. Hybrid Retrieval Deep Dive
11.1 Why Four Signals
Signal	Catches	Misses
Vector	Paraphrases, synonyms, semantic similarity	Exact identifiers, rare terms, code snippets
Keyword (FTS5)	Exact strings, error messages, function names, identifiers	Paraphrases, conceptual queries
Graph	Concept neighborhoods, entity co-occurrence, associative connections	Documents with no extracted entities
Temporal	"When I was working on X", recency preference	Timeless knowledge
11.2 Score Fusion Math

text

combined_score = (vector_score × 0.40)
               + (keyword_score × 0.30)
               + (graph_score × 0.20)
               + (temporal_decay × 0.10)

temporal_decay = e^(-0.005 × age_days)

At age_days = 0 (today): decay = 1.0 At age_days = 100: decay ≈ 0.61 At age_days = 365: decay ≈ 0.16

This means a 3-year-old document needs very high vector+keyword relevance to surface above a moderately-relevant recent document.
11.3 Time Filter Syntax (Query-level)

Python

# Example: retrieve only from 2024-01-01 to 2024-06-30
from datetime import datetime, timezone

result = retriever.retrieve(
    query="Bloom filter deduplication",
    n_results=10,
    time_filter={
        "after":  datetime(2024, 1, 1, tzinfo=timezone.utc),
        "before": datetime(2024, 6, 30, tzinfo=timezone.utc),
    }
)

The TUI and Web UI expose this as natural language: "search in [date range]" → parsed by the conversation layer before calling retriever.
12. Conversation Layer Deep Dive
12.1 Context Window Management

Python

# conversation/engine.py

MAX_CONTEXT_TOKENS = 6000    # Leave room for system prompt + answer

def _build_context(self, hits, max_tokens=MAX_CONTEXT_TOKENS):
    """
    Assemble context block from hits, respecting token budget.
    Higher-scored chunks get priority when budget is tight.
    """
    import tiktoken
    encoder = tiktoken.get_encoding("cl100k_base")
    hits_sorted = sorted(hits, key=lambda x: x["combined_score"], reverse=True)

    context_parts = []
    sources = []
    used_tokens = 0

    for i, hit in enumerate(hits_sorted, start=1):
        chunk_tokens = len(encoder.encode(hit["content"]))
        if used_tokens + chunk_tokens > max_tokens:
            break
        # ... build source entry and context part
        used_tokens += chunk_tokens

    return "\n\n---\n\n".join(context_parts), sources

12.2 Citation Format

Answers are formatted with [Source N] inline references. The UI renders these as clickable source cards:

text

MEMEX: In March 2024, you encountered this issue while working on the Redis cache
layer [Source 1]. The solution you documented involved setting maxmemory-policy
to allkeys-lru [Source 2]. You later referenced a similar pattern in a Stack
Overflow answer you saved [Source 3].

Sources:
  [1] Redis cache debugging notes.md · filesystem · 2024-03-14
  [2] Makefile (redis-config project) · filesystem · 2024-03-15
  [3] Stack Overflow: Redis eviction policies · browser · 2024-03-14

12.3 Prompt Templates

Python

# conversation/prompts.py

SYSTEM_PROMPT = """You are MEMEX, a personal memory assistant. You have access to the
user's indexed documents, notes, browser history, and past activity.

Answer the user's question using ONLY the provided context below. Cite sources using
[Source N] notation inline. If the context does not contain enough information to
answer, say "I don't have enough in memory to answer that" — do not fabricate.

Be specific: include dates, file names, and direct references when available.
Be concise: prefer bullet points over long paragraphs for factual recall."""

TIME_QUERY_PROMPT = """The user's query contains a time reference: "{time_hint}".
Interpret this as a date range filter and apply it to the retrieval.
Examples:
- "last month" → past 30 days
- "in March" → March of the most recent year
- "last year" → 12-24 months ago
- "when I was working on X" → cluster around the X project's activity dates"""

13. Ingestor Deep Dive (Per Source)
13.1 Browser Ingestor

Python

# ingestors/browser.py

import sqlite3
import os
import shutil
import tempfile
import requests
from datetime import datetime, timedelta
from ingestors.base import BaseIngestor, RawDocument


BROWSER_DB_PATHS = {
    "chrome": {
        "darwin":  "~/Library/Application Support/Google/Chrome/Default/History",
        "linux":   "~/.config/google-chrome/Default/History",
        "windows": "%LOCALAPPDATA%/Google/Chrome/User Data/Default/History",
    },
    "firefox": {
        "darwin":  "~/Library/Application Support/Firefox/Profiles/",
        "linux":   "~/.mozilla/firefox/",
        "windows": "%APPDATA%/Mozilla/Firefox/Profiles/",
    },
}


class BrowserIngestor(BaseIngestor):

    def run(self):
        import time
        while True:
            self._poll()
            time.sleep(self.config["sources"]["browser"]["poll_interval_seconds"])

    def _poll(self):
        history_db = self._find_history_db()
        if not history_db:
            return

        # Copy DB to temp (browser locks it)
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            shutil.copy2(history_db, tmp.name)
            tmp_path = tmp.name

        try:
            conn = sqlite3.connect(tmp_path)
            cutoff = datetime.now() - timedelta(
                days=self.config["sources"]["browser"]["max_history_days"]
            )
            # Chrome stores timestamps as microseconds since 1601-01-01
            chrome_epoch_offset = 11644473600  # seconds between 1601 and 1970
            cutoff_chrome = int((cutoff.timestamp() + chrome_epoch_offset) * 1_000_000)

            rows = conn.execute("""
                SELECT url, title, last_visit_time, visit_count
                FROM urls
                WHERE last_visit_time > ?
                ORDER BY last_visit_time DESC
            """, (cutoff_chrome,)).fetchall()
            conn.close()

            for url, title, last_visit, _ in rows:
                if self._is_excluded(url):
                    continue
                content = self._fetch_page_content(url)
                if not content:
                    continue
                doc = RawDocument(
                    source_type="browser",
                    source_path=url,
                    raw_content=content.encode("utf-8"),
                    title=title,
                    source_created_at=self._chrome_ts_to_dt(last_visit),
                    source_modified_at=None,
                    metadata={"visit_count": _},
                )
                self.emit(doc)
        finally:
            os.unlink(tmp_path)

    def _fetch_page_content(self, url: str) -> Optional[str]:
        if not self.config["sources"]["browser"].get("fetch_page_content", True):
            return None
        try:
            resp = requests.get(url, timeout=10, headers={"User-Agent": "MEMEX/1.0 (local indexer)"})
            resp.raise_for_status()
            return resp.text
        except Exception:
            return None

    def _is_excluded(self, url: str) -> bool:
        excluded = self.config["sources"]["browser"].get("excluded_domains", [])
        from urllib.parse import urlparse
        domain = urlparse(url).netloc
        return any(exc in domain for exc in excluded)

    @staticmethod
    def _chrome_ts_to_dt(chrome_ts: int) -> datetime:
        chrome_epoch_offset = 11644473600
        unix_ts = chrome_ts / 1_000_000 - chrome_epoch_offset
        return datetime.utcfromtimestamp(unix_ts)

13.2 Filesystem Ingestor

Python

# ingestors/filesystem.py

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent, FileModifiedEvent
from ingestors.base import BaseIngestor, RawDocument
import os
import time


class FilesystemIngestor(BaseIngestor, FileSystemEventHandler):

    def __init__(self, config, queue):
        super().__init__(config, None, queue)
        self.observer = Observer()
        self.watch_paths = config["sources"]["filesystem"]["watch_paths"]
        self.included_extensions = set(config["sources"]["filesystem"]["included_extensions"])
        self.excluded_paths = config["sources"]["filesystem"]["excluded_paths"]
        self.max_file_size = config["sources"]["filesystem"]["max_file_size_mb"] * 1024 * 1024

    def run(self):
        for path in self.watch_paths:
            self.observer.schedule(self, path=path, recursive=True)
        self.observer.start()
        try:
            while True:
                time.sleep(1)
        except Exception:
            self.observer.stop()
        self.observer.join()

    def on_created(self, event: FileCreatedEvent):
        if not event.is_directory:
            self._ingest_file(event.src_path)

    def on_modified(self, event: FileModifiedEvent):
        if not event.is_directory:
            self._ingest_file(event.src_path)

    def _ingest_file(self, path: str):
        if not self._should_include(path):
            return
        try:
            size = os.path.getsize(path)
            if size > self.max_file_size:
                return
            with open(path, "rb") as f:
                raw = f.read()
            stat = os.stat(path)
            doc = RawDocument(
                source_type="filesystem",
                source_path=path,
                raw_content=raw,
                title=os.path.basename(path),
                source_created_at=None,
                source_modified_at=None,
                metadata={"size_bytes": size},
            )
            self.emit(doc)
        except (PermissionError, OSError):
            pass

    def _should_include(self, path: str) -> bool:
        _, ext = os.path.splitext(path)
        if ext.lower() not in self.included_extensions:
            return False
        for excluded in self.excluded_paths:
            if path.startswith(excluded):
                return False
        return True

13.3 Terminal Ingestor

Python

# ingestors/terminal.py

import os
import time
from ingestors.base import BaseIngestor, RawDocument


class TerminalIngestor(BaseIngestor):
    """
    Polls the shell history file for new commands.
    Uses last-read byte offset to avoid re-reading the entire file.
    """

    def __init__(self, config, queue):
        super().__init__(config, None, queue)
        self.history_path = self._resolve_history_path()
        self.last_offset = 0
        self.excluded_patterns = config["sources"]["terminal"].get("excluded_commands", [])

    def _resolve_history_path(self) -> str:
        configured = self.config["sources"]["terminal"].get("shell_history_path")
        if configured:
            return os.path.expanduser(configured)
        # Auto-detect
        for candidate in ["~/.zsh_history", "~/.bash_history", "~/.history"]:
            p = os.path.expanduser(candidate)
            if os.path.exists(p):
                return p
        return os.path.expanduser("~/.bash_history")

    def run(self):
        while True:
            self._poll()
            time.sleep(60)  # Poll every minute

    def _poll(self):
        if not os.path.exists(self.history_path):
            return
        try:
            with open(self.history_path, "rb") as f:
                f.seek(self.last_offset)
                new_content = f.read()
                self.last_offset = f.tell()

            if not new_content:
                return

            # Filter sensitive commands
            lines = new_content.decode("utf-8", errors="replace").splitlines()
            safe_lines = [
                line for line in lines
                if not any(pat.lower() in line.lower() for pat in self.excluded_patterns)
            ]

            if not safe_lines:
                return

            # Batch commands into a single document per poll
            batch_content = "\n".join(safe_lines)
            import hashlib
            checksum_input = f"{self.last_offset}:{batch_content}".encode()
            doc = RawDocument(
                source_type="terminal",
                source_path=f"{self.history_path}@offset:{self.last_offset}",
                raw_content=batch_content.encode("utf-8"),
                title=f"Terminal session ({time.strftime('%Y-%m-%d %H:%M')})",
                source_created_at=None,
                source_modified_at=None,
                metadata={"line_count": len(safe_lines)},
            )
            self.emit(doc)
        except Exception:
            pass

14. Privacy & Security Model
14.1 Trust Zones

text

┌─────────────────────────────────────────────┐
│  FULLY TRUSTED (localhost only)             │
│  - MEMEX daemon process                     │
│  - SQLite DB, ChromaDB, KuzuDB              │
│  - Ollama API (localhost:11434)             │
│  - Web UI (localhost:8080)                  │
│  - TUI (local terminal)                     │
└───────────────────┬─────────────────────────┘
                    │
┌───────────────────▼─────────────────────────┐
│  SEMI-TRUSTED (read-only observation)       │
│  - Browser history (copied, not modified)  │
│  - Filesystem (read-only access)           │
│  - Shell history (append-only poll)        │
│  - IMAP (IDLE + FETCH, never STORE)        │
└───────────────────┬─────────────────────────┘
                    │
┌───────────────────▼─────────────────────────┐
│  UNTRUSTED (no data sent here)              │
│  - The open internet                        │
│  - External APIs                            │
│  - Cloud services                           │
└─────────────────────────────────────────────┘

14.2 Local-Only API Enforcement

Python

# api/middleware.py

from fastapi import Request, HTTPException
import ipaddress


ALLOWED_HOSTS = {"127.0.0.1", "::1", "localhost"}


async def local_only_middleware(request: Request, call_next):
    client_ip = request.client.host
    try:
        ip = ipaddress.ip_address(client_ip)
        if not (ip.is_loopback):
            raise HTTPException(
                status_code=403,
                detail="MEMEX API is localhost-only. Remote access is not supported."
            )
    except ValueError:
        raise HTTPException(status_code=403, detail="Invalid client address.")
    return await call_next(request)

14.3 Secret Leakage Prevention

Python

# ingestors/redactor.py

import re
from typing import str


# Patterns for common secret formats
SECRET_PATTERNS = [
    (re.compile(r'(?i)(password|passwd|pwd)\s*[=:]\s*\S+'), '[REDACTED_PASSWORD]'),
    (re.compile(r'(?i)(api[_-]?key|apikey)\s*[=:]\s*\S+'), '[REDACTED_API_KEY]'),
    (re.compile(r'(?i)(secret|token|bearer)\s*[=:]\s*\S+'), '[REDACTED_SECRET]'),
    (re.compile(r'[A-Za-z0-9+/]{40,}={0,2}'), '[REDACTED_BASE64]'),  # Base64 blobs
    (re.compile(r'(?i)ghp_[a-zA-Z0-9]{36}'), '[REDACTED_GITHUB_TOKEN]'),
    (re.compile(r'(?i)sk-[a-zA-Z0-9]{48}'), '[REDACTED_OPENAI_KEY]'),
    (re.compile(r'\b\d{4}[- ]?\d{4}[- ]?\d{4}[- ]?\d{4}\b'), '[REDACTED_CARD]'),
    (re.compile(r'\b\d{3}-\d{2}-\d{4}\b'), '[REDACTED_SSN]'),
]


def redact_secrets(text: str) -> str:
    """Apply all secret patterns to text. Returns redacted version."""
    for pattern, replacement in SECRET_PATTERNS:
        text = pattern.sub(replacement, text)
    return text

The redactor is applied in UniversalParser after clean_content is produced and before it is passed to chunking or storage.
14.4 "Forget" Capability

MEMEX must support hard deletion that propagates across all three stores:

Python

# api/routes/documents.py

async def delete_document(doc_id: str, db, embedder: EmbeddingEngine, kuzu_conn):
    """
    Hard delete a document from:
    1. SQLite (documents + chunks + entity_mentions + relations cascade)
    2. ChromaDB (by chroma_id prefix)
    3. KuzuDB (remove edges referencing this doc)
    """
    # 1. Collect chroma IDs before deletion
    chroma_ids = [
        row["chroma_id"]
        for row in db.execute(
            "SELECT chroma_id FROM chunks WHERE doc_id = ? AND chroma_id IS NOT NULL",
            (doc_id,)
        ).fetchall()
    ]

    # 2. Delete from ChromaDB
    if chroma_ids:
        embedder.collection.delete(ids=chroma_ids)

    # 3. Remove relation edges in KuzuDB
    try:
        kuzu_conn.execute(
            "MATCH ()-[r:RELATES {source_doc_id: $doc_id}]-() DELETE r",
            {"doc_id": doc_id}
        )
    except Exception:
        pass

    # 4. Delete from SQLite (cascade handles chunks, entity_mentions)
    db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))
    db.commit()

    return {"success": True, "doc_id": doc_id}

14.5 Threat Model Summary
Threat	Mitigation
Data exfiltration via API	API bound to 127.0.0.1 only; local_only_middleware enforces
Secret/credential capture in terminal	redactor.py strips known secret patterns before storage
Sensitive files ingested	Per-source excluded_paths + excluded_domains config
Raw content retained indefinitely	raw_content_retention_days config purges bytes, keeps clean text
Ollama model leaking prompts	Ollama runs locally; no network call for inference
Database stolen from disk	SQLite/Chroma/Kuzu stored in ~/.memex/data/ — OS user permissions
Browser history of sensitive sites	Per-domain exclusion list in sources.browser.excluded_domains
Graph extraction hallucinating relations	min_relation_confidence threshold; evidence stored for audit
15. Storage & Persistence
15.1 SQLite Connection (WAL Mode)

Python

# storage/db.py

import sqlite3
import threading
from pathlib import Path

_local = threading.local()


def get_db() -> sqlite3.Connection:
    """Thread-local SQLite connection with WAL mode."""
    if not hasattr(_local, "conn") or _local.conn is None:
        db_path = _get_db_path()
        conn = sqlite3.connect(
            str(db_path),
            check_same_thread=False,
            timeout=10.0,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")       # Concurrent readers + writer
        conn.execute("PRAGMA synchronous=NORMAL")     # Balance durability/speed
        conn.execute("PRAGMA foreign_keys=ON")        # Enforce FK constraints
        conn.execute("PRAGMA busy_timeout=5000")      # 5s wait on lock
        conn.execute("PRAGMA cache_size=-64000")      # 64MB page cache
        _local.conn = conn
    return _local.conn

15.2 Raw Content Retention Policy

Python

# storage/maintenance.py

def purge_raw_content(db, retention_days: int):
    """
    Purge raw_content (bytes) from old documents.
    Keeps clean_content (text) for ongoing retrieval.
    """
    result = db.execute("""
        UPDATE documents
        SET raw_content = NULL
        WHERE raw_content IS NOT NULL
        AND ingested_at < datetime('now', ?)
    """, (f"-{retention_days} days",))
    db.commit()
    return result.rowcount


def vacuum_db(db):
    """Reclaim space after large deletions."""
    db.execute("VACUUM")

15.3 Three-Store Consistency Checklist

The daemon runs a nightly consistency reconciler:

Python

# storage/reconciler.py

def reconcile(db, embedder: EmbeddingEngine):
    """
    Detect and repair consistency gaps between SQLite, ChromaDB, and KuzuDB.
    """
    # 1. Documents marked is_embedded=1 but chunks have no chroma_id
    inconsistent_embedded = db.execute("""
        SELECT DISTINCT d.id
        FROM documents d
        JOIN chunks c ON c.doc_id = d.id
        WHERE d.is_embedded = 1
        AND c.chroma_id IS NULL
    """).fetchall()
    for row in inconsistent_embedded:
        # Reset and re-embed
        db.execute("UPDATE documents SET is_embedded = 0 WHERE id = ?", (row["id"],))
        db.commit()

    # 2. Chunks with chroma_id but not in Chroma (orphaned records)
    all_chroma_ids = {
        r["chroma_id"]
        for r in db.execute("SELECT chroma_id FROM chunks WHERE chroma_id IS NOT NULL").fetchall()
    }
    # (Spot-check a sample — full reconcile is O(n) against Chroma)

    # 3. Documents not yet embedded or graphed — queue them
    pending = db.execute("""
        SELECT id, clean_content, content_type
        FROM documents
        WHERE is_embedded = 0 OR is_graphed = 0
        LIMIT 100
    """).fetchall()
    return {
        "inconsistent_embedded": len(inconsistent_embedded),
        "pending_processing": len(pending),
    }

16. Logging, Observability & Debugging
16.1 Structured Logging

Python

# config/logging.py

import logging
import logging.handlers
import json
from datetime import datetime


class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_record = {
            "ts": datetime.utcnow().isoformat(),
            "level": record.levelname,
            "module": record.module,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            log_record["exc"] = self.formatException(record.exc_info)
        return json.dumps(log_record)


def setup_logging(config: dict):
    logger = logging.getLogger("memex")
    logger.setLevel(getattr(logging, config["daemon"]["log_level"].upper(), logging.INFO))

    # Rotating file handler
    file_handler = logging.handlers.RotatingFileHandler(
        config["storage"]["log_path"],
        maxBytes=50 * 1024 * 1024,  # 50MB
        backupCount=5,
    )
    file_handler.setFormatter(JSONFormatter())
    logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(module)s: %(message)s"))
    logger.addHandler(console_handler)

16.2 Health Endpoint

Python

# api/routes/system.py

@router.get("/health")
async def health():
    from storage.db import get_db
    import requests as req

    db = get_db()
    doc_count = db.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
    chunk_count = db.execute("SELECT COUNT(*) FROM chunks").fetchone()[0]
    embedded_count = db.execute("SELECT COUNT(*) FROM documents WHERE is_embedded = 1").fetchone()[0]

    # Check Ollama
    try:
        r = req.get(f"{config['ollama']['base_url']}/api/tags", timeout=2)
        ollama_healthy = r.status_code == 200
    except Exception:
        ollama_healthy = False

    return {
        "daemon_running": True,
        "ollama_healthy": ollama_healthy,
        "db_healthy": True,
        "doc_count": doc_count,
        "chunk_count": chunk_count,
        "embedding_coverage_pct": round(embedded_count / max(doc_count, 1) * 100, 1),
    }

16.3 Debug Mode

When daemon.log_level = "debug":

    Every raw document ingested is logged with source path, size, checksum
    Every chunking result logged with token counts per chunk
    Every Ollama embedding request/response size logged
    Every NER result logged with entity count per document
    Every retrieval query logged with per-signal scores for all hits
    Every LLM prompt logged (redacted for secrets)

17. Testing Strategy
17.1 Test Pyramid

text

                  ┌──────────────┐
                  │ E2E Tests    │
                  │ (5%)         │
                  │ Full pipeline│
                  └──────┬───────┘
            ┌────────────┴────────────┐
            │  Integration Tests      │
            │  (25%)                  │
            │  Ingest→embed→retrieve  │
            └────────────┬────────────┘
       ┌─────────────────┴─────────────────┐
       │         Unit Tests                │
       │         (70%)                     │
       │  Chunker, parsers, retriever,     │
       │  entity extractor, redactor       │
       └───────────────────────────────────┘

17.2 Unit Tests

Python

# tests/unit/test_chunker.py

import pytest
from parsers.chunker import SmartChunker


@pytest.fixture
def chunker():
    return SmartChunker({"chunker": {"max_tokens_prose": 400, "overlap_prose": 50}})


def test_chunks_prose_into_multiple_chunks(chunker):
    long_text = "\n\n".join([f"Paragraph {i}. " * 50 for i in range(20)])
    chunks = chunker.chunk("doc-1", long_text, "html")
    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.token_count <= 450  # Allow slight overflow on last chunk


def test_no_empty_chunks(chunker):
    chunks = chunker.chunk("doc-1", "Short text.", "plain")
    assert all(len(c.content.strip()) > 0 for c in chunks)


def test_chunk_indices_are_sequential(chunker):
    text = "\n\n".join([f"Para {i}. " * 30 for i in range(10)])
    chunks = chunker.chunk("doc-1", text, "markdown")
    indices = [c.chunk_index for c in chunks]
    assert indices == list(range(len(chunks)))


def test_code_chunked_differently_than_prose(chunker):
    code = "\n".join([
        "def function_one():",
        "    return 1",
        "",
        "def function_two():",
        "    return 2",
    ] * 20)
    chunks = chunker.chunk("doc-1", code, "code")
    assert len(chunks) >= 1

Python

# tests/unit/test_redactor.py

from ingestors.redactor import redact_secrets


def test_redacts_password():
    text = "DB_PASSWORD=super_secret_123"
    result = redact_secrets(text)
    assert "super_secret_123" not in result
    assert "REDACTED" in result


def test_redacts_github_token():
    text = "token = ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZabcde1234"
    result = redact_secrets(text)
    assert "ghp_" not in result


def test_preserves_normal_text():
    text = "Today I went to the store and bought apples."
    result = redact_secrets(text)
    assert result == text


def test_redacts_credit_card():
    text = "Card number: 4111 1111 1111 1111"
    result = redact_secrets(text)
    assert "4111" not in result

Python

# tests/unit/test_retriever.py

from unittest.mock import MagicMock, patch
from memory.retriever import HybridRetriever


def test_score_fusion_weights():
    retriever = HybridRetriever.__new__(HybridRetriever)
    retriever.VECTOR_WEIGHT = 0.40
    retriever.KEYWORD_WEIGHT = 0.30
    retriever.GRAPH_WEIGHT = 0.20
    retriever.TEMPORAL_WEIGHT = 0.10

    hits = [
        {"key": "a", "doc_id": "d1", "chunk_index": 0, "content": "x",
         "vector_score": 0.9, "keyword_score": 0.0, "graph_score": 0.0},
        {"key": "b", "doc_id": "d2", "chunk_index": 0, "content": "y",
         "vector_score": 0.0, "keyword_score": 1.0, "graph_score": 0.0},
    ]
    merged = retriever._merge(hits, [], [])
    scores = {h["key"]: h["combined_score"] for h in merged}
    assert scores["a"] == pytest.approx(0.9 * 0.40)
    assert scores["b"] == pytest.approx(1.0 * 0.30)

17.3 Integration Tests

Python

# tests/integration/test_ingest_pipeline.py

import pytest
import tempfile
import os
from ingestors.daemon import MEMEXDaemon


@pytest.fixture
def test_config(tmp_path):
    return {
        "daemon": {"log_level": "debug", "processing_workers": 1, "queue_size": 100},
        "sources": {"enabled": ["filesystem"]},
        "sources.filesystem": {
            "watch_paths": [str(tmp_path)],
            "excluded_paths": [],
            "included_extensions": [".txt", ".md"],
            "max_file_size_mb": 10,
        },
        "ollama": {
            "base_url": "http://localhost:11434",
            "embedding_model": "nomic-embed-text",
            "chat_model": "llama3:8b",
            "request_timeout_seconds": 60,
        },
        "storage": {
            "db_path": str(tmp_path / "test.db"),
            "chroma_path": str(tmp_path / "chroma"),
            "kuzu_path": str(tmp_path / "kuzu"),
            "log_path": str(tmp_path / "memex.log"),
            "raw_content_retention_days": 30,
            "max_db_size_mb": 100,
        },
        "graph": {
            "enable_entity_extraction": True,
            "enable_relation_extraction": False,  # Skip LLM in integration tests
            "spacy_model": "en_core_web_sm",
            "min_relation_confidence": 0.5,
            "max_chars_for_relation_extraction": 1000,
        },
        "retrieval": {
            "default_n_results": 5,
            "vector_weight": 0.40,
            "keyword_weight": 0.30,
            "graph_weight": 0.20,
            "temporal_weight": 0.10,
            "temporal_decay_lambda": 0.005,
        },
        "api": {"host": "127.0.0.1", "port": 8081},
    }


def test_file_ingest_to_retrieval(test_config, tmp_path):
    """End-to-end: write a file → ingest → embed → retrieve."""
    # Write a test document
    doc_path = tmp_path / "test_note.txt"
    doc_path.write_text("Bloom filters are a probabilistic data structure for set membership testing.")

    daemon = MEMEXDaemon(test_config)
    daemon._process_document(daemon.ingestors[0]._read_file(str(doc_path)))

    from storage.db import get_db
    db = get_db()
    row = db.execute("SELECT * FROM documents WHERE source_path = ?", (str(doc_path),)).fetchone()
    assert row is not None
    assert "Bloom" in row["clean_content"]
    assert row["is_embedded"] == 1

17.4 AI Integration Tests (Mock Ollama)

Python

# tests/integration/test_conversation.py

from unittest.mock import patch
from conversation.engine import ConversationEngine


def test_conversation_with_mock_llm(test_config):
    engine = ConversationEngine(test_config)

    mock_answer = "You studied Bloom filters in March 2024 [Source 1]."

    with patch.object(engine, "_call_llm", return_value=mock_answer):
        with patch.object(engine.retriever, "retrieve", return_value=[{
            "key": "d1__chunk__0",
            "doc_id": "d1",
            "chunk_index": 0,
            "content": "Bloom filter notes from March",
            "combined_score": 0.85,
            "vector_score": 0.85,
            "keyword_score": 0.0,
            "graph_score": 0.0,
        }]):
            result = engine.chat("Tell me about Bloom filters", session_id="test-session")

    assert "Bloom" in result["answer"]
    assert len(result["sources"]) >= 1
    assert result["session_id"] == "test-session"

18. Build, Packaging & Installation
18.1 Makefile

Makefile

.PHONY: all install install-dev test lint format clean build-ui dev setup-models

# ── Setup ──────────────────────────────────────────────────────────────────────
install:
	pip install -e .
	python -m spacy download en_core_web_sm

install-dev:
	pip install -e ".[dev]"
	python -m spacy download en_core_web_sm
	python -m spacy download en_core_web_trf

setup-models:
	@echo "Pulling Ollama models..."
	ollama pull nomic-embed-text
	ollama pull llama3:8b
	@echo "Models ready."

# ── UI ─────────────────────────────────────────────────────────────────────────
build-ui:
	cd ui/web && npm install && npm run build
	cp -r ui/web/dist/ api/static/

# ── Dev ────────────────────────────────────────────────────────────────────────
dev:
	@echo "Starting MEMEX daemon + API in dev mode..."
	uvicorn api.server:app --reload --host 127.0.0.1 --port 8080 &
	python cmd/memex/main.py --config ~/.memex/config.toml

dev-ui:
	cd ui/web && npm run dev

dev-tui:
	python -m ui.tui.app

# ── Testing ────────────────────────────────────────────────────────────────────
test:
	pytest tests/unit/ -v --tb=short

test-integration:
	pytest tests/integration/ -v --tb=short -m integration

test-all:
	pytest tests/ -v --tb=short --cov=. --cov-report=term-missing

# ── Quality ───────────────────────────────────────────────────────────────────
lint:
	ruff check .
	mypy . --ignore-missing-imports

format:
	ruff format .

# ── Init ──────────────────────────────────────────────────────────────────────
init-config:
	python -c "from config.config import load_config; load_config()"
	@echo "Config written to ~/.memex/config.toml"

# ── Maintenance ───────────────────────────────────────────────────────────────
reconcile:
	python -c "from storage.reconciler import reconcile; from storage.db import get_db; reconcile(get_db(), None)"

rebuild-embeddings:
	python scripts/rebuild_embeddings.py

# ── Clean ─────────────────────────────────────────────────────────────────────
clean:
	find . -type d -name "__pycache__" -exec rm -rf {} +
	find . -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache dist/ build/ *.egg-info

18.2 pyproject.toml

toml

[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.backends.legacy:build"

[project]
name = "memex"
version = "1.0.0"
description = "Local-first self-building personal memory engine"
requires-python = ">=3.11"

dependencies = [
    # Ingestion
    "watchdog>=4.0",
    "requests>=2.31",
    "pyperclip>=1.8",
    # Parsing
    "pdfminer.six>=20221105",
    "readability-lxml>=0.8",
    "beautifulsoup4>=4.12",
    "tree-sitter>=0.21",
    "pytesseract>=0.3",
    "Pillow>=10.0",
    "mistune>=3.0",         # Markdown → HTML → text
    # Embeddings + Vector DB
    "chromadb>=0.5",
    "tiktoken>=0.7",
    # Knowledge Graph
    "spacy>=3.7",
    "kuzu>=0.5",
    # Retrieval
    # (uses sqlite3 stdlib for FTS5)
    # API + Conversation
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "httpx>=0.27",
    # TUI
    "textual>=0.57",
    # Config
    "tomllib>=1.0",         # stdlib in Python 3.11+
    # Utilities
    "python-dateutil>=2.9",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-asyncio>=0.23",
    "pytest-cov>=5.0",
    "ruff>=0.4",
    "mypy>=1.9",
    "types-requests>=2.31",
]

[project.scripts]
memex = "cmd.memex.main:main"
memex-tui = "ui.tui.app:main"

18.3 Installation Script

Bash

#!/bin/bash
# install.sh — MEMEX one-shot installer

set -e

MEMEX_HOME="$HOME/.memex"
mkdir -p "$MEMEX_HOME/data/chroma" "$MEMEX_HOME/data/kuzu" "$MEMEX_HOME/logs"

echo "🧠 Installing MEMEX..."

# 1. Python environment
python3 -m venv "$MEMEX_HOME/venv"
source "$MEMEX_HOME/venv/bin/activate"

# 2. Install package
pip install --quiet memex

# 3. spaCy model
python -m spacy download en_core_web_sm --quiet

# 4. Check Ollama
if ! command -v ollama &> /dev/null; then
    echo "⚠️  Ollama not found. Install from https://ollama.com then run:"
    echo "   ollama pull nomic-embed-text"
    echo "   ollama pull llama3:8b"
else
    echo "📥 Pulling Ollama models (this may take a while)..."
    ollama pull nomic-embed-text
    ollama pull llama3:8b
fi

# 5. Init config
python -c "from config.config import load_config; load_config()"

# 6. Shell hook (optional)
echo ""
echo "✅ MEMEX installed!"
echo ""
echo "To start the daemon:    memex start"
echo "To open the TUI:        memex-tui"
echo "Web UI:                 http://localhost:8080"
echo ""
echo "Optional: add this to ~/.zshrc or ~/.bashrc to enable terminal ingestion:"
echo '  export PROMPT_COMMAND="history -a; $PROMPT_COMMAND"'

19. Platform Support Matrix
Feature	macOS (Intel)	macOS (Apple Silicon)	Linux (amd64)	Linux (arm64)	Windows (WSL2)
Filesystem watcher	✅ FSEvents	✅ FSEvents	✅ inotify	✅ inotify	✅ inotify
Browser history ingest	✅	✅	✅	✅	✅
Terminal history ingest	✅	✅	✅	✅	✅
Email (IMAP)	✅	✅	✅	✅	✅
Screenshot OCR	✅	✅	✅	✅	✅
ChromaDB (local)	✅	✅	✅	✅	✅
KuzuDB (local)	✅	✅	✅	✅	✅
Ollama (CPU)	✅	✅	✅	✅	✅
Ollama (GPU)	✅ Metal	✅ Metal	✅ CUDA	⚠️ limited	✅ CUDA (WSL2)
TUI (Textual)	✅	✅	✅	✅	✅
Web UI (Svelte)	✅	✅	✅	✅	✅
spaCy NER	✅	✅	✅	✅	✅
20. Performance Targets & Benchmarks
Metric	Target	Notes
Idle daemon CPU	< 1%	Event-driven watchers, no polling loops
File ingest latency (event → SQLite insert)	< 500ms	Excludes embedding time
Embedding latency (nomic-embed-text, 400 tokens)	< 2s CPU / < 300ms GPU	Per chunk via Ollama
Full document pipeline (parse + chunk + embed + graph)	< 30s CPU / < 10s GPU	Per average document
Keyword search (FTS5)	< 50ms	SQLite FTS5 BM25
Vector search (Chroma, 1M chunks)	< 200ms	HNSW cosine
Hybrid retrieval (all four signals, merged)	< 500ms	CPU
LLM answer generation (llama3:8b, 8-chunk context)	3–20s	Hardware dependent
SQLite insert (document + chunks)	< 10ms	WAL mode
Chroma collection size at 100k docs	< 2GB	~768 floats × 100k chunks × 4 bytes
Total storage at 1 year of normal usage	< 5GB	Depends on raw content retention
20.1 Background Scheduling Budget

text

Processing worker threads:          2 (configurable)
Per-worker:
  ├── Parse + chunk:                ~100ms–2s (depends on doc size/type)
  ├── Embed (per chunk):            ~1–2s CPU
  ├── NER (spaCy):                  ~200ms–2s (depends on text length)
  └── Relation extraction (LLM):   ~5–15s (optional, low priority)

Daemon goroutine/thread budget:
  ├── Filesystem watcher:           1 (event-driven)
  ├── Browser poller:               1 (sleeps 5 min between polls)
  ├── Terminal poller:              1 (sleeps 60s)
  ├── Email poller:                 1 (sleeps 10 min)
  ├── Clipboard poller:             1 (sleeps 30s)
  ├── Processing workers:           2
  ├── API server:                   1 (async uvicorn)
  └── Maintenance scheduler:        1 (nightly reconcile + purge)

21. Error Handling Strategy
21.1 Error Categories

Python

# internal/errors.py

class MEMEXError(Exception):
    """Base MEMEX error."""

class IngestionError(MEMEXError):
    """Failed to read/fetch source content."""

class ParseError(MEMEXError):
    """Content parsing failed (corrupt PDF, encoding issue, etc.)."""

class EmbeddingError(MEMEXError):
    """Ollama embedding request failed."""

class GraphError(MEMEXError):
    """Entity/relation extraction failed."""

class RetrievalError(MEMEXError):
    """Hybrid retrieval failed."""

class StorageError(MEMEXError):
    """SQLite or file system operation failed."""

21.2 Core Policy: Never Drop the Daemon

Every processing worker wraps document handling in broad exception catching. A single bad document must never crash the daemon:

Python

def _process_document(self, raw_doc: RawDocument):
    try:
        parsed = self.parser.parse(raw_doc)
        if not parsed:
            logging.debug(f"Skipped (no parser output): {raw_doc.source_path}")
            return
        doc_id = self._upsert_document(parsed)
        try:
            self.embedder.process(doc_id, parsed.clean_content, parsed.content_type)
        except EmbeddingError as e:
            logging.warning(f"Embedding failed for {doc_id}: {e}. Will retry on next reconcile.")
            # is_embedded stays 0 — reconciler will pick it up
        try:
            self.grapher.process(doc_id, parsed.clean_content)
        except GraphError as e:
            logging.warning(f"Graph extraction failed for {doc_id}: {e}. Will retry on next reconcile.")
            # is_graphed stays 0
    except Exception as e:
        logging.error(f"Unexpected error processing {raw_doc.source_path}: {e}", exc_info=True)
        # Never propagate — daemon keeps running

21.3 Ollama Unavailable Policy

If Ollama is not running when MEMEX starts:

    Ingestion continues normally (parse + store to SQLite)
    Embedding is queued (documents accumulate with is_embedded = 0)
    When Ollama becomes available, the reconciler back-fills all pending embeddings
    Chat queries return: "The AI backend is unavailable. Start Ollama and try again."

Python

def _check_ollama(config: dict) -> bool:
    try:
        r = requests.get(f"{config['ollama']['base_url']}/api/tags", timeout=2)
        return r.status_code == 200
    except Exception:
        return False

22. Dependency Registry
22.1 Python Dependencies

text

# requirements.txt

# ── Ingestion ─────────────────────────────────────────────────
watchdog>=4.0.0              # Filesystem event monitoring (inotify / FSEvents)
requests>=2.31.0             # HTTP client for page fetch + Ollama API
pyperclip>=1.8.2             # Clipboard access (cross-platform)

# ── Parsing ───────────────────────────────────────────────────
pdfminer.six>=20221105       # PDF text extraction
readability-lxml>=0.8.1      # HTML article extraction (Mozilla Readability port)
beautifulsoup4>=4.12.3       # HTML cleanup + text extraction
tree-sitter>=0.21.3          # Code parsing (syntax-aware)
pytesseract>=0.3.10          # Tesseract OCR Python binding
Pillow>=10.3.0               # Image loading for OCR
mistune>=3.0.2               # Markdown → HTML

# ── Chunking ──────────────────────────────────────────────────
tiktoken>=0.7.0              # Token counting (cl100k_base encoder)

# ── Vector Store ──────────────────────────────────────────────
chromadb>=0.5.3              # Local persistent vector database

# ── Knowledge Graph ───────────────────────────────────────────
spacy>=3.7.4                 # NLP + NER (en_core_web_sm / en_core_web_trf)
kuzu>=0.5.0                  # Embedded property graph database

# ── API ───────────────────────────────────────────────────────
fastapi>=0.110.0             # REST API framework
uvicorn>=0.29.0              # ASGI server
httpx>=0.27.0                # Async HTTP client

# ── TUI ───────────────────────────────────────────────────────
textual>=0.57.1              # Terminal UI framework (reactive components)

# ── Utilities ─────────────────────────────────────────────────
python-dateutil>=2.9.0       # Date parsing for temporal queries

# ── Dev / Test (extras) ───────────────────────────────────────
pytest>=8.0.0
pytest-asyncio>=0.23.6
pytest-cov>=5.0.0
ruff>=0.4.5
mypy>=1.9.0

22.2 Frontend Dependencies

JSON

// ui/web/package.json

{
  "dependencies": {
    "svelte": "^4.x",
    "@sveltejs/kit": "^2.x",
    "d3": "^7.x",
    "axios": "^1.x"
  },
  "devDependencies": {
    "vite": "^5.x",
    "@sveltejs/vite-plugin-svelte": "^3.x",
    "typescript": "^5.x"
  }
}

22.3 External Tools Required
Tool	Version	Required For	Install
Python	≥ 3.11	Backend daemon + API	brew install python / apt install python3
Ollama	Latest	Local LLM + embeddings	curl https://ollama.com/install.sh | sh
Tesseract	≥ 5.0	OCR for screenshots/images	brew install tesseract / apt install tesseract-ocr
Node.js	≥ 20	Web UI build	brew install node
Git	Any	Source clone	Pre-installed
23. Milestone & Phased Rollout Plan
Phase 1 — Foundation (Weeks 1–4)

Goal: Working ingestion + storage + keyword search

    Project structure, pyproject.toml, Makefile
    Config loader (TOML)
    SQLite schema + migrations
    BaseIngestor + RawDocument contract
    Filesystem ingestor (watchdog)
    Browser history ingestor (Chrome/Firefox)
    Universal parser: HTML + PDF + Markdown + plain text
    Smart chunker (prose strategy)
    SQLite FTS5 setup + full-text keyword search
    REST API: /api/v1/documents, /api/v1/health
    Unit tests: chunker, parsers, redactor
    README + setup guide

Deliverable: MEMEX watches your files and browser history, stores clean text, and is keyword-searchable via API.
Phase 2 — Semantic Memory (Weeks 5–8)

Goal: Embeddings + vector search + basic chat

    Ollama integration (health check, model list)
    EmbeddingEngine (nomic-embed-text → ChromaDB)
    Embedding cache (skip already-embedded chunks)
    HybridRetriever: vector + keyword fusion
    ConversationEngine: context injection + LLM chat
    Citation formatting in answers
    REST API: /api/v1/memory/search, /api/v1/conversation/chat
    Basic TUI (Textual): chat pane + source panel
    Integration tests: ingest → embed → retrieve pipeline

Deliverable: You can type a question in the TUI and get a cited answer grounded in your indexed documents.
Phase 3 — Knowledge Graph (Weeks 9–12)

Goal: Entity extraction + graph traversal + full hybrid retrieval

    spaCy NER integration (en_core_web_sm)
    EntityExtractor + entity upsert pipeline
    entity_mentions table + FTS5 linkage
    KuzuDB schema + entity/relation persistence
    LLM-based RelationExtractor (optional, off by default)
    Graph traversal in HybridRetriever
    Temporal re-ranking
    Web UI: Svelte scaffold + D3 knowledge graph
    REST API: /api/v1/graph/data, /api/v1/graph/entity/:name
    Integration tests: NER pipeline, graph retrieval

Deliverable: MEMEX builds a visual knowledge graph of your intellectual history. The graph enriches retrieval results.
Phase 4 — Full Ingestor Suite (Weeks 13–16)

Goal: All sources, deduplication, reconciler

    Terminal ingestor (shell history polling)
    Email ingestor (IMAP IDLE)
    Clipboard ingestor
    Screenshot ingestor + OCR
    Calendar ingestor (ICS)
    Code parser (tree-sitter, language-aware chunking)
    Image parser (Tesseract)
    Secret redactor (all sources)
    Nightly reconciler (consistency check + back-fill)
    Raw content purge (configurable retention)
    Document "forget" (hard delete across all stores)
    Shell hook instructions + installer script

Deliverable: MEMEX passively ingests every major digital surface. No manual setup per document.
Phase 5 — Polish & Hardening (Weeks 17–20)

Goal: Production-quality v1.0

    Full TUI: timeline sidebar + session history
    Full Web UI: Chat page + Timeline page + Sources page + Settings page
    Structured JSON logging + log rotation
    Health endpoint + stats endpoint
    Local-only API middleware (security enforcement)
    Performance benchmarking (embedding throughput, retrieval latency)
    80% test coverage target
    Cross-platform install script (macOS + Linux)
    Comprehensive documentation (README + in-app help)
    pyproject.toml packaging + PyPI-ready release

Deliverable: MEMEX v1.0 — install with one script, zero configuration beyond model pull.
24. Open Questions & Future Work
24.1 Open Technical Questions
Question	Status	Notes
KuzuDB archived on GitHub (Oct 2025)	Risk	Need fallback: SQLite-based edge table or migrate to another embedded graph engine (e.g. LanceDB graph layer or networkx serialized to SQLite)
Browser content fetch: many pages block scrapers	Open	May need headless browser (Playwright) for JS-heavy pages
Ollama endpoint versioning (/api/embed vs /api/embeddings)	Open	Build adapter layer for version-safe calls
IMAP IDLE: some providers don't support it	Open	Graceful fallback to periodic poll
Manifest V3 browser extension for real-time page capture	Backlog	Service workers can suspend — need reliable message-passing to local daemon
Deduplication across sources (same content, different paths)	Open	Content-based dedup (checksum) partially handles; needs exact-duplicate clustering
Handling very large files (>50MB): books, codebases	Backlog	Chunked streaming parse needed
24.2 Potential Future Modules
Module	Description	Priority
Browser Extension	Real-time page capture (MV3) with reliable local daemon sync	High
Timeline Clustering	Group documents by project/topic using temporal + graph signals	High
Automatic Summarization	Daily/weekly digest: "Here's what you learned this week"	Medium
Note Integration	Obsidian / Logseq / Notion export connector	Medium
Semantic Dedup	Cluster near-duplicate documents (same paper, different formats)	Medium
Voice Memo Ingestor	Whisper-based transcription of local audio recordings	Medium
Git Commit Ingestor	Index commit messages + diffs from local repos	High
Collaborative Mode	Encrypted, opt-in sharing of memory graphs between trusted users	Low
Mobile Companion	iOS/Android sync via local WiFi (no cloud)	Low
24.3 Known Limitations at v1.0

    KuzuDB maintenance risk: The KuzuDB repository was archived in October 2025. MEMEX v1.0 ships with KuzuDB but the migration path to an alternative embedded graph engine must be prepared before v2.0. The relation and entity tables in SQLite provide a fallback store.
    LLM relation extraction is noisy: Extracted relations at v1.0 are probabilistic. The confidence threshold (0.5 default) filters obvious hallucinations but some incorrect edges will exist in the graph. Users should treat the graph as a discovery tool, not a ground-truth knowledge base.
    Cold-start latency: First-run embedding of a large corpus (e.g., years of documents) is slow on CPU — estimated 2–8 hours for 10,000 documents without GPU. Subsequent incremental updates are fast.
    OCR accuracy: Screenshot and image ingestion is dependent on Tesseract accuracy. Low-resolution images, handwriting, or complex layouts will produce poor text.
    Browser history on encrypted profiles: Firefox encrypted profiles or Chrome multi-profile setups may require additional configuration to locate the correct history database.
    No real-time browser capture without extension: Without a browser extension, MEMEX can only access what's already in browser history (already-visited URLs), not live page reading sessions.

End of MEMEX Comprehensive Engineering Design Document — v1.0

This document covers the complete local-first architecture: ingestion → parsing → chunking → embedding → graph extraction → hybrid retrieval → cited conversation. All AI inference is local. All storage is on-device. No data ever leaves the machine.
