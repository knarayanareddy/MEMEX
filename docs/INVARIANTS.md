# Invariant Reference (INV-001 to INV-030)

> The 30 invariant tests are the backbone of MEMEX's correctness guarantees.
> Every PR must pass all 30 invariants before merging.

---

## Overview

Invariants are **blocking tests** — they enforce critical system properties that must never be violated. Unlike regular unit tests that check specific features, invariants enforce fundamental constraints on the system's behavior.

**Location**: `tests/invariants/`

**Run**: `pytest tests/invariants/ -v`

---

## INV-001 to INV-004: Security Invariants

**File**: `tests/invariants/test_security.py`

| ID | Invariant | What it verifies |
|----|-----------|-----------------|
| INV-001 | Loopback middleware exists | `LoopbackOnlyMiddleware` class is importable and registered |
| INV-002 | Non-loopback rejected, loopback allowed | Requests from `192.168.x.x` get 403; `127.0.0.1` and `::1` get 200 |
| INV-003 | Ollama URL is localhost-only | Default `ollama_base_url` contains `127.0.0.1`, no external domains |
| INV-004 | API host is loopback | `api_host` is `127.0.0.1`, never `0.0.0.0` |

---

## INV-005 to INV-006: Redaction Invariants

**File**: `tests/invariants/test_redaction.py`

| ID | Invariant | What it verifies |
|----|-----------|-----------------|
| INV-005 | All patterns redact fixtures | Every regex in `redaction_patterns.toml` correctly redacts its `test_fixture` |
| INV-005 | Individual pattern tests | OpenAI key, GitHub PAT, AWS key, private key, bearer token, DB string all redacted |
| INV-005 | Multiple secrets in one text | All secrets are redacted when multiple appear in the same string |
| INV-005 | Empty string handled | Empty string doesn't crash the redactor |
| INV-005 | Excluded domains loaded | Browser excluded domains list is loaded from Addendum D |
| INV-006 | No false positives | Innocuous text like "asking a question" is never redacted |

---

## INV-007 to INV-012: Forget Invariants

**File**: `tests/invariants/test_forget.py`

| ID | Invariant | What it verifies |
|----|-----------|-----------------|
| INV-007 | Chroma deletion | After forget, zero vectors remain for the document |
| INV-008 | SQLite chunks deleted | After forget, zero chunks remain in SQLite |
| INV-009 | Entity mentions deleted | After forget, all entity mentions are removed |
| INV-010 | Document not retrievable | After forget, `get_document()` returns `None` |
| INV-011 | Audit log with correct flags | Forget audit log entry is written with `chroma_verified=1`, `kuzu_verified=1`, `sqlite_verified=1` |
| INV-012 | Bulk forget by source type | Bulk forget removes all documents of a given `source_type` |

---

## INV-013 to INV-017: Ingestion Invariants

**File**: `tests/invariants/test_ingestion.py`

| ID | Invariant | What it verifies |
|----|-----------|-----------------|
| INV-013 | Deduplication by checksum | Duplicate checksum returns `None`; document count unchanged |
| INV-013 | Different checksum accepted | Different checksum creates a new document |
| INV-014 | Excluded domains enforced | Banking, password managers, SSO, localhost domains are skipped |
| INV-014 | Normal domains allowed | github.com, stackoverflow.com, docs.python.org are NOT skipped |
| INV-015 | Queue backpressure | Queue drops items when full and increments `dropped_count` |
| INV-016 | Parse failure isolation | Failed parse sets status to `PARSE_FAILED`; empty content sets `EMPTY` |
| INV-017 | Ollama unavailability | Embedding returns `None` (not crash) when Ollama is down; detection works |

---

## INV-018 to INV-024: Retrieval Invariants

**File**: `tests/invariants/test_retrieval.py`

| ID | Invariant | What it verifies |
|----|-----------|-----------------|
| INV-018 | Score descending order | Hybrid retrieval `_fuse_scores()` produces results sorted by combined score descending |
| INV-019 | Time filter correctness | Filter `after:X` excludes documents captured before `X` |
| INV-020 | Weight sum = 1.0 | `vector + keyword + graph + temporal == 1.0` exactly (within 1e-10) |
| INV-021 | Temporal decay monotonic | `exp(-λ × age_days)` decreases monotonically with age |
| INV-022 | Temporal decay range | `exp(-λ × age_days)` is always in range [0.0, 1.0] for all reasonable ages |
| INV-023 | Chunking budgets positive | All token budgets in `chunking.toml` are ≥ 0 |
| INV-024 | Context window sane | `max_context_tokens > 0` and `conversation_history_turns > 0` |

---

## INV-025 to INV-030: Config Hygiene Invariants

**File**: `tests/invariants/test_config_hygiene.py`

