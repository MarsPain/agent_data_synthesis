# Backend

## Backend Shape

The first backend should be a local Python pipeline with explicit modules and durable artifacts. "Local" means local orchestration, environment execution, tool execution, and artifact management. LLM-backed generation, solution policy, refinement, and optional judge steps must call a configured remote OpenAI-compatible API. Avoid introducing a web service until there is a concrete need for remote execution or interactive control.

## Proposed Module Boundaries

- `synthesis.seeds`: source registration, normalized seed records, seed
  transformation records, and deterministic taxonomy-expansion requests.
- `synthesis.run_profiles`: `run_profile_v1` through `run_profile_v4` parsing,
  validation, defaulted feature flags, optional profile-local domain source
  declarations, optional named/versioned coverage-profile references with
  bounded balance-weight overrides, sanitized metadata export, and stable
  config hashing for local synchronous runs.
- `synthesis.coverage`: domain-neutral coverage catalog, profile, capacity, and
  plan contracts plus deterministic validation, target-distribution
  compilation, hashing, and canonical plan writing.
- `synthesis.contacts_coverage`: the contacts-owned v1 through v3 reachable-cell
  catalogs, named smoke and representative profiles, expanded grounding
  capacity, executable selector-recovery structures, observation-backed
  grounding identity validation, and aggregate admitted-capacity projection.
- `synthesis.mobile_coverage`: the mobile-owned
  `mobile_messages_coverage_v1` through v3 catalogs, profiles, compatibility
  and difficulty declarations, recovery structures, observation-backed
  grounding identity validation, and message-capacity projection.
- `synthesis.workspace_coverage`: the workspace-owned
  `workspace_tasks_coverage_v1` through v3 catalogs, profiles, compatibility
  and difficulty declarations, recovery structures, observation-backed
  grounding identity validation, and workspace-item capacity projection.
- `synthesis.coverage_registry`: domain planning registration. It connects
  domain-owned catalogs, authoritative catalog/profile version registries,
  profile resolution, typed synthetic-fixture variants, and executable
  capacity projection to the shared compiler without adding domain-name
  branches to that compiler.
- `synthesis.coverage_assignments`: domain-neutral assignment scheduling,
  per-wave accepted-only reconciliation, bounded deficit backfill, stable
  assignment identities, overlap-aware stable-grounding allocation,
  minimum-grounding prompt projection, local
  task-contract membership validation, and sanitized assignment lineage.
- `synthesis.structural_taxonomy`: the versioned common classifier and
  like-for-like comparison contract for executed task type, ordered tool
  sequence, selector-field shape, state behavior, cross-step bindings, and
  recovery transitions. It excludes instruction text, provider identity, and
  coverage metadata so cell proliferation cannot manufacture family growth.
- `synthesis.domain_generation`: immutable domain generation specifications,
  complete machine-readable provider output contracts, strict task-contract
  parsing, replayable grounding arguments paired with observations, explicit
  required-capability, final-answer evidence, and expected-state tool ownership, fixed sanitized
  schema-failure reasons/details, deterministic batch candidate namespaces,
  domain-owned exact-target synchronous batch sizes under a shared ceiling of
  five, sentinel-based final-answer derivation from validated expected state,
  primary-observation and expected-state-reference grounding gates, per-batch
  task-type focus rotation, sliding grounding windows, bounded prior-instruction
  exclusion lists with count-only persisted lineage, and sanitized
  representative eligibility evidence.
- `synthesis.stable_ids`: shared slugify primitive used by environment ID
  minting and generation-time final-answer derivation so their outputs cannot
  drift apart.
- `synthesis.sources`: source governance records, license decisions, default-deny
  network policy, sandbox policy, source-bundle validation, source-policy hashes,
  deterministic no-network external-source fixtures, controlled HTTPS fetch
  contracts, bounded request admission, profile-local file admission, and
  sanitized source-event records.
- `synthesis.domain_sources`: profile-local domain source importer protocol,
  importer resolution, generic import records, governed local source admission,
  and default fixture source identity registration. The shared source-governance
  builder consumes a domain-neutral identity record.
- `synthesis.environments`: environment builders, typed contacts environment
  input records, reset/checkpoint operations, and state adapters.
- `synthesis.mobile_sources`: mobile messages JSON importer that converts
  admitted source bytes into `MobileMessagesEnvironmentInput`.
- `synthesis.workspace_sources`: workspace tasks JSON importer that converts
  admitted source bytes into `WorkspaceEnvironmentInput`.
