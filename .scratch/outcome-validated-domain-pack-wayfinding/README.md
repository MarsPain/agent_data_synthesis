# Outcome-Validated Domain Pack

- **Status:** closed
- **Label:** `wayfinder:map`
- **Assignee:** Codex

## Destination

Produce an implementable specification in which a versioned Domain Pack is the
single source of truth for domain capability semantics. Prove the intended
design with a Workspace tracer that connects coverage-driven LLM release
candidate generation, a three-level release qualification model, a verified
release pack, and a hash-bound downstream benchmark result.

## Notes

- This map produces decisions and a path to a specification; it does not
  implement the specification or run provider or training workloads.
- Use `/domain-modeling` whenever canonical terms are resolved and update
  `CONTEXT.md` at that time.
- Use `/codebase-design` when deciding the Domain Pack interface and seam.
- Use `/cs-critical-thinking-partner` for release-policy, experiment-validity,
  leakage, failure-mode, and evidence-strength decisions.
- Use `/prototype` when an interface sketch or release-state model needs a
  concrete artifact for human reaction.
- Preserve fail-closed admission, source governance, mutation safety, artifact
  identity, and the distinction between releaseability and downstream utility.
- Workspace is the tracer domain; Contacts and Mobile remain compatibility
  evidence, not additional tracer implementations for this effort.
- The accepted handoff is now published as the
  [canonical product spec](../../docs/product-specs/outcome-validated-domain-pack.md),
  [deep design](../../docs/design-docs/outcome-validated-domain-pack.md),
  [ADRs](../../docs/adr/README.md), and
  [implementation tracker](../outcome-validated-domain-pack/README.md). This map
  remains historical decision provenance.

## Decisions so far

<!-- Closed decision tickets are indexed here by name with a one-line gist. -->

- [Define Release Qualification Levels and Allowed Claims](decisions/01-release-qualification-levels.md) — Adopt cumulative, exact-identity-bound Release Candidate, Publishable, and Training Recommended claim levels with fail-closed promotion and independent releaseability and downstream-utility evidence.
- [Define Canonical Domain Capability Identity](decisions/02-canonical-domain-capability-identity.md) — Identify a capability by its logical Domain Pack and stable pack-local semantic key, version it separately, and require every task, execution, coverage, evaluation, mutation, and release projection to reference it explicitly rather than act as an alias.
- [Design the Domain Pack Interface and Seam](decisions/03-domain-pack-interface-seam.md) — Adopt a pure plan/open lifecycle, run-scoped generation, isolation, attempt, and replay behavior, and typed pack assessment while the shared framework retains orchestration and qualification authority.
- [Define Domain Pack Versioning and Compatibility](decisions/04-domain-pack-versioning-and-compatibility.md) — Use immutable hash-bound pack composition versions, projection-scoped legacy mappings, canonical-only writes, and separate readability, runnability, semantic-equivalence, and evidence-admissibility judgments.
- [Define Publishability Evidence and Decision Authority](decisions/05-publishability-evidence-and-authority.md) — Require a hash-bound publishability evidence bundle, non-waivable machine governance gates, independently authenticated scoped approval, and separation of risk acceptance from publication authority.
- [Define Training Recommended Evidence](decisions/06-training-recommended-evidence.md) — Require one pre-registered external training pair with release/control record counts matched within ten percent and a primary 95% bootstrap lower bound above one-percent relative gain, while treating the Publishable release as immutable and leaving any model-level guardrails optional.
- [Align Workspace Release-Candidate Semantics](decisions/07-workspace-release-candidate-semantics.md) — Bind five canonical Workspace capabilities before generation, model recovery and missing-item safety independently from task types and runtime branching, and require unchanged capability references across coverage, execution, held-out evaluation, and release completeness without weakening existing floors.
- [Define Contacts and Mobile Compatibility Fixtures](decisions/08-contacts-mobile-compatibility-fixtures.md) — Freeze all checked-in Contacts/Mobile profiles plus four self-contained golden artifact chains, map legacy projections to explicit canonical capabilities, and require separate readability, runnability, semantic-equivalence, and fail-closed evidence-admission assertions.
- [Specify the Workspace Training Recommendation Protocol](decisions/09-workspace-training-recommendation-protocol.md) — Verify unsigned, content-addressed external experiment files without running training or tokenization, match release/control record counts within ten percent, and decide utility solely from a reproducible paired task-success bootstrap whose 95% lower bound exceeds one percent.
- [Define the Workspace Tracer Proof](decisions/10-workspace-tracer-proof.md) — Require a real-LLM Workspace leg to establish Release Candidate, fixture-isolated Publishable and Training Recommended conformance paths, one hash-bound offline proof root, deterministic replay, and an explicit fail-closed mutation matrix.
- [Define the Specification Artifact Split and Handoff](decisions/11-specification-artifact-split-and-handoff.md) — Hand off into one product spec, one deep design, two focused ADRs, the glossary, and Local Markdown implementation tickets, with no new execution-plan lifecycle or copied decision narratives.

## Not yet specified

<!-- All remaining in-scope work is represented by open child decisions. -->

## Out of scope

- Implementing the Domain Pack interface, release policy, or Workspace tracer.
- Running paid provider generation, model training, or an external benchmark.
- Automatically promoting or publishing a dataset from machine evidence.
- Adding a fourth domain, expanding coverage catalogs, or implementing semantic
  duplicate detection solely to complete this map.
- Distributed workers, external MCP execution, a release portal, or model
  serving infrastructure.
