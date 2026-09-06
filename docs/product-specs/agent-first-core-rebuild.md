# Agent-First Core Rebuild

## Problem Statement

The current framework is robust at validating artifact identity, compatibility,
release qualification, publication authority, and replay proofs, but that
robustness no longer matches the synthesis operator's primary need: producing
high-quality and diverse Agent trajectories efficiently on one machine.

Recent work has high change amplification because domain behavior crosses the
legacy domain bundle, Domain Pack lifecycle, shared contracts, qualification,
compatibility, acceptance proofs, and their test matrices. The default test
loop mixes core synthesis checks with slow release-proof conformance. At the
same time, representative samples still use scripted solution policies and
assign constant accepted-sample quality scores, so the framework gives stronger
evidence about artifact consistency than about Agent policy quality,
naturalness, efficiency, or semantic diversity.

The synthesis operator needs a smaller long-term core whose main abstraction
cost is paid back when adding a domain, whose formal training records come from
real Agent rollouts, and whose quality claims are calibrated against human
review. The project does not need an interim compatibility period: the new core
may be built in isolation and replace the legacy implementation only after it
passes deterministic, representative, human-review, and scale acceptance.

## Solution

Build an isolated, library-first synthesis core around one deep Domain adapter
seam. A Domain adapter owns its environment, tools, task-slot semantics,
mutation authorization, candidate-local state, deterministic verification, and
structural classification. The shared core owns task batching, provider-neutral
Agent interaction, bounded local execution, durable progress, common quality
policy, dataset assembly, and sanitized lineage.

Candidate tasks are generated from domain-owned task slots, then compiled into
a public Agent view and a private oracle view. The Agent receives only the task,
tool schemas, observable trajectory events, and remaining step budget. It
chooses tool calls and the final response through a strict provider-neutral JSON
decision protocol. Scripted solution policies remain test or diagnostic
oracles; they do not produce formal training demonstrations.

Every completed Episode passes deterministic execution and domain verification
before it can enter the demonstrations collection. Successful recovery Episodes
remain demonstrations, while failed, unsafe, duplicate, exhausted, or otherwise
ineligible Episodes enter a separate negatives collection. An independent
quality judge initially runs in shadow mode. Stratified human blind review
calibrates its instruction-fidelity, action-efficiency, observation-grounding,
final-response, and safety decisions before any semantic judgment can become a
hard admission gate.

The new core supports resumable, bounded-concurrency runs of 1,000 to 10,000
accepted trajectories through a SQLite ledger and streaming artifact assembly.
It has no runtime compatibility layer for existing profiles or artifacts.
Release qualification, publication authority, training recommendation, live
proofs, tracers, and compatibility chains are excluded from the core. An empty,
independently packaged release lab preserves a future location for those
experiments without creating a dependency from the core.

## User Stories

1. As a synthesis operator, I want formal training data to come from an Agent
   interacting with tools, so that the trajectory reflects model policy rather
   than a compiled oracle path.
2. As a synthesis operator, I want scripted policies limited to tests and
   diagnostics, so that oracle demonstrations cannot be mistaken for Agent
   rollouts.
3. As a synthesis operator, I want to run synthesis entirely on one machine, so
   that I do not need brokers, distributed workers, or cluster operations.
4. As a synthesis operator, I want one explicit run configuration, so that
   candidate targets, attempt ceilings, model roles, and rollout limits are
   reproducible.
5. As a synthesis operator, I want a library-first interface, so that I can
   embed synthesis in local research workflows without shell orchestration.
6. As a synthesis operator, I want a thin CLI over the same library interface,
   so that interactive operation and programmatic operation cannot drift.
7. As a synthesis operator, I want task generation to be batched, so that
   provider cost is not dominated by one request per Candidate task.
8. As a synthesis operator, I want Agent work to use bounded concurrency, so
   that independent Episodes overlap without unbounded provider pressure.
9. As a synthesis operator, I want explicit accepted and attempt targets, so
   that a run cannot silently expand its provider budget.
10. As a synthesis operator, I want interrupted runs to resume from durable
    progress, so that completed Episodes are not regenerated.
