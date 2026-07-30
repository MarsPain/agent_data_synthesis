# 05 — Publish and Gate Coverage Evidence

**What to build:** Publish hash-bound planned-versus-accepted coverage evidence,
surface structural concentration and grounding reuse in quality reporting, and
require mandatory fulfillment before a coverage-driven run can claim
representative status.

**Blocked by:** [04 — Add Three-Domain Coverage Catalogs](04-three-domain-coverage-catalogs.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Coverage-Driven Representative Synthesis](../../../docs/product-specs/coverage-driven-representative-synthesis.md)

## Acceptance criteria

- [x] A versioned coverage evidence artifact binds catalog, profile, plan, scheduler, run profile, assignment, and admitted-sample identities by stable hashes.
- [x] Evidence reports planned, attempted, generated, accepted, rejected, and remaining counts per cell with bounded rejection and deficit reasons.
- [x] Evidence separately reports structural-family concentration, grounding reuse, difficulty distribution, exact duplicates, and fulfillment status.
- [x] Aggregate counts reconcile exactly with accepted samples, rejections, assignments, and the plan attempt ceiling.
- [x] Quality and representative evidence consume sanitized coverage summaries without reading raw prompts, provider responses, private source payloads, or arbitrary profile JSON.
- [x] Diagnostic runs may retain valid partial samples with an incomplete coverage decision.
- [x] A coverage-driven representative claim fails or remains insufficient when mandatory coverage is incomplete, even if executable and verification rates pass.
- [x] Coverage fulfillment cannot override source, safety, mutation, verification, exact-duplicate, held-out, or release failures.
- [x] Changed catalogs, profiles, plans, assignments, or sample membership invalidate the corresponding hashes and representative claim.
- [x] Existing non-coverage quality, profile-decision, release, audit, and representative evidence remains backward compatible.

## Scope guard

Do not make semantic duplicate detection blocking, change downstream benchmark
protocols, or claim that structural coverage alone proves model improvement.
