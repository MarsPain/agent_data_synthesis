# Async Local Orchestration

## Problem Statement

Long representative synthesis runs now exceed the point where an all-or-nothing
synchronous process is operationally acceptable. The target-30 provider
campaign took more than ten minutes in both contacts and mobile messages. An
interruption late in one of these runs can lose progress, repeat remote work,
obscure which candidate tasks reached a terminal outcome, and make provider
usage harder to attribute.

The synthesis operator needs a local runner that preserves completed work,
resumes safely, supports bounded concurrency, and cancels without corrupting
artifacts. This must not create a second synthesis pipeline, weaken existing
quality gates, broaden provider authorization, or turn diagnostic evidence into
release readiness. The current synchronous command remains useful for small
runs and must remain the default.

## Solution

Provide an explicitly enabled local orchestration module above the existing
candidate-processing seam. One synthesis job is represented by versioned,
durable work items and an append-only local event journal. The runner persists
intent before starting work, executes candidate tasks through the existing
generation, mutation-admission, execution, verification, duplicate-admission,
and artifact-assembly flow, and records terminal outcomes before advancing the
job.

The first supported execution mode is resumable serial execution. Bounded
concurrency is added through the same interface only after serial recovery and
deterministic merge behavior are proven. Completed work items are never
reprocessed during normal resumption. Interrupted work is classified and
requeued under a bounded policy. Core dataset artifacts are assembled in stable
sequence order so a completed deterministic async run is equivalent to the
synchronous run for the same inputs.

Repository-local orchestration artifacts describe job state, journal events,
and sanitized provider usage. They are separate from dataset artifacts and do
not change release eligibility. No external broker, worker service, or local
LLM deployment is required.

## User Stories

1. As a synthesis operator, I want to opt into a durable local job, so that a
   long synthesis run can survive process interruption.
2. As a synthesis operator, I want synchronous execution to remain the
   default, so that small and deterministic runs retain their current behavior.
3. As a synthesis operator, I want to assign a stable job identifier, so that I
   can distinguish multiple runs that use the same run profile.
4. As a synthesis operator, I want a job to bind its normalized configuration,
   so that I cannot accidentally resume it with different semantics.
5. As a synthesis operator, I want completed work items to be skipped on
   resumption, so that accepted samples and rejected candidates are not
   needlessly recomputed.
6. As a synthesis operator, I want interrupted work to be identified
   explicitly, so that recovery does not pretend an unknown outcome completed.
7. As a synthesis operator, I want ambiguous in-flight provider attempts to be
   visible, so that usage and retry claims remain honest after a crash.
8. As a synthesis operator, I want ambiguous attempts to count conservatively
   against the authorized logical-call budget, so that resumption cannot exceed
   the authorization envelope.
9. As a synthesis operator, I want validated generated task contracts to be
   durably checkpointed, so that a crash after generation does not require the
   provider response to be regenerated.
10. As a synthesis operator, I want coverage assignments and accepted-only
    deficit state to be recoverable, so that bounded backfill resumes from the
    same coverage plan.
11. As a synthesis operator, I want serial resumption before concurrency is
    enabled, so that correctness and cost protection are established first.
12. As a synthesis operator, I want to configure a positive bounded
    concurrency value, so that independent candidate tasks may overlap without
    creating unbounded provider traffic.
13. As a synthesis operator, I want the async mode to default to concurrency
    one, so that enabling durability does not implicitly increase request
    pressure.
14. As a synthesis operator, I want cooperative cancellation, so that the
    runner stops accepting new work while allowing in-flight work to reach a
    recordable outcome.
15. As a synthesis operator, I want a cancelled job to remain resumable, so
    that cancellation is not equivalent to discarding the run.
16. As a synthesis operator, I want a clear completed, cancelled, or failed job
    outcome, so that partial progress is never mistaken for a complete dataset.
17. As a synthesis operator, I want malformed or incompatible durable state to
    fail before provider work begins, so that recovery errors do not spend
    budget.
18. As a synthesis operator, I want two processes to be prevented from running
    the same local job concurrently, so that they cannot duplicate work or
    corrupt the journal.
19. As a synthesis operator, I want per-role call and token summaries, so that
    I can identify which generation or judging roles consume provider capacity.
