# Backend

## Backend Shape

The first backend should be a local Python pipeline with explicit modules and durable artifacts. "Local" means local orchestration, environment execution, tool execution, and artifact management. LLM-backed generation, solution policy, refinement, and optional judge steps must call a configured remote OpenAI-compatible API. Avoid introducing a web service until there is a concrete need for remote execution or interactive control.

## Proposed Module Boundaries

- `synthesis.seeds`: source registration, normalized seed records, seed
  transformation records, and deterministic taxonomy-expansion requests.
- `synthesis.run_profiles`: `run_profile_v1` and `run_profile_v2` parsing,
  validation, defaulted feature flags, optional profile-local domain source
  declarations, sanitized metadata export, and stable config hashing for local
  synchronous runs.
- `synthesis.sources`: source governance records, license decisions, default-deny
  network policy, sandbox policy, source-bundle validation, source-policy hashes,
  deterministic no-network external-source fixtures, controlled HTTPS fetch
  contracts, bounded request admission, profile-local file admission, and
  sanitized source-event records.
- `synthesis.domain_sources`: profile-local domain source importer protocol,
  importer resolution, generic import records, and governed local source
  admission into domain-owned typed environment input.
- `synthesis.environments`: environment builders, typed contacts environment
  input records, reset/checkpoint operations, and state adapters.
- `synthesis.mobile_sources`: mobile messages JSON importer that converts
  admitted source bytes into `MobileMessagesEnvironmentInput`.
- `synthesis.runtime`: internal environment runtime protocol, sanitized
  `runtime_metadata_v1` construction, immutable runtime capability descriptors,
  and deterministic runtime registry lookup for lifecycle and capability
  evidence shared by contacts and mobile domain environments.
- `synthesis.episodes`: internal `episode_log_v1` construction, deterministic
  transition hashing, redaction, and diagnostic episode summaries over existing
  trajectories.
- `synthesis.episode_quality`: opt-in `episodes.jsonl` persistence and
  `episode_quality_report_v1` construction over sanitized episode logs. It
  validates runtime/episode evidence, scores transition completeness and
  state-change support, and writes compact summaries without raw tool payloads,
  prompts, credentials, or host paths.
- `synthesis.episode_replay`: opt-in `episode_replay_report_v1` construction
  over sanitized episode logs. It reads replay support, state-changing tools,
  and rebuild seed facts from the runtime registry, rebuilds fresh supported
  fixture runtimes, re-executes action transitions through
  `ToolRegistry.execute()`, compares observation/state-change hashes, and writes
  compact summaries without raw tool payloads, prompts, credentials, or host
  paths.
- `synthesis.reward_labels`: opt-in `reward_labels.jsonl` and
  `reward_label_report_v1` construction over sanitized episode, quality, and
  replay evidence. It reads reward-label and state-changing-tool support from
  runtime descriptors, then produces deterministic scalar labels and
  preference-group metadata without training reward models, collecting RL
  rollouts, changing release admission, or extracting a runtime package.
- `synthesis.tools`: tool definitions, schema generation, registry, dependency
  graph, capability-gap records, bounded tool proposals, and curated local tool
  admission.
- `synthesis.mcp`: local MCP-compatible adapter manifests, tool-call request and
  result envelopes, adapter lineage records, and the in-process contacts adapter
  shim. It does not start an MCP server or connect to external tool servers.
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

1. Register seeds and target domain. For configurable local runs, load a
   validated `run_profile_v1` or `run_profile_v2` file and translate its seed,
   generation mode, dataset version, feature flags, and optional governed local
   domain source into the existing synchronous pipeline arguments.
2. Validate the source bundle before environment construction. External-source
   material must pass license, network, and sandbox gates or be rejected with
   `source_policy_rejected`.
3. When controlled network-backed synthesis is explicitly enabled, fetch one
   allowlisted HTTPS JSON source through the injectable HTTP boundary, enforce
   timeout, byte, content-type, redirect, and request-budget limits, and convert
   the payload into a typed contacts environment input. When a `run_profile_v2`
   declares `source.kind=local_contacts_json` or
   `source.kind=local_mobile_messages_json`, read the profile-relative JSON file
   under its byte budget, admit it as `source_kind=local_file`, and hand the
   admitted bytes to the matching domain importer. The default pipeline does not
   fetch external network sources or ingest arbitrary local files.
