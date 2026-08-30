# 05 — Assemble the Provider-Free Contacts Acceptance Proof

**What to build:** Let a test engineer build and independently verify a
Contacts acceptance proof from injected, sanitized provider-shaped evidence,
reconstructing the complete current Contacts chain without a provider call and
showing its fail-closed behavior at one observable proof boundary.

**Blocked by:** [04 — Extract a Pack-Neutral Acceptance and Replay Harness](04-extract-pack-neutral-acceptance-replay-harness.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Contacts Domain Pack Lifecycle and Second-Domain Validation](../../../docs/product-specs/contacts-domain-pack-lifecycle.md)

## Acceptance criteria

- [x] An injected Contacts acceptance run exercises production parsing, exact membership admission, enforce-mode mutation admission, isolated execution, verification, assessment, release packing, and qualification without network access or credentials.
- [x] Sanitized Contacts provider evidence is eligible for freezing only after independent release-pack verification and current qualification pass; invalid or incomplete evidence cannot construct a proof root.
- [x] Offline replay through production Contacts contracts reproduces parsing, admission, execution, verification, coverage, assessment, and qualification outcomes with zero provider calls.
- [x] The proof report separately exposes effective qualification, fixture or conformance results, and explicit non-claims for Publishable, Training Recommended, global mutation activation, Mobile Messages, and downstream utility.
- [x] Copied positive artifacts produce independently attributable bounded failures for Pack, plan, source, runtime, capability, assignment, mutation, episode, verifier, coverage, assessment, release-pack, and qualification drift.
- [x] The proof and negative-case artifacts retain only sanitized material and do not change the frozen legacy Contacts compatibility corpus or the established Workspace proof.
- [x] Focused proof tests, the full relevant unit suite, and documentation validation pass without a real provider request.

## Implementation

Added the provider-free `contacts_acceptance` adapter over the pack-neutral
acceptance/replay harness. The injected-only runner binds the exact Contacts
release profile and Domain plan, performs independent mutation-judge preflight,
routes generation through the production coverage and Contacts lifecycle, and
freezes sanitized evidence only after Contacts release-pack verification and
Release Candidate qualification pass. The proof root reconstructs Contacts
parsing, membership, enforce-mode admission, isolated execution, replay,
assessment, qualification, compatibility conformance, and 13 one-fact drift
cases without provider calls. It records explicit non-claims for publication,
training, global mutation activation, Mobile Messages, and downstream utility;
the next ticket owns any real-provider operator path.

Focused Contacts proof tests cover positive injected evidence, membership
rejection/backfill, sanitization and freeze gating, authorization no-go,
independent-judge preflight failure, and positive-artifact integrity drift.

## Scope guard

Do not expose a real-provider CLI path or execute a paid run. This ticket
proves that the complete Contacts acceptance chain is reproducible and safe to
operate before an operator is asked to authorize external work.
