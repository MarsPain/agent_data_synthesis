# 07 — Run Contacts Live Acceptance and Freeze Replay Proof

**What to build:** With fresh explicit operator authorization, run one bounded
real-provider Contacts acceptance campaign and record either a valid,
provider-free-replayable current Contacts Release Candidate proof or a
sanitized no-go result that accurately preserves the remaining limitation.

**Blocked by:** [06 — Add Explicitly Authorized Contacts Live Acceptance](06-add-authorized-contacts-live-acceptance.md) (completed)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Contacts Domain Pack Lifecycle and Second-Domain Validation](../../../docs/product-specs/contacts-domain-pack-lifecycle.md)

## Acceptance criteria

- [x] Before any paid request, the synthesis operator supplies a fresh authorization, a bounded budget, available credentials, and distinct approved generator and mutation-judge identities; the documented preflight must pass.
- [x] The real run uses the exact Contacts Domain Pack plan, enforced mutation admission, isolated Contacts execution, current coverage and held-out contracts, and the production release-evidence path.
- [x] If every applicable machine gate passes, the result freezes only sanitized real-provider evidence, independently verifies the Contacts release pack and Release Candidate qualification, and produces an immutable proof that replays with zero provider calls.
- [x] If any gate fails, the result is a bounded no-go or failure record; it does not freeze reusable responses, construct a real proof, promote a dataset, or overstate the outcome as a qualification.
- [x] Clean offline verification passes the positive proof, its declared replay behavior, and all required Contacts negative or boundary cases without network access.
- [x] The final record distinguishes the exact Contacts Release Candidate claim from false Publishable and Training Recommended claims, global mutation-activation status, and any downstream-utility claim.
- [x] The ticket records an evidence-backed recommendation about whether a Mobile Messages lifecycle decision should be opened, without implementing Mobile Messages work.

## Scope guard

Do not initiate Mobile Messages implementation, publication approval, dataset
distribution, training, or a broader provider campaign. This is one bounded
Contacts acceptance or no-go operation; a fresh authorization is required for
every actual provider-spending attempt.

## Authorization record

On 2026-09-04, the synthesis operator explicitly authorized one bounded
Contacts live-acceptance operation with authorization ID
`contacts-live-20260904-01`: `deepseek-v4-flash` generation, the independent
`deterministic_contacts_mutation_judge_v1` judge, at most 10 generator calls,
at most 11 judge calls, and zero generator retries. The configured
OpenAI-compatible destination is `api.deepseek.com`; only Contacts fixture
tasks, coverage assignments, synthetic contact fields, and mutation-judgment
requests are in scope. The operation writes to
`artifacts/contacts-live-acceptance-20260904-01`.

## Implementation

Hardened the live evidence boundary so frozen Contacts evidence rejects
per-attempt retry overflow, logical-call-budget overflow, provider parser drift,
provider-error records carrying response material, and incomplete replay-input
sets. Fixed replay to reconstruct the exact issued coverage assignment,
locally-derived difficulty, and recovery branch before Contacts execution, and
to require replayed accepted/rejected outcomes to match the frozen outcome.
Added the public `real_live` proof-verification seam and the offline
`scripts/verify_contacts_acceptance_proof.py` command; verification replays the
copied proof through production Contacts contracts with zero provider calls.

The focused injected-transport acceptance test now covers the offline verifier,
exact release-profile fields, and frozen budget integrity. No real provider
request was made during this implementation work; the subsequent explicitly
authorized live result is recorded below. No Contacts Release Candidate or
downstream-utility claim is asserted from the injected proof alone.

Evidence-backed Mobile Messages recommendation: defer opening a Mobile
Messages implementation; after a separately authorized `real_live` Contacts
proof passes the offline verifier, open only a decision-scoped Mobile Messages
lifecycle ticket. This ticket does not authorize or implement Mobile Messages.

## Live execution attempt — 2026-09-04

The authorized operation `contacts-live-20260904-01` reached the fixed
mutation-judge preflight and failed closed with
`contacts_live_mutation_judge_preflight_failed`. The sanitized failure record
reports one judge attempt with `provider_outcome: unavailable` and an
`http_status` failure class; it made zero logical or physical generator calls,
used no generator tokens, and did not process a candidate.

The only retained artifact is the bounded, sanitized
[failure record](../../../artifacts/contacts-live-acceptance-20260904-01/contacts_live_attempt_failure.json).
It declares no frozen provider evidence, proof root, tracer proof, or
qualification. This authorization is consumed. The configuration correction
below supersedes the failed model binding; the ticket is now blocked pending a
fresh authorization for any future real-provider attempt. It does not claim a
Contacts Release Candidate, Publishable, Training Recommended, mutation
activation, or downstream-utility outcome.

