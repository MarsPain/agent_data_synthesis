# 05 — Add the Workspace Tasks Domain Adapter

**What to build:** Produce verified Workspace Tasks Agent Episodes through the
interface validated by two production Domains, without new shared-core
knowledge of Workspace behavior.

**Blocked by:** [04 — Add Mobile Messages and validate the second-Domain seam](04-add-mobile-messages-domain-adapter.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [ ] The adapter admits and freezes fixture/local inputs without exposing item, task, document, or comment schemas to shared core modules.
- [ ] Slots cover item search, task creation, comment addition, search recovery, and missing-item safe failure, with known capacity or explicit exhaustion/unknown-capacity reporting.
- [ ] Compilation binds action, target, arguments, conditions, and success criteria to the public request and observable evidence. Negation, unmet conditions, ambiguous items, and unsupported private targets are rejected.
- [ ] Legitimate open task/comment content uses Domain-owned predicates; exact public requirements remain exact. Oracle fields stay private.
- [ ] Isolated search, authorized mutations, recovery, safe failure, and unauthorized-mutation rejection traverse the common interface; replay uses the frozen source and saved Task case.
- [ ] Assessment checks grounded final response, requested state, and absence of unintended persistent changes.
- [ ] Semantic and structural examples distinguish material request meaning and executed topology; the nine-family baseline is behaviorally grounded and cannot grow from coverage labels or redundant calls.
- [ ] The shared compliance suite and provider-mock end-to-end tests pass without core, ledger, rollout, or quality changes for Workspace.
- [ ] The test-only fourth Domain registers without core changes, and architecture checks reject Domain-to-Domain imports and production identities outside built-in registration.

## Scope guard

Do not migrate Workspace qualification, publishability, training recommendation,
tracers, authority fixtures, live acceptance machinery, or compatibility
readers. If this Domain reveals a broken seam, record and resolve that defect
rather than hiding it in a shared-core Workspace branch.