20. As a synthesis operator, I want provider-reported price metadata preserved
    when available, so that known costs can be attributed without inventing
    missing prices.
21. As a synthesis operator, I want an explicit statement when price metadata
    is unavailable, so that token counts are not presented as a dollar-cost
    estimate.
22. As a synthesis operator, I want resumption to reuse the original provider,
    model, run profile, and authorization limits, so that recovery does not
    silently broaden external access.
23. As a domain-pack maintainer, I want async execution to call the existing
    candidate-processing interface, so that domain generation and verification
    semantics are not duplicated in orchestration code.
24. As a domain-pack maintainer, I want candidate-local environment rebuild and
    checkpoint behavior preserved, so that concurrent work remains isolated.
25. As a coverage maintainer, I want stable assignment and sequence identities,
    so that out-of-order completion does not change deterministic deficit
    reconciliation.
26. As a quality maintainer, I want duplicate admission to run in stable
    sequence order, so that concurrency does not change which equivalent sample
    is accepted first.
27. As a dataset maintainer, I want the existing dataset writer to remain the
    only artifact-assembly implementation, so that sync and async modes do not
    drift into separate formats.
28. As a dataset consumer, I want completed async runs to produce the same core
    artifacts as synchronous runs for deterministic inputs, so that downstream
    consumers do not need an async-specific reader.
29. As a dataset consumer, I want partial artifacts to be explicitly
    diagnostic and incomplete, so that they cannot satisfy release gates.
30. As a security reviewer, I want orchestration state to exclude credentials,
    authorization headers, raw prompts, raw provider responses, private source
    payloads, and host paths, so that durability does not create a new secret
    surface.
31. As a security reviewer, I want source admission, sandbox admission, role
    guardrails, and remote-context policy to remain enforced, so that async mode
    cannot bypass existing controls.
32. As a framework maintainer, I want invalid job and work-item transitions to
    fail closed, so that corrupted lifecycle state cannot be interpreted
    optimistically.
33. As a framework maintainer, I want journal recovery to tolerate only a
    truncated final append while rejecting earlier corruption, so that crash
    recovery is bounded and auditable.
34. As a framework maintainer, I want schema-versioned orchestration records,
    so that future state migrations are explicit rather than inferred.
35. As a framework maintainer, I want orchestration timestamps and runtime
    metrics isolated from deterministic dataset bytes, so that wall-clock data
    does not break reproducibility.
36. As a framework maintainer, I want profile scale signals to recommend async
    work without automatically enabling it, so that activation remains an
    explicit operator choice.
37. As a test author, I want the complete job runner to be the principal test
    seam, so that tests verify observable recovery behavior rather than private
    queue mechanics.
38. As a test author, I want deterministic failure injection around durable
    transitions, so that interruption cases can be reproduced without real
    process crashes or paid provider calls.
39. As a contributor, I want one local orchestration module with a small
    interface, so that lifecycle complexity remains localized rather than
    spreading across domain packs.
40. As a contributor, I want external brokers and distributed workers excluded
    from the first implementation, so that the solution remains proportionate
    to the observed local scale.

## Implementation Decisions

- The orchestration module sits above the existing candidate-processing and
  deterministic merge interfaces. It coordinates work but does not implement
  task generation, mutation admission, environment isolation, execution,
  verification, duplicate detection, coverage semantics, or dataset assembly.
- The principal programmatic interface creates or resumes one synthesis job
  from a validated run configuration, output location, job identifier,
  concurrency limit, and cancellation signal. Callers receive a job result with
  terminal status, progress counts, artifact references, and sanitized usage.
- Async execution is available only through an explicit programmatic option or
  CLI flag. The CLI exposes an enable flag, a job identifier, a resume option,
  and a maximum-concurrency option. Enabling async without an explicit
  concurrency value uses one worker.
- A normalized configuration hash binds the run profile, domain identity,
  generation configuration, enabled features, coverage plan when present,
  provider/model aliases, and declared logical-call budget. Credentials and
  raw paths are excluded. Resume rejects any hash or identity mismatch before
  provider construction.
- The orchestration contracts are versioned independently as job, work-item,
  event-journal, and usage-summary records. Stable identifiers are derived
  locally and cannot be asserted by provider output.