- `awm_runtime`: package-neutral runtime protocol primitives, sanitized
  `runtime_metadata_v1` construction, immutable runtime capability descriptors,
  runtime registry primitives, runtime action request/result envelopes, runtime
  sessions over environment/tool-registry pairs, package-neutral
  `episode_log_v1` construction, deterministic transition hashing, redaction,
  and diagnostic episode summaries.
- `synthesis.runtime_registry`: repository-owned contacts/mobile/workspace
  descriptor construction and default registry selection. Domain-specific
  rebuild seeds stay here rather than in `awm_runtime`; runtime-facing code uses
  this module for repository-owned default descriptor lookup.
- `synthesis.rollouts`: diagnostic local rollout collection over runtime
  sessions. It executes scripted policies through action envelopes, enforces
  max-step limits, exports sanitized `episode_log_v1` records, and does not
  implement RL algorithms, reward-model training, distributed workers, external
  MCP execution, or default CLI output.
- `synthesis.episode_quality`: opt-in `episodes.jsonl` persistence and
  `episode_quality_report_v1` construction over sanitized episode logs. It
  validates runtime/episode evidence, reads known-runtime and state-changing
  tool facts from runtime descriptors, scores transition completeness and
  state-change support, and writes compact summaries without raw tool payloads,
  prompts, credentials, or host paths.
- `synthesis.episode_replay`: opt-in `episode_replay_report_v1` construction
  over sanitized episode logs. It reads replay support, state-changing tools,
  and rebuild seed facts from the runtime registry, rebuilds fresh supported
  fixture runtimes, re-executes action transitions through
  `RuntimeSession.execute_action(...)`, compares observation/state-change
  hashes, and writes compact summaries without raw tool payloads, prompts,
  credentials, or host paths.
- `synthesis.reward_labels`: opt-in `reward_labels.jsonl` and
  `reward_label_report_v1` construction over sanitized episode, quality, and
  replay evidence. It reads reward-label and state-changing-tool support from
  runtime descriptors, then produces deterministic scalar labels and
  preference-group metadata without training reward models, collecting RL
  rollouts, changing release admission, or changing the runtime package
  boundary.
- `synthesis.tools`: tool definitions, schema generation, registry, dependency
  graph, capability-gap records, bounded tool proposals, and curated local tool
  admission.
- `synthesis.workspace_environment`, `synthesis.workspace_tools`, and
  `synthesis.workspace_tasks`: deterministic third-domain workspace pack. It
  owns local SQLite workspace projects, tasks, documents, comments, workspace
  tool schemas/handlers, deterministic candidates, scripted policies, checkpoint
  and rebuild semantics, typed source-backed environment input, and sanitized
  runtime metadata. It accepts governed profile-local workspace JSON through
  `synthesis.workspace_sources`; it does not call external workspace APIs.
- `synthesis.mcp`: local MCP-compatible adapter manifests, tool-call request and
  result envelopes, adapter lineage records, and the in-process runtime-backed
  adapter shim for supported local runtimes. It does not start an MCP server or
  connect to external tool servers.
- `synthesis.sandbox`: generated executable artifact records, Python static
  safety scans, sandbox admission decisions, redacted sandbox audit records, and
  the restricted local execution helper for explicitly admitted fixture code.
- `synthesis.tasks`: task generation, seed-transformation expansion, task
  suggestion, edited-task assembly, difficulty scoring, curriculum policies,
  expected state declarations, optional branch-plan records, and candidate-level
  generation lineage attachment.
- `synthesis.task_contracts`: internal task-intent, policy-hint,
  expected-outcome, and expected-state contracts derived from `CandidateTask`
  before execution and verification. It owns task-contract validation and
  compatibility conversion without changing public candidate artifacts.
- `synthesis.execution`: solution policy selection/parsing, ordered tool-step
  execution, bounded branch-plan execution, trajectory runner, retry policy,
  environment checkpoint/restore boundaries, and event capture.
- `synthesis.verification`: executable, logical, state-change, and judge-based
  validators.
- `synthesis.refinement`: repairability decisions, critic/refiner attempt
  values, deterministic fixture repairs, remote critic/refinement parsing, and
  sanitized refinement lineage.
- `synthesis.roles`: role definitions, enabled/disabled role registry,
  role-owned output types, invocation metadata, and guardrails that prevent
  future roles from making provider calls before an explicit enabling plan.
- `synthesis.quality`: quality reports, metric slices, duplicate signatures,
  logical consistency checks, human-review records, and parent-version comparison.
- `synthesis.evaluation`: domain-aware deterministic held-out benchmark suites
  and sanitized evaluation-report construction over existing environment, tool,
  execution, and verifier boundaries.
