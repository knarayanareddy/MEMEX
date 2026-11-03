# MEMEX remediation plan

All steps are proposed, not executed. Preserve real user data; use isolated synthetic stores for destructive verification. Findings are in [REVIEW.md](REVIEW.md).

## Phases and dependency map

| Phase | Task | Dependencies | Exit criterion |
|---|---|---|---|
| Baseline | MX-T1 | Owner approves isolated host | Failed CI stage identified and reproducible |
| Delete-path correctness and privacy | MX-T2 | MX-T1 | Cross-store forget/readback demonstrated on synthetic data |
| Local authorization boundary | MX-T3 | MX-T1 | Sensitive routes protected beyond peer-locality alone |
| Supply-chain integrity | MX-T4 | MX-T1 | Build inputs pinned and integrity-checked |
| Automation and usability | MX-T5 | MX-T2–T4 | Negative tests fail when controls are broken |
| Recovery acceptance | MX-T6 | MX-T5 | Restore drill and delete-after-restore behavior observed |
| Owner approval and release decision | MX-T7 | MX-T2–T6 | Explicit approvals, release gates and rollback policy recorded |

### MX-T1 — Reproduce baseline (MX-02)

Prerequisite: isolated test environment. Observed `.github/workflows/ci.yml`, `pyproject.toml`.
1. Retrieve the failed pinned run's job logs and identify the first causal failure and environment.
2. Resolve declared dependencies in a disposable environment without changing thresholds; record versions and exact revision.
3. Reproduce the failed stage and distinguish environment failure from source failure; record results and ownership.

Deliverable: reproducible failure report. Verification: confirm the recorded command is the one actually defined by the workflow and that any proposed change targets the observed failure rather than suppressing a gate.
- [ ] CI failure classified with job, stage and logs.
- [ ] Tested SHA and dependency versions recorded.
- [ ] No existing checks disabled to obtain green.

### MX-T2 — Demonstrate deletion and retained-metadata boundaries (MX-04)

Prerequisite: MX-T1. Observed `memex/protect/forget.py`; proposed deeper inspection and tests under `memex/db/` and `tests/`.
1. Inventory every persistence surface for one synthetic marker and one secret canary: document rows, chunks, vector entries, graph mentions, forget logs, caches and backups.
2. Exercise ingestion, forget, interruption between stores and retry handling; independently query each live store and each retained artifact after every step.
3. Adjust deletion, retry or retention handling where evidence warrants, and explicitly document what metadata may remain by design versus what must be purged.

Deliverable: deletion matrix plus regression tests. Verification: deliberately skip one deletion sink and confirm the independent readback detects the marker; separately report any approved backup or audit-log retention boundary instead of calling it hard deletion.
- [ ] Synthetic secret canary absent from every intended live-store output.
- [ ] Interrupted forget converges or reports an actionable failure.
- [ ] Residual metadata and retention exceptions explicitly documented.

### MX-T3 — Protect destructive and private-data routes (MX-03)

Prerequisite: MX-T1. Observed `memex/api/middleware.py`, `memex/api/routes/memory.py`, and `memex/web/static/app.js`.
1. Trace sensitive routes, methods and clients; distinguish peer-locality checks from user/session authorization and from browser-origin protections.
2. Define the supported local-user model, then add host/origin checks and authorization appropriate to destructive and private-data routes without trusting loopback alone.
3. Test hostile web origin, rebinding-style Host, forged headers, non-loopback peer, authorized local UI, CLI caller and concurrent same-host users.

Deliverable: explicit boundary policy and integration tests. Verification: deliberately remove one required protection and confirm at least one hostile request test succeeds when broken and fails once the control is restored.
- [ ] Unauthorized destructive and private-data requests are rejected.
- [ ] Supported local clients remain usable.
- [ ] Route policy states whether multi-user same-host use is supported or out of scope.

### MX-T4 — Make builds reproducible (MX-01)

Prerequisite: MX-T1. Observed `Dockerfile`, `uv.lock`, `pyproject.toml`.
1. Identify installer and model artifacts, supported platforms and transitive dependency resolution.
2. Replace mutable installer execution with reviewed versioned, integrity-checked artifacts and a documented locked dependency build.
3. Build twice in a controlled environment, compare provenance and run a negative integrity test with a modified artifact.

Deliverable: pinned build inputs and provenance. Verification: confirm the build refuses a digest mismatch rather than silently downloading or running another artifact.
- [ ] Artifact identity and digest recorded.
- [ ] Integrity failure blocks the build.
- [ ] Build instructions name the reviewed artifact source.