| ID | Invariant | What it verifies |
|----|-----------|-----------------|
| INV-025 | No hardcoded retrieval weights | Weight values (0.40, 0.30, etc.) not in source outside config loading |
| INV-026 | No hardcoded retention days | `purge_after_days` not hardcoded outside config |
| INV-027 | No hardcoded chunk budgets | `prose_tokens` and similar not hardcoded outside config |
| INV-028 | Model name is config-driven | `Settings.embed_model` comes from config, is a non-empty string |
| INV-029 | Chroma metadata includes model | `embed_and_store()` includes `embed_model` and `embed_model_version` in metadata |
| INV-030 | All addenda parse | Every TOML file in `memex/config/` exists and parses without error |

---

## ID-to-Test Mapping

This table shows the exact mapping between INV IDs and test functions:

| INV ID | Test File | Test Function |
|--------|-----------|---------------|
| INV-001 | `test_security.py` | `test_inv001_loopback_middleware_exists` |
| INV-002 | `test_security.py` | `test_inv002_non_loopback_rejected`, `test_inv002_loopback_allowed`, `test_inv002_ipv6_loopback_allowed` |
| INV-003 | `test_security.py` | `test_inv003_ollama_base_url_is_localhost`, `test_inv003_no_external_urls_in_config` |
| INV-004 | `test_security.py` | `test_inv004_api_host_is_loopback` |
| INV-005 | `test_redaction.py` | `test_inv005_all_patterns_redact_fixtures`, `test_inv005_*_redaction`, etc. |
| INV-006 | `test_redaction.py` | `test_inv006_no_false_positives`, `test_inv006_innocuous_text_unchanged` |
| INV-007 | `test_forget.py` | `test_inv007_chroma_deletion` |
| INV-008 | `test_forget.py` | `test_inv008_sqlite_chunks_deleted` |
| INV-009 | `test_forget.py` | `test_inv009_entity_mentions_deleted` |
| INV-010 | `test_forget.py` | `test_inv010_document_not_in_search` |
| INV-011 | `test_forget.py` | `test_inv011_forget_audit_log` |
| INV-012 | `test_forget.py` | `test_inv012_bulk_forget_by_source` |
| INV-013 | `test_ingestion.py` | `test_inv013_duplicate_checksum_rejected`, etc. |
| INV-014 | `test_ingestion.py` | `test_inv014_*_domains_excluded`, `test_inv014_normal_domains_allowed` |
| INV-015 | `test_ingestion.py` | `test_inv015_queue_drop_when_full`, `test_inv015_dropped_count_increments` |
| INV-016 | `test_ingestion.py` | `test_inv016_parse_failure_marks_status`, `test_inv016_empty_content_marks_empty` |
| INV-017 | `test_ingestion.py` | `test_inv017_embedder_handles_unavailable`, `test_inv017_ollama_unavailable_detected` |
| INV-018 | `test_retrieval.py` | `test_inv018_score_ordering` |
| INV-019 | `test_retrieval.py` | `test_inv019_time_filter_after` |
| INV-020 | `test_retrieval.py` | `test_inv020_weights_sum_to_one` |
| INV-021 | `test_retrieval.py` | `test_inv021_temporal_decay_monotonically_decreasing` |
| INV-022 | `test_retrieval.py` | `test_inv022_temporal_decay_range` |
| INV-023 | `test_retrieval.py` | `test_inv023_chunking_budgets_are_positive` |
| INV-024 | `test_retrieval.py` | `test_inv024_context_window_sane` |
| INV-025 | `test_config_hygiene.py` | `test_inv025_no_hardcoded_weights` |
| INV-026 | `test_config_hygiene.py` | `test_inv026_no_hardcoded_retention_days` |
| INV-027 | `test_config_hygiene.py` | `test_inv027_no_hardcoded_chunk_budgets` |
| INV-028 | `test_config_hygiene.py` | `test_inv028_model_name_config_driven` |
| INV-029 | `test_config_hygiene.py` | `test_inv029_chroma_metadata_includes_model` |
| INV-030 | `test_config_hygiene.py` | `test_inv030_addenda_files_exist_and_parse` |

---

## Writing New Invariants

When adding a new system property that must always hold:

1. Assign the next sequential INV-NNN number
2. Add the test to the appropriate file in `tests/invariants/`
3. Update this document's tables
4. Use the `@pytest.mark.invariant` marker
5. Name the test function `test_invNNN_descriptive_name`

```python
import pytest

@pytest.mark.invariant
def test_inv031_my_new_invariant():
    """INV-031: Description of what this enforces."""
    # Setup
    # Exercise
    # Assert
```

---

*This document is the canonical reference for invariant IDs. Test function names must match the IDs documented here.*