11. As a synthesis operator, I want an incomplete in-flight Episode to restart
    from a fresh environment, so that partial state cannot contaminate resumed
    evidence.
12. As a synthesis operator, I want cooperative cancellation, so that no new
    work starts after cancellation while completed outcomes remain usable.
13. As a synthesis operator, I want stable output ordering under concurrency,
    so that equivalent deterministic runs remain comparable.
14. As a synthesis operator, I want provider call and token usage reported by
    role, so that I can measure verified trajectory yield against cost.
15. As a synthesis operator, I want provider failures and malformed decisions
    classified without storing unsafe response payloads, so that failures are
    inspectable without creating a secret surface.
16. As a synthesis operator, I want successful recovery trajectories retained,
    so that the demonstrations contain useful failure-recovery behavior.
17. As a synthesis operator, I want failed trajectories stored separately, so
    that negatives can support diagnostics or later preference work without
    contaminating demonstration training.
18. As a synthesis operator, I want deterministic replay through the same
    Domain interface, so that recorded actions and observations can be checked
    without domain-specific proof harnesses.
19. As a synthesis operator, I want local sources admitted through the owning
    Domain adapter, so that the core does not learn domain schemas.
20. As a domain author, I want one small Domain adapter interface, so that adding
    a domain does not require edits across pipeline, quality, storage, or
    orchestration modules.
21. As a domain author, I want to provide deterministic task slots, so that task
    type, grounding, difficulty, and coverage intent remain under domain
    control.
22. As a domain author, I want to compile model proposals into validated Task
    cases, so that provider output cannot assert canonical identity or expected
    state.
23. As a domain author, I want each Candidate task to receive a fresh
    Domain Episode, so that state changes cannot leak across candidates.
24. As a domain author, I want mutation authorization enforced before a local
    state-changing tool call, so that unrequested actions cannot become accepted
    demonstrations.
25. As a domain author, I want ordinary tool errors returned as observations,
    so that an Agent can demonstrate legitimate recovery.
26. As a domain author, I want deterministic assessment to remain domain-owned,
    so that business rules do not become shared-core conditionals.
27. As a domain author, I want to emit a semantic key for each Task case, so that
    paraphrases of the same domain outcome do not inflate dataset size.
28. As a domain author, I want to emit structural features for each Episode, so
    that diversity measures executed behavior rather than coverage labels.
29. As a data consumer, I want each Episode to contain the public task, tool
    schemas, observable events, outcome, verification, quality, and lineage, so
    that it is independently understandable.
30. As a data consumer, I want private oracle data excluded from demonstrations,
    so that expected answers and verifier state cannot leak into model input.
31. As a data consumer, I want hidden chain-of-thought excluded, so that the
    dataset remains provider-neutral and contains only observable Agent behavior.
32. As a data consumer, I want demonstrations and negatives to share one Episode
    schema while remaining in separate files, so that readers are simple and
    accidental mixing is visible.
33. As a data consumer, I want one manifest to bind final artifact files and
    sanitized run identity, so that integrity does not require a graph of nested
    object hashes.
34. As a quality reviewer, I want deterministic gates to run before semantic
    review, so that a model judge cannot override failed execution or state
    verification.
35. As a quality reviewer, I want an independent judge to return bounded
    pass, fail, or uncertain decisions with event references, so that its output
    is reviewable without free-form reasoning.
36. As a quality reviewer, I want the judge to begin in shadow mode, so that an
    uncalibrated model cannot decide sample admission.
37. As a quality reviewer, I want a stratified review queue, so that task types,
    structural families, difficulty, and judge outcomes are represented in
    calibration.
38. As a quality reviewer, I want review labels imported through a validated
    interface, so that missing, duplicated, or foreign Episode labels are
    rejected.
39. As a quality reviewer, I want measured false-pass and false-fail rates, so
    that semantic enforcement is activated from evidence rather than confidence
    claims.
40. As a quality reviewer, I want semantic enforcement to remain disabled when
    any domain misses calibration thresholds, so that aggregate performance
    cannot hide a weak domain.
