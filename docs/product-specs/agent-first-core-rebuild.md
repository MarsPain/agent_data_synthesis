# Agent-First Core Rebuild

## Problem Statement

The current framework spends more complexity on artifact identity,
compatibility, release qualification, publication authority, and replay proofs
than on the synthesis operator's primary need: producing correct, diverse Agent
trajectories efficiently on one machine.

Domain changes cross the legacy bundle, Domain Pack lifecycle, shared contracts,
qualification, compatibility, and proof test matrices. Meanwhile, representative
samples still use scripted solution policies and constant accepted-sample
quality scores. Artifact consistency is better established than Agent behavior
or semantic quality.

The replacement must reduce the number of places a domain author changes,
collect real Agent rollouts, and make its quality evidence interpretable.
Engineering readiness, observed dataset quality, and eligibility to automate
semantic admission are separate decisions. A useful replacement must not remain
blocked solely because a model judge cannot yet meet calibration thresholds.

## Solution

Build an isolated, library-first synthesis core around one deep Domain adapter
seam. Domains own executable environments, tools, task semantics, mutation
authorization, deterministic assessment, and structural classification. The
shared core owns model interaction, bounded execution, durable progress, common
admission policy, dataset assembly, and sanitized lineage.

Compile proposals into a public task and private verification criteria whose
meaning is supported by the public request and observable environment. An Agent
then chooses tool calls and a final response through a provider-neutral JSON
protocol. Scripted policies are diagnostic oracles, not formal demonstrations.

Use SQLite and streaming export for single-machine runs. Retire legacy
compatibility, qualification, authority, proof, and tracer implementations after
engineering and independent human dataset acceptance. A judge starts in shadow
mode; semantic enforcement is an independently deliverable option requiring
held-out human evidence. A release lab is deferred until it has a concrete
consumer.

## User Stories

1. As an operator, I want observable Agent trajectories rather than oracle
   scripts, including successful recovery and separately stored negatives.
2. As an operator, I want a library-first run/resume interface and thin CLI,
   with deterministic replay and validated review-label import.
3. As an operator, I want bounded task generation, concurrency, rollout steps,
   repairs, retries, and durable provider budgets across cancellation and resume.
4. As an operator, I want frozen local inputs and saved Task cases, so recovery
   and replay use the original environment and task meaning.
5. As an operator, I want task-space exhaustion distinguished from scheduler
   capacity, so a larger attempt budget does not imply more distinct tasks.
6. As a domain author, I want one code adapter owning task compilation,
   isolated state, tools, authorization, assessment, and diversity semantics.
7. As a domain author, I want public instructions and private verification
   criteria to agree, including requests with several acceptable outcomes.
8. As a domain author, I want task additions and verifier changes confined to
   the Domain, with one reusable compliance suite.
9. As a consumer, I want one observable Episode schema with public task, tools,
   events, outcome, verification, admission mode, and sanitized lineage.
10. As a consumer, I want deterministic admission, human review, and enforced
    judge approval distinguished without exposing private oracle fields.
11. As a reviewer, I want blind labels and explicit metric denominators, with
    diagnostic error enrichment separated from dataset acceptance.
12. As a reviewer, I want a judge independent of both task generator and Agent,
    and enforcement enabled only for the model, Domain, and task distribution
    actually evaluated.
13. As a maintainer, I want a real Domain to challenge the interface early,
    followed by a second Domain before treating that interface as stable.
14. As a maintainer, I want fast behavioral tests, module-owned persistence
    models, a test-only fourth Domain, and measurable change locality.
15. As a maintainer, I want one atomic cutover without old-format readers,
    followed by one implementation and test surface.
16. As a maintainer, I want engineering and human dataset acceptance to permit
    cutover while an unqualified judge remains explicitly in shadow mode.

## Implementation Decisions

### Public Interface and Domain Ownership

- Build an isolated package with no imports from legacy synthesis or runtime
  packages. Keep the legacy entrypoint frozen until cutover.
- The synthesis engine exposes run and resume. Replay and review-label import
  operate on completed run directories. The CLI delegates to these interfaces.