## Default judge correction — 2026-09-04

The failed operation exposed that
`deterministic_contacts_mutation_judge_v1` was sent as a literal remote model
identifier rather than resolved as a local alias. The exact Contacts live
release profile, its fixture, and the live CLI default now use the independent
`deepseek-v4-pro` judge. This configuration change does not alter the retained
failure record or authorize another provider request. The timeout-policy
correction below supersedes the original 1.0-second deadline.

## Second authorization record — 2026-09-04

The synthesis operator explicitly authorized one new bounded Contacts
live-acceptance operation with authorization ID
`contacts-live-20260904-02`. It uses the configured OpenAI-compatible
`api.deepseek.com` endpoint, `deepseek-v4-flash` generation, the independent
`deepseek-v4-pro` mutation judge, a maximum of 10 generator calls and 11 judge
calls, zero generator retries, and the existing 1.0-second judge timeout. Only
Contacts fixture tasks, coverage assignments, synthetic contact fields, and
mutation-judgment requests are in scope. The operation writes to
`artifacts/contacts-live-acceptance-20260904-02`.

## Corrected-default execution attempt — 2026-09-04

The authorized operation `contacts-live-20260904-02` used the corrected
`deepseek-v4-pro` judge binding and failed closed at the same fixed preflight.
Its bounded, sanitized [failure record](../../../artifacts/contacts-live-acceptance-20260904-02/contacts_live_attempt_failure.json)
reports one judge attempt with the distinct `timeout` failure class. It made
zero logical or physical generator calls, used no generator tokens, processed
no candidate, and published no frozen provider evidence, proof root, tracer
proof, or qualification.

This establishes that the existing 1.0-second judge timeout is insufficient
for this endpoint/model/preflight combination. The second authorization is
consumed. The ticket is blocked pending an explicitly approved timeout/retry
policy change and a fresh authorization; it does not claim a Contacts Release
Candidate, Publishable, Training Recommended, mutation activation, or
downstream-utility outcome.

## Timeout-policy correction — 2026-09-04

The synthesis operator approved a 90-second judge deadline with zero judge
retries, leaving thinking-mode behavior unchanged. The exact Contacts live
release profile, fixture, and test coverage now bind those values. This keeps
the judge-call ceiling at 11 and did not authorize a third provider attempt;
the third authorization is recorded below.

## Third authorization record — 2026-09-04

The synthesis operator explicitly authorized one new bounded Contacts
live-acceptance operation with authorization ID
`contacts-live-20260904-03`. It uses the configured OpenAI-compatible
`api.deepseek.com` endpoint, `deepseek-v4-flash` generation, the independent
`deepseek-v4-pro` mutation judge, a maximum of 10 generator calls and 11 judge
calls, zero generator retries, and the approved 90-second, zero-retry judge
policy. Only Contacts fixture tasks, coverage assignments, synthetic contact
fields, and mutation-judgment requests are in scope. The operation writes to
`artifacts/contacts-live-acceptance-20260904-03`.

## Third execution attempt — 2026-09-04

The authorized operation `contacts-live-20260904-03` used the corrected
`deepseek-v4-pro` binding and the approved 90-second, zero-retry judge policy.
The preflight received one response, so it no longer timed out, but the strict
semantic-verdict contract classified it as `output_invalid`. Its bounded,
sanitized [failure record](../../../artifacts/contacts-live-acceptance-20260904-03/contacts_live_attempt_failure.json)
records 944 prompt tokens, 2,997 completion tokens, and 3,941 total judge
tokens; it made zero logical or physical generator calls, processed no
candidate, and published no frozen provider evidence, proof root, tracer proof,
or qualification.

The response body is intentionally not retained, so the record cannot
distinguish the exact schema or semantic-verdict deviation. This authorization
is consumed. The ticket is blocked pending an explicitly approved correction
to the remote judge configuration or output contract, regression coverage, and
fresh authorization for any future provider attempt; it does not claim a
Contacts Release Candidate, Publishable, Training Recommended, mutation
activation, or downstream-utility outcome.

## Thinking-mode correction — 2026-09-04

The synthesis operator approved an explicit judge-only non-thinking setting:
`thinking_mode: disabled`. The exact Contacts live release profile, fixture,
and injected-transport preflight coverage now bind that setting alongside the
existing `deepseek-v4-pro`, 90-second, zero-retry policy. This configuration
change did not authorize a provider request by itself; the newly authorized
attempt is recorded below.