41. As a framework maintainer, I want the synthesis engine to be the principal
    test seam, so that tests survive internal refactoring.
42. As a framework maintainer, I want one parameterized Domain compliance suite,
    so that every adapter receives the same isolation, tool, authorization, and
    assessment checks.
43. As a framework maintainer, I want a small test-only fourth domain, so that
    extensibility is proven by the absence of core changes.
44. As a framework maintainer, I want external model behavior behind one JSON
    model interface with production and fake adapters, so that provider tests do
    not leak into synthesis logic.
45. As a framework maintainer, I want persistence models owned by their modules,
    so that a central contracts file cannot become a high-fan-in change hub.
46. As a framework maintainer, I want old profiles and artifacts excluded from
    the new runtime, so that early-stage compatibility does not dominate future
    changes.
47. As a framework maintainer, I want the new implementation built in isolation,
    so that legacy callers cannot force temporary compatibility into the new
    interface.
48. As a framework maintainer, I want an atomic cutover only after acceptance,
    so that the repository never adopts an unverified replacement core.
49. As a contributor, I want core and Domain tests to finish quickly, so that
    ordinary development receives feedback in seconds rather than through
    release-proof workflows.
50. As a contributor, I want architecture dependency rules enforced by tests,
    so that built-in domain names and release-lab dependencies cannot creep back
    into the core.
51. As a contributor, I want one short feature tracker with independently
    verifiable tickets, so that work state is visible without creating another
    execution-plan archive.
52. As a future release researcher, I want a separately packaged release lab,
    so that publication or downstream-training experiments can evolve without
    changing synthesis behavior.

## Implementation Decisions

- The replacement is built as an isolated package and has no imports from the
  legacy synthesis or runtime packages. The legacy implementation remains
  frozen until the atomic cutover.
- The principal public module is a synthesis engine with run and resume
  operations. Replay and review-label import are separate high-level operations
  over completed run directories.
- The Domain seam consists of a Domain adapter that opens a Domain run, a Domain
  run that supplies task slots, compiles Task cases, and starts candidate-local
  Episodes, and a Domain Episode that lists tools, executes calls, and assesses
  the completed observable trajectory.
- Domain adapters are code, not generated code or declarative schemas. Contacts,
  Mobile Messages, and Workspace Tasks are the initial production adapters.
- A test-only fourth adapter must register without changing synthesis, storage,
  or quality behavior. Built-in registration is the only central location that
  may mention production domain identities.
- Task slots are deterministic for a fixed Domain version, source, run seed, and
  attempt ceiling. They carry generation and coverage intent but not provider-
  asserted identity.
- A compiled Task case has an Agent-visible view and a private oracle view. The
  core owns Candidate and Episode identity. The private view is available only
  to mutation authorization, deterministic assessment, and the operational
  ledger.
- Each Task case includes a Domain-owned semantic key. Duplicate semantic keys
  within a run are ineligible for demonstrations even when instructions differ.
- Each Domain assessment includes bounded checks, coverage tags, a structural
  key, state-change evidence, and reason codes. The shared quality module does
  not interpret domain-specific fields.
- The task generator, Agent, and quality judge use one provider-neutral JSON
  model interface. The production adapter uses an OpenAI-compatible chat
  endpoint; deterministic fakes provide the second adapter for tests.
- An Agent decision is exactly one tool call or one final response. It contains
  no reasoning field. The next request contains only the public task, available
  tool schemas, prior observable events, and remaining step budget.
- Task proposals are generated in batches of eight by default. Agent Episodes
  run with concurrency four by default, configurable from one through sixteen.
- Rollouts allow twelve steps by default, configurable from one through sixty-
  four. One malformed-decision repair request and two transport retries are
  allowed. All limits and explicit accepted/attempt targets are bound to the run
  configuration.
- Unknown tools, invalid arguments, and ordinary tool failures produce bounded
  observations and may be recovered within the step limit. An unauthorized
  mutation terminates the Episode before the state-changing operation.
- Candidate environments are isolated. Resume restarts an incomplete Episode in
  fresh state and never repeats an Episode already committed as terminal.
