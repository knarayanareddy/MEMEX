"""
MEMEX Invariant Test Suite.

These tests verify the system properties that must always hold.
Any test marked with @invariant("INV-XXX") that fails blocks the PR merge.

Canonical list: tests/invariants/__init__.py (Addendum E)
"""

BLOCKING_INVARIANTS = [
    "INV-001", "INV-002", "INV-003", "INV-004",  # Security
    "INV-005", "INV-006", "INV-007",               # Redaction + purge
    "INV-008", "INV-009", "INV-010", "INV-011",    # Forget completeness
    "INV-012", "INV-013",                           # Forget audit
    "INV-014", "INV-015",                           # Citation validity
    "INV-016", "INV-017", "INV-018", "INV-019",    # Retrieval math
    "INV-020", "INV-021", "INV-022",               # Ingestion
    "INV-023", "INV-024", "INV-025",               # Failure handling
    "INV-026", "INV-027", "INV-028", "INV-029", "INV-030",  # Config hygiene
]