- `synthesis.profile_decisions`: opt-in profile benchmark decision reports built
  from manifest, quality report, optional parent comparison, optional held-out
  evaluation evidence, runtime, and deterministic thresholds.
- `synthesis.dataset_release`: opt-in dataset release admission reports built
  from manifest, quality, evaluation, and profile-decision artifacts. It
  separates concrete artifact-set release eligibility from profile promotion.
- `synthesis.release_review`: opt-in release-audit review-item construction,
  deterministic redacted item ids, local reviewer-decision validation, and
  aggregate resolution reporting. It consumes existing release artifacts and
  cannot admit or reject candidates or datasets.
- `synthesis.mutation_calibration`: standalone deterministic construction of a
  balanced cross-domain mutation-admission review packet, pre-tuning held-out
  split freeze, strict direct-human label import, contamination validation, and
  hash-bound reviewed-corpus assembly. It neither invokes nor scores a semantic
  judge and does not alter dataset manifests or candidate admission.
- `synthesis.mutation_activation`: three-repeat evaluation of an independently
  configured semantic mutation judge over a reviewed calibration corpus,
  deterministic safety-first activation metrics and breakdowns, and sanitized
  hash-bound activation or no-go reporting.
- `synthesis.representative_activation_gate`: offline final-gate assembly and
  verification across a validated activation report, fresh three-domain
  representative enforce campaign, mutation-safe manifests, a protected
  historical-campaign digest, costs, failures, and explicit limitations. Its
  readiness result distinguishes framework activation from dataset release.
- `synthesis.candidate_processing`: single-candidate validation, policy
  execution, verification, logical gates, optional tool-expansion reruns,
  optional refinement reruns, provisional candidate outcomes, and deterministic
  merge/admission records for ordered duplicate gates.
- `synthesis.datasets`: sample assembly, per-record run-profile attribution,
  manifests, artifact exports, generation failure rejection records, and quality
  report path plumbing.
- `synthesis.orchestration`: jobs, workers, queues, cancellation, and metrics.
- `synthesis.llm`: remote provider adapter, request/response capture, bounded
  retry policy, sanitized provider error classification, prompt hashing, cost
  metadata, and model configuration.

## LLM Provider Boundary

The backend should treat the LLM as an external dependency reached through an OpenAI-compatible API URL. It should not include local LLM cluster provisioning, GPU scheduling, model serving, or inference runtime management.

Minimum runtime configuration:

- `AGENT_DATA_LLM_BASE_URL`: remote OpenAI-compatible API base URL.
- `AGENT_DATA_API_KEY`: secret key for the selected provider.
- `AGENT_DATA_LLM_MODEL`: model id used for generation, solution policy, refinement, or judge calls.

Provider calls should go through the role registry for role-backed generation
steps. Enabled roles currently include `task_generation`, `solution_policy`,
`critic_refinement`, `task_suggester`, `task_editor`, and the bounded
`tool_generation` proposal role. Future environment, verifier, and judge roles
remain disabled guardrails. `task_suggester` may only produce intent-level
`task_suggestion` records, and `task_editor` may only produce `edited_task`
records that are validated before execution. `tool_generation` may only produce
structured tool proposal records; it does not produce executable code or
installable packages. Disabled executable roles record that future outputs
require sandbox admission before execution. Provider lineage should record role
name, role version, output type, owner module, retry policy, sandbox-admission
requirement where relevant, model id, base URL host, prompt or config hash,
token and cost metadata when available, retry count, and error class. Transient
transport failures, timeouts, HTTP 429, and HTTP 5xx responses may be retried
within a bounded local budget. Secrets must never be written to manifests,
trajectories, exports, or logs.

## Job Lifecycle

1. Register seeds and target domain. For configurable local runs, load a file
   using `run_profile_v1` through `run_profile_v4` and translate its seed,
   generation mode, dataset version, feature flags, and optional governed local
   domain source into the existing synchronous pipeline arguments.
2. Validate the source bundle before environment construction. External-source
   material must pass license, network, and sandbox gates or be rejected with
   `source_policy_rejected`.