- A Domain adapter opens a Domain run. The run supplies deterministic task
  slots, compiles proposals into Task cases, and opens candidate-local Episodes.
  An Episode lists tools, executes calls, and assesses observable execution.
- Contacts, Mobile Messages, and Workspace Tasks are code adapters. Built-in
  registration is the only central location naming production Domains.
- Keep the interface provisional through a real Contacts slice and second
  production Domain. Adding a test-only fourth Domain requires no synthesis,
  ledger, rollout, or quality changes.
- Task slots are deterministic for a fixed Domain version, frozen source, seed,
  and attempt ceiling. The core assigns Candidate/Episode identity and stable
  sequence; providers cannot assert identity, authority, or expected state.
- Each Task case has a public Agent view, a private oracle view, and a
  Domain-owned semantic key. Private data is available only to Domain
  authorization/assessment and the private operational ledger.
- Each assessment emits bounded checks, reason codes, coverage tags, structural
  key, and state-change evidence. Shared quality policy does not interpret
  domain fields or accept an unrestricted dictionary as a substitute for a
  defined interface.

### Task Meaning and Verification

- Compilation must establish that the requested action, target, arguments,
  conditions, and success criteria follow from the public instruction and
  evidence obtainable through the available tools. A task-slot intention or
  provider assertion alone cannot authorize a mutation.
- The first implementation supports bounded, deterministically checkable
  request forms. Unsupported free-form semantics, missing authorization,
  unresolved target ambiguity, and uncheckable conditions are rejected before
  rollout with bounded reasons. An uncalibrated judge cannot certify them.
- Negated actions are forbidden; conditional mutations are allowed only after
  their condition is established from observable evidence. Tool execution
  checks the actual arguments against this authorization before changing state.
- Private criteria may contain expected source facts, but must not impose an
  undisclosed choice. A request for an unspecified follow-up note cannot require
  one hidden exact sentence. Use a Domain-owned allowed-result set or predicate
  for open outcomes; do not execute model-generated verifier code.
- Final assessment checks requested effects, absence of unintended effects,
  final-answer grounding, and terminal outcome. Exact equality is appropriate
  only when the public request and environment determine an exact result.
- Semantic keys describe the requested outcome and relevant constraints and
  grounding, not instruction wording. Paraphrases collapse; distinct authorized
  outcomes or material conditions remain distinct.
- Structural keys describe meaningful executed tool/state/binding/recovery
  topology. Wording changes, entity substitutions with unchanged topology,
  coverage labels, and redundant tool calls cannot manufacture new families.
- Each production Domain owns a small reviewed classification corpus with
  expected equivalences and distinctions. Preserve the behavioral meaning of
  the historical family baseline through these examples, without adding
  old-format readers or retaining the legacy proof machinery.

### Model Interaction and Limits

- Task generator, Agent, and optional quality judge use one JSON model
  interface. The production adapter uses an OpenAI-compatible chat endpoint;
  deterministic fakes and production mock transport exercise the same contract.
- An Agent decision is exactly one tool call or one final response, with no
  reasoning field or extra keys. Agent context contains only the public task,
  tool schemas, prior observable events, and remaining step budget.
- Default task batches contain eight proposals. Episode concurrency defaults
  to four, configurable from one through sixteen. Rollouts default to twelve
  steps, configurable from one through sixty-four.
- Allow one malformed-decision repair per Episode and at most two transport
  retries per logical model request. Generator and judge malformed output is
  classified without unbounded repair loops. Explicit timeouts, response-size
  and output-token limits, accepted/attempt targets, and per-role plus total
  physical-request ceilings are frozen in the run configuration.
- One task attempt is one allocated slot, including generation/compilation
  failure or duplicate rejection. Repairs, retries, and resume reuse that slot
  but consume new physical-request reservations; they do not reset either
  ceiling. A batch cannot allocate more than the remaining slot budget.
- Unknown tools, invalid arguments, and ordinary tool failures become bounded
  observations recoverable within the step budget. Unauthorized mutation
  terminates before the operation and produces a negative.
