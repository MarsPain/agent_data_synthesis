# 05 — Assemble the Provider-Free Contacts Acceptance Proof

**What to build:** Let a test engineer build and independently verify a
Contacts acceptance proof from injected, sanitized provider-shaped evidence,
reconstructing the complete current Contacts chain without a provider call and
showing its fail-closed behavior at one observable proof boundary.

**Blocked by:** [04 — Extract a Pack-Neutral Acceptance and Replay Harness](04-extract-pack-neutral-acceptance-replay-harness.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Contacts Domain Pack Lifecycle and Second-Domain Validation](../../../docs/product-specs/contacts-domain-pack-lifecycle.md)

## Acceptance criteria

- [ ] An injected Contacts acceptance run exercises production parsing, exact membership admission, enforce-mode mutation admission, isolated execution, verification, assessment, release packing, and qualification without network access or credentials.
- [ ] Sanitized Contacts provider evidence is eligible for freezing only after independent release-pack verification and current qualification pass; invalid or incomplete evidence cannot construct a proof root.
- [ ] Offline replay through production Contacts contracts reproduces parsing, admission, execution, verification, coverage, assessment, and qualification outcomes with zero provider calls.
- [ ] The proof report separately exposes effective qualification, fixture or conformance results, and explicit non-claims for Publishable, Training Recommended, global mutation activation, Mobile Messages, and downstream utility.
- [ ] Copied positive artifacts produce independently attributable bounded failures for Pack, plan, source, runtime, capability, assignment, mutation, episode, verifier, coverage, assessment, release-pack, and qualification drift.
- [ ] The proof and negative-case artifacts retain only sanitized material and do not change the frozen legacy Contacts compatibility corpus or the established Workspace proof.
- [ ] Focused proof tests, the full relevant unit suite, and documentation validation pass without a real provider request.

## Scope guard

Do not expose a real-provider CLI path or execute a paid run. This ticket
proves that the complete Contacts acceptance chain is reproducible and safe to
operate before an operator is asked to authorize external work.