- A job lifecycle supports pending, running, cancelling, cancelled, completed,
  and failed states. Completion is valid only when every required work item and
  any bounded coverage backfill have terminal outcomes. Invalid transitions
  fail closed.
- A work-item lifecycle supports pending, running, completed, failed, and
  cancelled states. A completed item records a result kind of accepted or
  rejected; candidate rejection is a valid processing result rather than an
  orchestration failure. On reload, a non-terminal running item is classified
  as interrupted and returned to pending under the bounded recovery policy.
- One work item represents a stable candidate sequence slot or coverage
  assignment and its complete generation-through-gates attempt. The journal
  records the work intent before any remote call. Coverage-driven runs persist
  assignment identity and reconstruct scheduler reconciliation from terminal
  outcomes before issuing deterministic backfill assignments.
- After a provider response passes schema and domain validation, the normalized
  task contract may be checkpointed as internal resumable state. Raw prompts,
  raw response envelopes, unrestricted grounding context, and provider error
  bodies are never checkpointed.
- The durable source of truth is a repository-local append-only event journal.
  Each event has a monotonic sequence, schema version, job and work-item
  identity, transition type, sanitized payload, and integrity metadata.
  Derived job snapshots and usage summaries can be rebuilt from the journal.
- Journal appends are flushed before the associated side effect begins. Reload
  may discard one incomplete final append and record that recovery; malformed,
  reordered, duplicated, or integrity-invalid earlier events fail closed.
- A local exclusive job lock prevents simultaneous writers. Lock acquisition
  failure does not alter state or call a provider. Stale-lock recovery must be
  explicit and must validate the journal before proceeding.
- The system guarantees exactly-once admission and artifact identity for a
  completed work item, not exactly-once transport to an external provider. A
  process can fail after a provider accepted a request but before the response
  was durably recorded. Such attempts are reported as ambiguous and counted
  conservatively against the logical-call budget before retry or resumption.
- Existing bounded transport retries remain owned by the provider adapter. The
  orchestration layer does not add an unbounded retry loop or reinterpret
  transport retries as new coverage assignments.
- The persisted logical-call budget is cumulative across the original run and
  every resume. Known and ambiguous issued attempts consume budget. The runner
  stops before an action that could exceed the declared authorization.
- Candidate work may complete out of order, but provisional outcomes are
  merged by stable sequence index through the existing merge interface. This
  preserves duplicate admission, review order, proposal order, coverage
  reconciliation, and deterministic artifact content.
- The existing dataset writer remains the sole assembler for samples,
  rejections, manifests, quality evidence, reviews, coverage evidence, and
  episode evidence. Orchestration-owned job, journal, and usage artifacts are
  separate, so completed deterministic core artifacts can remain byte
  equivalent to synchronous output.
- Cancellation is cooperative. It changes the job to cancelling, stops new
  work pickup, allows bounded in-flight calls to return or reach their existing
  timeout, persists resulting terminal or interrupted state, writes a valid
  job snapshot, and then changes the job to cancelled.
- A cancelled or failed job is resumable only when its job identity,
  configuration hash, durable state, authorization budget, and output ownership
  validate. A completed job is idempotently inspectable but is not resumed as
  new work.
- Partial dataset artifacts, when emitted, are rebuilt from durable terminal
  outcomes through the normal writer and remain diagnostic. The orchestration
  job status and ordinary fulfillment/release gates prevent them from being
  interpreted as complete or releaseable.
- Usage aggregation reads sanitized role lineage from durable terminal
  outcomes and provider-attempt events. It reports call counts, retry counts,
  known and ambiguous attempts, token fields, provider/model aliases, and
  provider-reported price metadata when present. It never estimates missing
  prices.
- Source governance, remote-context admission, sandbox policy, mutation
  admission, role enablement, provider host allowlists, and secret redaction are
  invoked through their existing interfaces. Async mode grants no new network,
  source, mutation, or release authority.
- The orchestration module uses local-substitutable filesystem and clock
  dependencies behind internal seams for deterministic tests. These internal
  seams are not added to the external job-runner interface.
- Profile-decision `async_orchestration: activate` remains evidence and does
  not switch execution mode automatically. Operators must explicitly opt in.

## Testing Decisions

- The principal test seam is the complete opt-in job-runner interface. Tests
  assert terminal job state, durable resumption behavior, provider-call budget,
  and emitted artifacts rather than coroutine scheduling or private helper
  calls.
