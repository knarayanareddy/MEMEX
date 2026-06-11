# Security Policy

## Reporting a Vulnerability

We take security seriously. If you discover a vulnerability in MEMEX, please report it responsibly.

### How to Report

1. **Do not** open a public GitHub issue for security vulnerabilities
2. Email security reports to the repository maintainer via GitHub's private vulnerability reporting
3. Include:
   - Description of the vulnerability
   - Steps to reproduce
   - Affected versions
   - Potential impact
   - Suggested fix (if available)

### Response Timeline

| Timeframe | Action |
|-----------|--------|
| 48 hours | Acknowledge receipt of report |
| 7 days | Initial assessment and severity classification |
| 30 days | Fix development and testing |
| 45 days | Public disclosure (after fix is released) |

---

## Security Model

MEMEX is designed with a **zero-trust-external** security model:

### Core Principles

1. **No outbound connections** — MEMEX never transmits data to external servers
2. **No telemetry** — Zero analytics, zero tracking, zero phone-home
3. **Local-only API** — All endpoints bound to `127.0.0.1:7700`
4. **Secret redaction** — Sensitive data is scrubbed before storage
5. **Hard forget** — Complete, verifiable deletion across all stores
6. **Audit logging** — Every forget operation is recorded

### Trust Zones

| Zone | Components | Trust Level |
|------|-----------|-------------|
| Zone 1 | MEMEX daemon, local stores, Ollama, UI | Fully trusted |
| Zone 2 | Browser DB, filesystem, terminal history | Semi-trusted (read-only) |
| Zone 3 | External services | Untrusted — no data transmitted |

### Network Security

- **API**: Bound to `127.0.0.1:7700` — `LoopbackOnlyMiddleware` rejects all non-loopback requests
- **Docker**: Ports bind to `127.0.0.1:7700:7700` — not `0.0.0.0`
- **Ollama**: Communicates via `http://127.0.0.1:11434` — localhost only
- **No CORS**: API is same-origin only

### Secret Redaction

Before any content is stored, the `Redactor` applies:

1. **7 regex patterns** — OpenAI keys, GitHub PATs, AWS keys, private keys, bearer tokens, DB strings, credit cards
2. **Shannon entropy heuristic** — Catches unknown high-entropy strings (≥4.5 bits/char, ≥20 chars) when context contains key/secret/password words
3. **22 excluded browser domains** — Banking, password managers, SSO, email, health, and messaging sites are never fetched

### Hard Forget Protocol

The 10-step atomic forget protocol ensures complete data deletion:

1. Fetch all chunk IDs for the document
2. Delete vectors from ChromaDB
3. Delete graph nodes from KuzuDB
4. Delete entity mentions from SQLite
5. Delete relations from SQLite
6. Delete chunks from SQLite
7. Delete document row from SQLite
8. FTS auto-updates via triggers
9. Orphan entity cleanup
10. Write audit log entry

If any step fails, the failure is logged as `FORGET_PARTIAL_FAILURE` and the document is marked for retry.

### Data Encryption

MEMEX itself does not encrypt stored data. However:

- `memex doctor` checks for disk encryption (FileVault/LUKS/BitLocker)
- Data directory permissions are enforced to `0o700` (owner-only)
- Users are warned if disk encryption is not detected

### Supported Versions

| Version | Status |
|---------|--------|
| 2.0.x | ✅ Active support |
| 1.0.x | ⚠️ End of life |

---

## Security Best Practices for Users

### Recommended

- ✅ Enable full-disk encryption (FileVault / LUKS / BitLocker)
- ✅ Keep Ollama and models updated
- ✅ Review excluded domains in `redaction_patterns.toml`
- ✅ Periodically audit the forget log: `SELECT * FROM forget_audit_log`
- ✅ Restrict `~/.memex/` permissions: `chmod 700 ~/.memex`

### Avoid

- ❌ Exposing port 7700 to the network
- ❌ Running MEMEX on shared/multi-user systems without isolation
- ❌ Disabling the loopback middleware
- ❌ Storing MEMEX data on unencrypted volumes
- ❌ Removing excluded domains from `redaction_patterns.toml`

---

## Security Invariants

The following invariant tests (from `tests/invariants/`) enforce security properties:

| Test | Invariant |
|------|-----------|
| `test_security.py` | Loopback-only middleware rejects external requests |
| `test_security.py` | No outbound connections are made |
| `test_redaction.py` | All 7 patterns redact correctly |
| `test_redaction.py` | Innocuous text is never redacted |
| `test_redaction.py` | Shannon entropy heuristic catches high-entropy strings |
| `test_forget.py` | All stores are cleared after forget |
| `test_forget.py` | Audit log is written after forget |
| `test_config_hygiene.py` | All redaction patterns have valid regex |
| `test_config_hygiene.py` | All excluded domains are parseable |

These tests are **blocking** — they must pass for any PR to be merged.

---

*This security policy was last updated for MEMEX v2.0.0.*
