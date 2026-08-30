# 06 — Add Explicitly Authorized Contacts Live Acceptance

**What to build:** Let an operator invoke a bounded, explicitly authorized
Contacts live-acceptance path that validates its exact configuration and fails
safely before or during provider work, while preserving a provider-free default
pipeline and a complete audit record for either outcome.

**Blocked by:** [05 — Assemble the Provider-Free Contacts Acceptance Proof](05-assemble-provider-free-contacts-acceptance-proof.md)

**Status:** completed

**Assignee:** Unassigned

**Parent spec:** [Contacts Domain Pack Lifecycle and Second-Domain Validation](../../../docs/product-specs/contacts-domain-pack-lifecycle.md)

## Acceptance criteria

- [x] The operator-facing live path requires a fresh authorization identifier, the exact Contacts release-candidate profile, bounded candidate and attempt budgets, bounded retry-expanded physical-call ceilings, and distinct generator and mutation-judge identities.
- [x] Before any generator request, the path sends a fixed non-source-backed request through the production independent-judge contract and fails closed when preflight does not return a valid supported result.
- [x] A valid live-shaped injected-transport test exercises Contacts generation, enforce-mode admission, release verification, response-free failure handling, evidence freezing, and replay assembly without using a network credential or provider service.
- [x] Provider, parser, judge, budget, pipeline, release-evidence, or qualification failure writes a sanitized bounded failure record that records authorization and run binding, usage totals, rejection summary, and effective qualification status without responses, prompts, credentials, or source payloads.
- [x] The path freezes `real_live` provider evidence and constructs a real proof only after the exact Contacts release pack and Release Candidate qualification verify independently.
- [x] Existing default commands remain offline and provider-free; the Contacts live path does not modify semantic-mutation activation thresholds or claim global activation.
- [x] Focused command, authorization, preflight, budget, sanitization, and regression tests pass with injected transports only.

## Implementation

Added `synthesis.contacts_live_acceptance` and
`scripts/run_contacts_live_acceptance.py` as the explicitly authorized
Contacts operator boundary. The path validates the exact Contacts Release
Candidate profile, budgets, retry ceiling, and independent judge identity;
preflights the production mutation-judge contract before generation; and
records bounded failure evidence without responses, prompts, credentials, or
source payloads.

The Contacts proof assembler now accepts an explicit evidence contract, so the
same production proof graph can verify both provider-free injected evidence and
sanitized `real_live` evidence without duplicating Contacts semantics. Focused
injected-transport tests cover authorization, preflight ordering, budget
failure, CLI defaults, live evidence, qualification gating, and zero-provider
replay. No real provider request or operator authorization was consumed.

## Scope guard

Do not make an actual provider request, consume an operator authorization, or
claim a real Contacts qualification in this ticket. It implements the safe
operator boundary that a separately authorized acceptance task will use.