- SQLite is the sole operational ledger. Each Candidate outcome is committed in
  one transaction and exported by stable sequence. No append-only hash journal,
  evidence graph, or persisted lock schema is introduced.
- The design target is 1,000 to 10,000 accepted trajectories per local run. The
  implementation streams work and final export rather than retaining the full
  dataset in memory.
- Demonstrations contain successful and successful-recovery Episodes. Negatives
  contain failed, unsafe, duplicate, exhausted, or semantically rejected
  Episodes. The collections never share a training split.
- Persisted public contracts are limited to one run configuration, one Task
  case ledger record, one Episode, one quality judgment, one review label, one
  quality report, and one run manifest. Pydantic validates these contracts at
  persistence seams; owning modules keep their own models.
- The manifest hashes final dataset files and the normalized run configuration.
  Nested content hashes and per-domain evidence chains are not part of the new
  core.
- Provider credentials, unrestricted prompts or responses, private oracle
  values, and local absolute source paths do not appear in dataset artifacts.
  Sanitized model identity, prompt-template identity, response hashes, token
  usage, and bounded failure classes remain in lineage.
- Deterministic execution, mutation authorization, final-state verification,
  final-answer grounding, unsafe-material scanning, and semantic-key duplicate
  admission are hard gates from the first version.
- The independent quality judge scores instruction fidelity, action efficiency,
  observation grounding, final-response quality, and safety with pass, fail, or
  uncertain outcomes, bounded reasons, and event references. Its identity must
  differ from the Agent model identity.
- Judge decisions begin in shadow mode. Calibration requires at least one
  hundred human-reviewed Episodes, at least thirty per production Domain, all
  fail or uncertain outcomes from the bounded calibration campaign, and a
  stratified fill of passing outcomes.
- Semantic enforcement may activate only when overall human/judge agreement is
  at least 85 percent, false-pass rate is at most 5 percent, false-fail rate is
  at most 10 percent, no Domain false-pass rate exceeds 10 percent, and no
  judge-passed Episode has a human-confirmed critical safety failure.
- Formal cutover evidence uses an explicitly authorized real-provider campaign
  targeting forty accepted Episodes per production Domain with at most eighty
  attempts per Domain.
- Cutover requires every demonstration to pass deterministic verification, zero
  unauthorized mutations, zero semantic-key duplicates, at least 90 percent
  human blind-review pass rate, and no critical safety issue. Structural-family
  counts must not fall below seven for Contacts, twelve for Mobile Messages, and
  nine for Workspace Tasks; the largest family share must not exceed 0.35 in any
  Domain.
- The public CLI has run, resume, replay, and review-label-import commands and
  delegates all behavior to the library interface. Remote model use remains an
  explicit run-configuration choice.
- The runtime dependency set is reduced to the OpenAI-compatible HTTP client,
  Pydantic, and the Python standard library. Test tooling is a development-only
  dependency.
- Old run profiles and artifacts are not migrated or read. They remain
  recoverable through repository history or may be regenerated after cutover.
- The release lab is an empty independently packaged skeleton in this feature.
  It may depend on finalized public artifacts in the future; the synthesis core
  must never import it.
- The existing release qualification, publishability, training recommendation,
  live proof, tracer, compatibility, and legacy execution-plan implementations
  are removed only after the replacement passes every cutover criterion.
- Current implementation work is represented by one feature tracker and
  tracer-bullet tickets. New execution-plan lifecycle documents are not created.

## Testing Decisions

- The highest test seam is the synthesis engine. Tests provide a run
  configuration, registered Domain adapters, and model adapters, then assert on
  terminal run state and emitted public artifacts.
- Tests do not call private rollout, storage, parser, scheduler, or quality
  helpers merely to preserve legacy implementation structure. When the new
  external seam covers old behavior, old helper tests are deleted rather than
  layered beneath it.
- A reusable Domain compliance suite exercises task-slot determinism, proposal
  compilation, tool-schema validity, candidate isolation, read-only execution,
  authorized mutation, rejected mutation, error recovery, deterministic
  assessment, semantic keys, and structural keys for every adapter.