3. When controlled network-backed synthesis is explicitly enabled, fetch one
   allowlisted HTTPS JSON source through the injectable HTTP boundary, enforce
   timeout, byte, content-type, redirect, and request-budget limits, and convert
   the payload into a typed contacts environment input. When a `run_profile_v2`
   declares `source.kind=local_contacts_json`,
   `source.kind=local_mobile_messages_json`, or
   `source.kind=local_workspace_tasks_json`, read the profile-relative JSON file
   under its byte budget, admit it as `source_kind=local_file`, and hand the
   admitted bytes to the matching domain importer. Controlled network ingestion
   remains contacts-only. The default pipeline does not fetch external network
   sources or ingest arbitrary local files.
   When the profile selects `coverage_profile`, project only the admitted,
   aggregate environment capacity into the domain planning definition and
   validate both its explicit accepted target and the existing candidate target
   against the profile-derived attempt ceiling. The
   `--preview-coverage-plan` and `--write-coverage-plan` paths compile and
   optionally write `coverage_plan.json`, then exit before provider
   construction, candidate generation, or execution. A normal
   coverage-enabled LLM run persists the same plan and issues the deterministic
   initial assignment wave. After each wave, it reconciles locally validated
   accepted assignments separately from in-flight and rejected work, then uses
   only remaining plan capacity for deterministic accepted-deficit backfill.
4. Build or load an environment version with source provenance, source-policy
   hash metadata, and environment-source admission status. Preserve that
   provenance when rebuilding isolated per-candidate environments.
5. Build or load a tool registry version.
6. Resolve the role registry and generate candidate tasks by curriculum policy
   through the `task_generation` role when remote generation is enabled. V3
   resolves the selected domain bundle first and requests at most five contracts
   per call until the declared target is exactly fulfilled. Contacts requests
   five; mobile and workspace request two. Each request has a one-based batch
   index and deterministic domain/batch candidate-ID prefix, and declares
   the exact response shape and count, field JSON types and non-empty rules,
   task-type/tool coupling, expected-state behavior, forbidden fields, and
   JSON-only output from the domain-owned generation specification.
   Each batch focuses a single task type by rotation, renders each grounding
   list as a sliding window, and carries a bounded exclusion list of recent
   prior instructions; when the focused task type declares state-tool answer
   derivation, the provider record must carry the fixed sentinel and the real
   final answer is derived deterministically from validated expected state.
   Persisted candidate lineage keeps only the exclusion count, never
   instruction text.
   For a coverage-enabled run, the scheduler chooses mandatory cells
   before the largest normalized remaining deficit with cell-id tie-breaking.
   Each provider call receives one cell contract, only that cell's tools, and
   one assigned grounding unit. The compiler allocates stable grounding-unit
   identities across cells before generation, so intersecting cell eligibility
   cannot exceed the profile reuse limit. Recovery cells are admitted only
   after their read-only failing and successful branches execute against the
   domain registry and the success reproduces assigned final-answer evidence.
   Provider records retain the existing exact-key
   schema and cannot assert plan, assignment, cell, fulfillment, lineage, or
   coverage-score fields. The local validator checks task type, ordered tools,
   state behavior, and exact grounding membership before the candidate enters
   normal processing; mismatches become `coverage_assignment_mismatch` rather
   than being reclassified. Candidate-processing and generation rejections
   leave the assigned cell underfilled. The next bounded wave selects mandatory
   deficits first, then the largest normalized deficit with cell-id
   tie-breaking, and stops exactly at the plan attempt ceiling. Dataset writing
   then publishes `coverage_evidence.json`, binding the exact planning and
   persisted membership identities and reporting per-cell outcomes plus
   sanitized concentration and reuse summaries. An incomplete diagnostic run
   keeps its admitted samples and records incomplete fulfillment. Profile
   promotion and representative-scale evidence require a fulfilled,
   identity-verified coverage summary whenever the run profile selects
   coverage; that requirement is additive to all existing gates.
7. If remote generation fails after configuration, write a classified generation
   rejection plus manifest and quality report artifacts. Strict response failures
   retain the public `llm_response_schema_error` cause and exactly one approved
   fixed `schema_reason` plus an optional matching fixed `schema_detail`; they
   never retain provider records or provider-derived exception messages.
8. Optionally expand seeds through deterministic or remote seed transformation,
   task suggestion, and task editing. Edited candidates are admitted only after
   normal candidate-contract validation, and rejected suggestions remain
   inspectable as rejected records.
9. Convert each schema-valid `CandidateTask` into an internal task contract and
   validate task intent, policy hints, expected final-answer evidence, expected
   state checks, branch plans, and safety rules before execution. Public task
   sample and rejection shapes remain unchanged.
10. Generate or select a solution policy for each valid task, using the
   `solution_policy` role for remote policies and deterministic local lineage for
   scripted policies.
11. Execute policy steps directly against the local registry by default. When
   `--enable-mcp-adapter` or `enable_mcp_adapter=True` is explicitly set, route
   the same policy steps through the local in-process runtime-backed adapter
   shim. The
   top-level trajectory still records the normal action, observation,
   state-change, and final-response events; adapter call metadata is stored in
   lineage and rejection details.
