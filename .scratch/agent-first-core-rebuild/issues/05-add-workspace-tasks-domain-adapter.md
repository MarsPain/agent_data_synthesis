# 05 — Add the Workspace Tasks Domain Adapter

**What to build:** Produce verified Workspace Tasks Agent Episodes through the
interface validated by two production Domains, without new shared-core
knowledge of Workspace behavior.

**Blocked by:** [04 — Add Mobile Messages and validate the second-Domain seam](04-add-mobile-messages-domain-adapter.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [x] The adapter admits and freezes fixture/local inputs without exposing item, task, document, or comment schemas to shared core modules.
- [x] Slots cover item search, task creation, comment addition, search recovery, and missing-item safe failure, with known capacity or explicit exhaustion/unknown-capacity reporting.
- [x] Compilation binds action, target, arguments, conditions, and success criteria to the public request and observable evidence. Negation, unmet conditions, ambiguous items, and unsupported private targets are rejected.
- [x] Legitimate open task/comment content uses Domain-owned predicates; exact public requirements remain exact. Oracle fields stay private.
- [x] Isolated search, authorized mutations, recovery, safe failure, and unauthorized-mutation rejection traverse the common interface; replay uses the frozen source and saved Task case.
- [x] Assessment checks grounded final response, requested state, and absence of unintended persistent changes.
- [x] Semantic and structural examples distinguish material request meaning and executed topology; the nine-family baseline is behaviorally grounded and cannot grow from coverage labels or redundant calls.
- [x] The shared compliance suite and provider-mock end-to-end tests pass without core, ledger, rollout, or quality changes for Workspace.
- [x] The test-only fourth Domain registers without core changes, and architecture checks reject Domain-to-Domain imports and production identities outside built-in registration.

## Implementation notes

- `agent_synthesis.workspace_tasks` owns source admission and normalization,
  source-derived deterministic slots, public/private compilation,
  candidate-local tools, mutation authorization, replay validation, and
  assessment. The shared core, ledger, rollout, and quality modules remain
  unchanged.
- The fixture emits nine behaviorally distinct structures: direct, directory,
  recovery, and missing-item search; exact and open task creation; and direct,
  recovery, and verified comment addition. Local inputs select equivalent safe
  structures from their admitted items, while their finite capacity reports
  exhaustion honestly.
- Mutations require an observed target, allow one authorized persistent change
  per Episode, and verify grounded final responses plus exact or Domain-owned
  open-content predicates. Replay rebuilds cases only from the frozen source,
  rejecting a forged or non-emitted saved case before execution.
- `agent_synthesis.builtin_domains` is the explicit production composition
  point for Contacts, Mobile Messages, and Workspace Tasks. The generic
  `AdapterRegistry` still accepts the test-only fourth Domain without a core
  change; architecture tests enforce import direction and identity placement.

## Final validation

- `python -m unittest` passed: 1,069 tests in 80.402 seconds.
- `python scripts/validate_docs.py` passed.
- The two-axis code review found no remaining Standards or Spec issue after
  replay/source-integrity fixes.

## Scope guard

Do not migrate Workspace qualification, publishability, training recommendation,
tracers, authority fixtures, live acceptance machinery, or compatibility
readers. If this Domain reveals a broken seam, record and resolve that defect
rather than hiding it in a shared-core Workspace branch.