## Fourth authorization record — 2026-09-04

The synthesis operator explicitly authorized one new bounded Contacts
live-acceptance operation with authorization ID
`contacts-live-20260904-04`. It uses the configured OpenAI-compatible
`api.deepseek.com` endpoint, `deepseek-v4-flash` generation, the independent
`deepseek-v4-pro` mutation judge, a maximum of 10 generator calls and 11 judge
calls, zero generator retries, and the approved 90-second, zero-retry,
non-thinking judge policy. Only Contacts fixture tasks, coverage assignments,
synthetic contact fields, and mutation-judgment requests are in scope. The
operation writes to `artifacts/contacts-live-acceptance-20260904-04`.

## Fourth execution attempt — 2026-09-04

The authorized operation `contacts-live-20260904-04` passed the corrected
non-thinking `deepseek-v4-pro` judge preflight: its single judge response used
865 prompt tokens, 304 completion tokens, and 1,169 total tokens. The pipeline
then made one logical and physical `deepseek-v4-flash` generator call, which
ended in a bounded `provider_error`; it accepted no candidate. Its bounded,
sanitized [failure record](../../../artifacts/contacts-live-acceptance-20260904-04/contacts_live_attempt_failure.json)
therefore reports `contacts_live_pipeline_failed`, no frozen provider evidence,
no proof root, no tracer proof, and no qualification.

The generator failure record deliberately retains only the aggregate
`provider_error` outcome, not the raw provider response, HTTP status, prompt,
or credential. This authorization is consumed. The ticket is blocked pending a
bounded generator-failure diagnosis or correction and fresh authorization for
any future provider attempt; it does not claim a Contacts Release Candidate,
Publishable, Training Recommended, mutation activation, or downstream-utility
outcome.

## Standing Contacts authorization — 2026-09-04

The synthesis operator authorized further provider calls without per-attempt
confirmation when they are necessary to diagnose or complete this ticket only.
Each call must still use a fresh authorization ID and output directory, remain
at `api.deepseek.com`, use the current `deepseek-v4-flash` generator and
the 90-second generator deadline plus the non-thinking `deepseek-v4-pro` judge
policy, and stay within the declared Contacts fixture/payload,
10-generator-call, 11-judge-call, and zero-generator-retry bounds. This
standing authorization does not cover other domains,
publication, training, distribution, or broader provider campaigns.

## Generator failure diagnostics — 2026-09-04

Live failure records now retain aggregate sanitized generator failure classes
(`timeout`, `http_status`, `transport`, `response_schema`, `configuration`, or
`provider_error`) without retaining provider payloads or error messages. The
injected-transport regression covers ordinary HTTP failure aggregation and
single-call ambiguous timeouts.

## Fifth authorization record — 2026-09-04

The standing authorization binds the next bounded diagnostic or acceptance
operation to `contacts-live-20260904-05`, using the same endpoint, models,
payload scope, 10-generator-call and 11-judge-call limits, zero generator
retries, and output directory
`artifacts/contacts-live-acceptance-20260904-05`.

## Fifth execution attempt — 2026-09-04

The authorized operation `contacts-live-20260904-05` passed the non-thinking
judge preflight and reached eight generator calls. Seven were validated; the
eighth failed with the newly captured `timeout` class. Its bounded, sanitized
[failure record](../../../artifacts/contacts-live-acceptance-20260904-05/contacts_live_attempt_failure.json)
reports 30,402 aggregate generator tokens and no frozen provider evidence,
proof root, tracer proof, or qualification. This authorization is consumed.

## Generator deadline correction — 2026-09-04

The fifth failure confirms that the former 30-second generator deadline was
insufficient for this endpoint/model/prompt path. The standing authorization
therefore adopts a 90-second generator deadline, bound into the live
authorization record and CLI default, without increasing retry or call limits.
Injected-transport regression proves the deadline reaches actual generator
requests and that ambiguous generator failures remain safely classified.

## Sixth authorization record — 2026-09-04

The standing authorization binds the next bounded Contacts operation to
`contacts-live-20260904-06`, with the same endpoint, models, payload scope,
10-generator-call and 11-judge-call limits, zero generator retries, and
90-second generator/judge deadlines. Its output directory is
`artifacts/contacts-live-acceptance-20260904-06`.

## Sixth execution attempt — 2026-09-04

