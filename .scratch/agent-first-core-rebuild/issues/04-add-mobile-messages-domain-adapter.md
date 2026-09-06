# 04 — Add Mobile Messages and Validate the Second-Domain Seam

**What to build:** Produce verified Mobile Messages Episodes and use this
second production Domain to validate and stabilize the interface through a
concrete task/verifier change-locality exercise.

**Blocked by:** [03 — Add Contacts and establish early Agent feasibility](03-add-contacts-domain-adapter.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [ ] The adapter freezes admitted fixture/local inputs without shared-core knowledge of message, reminder, or draft schemas.
- [ ] Deterministic slots cover message search, reminder creation, draft reply, and search recovery, with bounded capacity/exhaustion reporting.
- [ ] Public task semantics support selected messages, authorized reminder/draft arguments, and conditions; compilation rejects missing authority, wrong bindings, negation, and unsupported private exact targets.
- [ ] Open reply content uses a Domain predicate or allowed-result set; explicit exact content retains exact verification without leaking oracle fields.
- [ ] Isolated execution and replay cover search, authorized mutations, recoverable failure, and rejection before unauthorized mutation; final assessment checks grounded response and intended state only.
- [ ] Semantic keys preserve material request differences; reviewed structural examples establish the twelve-family baseline and show that paraphrases, entity swaps, and padded tool sequences do not create families.
- [ ] The shared compliance suite and provider-mock end-to-end tests pass without Mobile-specific branches in core modules.
- [ ] A bounded exercise adds one task type and changes one verifier rule inside a production Domain. Its diff stays in that Domain and its fixtures/docs/tests, with no core edits, generic configuration escape hatch, or copied core workflow.
- [ ] Any interface corrections discovered by the second Domain are resolved for both adapters before the locality exercise is repeated and the seam is treated as stable.
- [ ] The ticket records changed modules, public-contract count, dependency direction, and test timings; it does not equate fewer lines or passing import rules alone with simpler design.

## Scope guard

Do not port Mobile compatibility corpora, release evidence, legacy profiles, or
Domain Pack projections. Do not add task types solely to inflate structural
counts or create a generic Domain framework to satisfy the locality exercise.
No additional paid campaign is required by this ticket.
