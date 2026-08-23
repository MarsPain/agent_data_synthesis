# 09 — Run Live Workspace Acceptance and Freeze Deterministic Replay

**What to build:** Run one explicitly authorized coverage-driven real-LLM Workspace acceptance campaign through the production Domain Pack path, establish a real independently verifiable Release Candidate, freeze only sanitized provider responses needed for deterministic replay, and replace the offline tracer's provisional provider evidence with the accepted real chain.

**Blocked by:** [08 — Assemble the offline Workspace tracer proof](08-offline-workspace-tracer-proof.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Outcome-Validated Domain Pack](../../../docs/product-specs/outcome-validated-domain-pack.md)

## Acceptance criteria

- [x] Provider execution begins only with explicit authorization, bounded candidate/attempt budget, configured generator and independent mutation-judge identities, and sanitized evidence policy.
- [x] The run uses the exact coverage-enabled release-candidate Workspace plan, real LLM generation, enforced mutation admission, isolated local execution, and production verification.
- [x] The accepted result satisfies all five Workspace capability requirements, every machine floor, Domain assessment, standalone pack verification, and real Release Candidate qualification.
- [x] Provider evidence binds provider/model/config identity, assignment, request/response hashes, parser/contract version, usage, and bounded outcome without credentials, raw private source payloads, or unrestricted prompts.
- [x] Sanitized real responses are frozen as immutable replay inputs only after the real run's artifacts and qualification verify independently.
- [x] Offline replay through production contracts reproduces the declared parsing, admission, execution, verification, assessment, and qualification outcomes without another provider call.
- [x] Hand-authored invalid responses remain the oracle for stochastic rejection cases and cannot be replaced by hoping a live provider emits failures.
- [x] The final Workspace tracer proof passes every positive, conformance, compatibility, replay, and negative case from a clean offline verification.
- [x] The final effective qualification remains Release Candidate; fixture-based Publishable and Training Recommended conformance never become real claims.
- [x] Provider cost, sanitized usage, authorization boundary, and any non-accepted attempts are recorded without overstating the proof as publication approval or downstream utility.

## Scope guard

Do not run external training, request real publication approval, publish the
dataset, broaden provider spending beyond the approved bound, or retain
credentials and unrestricted provider/source content in fixtures.

## Implementation

Added an explicitly gated live Workspace acceptance runner with fixed
release-candidate profile identity, candidate/attempt budgets, independent
mutation-judge identity, injected LLM configuration, and isolated local
execution. The runner records only bounded provider lineage, assignment
lineage, request/response hashes, parser version, usage, retry counts, cost
status, and non-accepted outcomes. Sanitized responses are frozen only after
release-pack verification and Release Candidate qualification.

Added provider-free replay through the production Domain parser and coverage
membership checks, plus a live-shaped tracer-proof assembler that preserves
fixture-only Publishable and Training conformance. The operator CLI requires
`--authorize-live-provider` and explicit identity/budget arguments.

After the first failed run, added a fixed non-source-backed independent-judge
preflight through the production semantic-judge contract. It runs before any
generation call, is included in a physical judge-call ceiling derived from the
authorized coverage plan and retry bound (50 calls for the current 24-attempt,
one-retry profile), and fails closed without freezing a response. Every failed
authorized preflight, pipeline, release-evidence, or qualification attempt
writes `live_attempt_failure.json` with its authorization and run binding,
bounded generator/judge usage, bounded rejection-cause summary, and no
response, prompt, credential, source payload, or tracer proof.

Before the live authorization, the focused injected-transport test exercised
the complete live-shaped run, replay, and proof chain without network or
credentials. A real run is separately authorized using the CLI above.

## Live execution attempt — 2026-08-23

An explicitly authorized run was executed against `https://api.deepseek.com`
with generator `deepseek-v4-flash`, independent mutation judge
`deepseek-v4-pro`, and candidate/attempt budgets of 24. It made 16 generation
attempts, reached the 12-sample coverage target, and recorded 4 non-accepted
attempts caused by `mutation_admission_failed / judge_unavailable`. The
resulting rejection rate was 0.25, above the 0.20 Release Candidate floor;
runtime was 694.58 seconds and also triggered the async-orchestration gate.