### MX-T5 — Prove automation and usability (preventive)

Prerequisite: MX-T2–T4. Observed workflow and test inventory; proposed new tests under `tests/`.
1. Add regression tests for delete verification, retained-metadata boundaries, adversarial origins and source-content injection using synthetic fixtures.
2. Run relevant existing checks and any new negative tests without lowering coverage or thresholds; bind results to the tested SHA.
3. Exercise web and TUI keyboard use, failure messaging, source disclosure and delete confirmation with representative local-user scenarios.

Deliverable: evidence-linked CI and usability report. Verification: each critical negative assertion must fail when its corresponding behavior is intentionally broken.
- [ ] CI evidence points to the tested SHA.
- [ ] Negative tests are behavior-proving, not mirror assertions.
- [ ] UI discloses collection scope, delete limits and failure states accurately.

### MX-T6 — Recovery and restore acceptance (preventive)

Prerequisite: MX-T5 and owner-defined RPO/RTO targets. Observed `docker-compose.yml`; proposed `docs/RECOVERY.md` and recovery tests/runbooks.
1. Enumerate all recovery-relevant artifacts: container/image version, SQLite/Chroma/Kuzu data, logs, forget logs, backup media, keys and configuration.
2. Define backup creation, encryption, retention, restore order and delete-from-backup policy for synthetic datasets, including what is intentionally retained and for how long.
3. Restore synthetic data into an isolated instance, measure actual recovery time and point, then re-run forget/readback checks on the restored instance to confirm post-restore privacy behavior.

Deliverable: recovery runbook and observed restore-drill evidence. Verification: prove the restored instance serves the expected synthetic data before and after a forget test; fail the task if only backup creation was observed or if restore behavior is inferred instead of measured.
- [ ] Recovery runbook names stores, artifacts and restore order.
- [ ] Measured RPO/RTO recorded against target.
- [ ] Delete-after-restore behavior independently checked.

### MX-T7 — Owner approvals, release gates and rollback policy (preventive)

Prerequisite: MX-T2–T6. Observed `SECURITY.md`, `docker-compose.yml`, `memex/web/static/app.js`; proposed release evidence pack and owner sign-off record.
1. Present owner decisions on watch scope, same-host user model, allowed model/provider egress, forget-log metadata retention, backup retention and any non-loopback exposure.
2. Convert approved decisions into explicit release gates, rollback conditions and incident owners, and link each gate to concrete evidence from MX-T1–MX-T6.
3. Run an independent pre-release review of the evidence pack and block release if any gate depends on an unrun test, unreproduced CI claim or unapproved retention exception.

Deliverable: owner approval record, release checklist and rollback policy. Verification: remove one required approval or one linked evidence item and confirm the release decision cannot pass.
- [ ] Owner approvals captured for scope, egress, retention and exposure.
- [ ] Release checklist cites evidence, not README or policy promises alone.
- [ ] Rollback plan identifies known-good artifact/data set and approval path for destructive restore.

## Production acceptance checklist

- [ ] Pinned CI failure reproduced and resolved without suppressing checks.
- [ ] Delete/verify behavior proven on synthetic data across each intended live store.
- [ ] Route protections tested against hostile same-host/browser scenarios.
- [ ] Build inputs pinned and integrity-checked.
- [ ] Restore drill observed with measured RPO/RTO and delete-after-restore verification.
- [ ] Owner approvals recorded for data scope, egress, retention and exposure boundaries.

## Changes requiring owner approval

- Expanding watched directories or source types beyond the current local prototype scope.
- Any same-host multi-user support claim or any exposure beyond loopback.
- Any outbound model/provider/network dependency that weakens the local-only claim.
- Retaining document-derived metadata in forget logs, backups or restored instances beyond the approved policy.
- Any destructive rollback or restore into current user data.

## Release and rollback policy

1. Release only from a SHA with evidence attached for MX-T1–MX-T7; do not substitute README badges or historical claims for current proof.
2. Preserve a known-good artifact set and compatible backup before release; pause ingestion before rollback and restore only into an isolated instance first.
3. Do not overwrite current user data, widen exposure, or change retention behavior without explicit owner approval and a recorded recovery path.

## Recovery acceptance criteria

- Recovery evidence must include observed restore output, not just successful backup creation.
- The restored instance must be queried directly before and after a forget operation using synthetic markers.
- Any data that intentionally survives in backups or logs must be named, time-bounded and owner-approved.
- If measured RPO/RTO misses target, release remains blocked until the target or expectation is renegotiated and recorded.