- Provider failures, exhausted limits, and incomplete runs have bounded reasons.
  Report calls, retries, known tokens, and unknown usage by role; do not infer
  prices or represent an unknown response as zero token cost.

### Persistence, Recovery, and Capacity

- SQLite is the sole operational ledger. Commit each terminal Candidate outcome
  transactionally and export by stable sequence. No append-only hash journal,
  evidence graph, persisted lock schema, or distributed coordinator is added.
  One run directory permits one active writer through a process-lifetime lock.
- Before paid work, the Domain admits and freezes local source bytes or
  normalized initial state in the private run directory and records its content
  fingerprint. Resume and replay use that snapshot, not a mutable source path.
  Missing or corrupted snapshots fail before any provider call.
- Persist allocated slots before generation and compiled public/private Task
  cases before Agent execution. Resume preserves committed Task cases and
  original identities rather than regenerating their meaning.
- Reserve each physical provider request durably before dispatch, including
  generation, Agent, judge, repair, retry, and restarted-Episode requests.
  Unknown outcomes after a crash remain charged against the request ceiling.
  Resume never replenishes counters; abandoned generation requests may be
  reissued only within the remaining budget.
- Resume rejects configuration, Domain-version, or snapshot drift; skips
  committed terminal Episodes; and restarts incomplete Episodes from frozen
  initial state. This promises no repeated terminal work, not exactly-once
  remote requests. If the remaining budget is insufficient, report partial
  completion rather than silently expanding it.
- Cancellation stops new dispatch, preserves completed outcomes, and leaves
  incomplete work resumable. Concurrent completion and duplicate admission
  have stable ordering and deterministic winners.
- The engine streams work and export, targeting 1,000 to 10,000 accepted
  trajectories when the Domain has sufficient distinct task capacity. A
  scheduler benchmark cannot certify that production task-space capacity.
- Domains expose known slot exhaustion and report finite capacity when known.
  Reject an impossible target before paid work when capacity is known. Skip
  already admitted semantic keys before Agent execution; bounded replacement
  attempts never manufacture new identity from paraphrases. Stop at Domain
  exhaustion or the attempt ceiling and report the unfulfilled target. Unknown
  capacity remains explicitly unknown.

### Artifacts and Admission

- Demonstrations contain deterministically successful and successful-recovery
  Episodes. Negatives contain failed, unsafe, duplicate, exhausted, and
  ineligible Episodes. They share one schema but are separate collections;
  dataset split assignment must not leak the same semantic task across
  training and evaluation through either collection.
- Deterministic execution, authorization, final-state verification, final-answer
  grounding, unsafe-material scanning, and semantic-key duplicate admission
  are hard gates from the first version.
- Shadow demonstrations mean deterministic admission, not automatic human
  approval. Admission mode and review evidence remain explicit. Validated
  human-pass labels identify a reviewed subset; failed, uncertain, and
  unreviewed Episodes cannot be presented as human-approved.
- Public persistence contracts are limited to run configuration, Episode,
  quality judgment, review label, quality report, and manifest. The Task case
  ledger record is private. Owning modules validate their models with Pydantic
  at persistence seams; no central contracts module is introduced.
- The manifest binds final artifact files and normalized sanitized configuration,
  including the source fingerprint. Internal snapshot integrity and flat file
  hashes do not grow into nested object hashes or per-domain evidence chains.
- Credentials, unrestricted provider payloads, private oracle fields, and local
  absolute source paths are excluded from datasets, public reports, and logs.
  Values legitimately revealed by public instructions or tool observations may
  occur in Episodes; oracle-field exclusion is not a blanket value blacklist.
  Retain sanitized model/template identity, response hashes, bounded failure
  classes, and usage. Keep frozen inputs and oracle records private.
- Review-label import validates known queued Episode ids, purpose/cohort
  membership, dimensions, and bounded evidence references. Duplicate, foreign,
  malformed, and unsafe labels are rejected. Partial submissions remain
  incomplete until every required label is present; import does not silently
  rewrite finalized Episodes or acceptance denominators.
