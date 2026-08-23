# 06 — Add Explicitly Authorized Contacts Live Acceptance

**What to build:** Let an operator invoke a bounded, explicitly authorized
Contacts live-acceptance path that validates its exact configuration and fails
safely before or during provider work, while preserving a provider-free default
pipeline and a complete audit record for either outcome.

**Blocked by:** [05 — Assemble the Provider-Free Contacts Acceptance Proof](05-assemble-provider-free-contacts-acceptance-proof.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Contacts Domain Pack Lifecycle and Second-Domain Validation](../../../docs/product-specs/contacts-domain-pack-lifecycle.md)

## Acceptance criteria

- [ ] The operator-facing live path requires a fresh authorization identifier, the exact Contacts release-candidate profile, bounded candidate and attempt budgets, bounded retry-expanded physical-call ceilings, and distinct generator and mutation-judge identities.
- [ ] Before any generator request, the path sends a fixed non-source-backed request through the production independent-judge contract and fails closed when preflight does not return a valid supported result.
- [ ] A valid live-shaped injected-transport test exercises Contacts generation, enforce-mode admission, release verification, response-free failure handling, evidence freezing, and replay assembly without using a network credential or provider service.
- [ ] Provider, parser, judge, budget, pipeline, release-evidence, or qualification failure writes a sanitized bounded failure record that records authorization and run binding, usage totals, rejection summary, and effective qualification status without responses, prompts, credentials, or source payloads.
- [ ] The path freezes `real_live` provider evidence and constructs a real proof only after the exact Contacts release pack and Release Candidate qualification verify independently.
- [ ] Existing default commands remain offline and provider-free; the Contacts live path does not modify semantic-mutation activation thresholds or claim global activation.
- [ ] Focused command, authorization, preflight, budget, sanitization, and regression tests pass with injected transports only.

## Scope guard

Do not make an actual provider request, consume an operator authorization, or
claim a real Contacts qualification in this ticket. It implements the safe
operator boundary that a separately authorized acceptance task will use.