Evaluation and held-out checks passed, but dataset release and Release
Candidate qualification did not. No provider evidence was frozen and no live
tracer proof was published from this failed attempt. The ticket remains
`in-progress`: the bounded retry safeguards and focused offline regression are
complete, but a fresh explicit authorization and independent-judge selection
are required before another provider-spending run can establish the real Release
Candidate.

## Retry execution attempt — 2026-08-23

A second, separately authorized attempt used authorization
`workspace-acceptance-20260823-retry3`, the same DeepSeek generator/judge
identities and 24/24 logical budgets, plus an explicitly recorded three-retry
generator limit (96 physical generation calls at most). The fixed
`deepseek-v4-pro` semantic-judge preflight made its two bounded calls, both of
which had the sanitized `provider_error` outcome. It therefore failed as
`live_mutation_judge_preflight_failed` before any generation call: zero logical
and zero physical generator calls were made.

The attempt wrote
`artifacts/workspace-live-acceptance-20260823-retry3/live_attempt_failure.json`.
It did not freeze `trace/provider.json`, construct a live tracer proof, publish
anything, or start training. The new authorization is consumed. Ticket 09
remains `in-progress`; completing the real Release Candidate now requires a
fresh authorization and either an explicitly approved independent judge change
or confirmed recovery of the current judge service.

## Prepared retry configuration — 2026-08-23

The next profile revision retains `deepseek-v4-pro` as the independent judge
and now explicitly uses its documented non-thinking request mode
(`thinking_mode: disabled`). The setting is sent only to the judge and is bound
into its sanitized configuration identity; the generation model remains
`deepseek-v4-flash`. The operator selected a 90-second bounded judge deadline
(the profile schema allows at most 120 seconds). This configuration has passed
offline injected-transport coverage, but has not received a new live
authorization at the time this configuration was prepared and did not change
either failed attempt's evidence. The later separately authorized execution is
recorded below.

## Completed live execution and offline proof recovery — 2026-08-23

The separately authorized execution
`workspace-acceptance-20260823-pro-disabled-thinking-90s` completed one bounded
real-provider campaign with generator `deepseek-v4-flash`, independent judge
`deepseek-v4-pro`, candidate/attempt budgets of 24/24, and a three-retry
generation limit (96 physical calls maximum). The judge used the documented
non-thinking request mode with the bounded 90-second deadline. It made 13
logical/physical generator calls (no generator retries) and seven successful
judge calls against its ceiling of 50. Sanitized usage and the intentionally
unpriced `not_reported` cost record are frozen in the provider evidence.

The run accepted 12 samples and recorded one
`domain_plan_membership_rejected` terminal rejection. Coverage fulfillment,
release-pack verification, Domain assessment, and Release Candidate
qualification all passed. The qualification is exactly `release_candidate`;
`publishable` and `training_recommended` are both false. The acceptance replay
made zero provider calls.

The original CLI returned a proof-stage `provider_contract` result after the
provider evidence had already been frozen. Offline replay isolated two
assembler/verifier defects: a contract-valid response rejected later by the
Domain Pack was omitted from assignment binding, and a pre-admission terminal
rejection was incorrectly equated with a mutation-admission rejection. Both
were corrected with fail-closed regression coverage. No additional provider
request was made.

The resulting immutable proof was reconstructed from the same frozen
acceptance directory at
`artifacts/workspace-live-acceptance-20260823-pro-disabled-thinking-90s-tracer-proof-reconstructed/`.
Its root is `workspace_tracer_proof_640cbdab97625f14`, hash
`sha256:640cbdab97625f144608ba792c90c58975e2a0b22c1e30ff3db6c04381d4051d`.
Clean offline CLI verification passed the positive chain and all 13 negative
or boundary cases. No dataset was published, no external approval was sought,
and no training was started.
