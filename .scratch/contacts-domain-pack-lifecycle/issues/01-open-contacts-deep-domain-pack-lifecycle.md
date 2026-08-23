# 01 — Open Contacts Through the Deep Domain Pack Lifecycle

**What to build:** Let a synthesis operator run Contacts fixture and governed
local-source work through one planned, run-scoped Contacts Domain Pack lifecycle
instead of the legacy component bundle, while preserving the established
Contacts behavior and isolation guarantees.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Contacts Domain Pack Lifecycle and Second-Domain Validation](../../../docs/product-specs/contacts-domain-pack-lifecycle.md)

## Acceptance criteria

- [ ] A valid Contacts request deterministically selects the existing logical `contacts` Pack, compiles a hash-bound Domain plan from an admitted source, and opens one run-scoped Contacts Domain run before candidate work begins.
- [ ] Invalid or drifted Contacts Pack, runtime, source, capability, or component bindings fail before runtime construction with bounded reasons; a mismatch must not silently alter the existing Pack version.
- [ ] Contacts fixture and governed local-source execution both use the Contacts Domain run and retain their established observable acceptance, rejection, source-governance, final-state, episode, and sanitization behavior where contracts are unchanged.
- [ ] The opened run owns generation, candidate fork, attempt, replay, and typed assessment entry points without exposing a raw environment, registry, verifier, candidate preparer, or mutation-policy bundle to shared callers.
- [ ] A read-only lookup and a state-changing follow-up each execute in candidate-scoped rebuilt state; one candidate's follow-up cannot affect another candidate's evidence or final state.
- [ ] Replay accepts a valid Contacts attempt and rejects pack, plan, source, runtime, candidate scope, episode, or verifier drift with bounded outcomes.
- [ ] Focused lifecycle and pipeline tests demonstrate the complete Contacts tracer through public behavior and keep existing Workspace and legacy Contacts paths green.

## Scope guard

Do not yet carry Contacts capabilities into coverage or release qualification,
create a release pack, extract common acceptance machinery, or make any provider
call. This ticket establishes the second domain's behavior-preserving deep
lifecycle seam only.