- Runtime dependencies are the OpenAI-compatible HTTP client, Pydantic, and the
  standard library. Test tooling is development-only.

### Shadow Review and Optional Enforcement

- The judge assesses instruction fidelity, action efficiency, observation
  grounding, final-response quality, and safety from the public task, observable
  events, bounded deterministic results, and a fixed rubric. Its known model
  identity must differ from both task generator and Agent identities.
  Different identities are a minimum control, not proof of uncorrelated errors.
- Each dimension is pass, fail, or uncertain with bounded reasons and event
  references. For both judge and human labels, any failed dimension makes the
  Episode fail; otherwise any uncertain dimension makes it uncertain; all five
  must pass for an Episode pass. A critical safety failure is always a fail.
- Missing, invalid, or unavailable judge results are reported as unavailable and
  treated as uncertain for admission. Unknown or matching model identities
  make enforcement ineligible. Shadow judgments never change either collection.
- Blind review hides model identities, judge verdicts, and admission decisions.
  Reviewers see the public task, tools, and observable trajectory. Deterministic
  results remain available for later adjudication, not as a suggested label.
- Calibration development uses an error-enriched cohort: at least one
  hundred reviewed Episodes, at least thirty per Domain, all judge fail or
  uncertain outcomes in its bounded campaign, and a stratified fill of passes
  by task type, difficulty, and structural family. Report its sampling counts
  and raw confusion table as diagnostics, not population quality estimates.
- Activation requires a separate, untouched evaluation cohort of at least one
  hundred deterministically eligible Episodes and thirty per Domain. Freeze
  cohort membership without selecting on judge verdict, and review it in full.
  Freeze rubric, thresholds, model/prompt settings, Domain versions, and task
  distribution before inspecting its labels. Development and evaluation use
  disjoint semantic-task groups and relevant grounding groups; new ids or
  paraphrases do not establish independence.
- Compute the following empirical metrics on the evaluation cohort only. Let
  J and H be aggregate judge and human verdicts; unavailable J counts as
  uncertain. Report the numerator, denominator, three-way confusion table,
  and overall/per-Domain values. A required zero denominator or missing human
  label makes activation ineligible.

  | Metric | Definition | Activation threshold |
  | --- | --- | --- |
  | Agreement | count(J = H) / reviewed count | Overall at least 85% |
  | False-pass | count(J = pass and H != pass) / count(J = pass) | Overall at most 5%; each Domain at most 10% |
  | False-fail | count(H = pass and J != pass) / count(H = pass) | Overall at most 10% |
  | Critical safety false-pass | Judge-passed Episodes with human-confirmed critical safety failure | Zero |

- Human uncertain is not approval; judge uncertain is not admission. These are
  finite-cohort measurements, not guarantees of population error bounds.
  Calibration development diagnostics cannot substitute for held-out results.
- One flat quality-policy identity binds rubric, judge/generator/Agent identities
  and prompt/decoding settings, Domain versions, source/task-distribution scope,
  thresholds, and reviewed evaluation evidence. A change outside that scope
  requires a new policy and fresh evaluation; it cannot borrow old eligibility.
- Eligible enforcement is an explicit choice for a new run, never a mid-run
  transition. Enforce admits only judge-pass Episodes that also pass every
  deterministic gate. Fail, uncertain, and unavailable judgments stay out.
  Ineligible enforcement requests fail before paid work rather than silently
  falling back. Failed activation does not invalidate shadow core operation.

## Acceptance and Cutover

Acceptance records three separate results in the quality report, not a release
qualification state machine.

| Decision | Required evidence | Effect |
| --- | --- | --- |
| Engineering readiness | Behavioral, Domain, model, recovery, architecture, installation, locality, and scale checks | Required for core cutover |
| Dataset acceptance | Frozen three-domain Agent cohort and independent human review below | Required for core cutover |
| Semantic enforcement eligibility | Optional held-out judge evaluation above | Required only to enable automated semantic admission |

### Early Feasibility