12. When a candidate carries a bounded branch plan, execute branch attempts from a
   clean environment checkpoint until one terminal path succeeds, preserving
   rejected branch outcomes separately from the selected trajectory.
13. Verify outputs and expected state changes independently through
   contract-aware expected-outcome and expected-state helpers.
14. Build internal episode evidence for accepted executions and rejected
   executions that already have a trajectory. Episode evidence is not written to
   default dataset artifacts or release artifacts.
15. For repairable verification or logical-support failures, optionally run one
   `critic_refinement` attempt and rerun validation, execution, verification,
   and quality gates through the normal path.
16. When execution exposes a capability gap such as a missing tool or schema
   mismatch, optionally request one `tool_generation` proposal, admit only a
   matching curated local implementation, and rerun through the normal execution,
   verification, and quality gates.
17. When `--enable-sandbox-fixture` or `enable_sandbox_fixture=True` is
   explicitly set, run a deterministic generated-code fixture through static
   scan, admission, restricted local execution, and redacted audit serialization.
   This fixture does not enable arbitrary generated tools, environments, or
   verifiers and does not change default accepted/rejected sample counts.
18. Merge provisional candidate outcomes in stable sequence order, applying
   exact duplicate admission deterministically after execution so completion
   order cannot choose the accepted sample. Logical consistency remains a
   candidate-local gate before merge.
19. Route failed samples by error class and optional candidate-review policy.
   Candidate-time reviewable rejections use `review_queue.jsonl` with
   `human_review_record_v1`; this is not the release-audit review queue.
20. Export accepted samples, rejections, source-event audits when enabled,
   sandbox audits when enabled, tool proposal events, branch lineage,
   task-expansion lineage, quality reports, lineage, sanitized run-profile
   manifest metadata, and narrow per-record run-profile attribution when a
   profile is supplied.
21. When `--write-episode-quality-report` is explicitly supplied, write
   `episodes.jsonl`, score it into `episode_quality_report.json`, and rewrite
   only the manifest artifact map to reference both opt-in artifacts. This
   local synchronous consumer validates and scores runtime episode evidence by
   reading runtime identity and state-changing-tool facts from descriptors; it
   does not replay actions against fresh state, train reward models, collect RL
   rollouts, or change candidate admission.
22. When `--write-episode-replay-report` is explicitly supplied, write
   `episodes.jsonl`, replay it into `episode_replay_report.json`, and rewrite
   only the manifest artifact map to reference both opt-in artifacts. This
   local synchronous consumer rebuilds fixture runtimes and executes tool
   transitions; it does not train reward models, collect RL rollouts, call
   external MCP environment servers, change release admission, or publish a
   separate runtime package.
23. When `--write-reward-label-report` is explicitly supplied, write
   `episodes.jsonl`, compute quality and replay evidence in memory when their
   reports were not explicitly requested, write `reward_labels.jsonl` and
   `reward_label_report.json`, and rewrite only the manifest artifact map to
   reference `episodes`, `reward_labels`, and `reward_label_report`. This local
   synchronous consumer produces deterministic labels from descriptor-backed
   reward/state support; it does not train reward models, collect RL rollouts,
   call external MCP environment servers, change release admission, promote
   profiles, or publish a separate runtime package.

The workspace third-domain probe follows the same consumer rule as contacts and
mobile: replay, reward labels, episode quality, rollouts, and local adapter
execution use runtime descriptors, `RuntimeSession`, and action envelopes. They
must not add workspace-specific branches or tool allowlists.
24. When `--write-evaluation-report` is explicitly supplied, resolve the
   deterministic held-out suite from the manifest run-profile domain, write
   `evaluation_report.json`, and rewrite only the manifest artifact map to
   reference that report. Contacts profiles run the contacts suite; mobile
   profiles run the mobile messages suite. The evaluation report includes
   domain identity, controlled expected-failure benchmark semantics, and
   per-capability threshold decisions.
25. When `--write-profile-decision-report` is explicitly supplied, read the
   exported manifest and quality report, write `profile_decision_report.json`,
   include held-out evaluation evidence when an evaluation report was also
   requested, separate the MVP quality-floor decision from the higher-level
   profile-promotion decision, reject domain-mismatched evaluation evidence as
   insufficient for promotion, and rewrite only the manifest artifact map to
   reference that report.
26. When `--write-dataset-release-report` is explicitly supplied, require both
   evaluation and profile-decision reports, read those existing artifacts, write
   `dataset_release_report.json`, and rewrite only the manifest artifact map to
   reference that report. Release admission distinguishes diagnostic probes from
   release candidates, rejects domain-mismatched evaluation evidence, and does
   not change candidate processing, evaluation, or profile promotion.
