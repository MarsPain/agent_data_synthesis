# 09 — Run Live Workspace Acceptance and Freeze Deterministic Replay

**What to build:** Run one explicitly authorized coverage-driven real-LLM Workspace acceptance campaign through the production Domain Pack path, establish a real independently verifiable Release Candidate, freeze only sanitized provider responses needed for deterministic replay, and replace the offline tracer's provisional provider evidence with the accepted real chain.

**Blocked by:** [08 — Assemble the offline Workspace tracer proof](08-offline-workspace-tracer-proof.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Outcome-Validated Domain Pack](../../../docs/product-specs/outcome-validated-domain-pack.md)

## Acceptance criteria

- [ ] Provider execution begins only with explicit authorization, bounded candidate/attempt budget, configured generator and independent mutation-judge identities, and sanitized evidence policy.
- [ ] The run uses the exact coverage-enabled release-candidate Workspace plan, real LLM generation, enforced mutation admission, isolated local execution, and production verification.
- [ ] The accepted result satisfies all five Workspace capability requirements, every machine floor, Domain assessment, standalone pack verification, and real Release Candidate qualification.
- [ ] Provider evidence binds provider/model/config identity, assignment, request/response hashes, parser/contract version, usage, and bounded outcome without credentials, raw private source payloads, or unrestricted prompts.
- [ ] Sanitized real responses are frozen as immutable replay inputs only after the real run's artifacts and qualification verify independently.
- [ ] Offline replay through production contracts reproduces the declared parsing, admission, execution, verification, assessment, and qualification outcomes without another provider call.
- [ ] Hand-authored invalid responses remain the oracle for stochastic rejection cases and cannot be replaced by hoping a live provider emits failures.
- [ ] The final Workspace tracer proof passes every positive, conformance, compatibility, replay, and negative case from a clean offline verification.
- [ ] The final effective qualification remains Release Candidate; fixture-based Publishable and Training Recommended conformance never become real claims.
- [ ] Provider cost, sanitized usage, authorization boundary, and any non-accepted attempts are recorded without overstating the proof as publication approval or downstream utility.

## Scope guard

Do not run external training, request real publication approval, publish the
dataset, broaden provider spending beyond the approved bound, or retain
credentials and unrestricted provider/source content in fixtures.