Before broadening production adapters, exercise a real Contacts Agent slice
with a separately authorized pilot: target eight demonstrations, at most sixteen
task attempts, and explicit physical-request/retry ceilings. Inspect public
request/oracle alignment, direct lookup, authorized mutation, and successful
recovery; retain observed failures and model usage. At least one successful
Episode of each behavior must be inspectable before the pilot establishes
feasibility. This is diagnostic evidence, not calibration or cutover evidence.
Keep its semantic-task and grounding groups out of final acceptance. A failed
pilot informs design changes; it cannot trigger automatic paid reruns.

### Three-Domain Dataset Acceptance

- Use a fresh, explicitly authorized campaign in shadow mode, targeting exactly
  forty demonstrations per Domain with at most eighty task attempts per Domain.
  Freeze source/slot scope, model settings, limits, taxonomy examples, and
  review rubric before generation. Pilot and calibration-development task
  groups are excluded. An optional independent shadow judge may run within
  its authorized budget; unavailable judgments do not determine core cutover.
- Every selected demonstration must be an Agent rollout and pass deterministic
  gates. No unauthorized mutation or unintended persistent state change may
  occur. The demonstration collection contains no duplicate semantic keys.
- Each Domain retains at least seven Contacts, twelve Mobile Messages, and nine
  Workspace Tasks structural families respectively, with largest share at most
  0.35. The reviewed classification examples establish the meaning of these
  historical floors; labels or redundant calls cannot satisfy them.
- Freeze the first forty admitted Episodes per Domain in stable sequence before
  human labeling. Review all 120 demonstrations, using the same dimension
  aggregation as calibration. Require at least 90% human pass overall and in
  each Domain, with zero critical safety failures. Fail, uncertain, and missing
  labels are not passes; any missing label leaves acceptance incomplete.
- This is a full review of the bounded demonstration cohort. Negatives and
  error-enriched calibration samples are reported separately and never enter
  its pass-rate denominator. Do not remove failures or refill the cohort after
  seeing human labels. Any revised candidate set requires fresh acceptance.
- The same cohort may additionally evaluate an already frozen judge policy
  only if it remained untouched by calibration development. Once its labels
  inform tuning, it cannot validate the revised policy; fresh held-out
  evaluation and any provider use require a separately bounded campaign.
- Report yield, rejection causes, recovery, structural distribution, human
  outcomes, calls, retries, tokens, unknown usage, and unavailable prices.
  Report elapsed time and tokens per deterministic and human-passed Episode;
  do not invent price estimates or downstream training claims.
- Dataset or engineering failure blocks cutover. Judge activation failure
  leaves shadow mode available and is not itself a cutover failure. No failed
  campaign authorizes relaxed thresholds or automatic paid repetition.

### Migration and Change Locality

- Before interface stabilization, add a task type and change a verifier rule in
  one production Domain. The resulting diff must stay within that Domain and
  its fixtures/docs/tests. No core change, domain conditional, new generic
  configuration escape hatch, or duplicated core workflow may be needed.
- Record this diff scope, new public-contract count, dependency direction, and
  test timings in the feature discussion. Line count alone is not a success
  metric. A failed locality exercise requires interface revision before more
  adapters are copied.
- Cut over atomically after engineering and dataset acceptance. Remove legacy
  runtime/synthesis, compatibility readers, qualification, authority, proof,
  tracer, and related active scripts/tests. Old artifacts and profiles are not
  migrated; historical recovery uses repository history or regeneration.
- Update canonical docs and entrypoints together. Completed execution plans
  remain reachable history. Do not create a release-lab skeleton; introduce a
  separate package only when a concrete artifact consumer needs it.
- Optional enforcement implementation or real activation may remain unfinished
  at cutover. The delivered default stays shadow, and its unreviewed outputs
  cannot be described as semantically approved.

## Testing Decisions

- Test through the synthesis engine, reusable Domain compliance suite, and JSON
  model adapter. Do not preserve private-helper tests solely for legacy parity.
- Domain compliance covers deterministic slots, public/private compilation,
  exact and open-ended success predicates, negation, unmet conditions, target
  binding, missing arguments, isolation, tool schemas, authorized/rejected
  mutation, safe failure, recovery, semantic keys, and structural examples.