27. When `--write-release-review-queue` is explicitly supplied, require
   `--write-release-quality-audit`, which in turn requires dataset release,
   held-out evaluation, and profile-decision reports. After writing the audit,
   translate only `watch` signals into deterministic redacted
   `release_review_item_v1` records in `release_review_queue.jsonl` and attach
   the queue to the manifest. `clear`, `blocked`, and `insufficient_evidence`
   audits create no queue. This queue is distinct from candidate-time
   `review_queue.jsonl`.
28. The offline `scripts/write_review_resolution.py` consumer reads an existing
   local release-review queue and an explicit reviewer-owned
   `review_decisions.jsonl`, writes aggregate-only
   `review_resolution_report.json`, and attaches only that report to the
   manifest. It does not attach the decisions file or rerun generation,
   evaluation, profile decisions, release admission, release-pack creation, or
   release-pack verification.
29. Every `run_profile_v4` run writes `mutation_admission_report_v1` and a
   `dataset_manifest_v2`. The report aggregates bounded admission outcomes by
   domain, task type, action, provenance, verdict, reason, provider outcome, and
   model independence. The manifest declares the sample and admission contract
   versions and hash-binds samples, rejections, and the report.
30. `dataset_release_pack_v2` construction and verification call the offline
   mutation-safe manifest verifier. Accepted mutations require enforce mode, a
   supported verdict, a successful judge call, independent generator/judge
   identities, non-diagnostic evidence, supported contracts, matching hashes,
   and a clean retained-material scan. Historical v1 manifests and packs retain
   their old reader path but cannot certify mutation safety.
31. The standalone `scripts/export_mutation_calibration_packet.py` workflow
   writes 200 deterministic review cases and a separate split-freeze artifact
   before prompt or policy tuning. It balances all five current mutation
   actions, all three domains, ten required scenario families, at least 100
   unsupported/adversarial sampling strata, and exactly 60 held-out cases.
32. The standalone `scripts/import_mutation_calibration_labels.py` workflow
   accepts only one complete, versioned, directly human-attested label per
   frozen case. It rejects duplicate cases or labels, changed split
   assignments, post-freeze input drift, invalid verdicts, incomplete coverage,
   missing provenance, and generated or judge-produced label methods before
   writing a `human_reviewed` corpus. Neither command makes provider calls.
33. The standalone `scripts/evaluate_mutation_activation.py` workflow requires
   a strictly human-reviewed corpus, an explicit generator-model identity, and
   a different bounded judge configuration. It invokes the judge three times
   over identical normalized inputs, fails closed on malformed or incomplete
   calls, and writes only bounded verdict metadata, operational totals, metric
   breakdowns, and corpus/configuration/input/output hashes. It never retains
   raw prompts, responses, credentials, or provider payloads and does not run
   the representative pipeline gate.
34. `run_profile_v4` benchmark profiles combine the bounded representative LLM
   generation contract with independent mutation-admission enforcement. The
   three checked-in representative profiles use this contract; executing them
   remains opt-in and requires explicit generator and judge configuration.
35. The final representative gate is written only after provider work has been
   separately authorized. It verifies all three mutation-safe manifests
   offline, rejects incomplete or non-representative domains, binds input
   hashes and model lineage, compares `_30_v5` with its retained pre-run tree
   digest, records costs/failures/limitations, and emits `no_go` for any failed
   threshold. Offline reconstruction rejects controlled tampering. Even an
   `activate` result records dataset release readiness as `not_established`.

Release-review outcomes are evidence only. They do not modify
`samples.jsonl`, `rejections.jsonl`, quality/evaluation/profile reports,
`dataset_release_report.json`, release-pack bytes, semantic-duplicate decisions,
or async-orchestration decisions. A `reviewed` resolution means every queued
item has a valid decision; it is not approval and does not make a dataset
releaseable.

Offline resolution may append `review_resolution_report` to a manifest after a
release pack was created. This is the only controlled post-pack append: pack
bytes remain unchanged, and verification passes only when removing that single
same-dataset report reference reconstructs manifest bytes whose SHA-256 and byte
count exactly match the manifest record locked in the pack. Missing, malformed,
extra, dataset-mismatched, or otherwise drifting content fails verification.