4. Build or load an environment version with source provenance, source-policy
   hash metadata, and environment-source admission status.
5. Build or load a tool registry version.
6. Resolve the role registry and generate candidate tasks by curriculum policy
   through the `task_generation` role when remote generation is enabled.
7. If remote generation fails after configuration, write a classified generation
   rejection plus manifest and quality report artifacts.
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
   the same policy steps through the local in-process contacts adapter shim. The
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
19. Route failed samples by error class and optional review policy.
20. Export accepted samples, rejections, source-event audits when enabled,
   sandbox audits when enabled, tool proposal events, branch lineage,
   task-expansion lineage, quality reports, lineage, sanitized run-profile
   manifest metadata, and narrow per-record run-profile attribution when a
   profile is supplied.
21. When `--write-episode-quality-report` is explicitly supplied, write
   `episodes.jsonl`, score it into `episode_quality_report.json`, and rewrite
   only the manifest artifact map to reference both opt-in artifacts. This
   local synchronous consumer validates and scores runtime episode evidence; it
   does not replay actions against fresh state, train reward models, collect RL
   rollouts, or change candidate admission.
22. When `--write-episode-replay-report` is explicitly supplied, write
   `episodes.jsonl`, replay it into `episode_replay_report.json`, and rewrite
   only the manifest artifact map to reference both opt-in artifacts. This
   local synchronous consumer rebuilds fixture runtimes and executes tool
   transitions; it does not train reward models, collect RL rollouts, call
   external MCP environment servers, change release admission, or extract an
   AWM runtime package.
23. When `--write-reward-label-report` is explicitly supplied, write
   `episodes.jsonl`, compute quality and replay evidence in memory when their
   reports were not explicitly requested, write `reward_labels.jsonl` and
   `reward_label_report.json`, and rewrite only the manifest artifact map to
   reference `episodes`, `reward_labels`, and `reward_label_report`. This local
   synchronous consumer produces deterministic labels; it does not train reward
   models, collect RL rollouts, call external MCP environment servers, change
   release admission, promote profiles, or extract an AWM runtime package.
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

The run-profile boundary is declarative and synchronous. `--run-profile` supports
the existing foundation fixture, remote LLM-backed generation when `--use-llm` is
also supplied, a deterministic contacts scale probe, and `run_profile_v2`
profile-local domain sources for contacts and mobile messages. Profile-local
source declarations conflict with `--enable-network-source` and with the
external source-governance fixture; they write only source kind, source id,
content hash, license label, and source-policy hash to manifest metadata and
per-record attribution.
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
builds a manifest for the contacts environment and curated contacts tool
registry, then executes calls through an in-process shim. The manifest records
adapter id, protocol label, adapter version, environment id/version,
source-policy hash, reset/checkpoint support, supported operations, tool schemas,
side-effect classes, and verifier implications. This path deliberately excludes
external MCP server discovery, browser automation, credential brokering, remote
filesystem access, and generated tool handlers.

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
rebuilt contacts environment, candidate-local tool registry, and candidate-local
adapter shim when enabled, then emits `ProvisionalCandidateOutcome` records.
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

Remaining async work is still deferred to plan 0014: durable queues, workers,
cancellation, resumption, external process isolation, and per-role async cost
tracking are not active runtime behavior.

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
for the report run, rebuilds fresh contacts/mobile fixture runtimes, writes
`episode_replay_report.json`, and attaches both artifact names to the manifest.
It gives plan 0025 stronger package-boundary evidence, but still does not
activate `synthesis.orchestration`, reward training, Agentic RL, external MCP
environment servers, release admission changes, or runtime package extraction.

Plan 0034 adds deterministic reward-label export over those same sanitized
episodes. The consumer is synchronous and opt-in: it persists `episodes.jsonl`
for the report run, computes quality/replay evidence in memory when needed,
writes `reward_labels.jsonl` and `reward_label_report.json`, and attaches only
reward artifacts unless quality/replay reports were explicitly requested. It
creates local scalar and preference-ready evidence, not reward-model training,
Agentic RL rollout collection, release admission changes, profile promotion, or
runtime package extraction.
