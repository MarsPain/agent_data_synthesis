# 08 — Audit Admission in Release Artifacts

**What to build:** Let a release manager verify mutation admission entirely
from retained artifacts. Extend the already-established per-candidate evidence
through manifests, aggregate reporting, and release packs so missing,
diagnostic-only, non-enforced, tampered, or historically unadjudicated mutations
cannot pass offline release validation.

**Blocked by:** [07 — Enforce Admission Before All Declared Mutations](07-enforce-declared-mutations.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Semantic Mutation Admission](../../../docs/product-specs/semantic-mutation-admission.md)

## Acceptance criteria

- [x] New manifests declare sample and admission contract versions and bind admission artifacts by hash.
- [x] Every new state-changing sample and rejection exposes the established sanitized evidence contract; read-only samples expose their classification without a semantic verdict.
- [x] A versioned aggregate report groups outcomes by domain, task type, action, provenance, verdict, reason, provider outcome, and model-independence status.
- [x] Offline release validation verifies enforce mode, supported verdicts, contract versions, hashes, and generator/judge independence without provider calls.
- [x] Shadow, diagnostic-only, missing, invalid, and deliberately tampered mutation evidence is rejected.
- [x] Historical contracts remain readable, while `_30_v5` remains byte-immutable and cannot be grandfathered into a new mutation-safe release.
- [x] Retained-material scans reject raw prompts, responses, chain-of-thought, credentials, headers, and unreferenced observations.
- [x] Run-level and release-pack tests cover valid evidence, each controlled failure, backward compatibility, and deterministic report writing.

## Scope guard

Do not redefine the authorization or verdict contracts established by the
tracer bullet, and do not re-adjudicate historical artifacts in place.