The run-profile boundary is declarative and synchronous. `--run-profile` supports
the existing foundation fixture, remote LLM-backed generation when `--use-llm` is
also supplied, a deterministic contacts scale probe, and `run_profile_v2`
profile-local domain sources for contacts, mobile messages, and workspace
tasks. Profile-local source declarations conflict with `--enable-network-source`
and with the external source-governance fixture; they write only source kind,
source id, content hash, license label, and source-policy hash to manifest
metadata and per-record attribution.
Per-record attribution omits target candidate counts, feature lists, profile
paths, source paths, payload rows, prompts, headers, API keys, and arbitrary
profile content. This path does not activate `synthesis.orchestration`, durable
queues, cancellation, resumption, external MCP servers, arbitrary file
ingestion, or generated environment/tool/verifier handlers.

The controlled network path is available from the CLI only with
`--enable-network-source`, `--source-url`, `--source-license-label`, and at least
one `--allowed-source-host`. Tests and local validation can exercise the same
path without external network access by passing `--mock-source-fixture`, which
injects a fixture-backed HTTP client.

The MCP-compatible adapter path is local and opt-in. `--enable-mcp-adapter`
builds a manifest from the runtime descriptor plus `RuntimeSession`, then maps
MCP-compatible tool-call envelopes into runtime action request/result records.
Contacts keeps its existing adapter identity and lineage fields; mobile message
runtimes expose `search_phone_messages`, `create_phone_reminder`, and
`draft_message_reply` through the same in-process adapter surface. The manifest
records adapter id, protocol label, adapter version, runtime/environment
id/version, source-policy hash, reset/checkpoint support, supported operations,
tool schemas, side-effect classes, and verifier implications. This path
deliberately excludes external MCP server discovery, browser automation,
credential brokering, remote filesystem access, and generated tool handlers.

The generated-code sandbox fixture is local and opt-in. `--enable-sandbox-fixture`
creates sanitized `sandbox_audits.jsonl` records for one admitted safe fixture
artifact and one rejected unsafe fixture artifact. The fixture records scan
status, admission outcome, artifact kind, and execution status in the quality
report without admitting generated handlers into the normal tool registry.

## Scaling Direction

Use synchronous run profiles and deterministic contacts scale probes before
activating a local async runner. Move to an actor or queue-based runner only when
profiled synchronous runs cannot satisfy throughput goals. The Matrix pattern
from the PDF should guide the later distributed form: task state travels with
messages; workers stay role-specific and mostly stateless. Scaling should
increase pipeline throughput and provider-call routing without adding local LLM
cluster deployment as a project responsibility.

Plan 0020 added an opt-in profile decision report above existing artifacts. The
report reads the synchronous manifest and quality report, applies explicit
thresholds, and preserves the rationale for keeping async orchestration and
semantic duplicate detection deferred until their documented triggers are met.
It does not activate `synthesis.orchestration` or change candidate-processing
behavior.

Plan 0021 hardened the candidate-processing boundary for a future local async
runner without activating `synthesis.orchestration`. The synchronous pipeline now
builds `CandidateExecutionRequest` values, executes each candidate against a
rebuilt domain environment, candidate-local tool registry, and candidate-local
runtime-backed adapter shim when enabled, then emits
`ProvisionalCandidateOutcome` records.
Tool-expansion admissions mutate only that candidate-local registry; proposal
records are serialized by candidate sequence. `merge_candidate_outcomes()` sorts
provisional outcomes by stable sequence index, admits the first duplicate
signature, converts later duplicates into `quality_duplicate` rejections, and
preserves review and tool-proposal ordering. Artifact writing remains centralized
in `synthesis.datasets`.

Plan 0022 added an opt-in held-out evaluation report before async
orchestration. `evaluation_report.json` runs deterministic contacts benchmark
tasks over the existing local execution/verifier boundaries, records
capability-level slices and optional parent evaluation comparisons, and feeds
held-out pass/regression evidence into profile decision reports when both
reports are requested. It does not change candidate generation, acceptance,
source governance, sandbox admission, or default synchronous output.

Plan 0023 tightened that opt-in reporting boundary. Held-out reports now
distinguish normal pass tasks from controlled expected-failure tasks and enforce
capability-level pass-rate thresholds. Profile decision reports now keep the MVP
quality floor separate from `profile_promotion`, which can pass, fail, block on
activated scale work, or report insufficient evidence. Low-volume exact
duplicate pressure is recorded as a watch rationale while semantic duplicate
detection remains deferred below the volume threshold.

Plan 0024 adds profile-purpose classification and an opt-in dataset release
admission report. `diagnostic_probe` profiles can validate framework behavior
and pass profile promotion without being treated as releaseable dataset
versions. `dataset_release` can pass only for `release_candidate` profiles with
passed profile promotion, passed held-out evaluation, deferred async and
semantic-duplicate decisions, zero source-policy rejection rate, and complete
release artifact references.