- Deterministic sync-versus-async equivalence tests run the same domain input
  through both modes. They compare accepted samples, rejections, ordering,
  coverage reconciliation, quality evidence, and other core artifacts. Only
  separately owned orchestration state and wall-clock fields may differ.
- Serial recovery tests inject interruption immediately before provider work,
  after a validated task contract is checkpointed, during candidate
  processing, after a terminal outcome is journaled, and before artifact
  assembly. Each test proves that completed phases are not repeated and that
  no candidate is admitted twice.
- Provider ambiguity tests simulate a lost response after request acceptance.
  They verify that the attempt is reported as ambiguous, consumes budget
  conservatively, and cannot create duplicate accepted output.
- Coverage tests interrupt initial assignments and bounded backfill, then prove
  that scheduler reconciliation and final fulfilled cells match the
  synchronous run.
- Concurrency tests force outcomes to finish in reverse order and verify that
  stable sequence merge produces the same duplicate winner and artifact order
  as serial execution.
- Cancellation tests confirm that new work stops, in-flight work is classified,
  the journal remains valid, partial outputs stay diagnostic, and the job can
  later resume.
- Contract tests cover every valid and invalid job/work-item transition,
  configuration mismatch, duplicate event, invalid identity, unsupported schema
  version, malformed snapshot, and exhausted logical-call budget.
- Journal tests cover clean replay, a truncated final append, mid-journal
  corruption, integrity mismatch, concurrent-writer lock rejection, and
  explicit stale-lock recovery.
- Redaction tests scan all orchestration artifacts for API keys, authorization
  headers, raw prompts, raw provider payloads, unrestricted source rows,
  environment variables, and absolute host paths.
- Usage tests aggregate multiple roles, retries, zero-token failures, ambiguous
  attempts, and optional provider price metadata without inventing cost values.
- CLI tests prove that the default command remains synchronous, invalid
  concurrency fails before work begins, resume requires compatible durable
  state, and async enablement is explicit.
- Existing candidate-processing tests provide prior art for isolated
  environments and provisional outcomes. Existing deterministic merge tests
  provide prior art for stable ordering and duplicate admission. Coverage
  scheduler tests provide prior art for accepted-only reconciliation and
  bounded backfill. Dataset validation and retained-material scans remain the
  final artifact checks.
- Real provider calls are operational evidence, not unit-test prerequisites.
  No paid validation run occurs without separate provider, model, credential,
  logical-call budget, and transport-retry authorization.

## Out of Scope

- Replacing the default synchronous runner.
- Automatically enabling async execution from profile or scale evidence.
- External brokers, queue services, databases, distributed workers, actors,
  containers, or cluster scheduling.
- A web service, REST or gRPC interface, dashboard, WebSocket progress stream,
  or remote cancellation endpoint.
- Multi-process execution or cross-machine job ownership.
- Exactly-once delivery guarantees from third-party provider transports.
- Unbounded retries, speculative duplicate requests, or automatic budget
  expansion.
- Changing generation, coverage, mutation-admission, verification, duplicate,
  quality, release, or structural-taxonomy thresholds.
- Expanding contacts or any other domain pack.
- Semantic duplicate detection, model training, Agentic RL, external MCP
  servers, browser automation, or local LLM deployment.
- Persisting raw prompts, raw provider responses, credentials, private source
  payloads, or generated executable code in orchestration state.

## Further Notes

The activation trigger is now observed rather than hypothetical. The
target-30 campaign recorded contacts runtime of 738.273 seconds and mobile
messages runtime of 662.632 seconds, both above the documented 600-second
threshold. The campaign also demonstrated that bounded provider retries and
coverage backfill need to survive as part of one cumulative job budget.

Contacts remains a demonstration domain. Its `revise-catalog` campaign outcome
is accepted as evidence that the architecture fails closed under structural
capacity saturation; this orchestration work does not require further contacts
scenario expansion and does not revise that evidence.

The
[historical async execution plan](../exec-plans/deferred/0014-async-local-orchestration-with-durable-queues.md)
remains useful implementation background, but this specification is canonical
for desired behavior. Current status, assignment, and activation state live
only in
[ISSUE-0001](../../.scratch/ISSUE-0001-async-local-orchestration.md).
