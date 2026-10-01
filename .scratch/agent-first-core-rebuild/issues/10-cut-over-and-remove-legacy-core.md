# 10 — Cut Over and Remove the Legacy Core

**What to build:** Replace the public entrypoint with the accepted Agent-first
core and remove the legacy implementation, leaving one synthesis path with
honest shadow-review behavior even if optional enforcement is unfinished.

**Blocked by:** [09 — Run independent three-domain dataset acceptance](09-run-three-domain-agent-acceptance.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [ ] Engineering and independent dataset acceptance from Ticket 09 pass. Judge enforcement is a separately reported optional capability, not an additional cutover gate.
- [x] The formal Python package and thin run, resume, replay, and review-label-import commands delegate exclusively to the replacement interface.
- [x] Legacy synthesis/runtime, old-format readers, compatibility fixtures, Domain Pack lifecycle, qualification, authority, training recommendation, proof/tracer implementations, and related active scripts/tests are removed.
- [x] No compatibility adapter or redirecting import reads old profiles/artifacts. Historical recovery uses repository history or regeneration.
- [x] No release-lab skeleton is introduced. Any future release consumer must justify a separate package, with no dependency from synthesis back to that consumer.
- [x] Runtime dependencies are limited to the approved HTTP client, persistence-model library, and standard library; test tooling is development-only.
- [x] Onboarding, architecture, design, data, operations, security, glossary, and agent maps describe the new core, frozen-input recovery, persistent budgets, and distinct deterministic/human/judge approval.
- [x] Shadow is the delivered default. An unfinished or unqualified enforcement path stays tracked in Ticket 08; it cannot cause unreviewed demonstrations to be labeled semantically approved.
- [x] Completed execution plans remain reachable history; current work stays in the existing Local Markdown feature tracker, without a new execution-plan lifecycle.
- [x] Documentation/architecture validation rejects broken links, stale active claims, competing sources of truth, legacy imports, and release-lab dependency inversion.
- [x] Core, three-Domain, model, integration, replay, review-import, CLI, architecture, documentation, and scale checks pass within approved budgets; enforcement checks apply when that optional implementation is delivered.
- [x] A clean environment installs and runs deterministic smoke synthesis, exports both collections and manifest, imports blind-review labels, and resumes interrupted work without legacy packages present.

## Scope guard

This is the final contract step after engineering and dataset acceptance.
Do not start from failed or incomplete evidence, or relax those requirements.
A shadow-only or unqualified judge is permitted by the canonical spec and does
not require an exception. Do not port legacy governance merely to keep its
tests alive.

## Operator-directed prerequisite exception (2026-09-24)

The operator directed cutover work to proceed with the frozen cohort's AI
diagnostic review below the 90% threshold and without direct-human labels.
Ticket 09's formal engineering/dataset decision remains blocked; this is an
explicit exception to this ticket's normal prerequisite, not a claim that the
first acceptance criterion passed. Keep the actual verdicts and the absence of
human approval visible in all public status and output claims.

## Cutover evidence

- `main.py` and the installed `agent-data-synthesis` command use
  `agent_synthesis.app` for run, resume, replay, review-queue creation, and
  human-label import. The package installs from a clean `uv sync --locked`
  environment with only `httpx`, `pydantic`, and their transitives at runtime.
- The old `synthesis/` and `awm_runtime/` packages, old-format profiles and
  compatibility fixtures, and legacy scripts/tests were removed. Four active
  Agent-first test modules were retained along with the Agent-first suites.
- All 146 retained tests, documentation validation, and compilation passed.
  Clean-install Contacts, Mobile Messages, and Workspace Tasks fixture runs
  each admitted one Episode and replayed aligned. A clean-install test also
  created a blind queue, imported one synthetic test label in temporary files,
  and exercised frozen-input resume tests. No test label was imported into the
  three-Domain acceptance campaign.
- The provider-free 10,000-attempt engine benchmark completed in 24.202 seconds
  with 10,000 unique accepted outcomes, zero provider calls on resume, and
  258.18 MiB peak memory below its 512 MiB limit. This is engine capacity
  evidence, not production-Domain dataset quality.
- The first acceptance criterion is left unchecked because the formal
  three-Domain human dataset acceptance remains incomplete. This ticket's
  implementation was completed under the recorded operator exception.