- Model contracts cover strict JSON, response bounds, sanitized lineage,
  response hashing, timeouts, retries, malformed decisions, and secret exclusion
  against production mock transport and fakes.
- End-to-end tests cover success, recovery, one repair and exhausted repair,
  unknown tools, invalid arguments, unauthorized mutation, step/provider
  exhaustion, cancellation, replay, and separate collections.
- Force reverse completion order to verify stable export and duplicate winners.
  Interrupt before/after Task-case persistence, provider dispatch, provider
  response persistence, and terminal commits. Repeated resumes must preserve
  request ceilings, terminal work, Task-case identity, and unknown usage.
- Modify the original source after snapshotting and prove unchanged replay;
  missing/corrupt snapshots and configuration/Domain drift fail before calls.
  Test known capacity shortfall, slot exhaustion, duplicate replacement bounds,
  and incomplete target reporting separately from storage scale.
- Quality tests cover shadow invariance, blind review, cohort separation,
  three-way aggregation, explicit denominators, zero-denominator failure,
  partial label import, foreign/duplicate labels, and fixed acceptance
  membership. Optional enforcement tests cover every inclusive threshold,
  per-Domain failure, identity/scope drift, critical safety failure, and
  non-activation without weakening core cutover.
- Architecture tests reject legacy/release-lab imports, core imports of
  production Domain implementations, Domain-to-Domain imports, and production
  domain literals outside built-in registration. Prove the fourth-Domain seam
  and production locality exercise without adding another framework layer.
- Core tests finish in less than five seconds, one Domain suite in less than
  fifteen seconds, and all ordinary non-scale tests in less than thirty seconds
  on the development machine.
- A manually selected ten-thousand-attempt fake-model scale suite uses a Domain
  with sufficient declared unique tasks, stays below 512 MiB peak memory,
  streams stable exports, and resumes without repeating terminal Episodes.
  Report attempts and unique accepted counts separately; this proves engine
  capacity, not production-Domain diversity or real-model quality.
- Real-provider work is never implicit. Pilot, acceptance, optional calibration,
  and reruns each require explicit authorization for their roles and ceilings.
  This specification and its implementation tickets do not authorize calls.
- Existing fixtures and semantic regression cases are behavioral prior art.
  Qualification, proof, compatibility, and helper tests are removed when their
  responsibilities disappear. Documentation validation continues to enforce
  links and source-of-truth ownership.

## Out of Scope

- Legacy profile/artifact support, converters, or redirecting imports.
- LLM-generated environments, tools, verifier code, arbitrary code execution,
  and a second declarative JSON/YAML Domain authoring mechanism.
- Native provider tool calling and hidden chain-of-thought capture.
- Distributed workers, brokers, service endpoints, local model serving, and
  GPU-cluster management.
- Network-backed Domain source collection; sources remain admitted local files
  or code configuration.
- Publication authority, cumulative qualification, training recommendations,
  live proof/tracer packages, compatibility corpora, and a release-lab skeleton.
- Automatic training, downstream benefit claims, or automatic judge activation
  from confidence scores, error-enriched samples, or reused tuning evidence.

## Further Notes

- Supersede [ADR 0002](../adr/0002-domain-pack-semantic-authority-and-deep-interface.md)
  before production code adopts the new Domain seam. Its replacement optimizes
  synthesis locality rather than proof-bearing capability qualification.
- Supersede [ADR 0001](../adr/0001-independent-semantic-mutation-admission.md)
  before removing semantic admission. Record bounded public-intent compilation,
  deterministic pre-mutation checks, independent post-execution review, and
  the explicit limits of shadow admission; moving a judge is not a substitute
  for validating authorization.
- [ADR 0003](../adr/0003-separate-evidence-verification-from-external-authority.md)
  remains a separation principle; external authority belongs outside synthesis.
- This spec owns desired behavior, migration, and acceptance. Ticket status,
  dependency edges, delivery order, assignments, and implementation discussion
  belong only in the local feature tracker.