Ticket 01 now adds an explicitly opt-in programmatic
`synthesis.orchestration.run_serial_job` tracer bullet for validated
deterministic run profiles. It writes versioned `job.json`, `work_items.jsonl`,
and append-only `events.jsonl` records under
`<output-dir>/orchestration/<job-id>/`, persists candidate intent before
processing, checkpoints terminal provisional outcomes, and resumes by feeding
completed outcomes back through the existing candidate-processing and stable
merge seams. The normal dataset writer remains the only core-artifact
assembler, so completed serial jobs preserve synchronous samples, rejections,
manifests, and quality reports. Orchestration state is not a dataset artifact
and is not attached to the manifest. The job binds an execution-input digest
alongside the run-profile digest; resume rejects policy, source, environment,
metadata, and output-mode drift before candidate processing begins. Journal
payloads are limited to normalized pipeline records and reject provider
envelopes, credentials, secret-like values, and host paths.

This first slice is deliberately limited to serial deterministic fixture and
scale-probe jobs. Provider resumption, coverage recovery, concurrency,
cancellation, CLI exposure, and per-role usage remain later tickets. The
default synchronous command and programmatic path remain unchanged. Desired
broader behavior is defined by the
[async local orchestration spec](product-specs/async-local-orchestration.md),
while current disposition lives only in
[ISSUE-0001](../.scratch/ISSUE-0001-async-local-orchestration.md).

Plan 0042 adds two offline consumers above the artifact boundary.
`synthesis.scale_evidence` validates and aggregates exactly one contacts,
mobile-messages, and workspace-tasks run without rerunning generation or
persisting input directories. `synthesis.downstream_benchmark` verifies an
existing release pack, binds its bytes to a fixed external benchmark protocol,
and normalizes a strict external observation. Neither consumer mutates
manifests, release admission, profile decisions, review evidence, or release
pack bytes, and neither invokes a trainer, model API, worker, or scheduler.

Plan 0030 stabilizes the internal runtime contract before any AWM runtime
package extraction. Contacts and mobile environments now satisfy the same
runtime protocol and accepted executions can produce sanitized in-memory episode
logs. This remains local synchronous behavior; reward model training, Agentic
RL rollout collection, external MCP environment servers, and durable async
workers remain deferred.

Plan 0031 adds the first repo-local non-synthesis consumer of those episode
logs. The consumer is still synchronous and opt-in: it persists `episodes.jsonl`
only for the report run, writes `episode_quality_report.json`, and attaches both
artifact names to the manifest. It gives plan 0025 second-consumer evidence, but
does not activate `synthesis.orchestration`, executable state replay, reward
training, Agentic RL, external MCP environment servers, or runtime package
extraction.

Plan 0032 adds the first repo-local execution-facing consumer of those episode
logs. The consumer is synchronous and opt-in: it persists `episodes.jsonl` only
for the report run, rebuilds fresh fixture runtimes through descriptor-owned
rebuild seeds, writes `episode_replay_report.json`, and attaches both artifact
names to the manifest. Contacts, mobile, and workspace fixtures now share this
runtime boundary. It gives plan 0025 stronger package-boundary evidence, but
still does not activate `synthesis.orchestration`, reward training, Agentic RL,
external MCP environment servers, release admission changes, or runtime package
publishing.

Plan 0034 adds deterministic reward-label export over those same sanitized
episodes. The consumer is synchronous and opt-in: it persists `episodes.jsonl`
for the report run, computes quality/replay evidence in memory when needed,
writes `reward_labels.jsonl` and `reward_label_report.json`, and attaches only
reward artifacts unless quality/replay reports were explicitly requested. It
creates local scalar and preference-ready evidence, not reward-model training,
Agentic RL rollout collection, release admission changes, profile promotion, or
runtime package publishing.

Plan 0025 Phase C adds the first rollout-facing runtime API without activating
RL. Runtime sessions wrap contacts/mobile/workspace environments and registries
with list-tools, checkpoint/restore, rebuild, and execute-action semantics.
Diagnostic rollout collection remains synchronous and local: it executes
scripted policies through action envelopes and emits sanitized `episode_log_v1`
records that replay and reward-label consumers can read. It does not change
default `main.py` output, train policies, create distributed workers, connect
external MCP servers, or publish a separate runtime package.

Plan 0025 Phase D generalizes the local adapter surface onto the same runtime
boundary. Adapter manifests are now runtime-backed rather than contacts-only,
and mobile adapter execution remains opt-in, in-process, and action-envelope
based. This adds adapter evidence for the staged 0025 extraction review while
keeping external MCP servers and package publishing deferred.