The authorized operation `contacts-live-20260904-06` passed the non-thinking
judge preflight and completed all 10 generator calls under the corrected
90-second deadline with no generator failure class. All 10 responses passed the
provider contract, but seven were rejected by Domain Plan membership, leaving
only three accepted samples against the five-sample coverage target. Its
bounded, sanitized [failure record](../../../artifacts/contacts-live-acceptance-20260904-06/contacts_live_attempt_failure.json)
records `contacts_live_coverage_evidence_incomplete`,
`domain_plan_membership_rejected: 7`, 61,595 aggregate generator tokens, and
no frozen provider evidence, proof root, tracer proof, or qualification.

This authorization is consumed. The ticket is blocked on a bounded diagnosis
and correction of the membership rejections. The standing Contacts
authorization remains available for a new bounded verification attempt after
that correction; this result makes no Contacts Release Candidate, Publishable,
Training Recommended, mutation activation, or downstream-utility claim.

## Membership-rejection diagnostics — 2026-09-04

Live no-go summaries now aggregate only allowlisted local
`membership_reason` values for Domain Plan membership rejections. The summary
does not retain generated tasks, provider responses, prompts, or source
payloads. The targeted regression covers safe aggregation of
`grounding_membership_mismatch`.

## Seventh authorization record — 2026-09-04

The standing authorization binds the next bounded Contacts operation to
`contacts-live-20260904-07`, with the same endpoint, models, payload scope,
10-generator-call and 11-judge-call limits, zero generator retries, and
90-second generator/judge deadlines. Its output directory is
`artifacts/contacts-live-acceptance-20260904-07`.

## Seventh execution attempt — 2026-09-04

The authorized operation `contacts-live-20260904-07` completed all 10
generator calls with no provider failure class, but again left only three
accepted samples. Its bounded, sanitized [failure record](../../../artifacts/contacts-live-acceptance-20260904-07/contacts_live_attempt_failure.json)
identifies all seven Domain Plan membership rejections as
`grounding_membership_mismatch`. It published no provider evidence, proof root,
tracer proof, or qualification.

## Grounding-reason refinement — 2026-09-04

The Contacts Domain Pack now differentiates safe local grounding failures as
primary-argument, expected-state, or final-answer mismatches; the live summary
whitelists each new reason. The primary-argument branch has a direct Domain Run
regression test. This refines diagnostics without relaxing any membership gate
or retaining provider content.

## Eighth authorization record — 2026-09-04

The standing authorization binds the next bounded Contacts operation to
`contacts-live-20260904-08`, with the same endpoint, models, payload scope,
10-generator-call and 11-judge-call limits, zero generator retries, and
90-second generator/judge deadlines. Its output directory is
`artifacts/contacts-live-acceptance-20260904-08`.

## Eighth execution attempt — 2026-09-04

The authorized operation `contacts-live-20260904-08` completed all 10
generator calls with no provider failure class, but again left three accepted
samples. Its bounded, sanitized [failure record](../../../artifacts/contacts-live-acceptance-20260904-08/contacts_live_attempt_failure.json)
attributes all seven membership rejections to
`grounding_final_answer_mismatch`. It published no provider evidence, proof
root, tracer proof, or qualification.

## Follow-up-state reason refinement — 2026-09-04

The Contacts Domain Pack now distinguishes an email/final-answer mismatch from
a follow-up state (`name` or `note`) mismatch. Direct local regressions cover
both primary-argument and follow-up-state branches. This preserves the same
strict membership gate while allowing the next run to select one prompt
correction rather than conflate two possible causes.

## Ninth authorization record — 2026-09-04

The standing authorization binds the next bounded Contacts operation to
`contacts-live-20260904-09`, with the same endpoint, models, payload scope,
10-generator-call and 11-judge-call limits, zero generator retries, and
90-second generator/judge deadlines. Its output directory is
`artifacts/contacts-live-acceptance-20260904-09`.

## Ninth execution attempt — 2026-09-04

The authorized operation `contacts-live-20260904-09` completed all 10
generator calls with no provider failure class, but again left three accepted
samples. Its bounded, sanitized [failure record](../../../artifacts/contacts-live-acceptance-20260904-09/contacts_live_attempt_failure.json)
identifies all seven membership rejections as
`grounding_followup_state_mismatch`. It published no provider evidence, proof
root, tracer proof, or qualification.

## Plan A — parser-enforced follow-up grounding contract — 2026-09-04

The shared `DomainTaskTypeSpec` now supports explicit expected-state grounding
bindings with `exact` and `contains` relations. Contacts follow-up declares
`name == observation.name` and `note contains observation.email`; the prompt
renders those bindings and the production parser requires one observation to
satisfy all of them. The prior post-generation Domain Plan rejection remains a
defense-in-depth gate, but malformed follow-up state now fails before candidate
processing.