- A model-adapter contract suite exercises strict JSON decisions, sanitized
  lineage, timeouts, retries, malformed responses, response hashing, and secret
  exclusion against both the production adapter's mock transport and the fake
  adapter.
- End-to-end core tests cover a direct success, successful tool-error recovery,
  malformed-decision repair, unknown tool, invalid arguments, unauthorized
  mutation, max-step exhaustion, provider failure, cancellation, resume,
  deterministic replay, duplicate admission, and separate demonstration and
  negative outputs.
- Concurrency tests force reverse completion order and confirm stable export and
  duplicate winners. Resume tests interrupt before and after terminal ledger
  commits and prove completed work is not repeated.
- Quality tests prove deterministic gates cannot be overridden by the judge,
  shadow decisions cannot affect admission, review selection is stratified,
  label imports reject foreign or duplicate Episode ids, and enforcement cannot
  activate below any calibration threshold.
- Architecture tests reject core imports of production Domain implementations,
  legacy packages, or the release lab; Domain-to-Domain imports; and production
  domain literals outside built-in registration.
- The test-only fourth Domain is the extensibility acceptance test. Adding it
  must require no changes to the synthesis engine, ledger, rollout, or quality
  modules.
- Core tests must complete in less than five seconds, one Domain suite in less
  than fifteen seconds, and all ordinary non-scale tests in less than thirty
  seconds on the development machine.
- A manually selected scale suite runs ten thousand fake-model attempts, keeps
  peak memory below 512 MiB, exports stable ordering, and proves interruption
  recovery without duplicate completed Episodes.
- Real-provider tests never run implicitly. The cutover campaign requires fresh
  operator authorization and supplies the human-review calibration corpus.
- Existing foundation, provider-mock, candidate-isolation, environment, tool,
  replay, and three-domain fixtures are prior art for behavior. Existing
  qualification, proof, compatibility, and private-helper tests are not carried
  into the replacement merely for parity.
- Documentation validation continues to enforce links and source-of-truth
  ownership while the feature is active and after cutover.

## Out of Scope

- Runtime support or converters for any existing run-profile, sample, manifest,
  release-pack, qualification, proof, or compatibility schema.
- LLM-generated environments, tools, verifier code, or arbitrary generated-code
  execution.
- Declarative JSON or YAML Domain construction in addition to code adapters.
- Native provider tool-calling protocols; the first production adapter uses the
  provider-neutral JSON decision contract.
- Hidden or complete chain-of-thought capture.
- Distributed workers, external brokers, multi-machine scheduling, local model
  serving, or GPU-cluster management.
- Network-backed Domain source collection; Domain sources are local files or
  code configuration.
- Training demonstrations that mix failed Episodes into the same collection.
- Publication approval, authenticated authority, cumulative qualification,
  Training Recommended decisions, live acceptance proofs, or compatibility
  corpora in the new core.
- Implementing release-lab readers or porting legacy governance behavior during
  this feature.
- Automatic activation of the semantic judge without the required human
  calibration evidence.

## Further Notes

- The accepted direction changes the premise of
  [ADR 0002](../adr/0002-domain-pack-semantic-authority-and-deep-interface.md):
  the new Domain seam is optimized for synthesis locality rather than
  proof-bearing capability qualification. The first implementation ticket must
  add a focused superseding ADR before production code adopts the new seam.
- The new deterministic mutation authorization plus calibrated post-execution
  quality policy also changes the core scope established by
  [ADR 0001](../adr/0001-independent-semantic-mutation-admission.md). Its
  superseding decision must be recorded before the legacy semantic-admission
  implementation is removed.
- [ADR 0003](../adr/0003-separate-evidence-verification-from-external-authority.md)
  remains valid as a separation principle, but external authority and training
  evidence move entirely outside the synthesis core.
- The principal test seam and both necessary secondary seams were confirmed in
  design discussion: callers test through the synthesis engine, Domain authors
  use one compliance suite through the Domain interface, and external model
  behavior is replaced through the JSON model interface.
- This specification owns change-scoped design, migration, cutover, and system
  acceptance. The local feature tracker owns ticket status, dependency edges,
  assignment, and implementation discussion.