Added `run_contacts_live_contract_canary`, a non-qualifying follow-up canary
that uses production prompt/parser/coverage/Contacts-membership seams, one
remote admission decision, frozen admission evidence, and a provider-free
local replay. It writes only sanitized status evidence and must pass before
another full Contacts acceptance campaign is attempted.

The parser-enforced contract, canary pass/fail behavior, prior Contacts
regressions, and the full offline suite (976 tests) pass. The canary is now the
next authorized provider operation.

## First Contacts contract-canary authorization — 2026-09-04

The standing authorization bound one non-qualifying, one-generator-call
follow-up grounding canary to authorization ID `contacts-canary-20260904-01`
and output directory
`artifacts/contacts-live-contract-canary-20260904-01`. It uses
`api.deepseek.com`, `deepseek-v4-flash`, the 90-second generator deadline, and
only the assigned synthetic Contacts follow-up grounding. It did not invoke the
mutation judge, execute a candidate, create a dataset, freeze provider
evidence, construct a proof, or make a qualification claim.

## Contacts contract-canary result — 2026-09-05

The one-call canary passed through the production prompt, parser, coverage
assignment, and Contacts Domain Plan membership seams for one follow-up
assignment. Its sanitized [record](../../../artifacts/contacts-live-contract-canary-20260904-01/contacts_live_contract_canary.json)
shows exactly one generator call under the 90-second deadline and no
qualification or proof. This is sufficient to unlock one full campaign under
the same standing authorization; it does not itself establish a release claim.
It predates the admission/replay extension below, so it does not unlock a new
full campaign on its own.

## First post-Plan A full campaign result — 2026-09-05

The full operation `contacts-live-20260905-01` passed the corrected generation
and admission path, reached independently verified Release Candidate
qualification, then failed closed at `contacts_replay_outcome_mismatch` during
the required provider-free replay. The failure record retains five generator
calls, three judge calls, a passed qualification summary, and the fact that
frozen provider evidence was discarded; it retains no provider content or
proof. This exposed the need to replay the frozen remote admission decision
rather than re-judge it locally.

## Extended Contacts contract-canary authorization — 2026-09-05

The standing authorization binds one non-qualifying, one-generator and
one-judge-call canary to authorization ID `contacts-canary-20260905-02` and
output directory `artifacts/contacts-live-contract-canary-20260905-02`. It
uses the existing endpoint, models, 90-second deadlines, and synthetic
follow-up payload scope, executes the candidate only in an isolated local
fixture, and verifies frozen-admission provider-free replay. It cannot create
a dataset, freeze provider evidence, construct a proof, or make a
qualification claim.

## Extended Contacts contract-canary result — 2026-09-05

The extended canary passed its one generator call, one remote admission-judge
call, exact follow-up grounding check, and provider-free frozen-admission local
replay. Its sanitized [record](../../../artifacts/contacts-live-contract-canary-20260905-02/contacts_live_contract_canary.json)
reports `admission_replay.provider_calls: 0` and no qualification or proof. It
is sufficient to unlock one full acceptance campaign under the corrected replay
path.

## Corrected full campaign authorization — 2026-09-05

The standing authorization binds the next full Contacts acceptance operation to
`contacts-live-20260905-02`, using `api.deepseek.com`, the
`deepseek-v4-flash` generator, non-thinking `deepseek-v4-pro` judge, 90-second
generator/judge deadlines, zero generator retries, at most 10 generator calls
and 11 judge calls, and the existing synthetic Contacts payload scope. Its
output directory is `artifacts/contacts-live-acceptance-20260905-02`.

## Corrected full campaign result — 2026-09-05

The authorized operation `contacts-live-20260905-02` passed all Contacts
machine gates and independently verified Release Candidate qualification. It
made five logical/physical generator calls with no retries and three successful
mutation-judge calls. It froze only sanitized real-live provider evidence and
constructed [proof `contacts_acceptance_proof_078df0cf72e18957`](../../../artifacts/contacts-live-acceptance-20260905-02-proof/contacts_acceptance_proof.json).

The independent offline verifier passed the positive chain and all 13 required
negative or boundary cases with zero provider calls. The proof claims exactly
`release_candidate`; `publishable`, `training_recommended`, global mutation
activation, and downstream utility are false. No publication, distribution,
training, or Mobile Messages implementation was initiated. The evidence now
supports opening only a separately scoped Mobile Messages lifecycle decision,
not implementation work.
