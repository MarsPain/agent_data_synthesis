# Backend

## Backend Shape

The first backend should be a local Python pipeline with explicit modules and durable artifacts. "Local" means local orchestration, environment execution, tool execution, and artifact management. LLM-backed generation, solution policy, refinement, and optional judge steps must call a configured remote OpenAI-compatible API. Avoid introducing a web service until there is a concrete need for remote execution or interactive control.

## Proposed Module Boundaries

- `synthesis.seeds`: source registration, normalized seed records, seed
  transformation records, and deterministic taxonomy-expansion requests.
- `synthesis.run_profiles`: `run_profile_v1` and `run_profile_v2` parsing,
  validation, defaulted feature flags, optional local contacts source
  declarations, sanitized metadata export, and stable config hashing for local
  synchronous runs.
- `synthesis.sources`: source governance records, license decisions, default-deny
  network policy, sandbox policy, source-bundle validation, source-policy hashes,
  deterministic no-network external-source fixtures, controlled HTTPS fetch
  contracts, bounded request admission, profile-local contacts JSON admission,
  and sanitized source-event records.
- `synthesis.environments`: environment builders, typed contacts environment
  input records, reset/checkpoint operations, and state adapters.
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
- `synthesis.profile_decisions`: opt-in profile benchmark decision reports built
  from manifest, quality report, optional parent comparison, runtime, and
  deterministic thresholds.
- `synthesis.candidate_processing`: single-candidate validation, policy
  execution, verification, duplicate/logical gates, optional tool-expansion
  reruns, optional refinement reruns, and structured per-candidate outcomes for
  the synchronous pipeline to merge in order.
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
   contacts source into the existing synchronous pipeline arguments.
2. Validate the source bundle before environment construction. External-source
   material must pass license, network, and sandbox gates or be rejected with
   `source_policy_rejected`.
3. When controlled network-backed synthesis is explicitly enabled, fetch one
   allowlisted HTTPS JSON source through the injectable HTTP boundary, enforce
   timeout, byte, content-type, redirect, and request-budget limits, and convert
   the payload into a typed contacts environment input. When a `run_profile_v2`
   declares `source.kind=local_contacts_json`, read the profile-relative JSON
   file under its byte budget, admit it as `source_kind=local_file`, and convert
   it through the same typed contacts environment input boundary. The default
   pipeline does not fetch external network sources or ingest arbitrary local
   files.
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
9. Generate or select a solution policy for each valid task, using the
   `solution_policy` role for remote policies and deterministic local lineage for
   scripted policies.
10. Execute policy steps directly against the local registry by default. When
   `--enable-mcp-adapter` or `enable_mcp_adapter=True` is explicitly set, route
   the same policy steps through the local in-process contacts adapter shim. The
   top-level trajectory still records the normal action, observation,
   state-change, and final-response events; adapter call metadata is stored in
   lineage and rejection details.
11. When a candidate carries a bounded branch plan, execute branch attempts from a
   clean environment checkpoint until one terminal path succeeds, preserving
   rejected branch outcomes separately from the selected trajectory.
12. Verify outputs and expected state changes independently.
13. For repairable verification or logical-support failures, optionally run one
   `critic_refinement` attempt and rerun validation, execution, verification,
   and quality gates through the normal path.
14. When execution exposes a capability gap such as a missing tool or schema
   mismatch, optionally request one `tool_generation` proposal, admit only a
   matching curated local implementation, and rerun through the normal execution,
   verification, and quality gates.
15. When `--enable-sandbox-fixture` or `enable_sandbox_fixture=True` is
   explicitly set, run a deterministic generated-code fixture through static
   scan, admission, restricted local execution, and redacted audit serialization.
   This fixture does not enable arbitrary generated tools, environments, or
   verifiers and does not change default accepted/rejected sample counts.
16. Apply dataset-quality gates such as exact duplicate detection and logical
   consistency checks.
17. Route failed samples by error class and optional review policy.
18. Export accepted samples, rejections, source-event audits when enabled,
   sandbox audits when enabled, tool proposal events, branch lineage,
   task-expansion lineage, quality reports, lineage, sanitized run-profile
   manifest metadata, and narrow per-record run-profile attribution when a
   profile is supplied.
19. When `--write-profile-decision-report` is explicitly supplied, read the
   exported manifest and quality report, write `profile_decision_report.json`,
   and rewrite only the manifest artifact map to reference that report.

The run-profile boundary is declarative and synchronous. `--run-profile` supports
the existing foundation fixture, remote LLM-backed generation when `--use-llm` is
also supplied, a deterministic contacts scale probe, and a `run_profile_v2`
profile-local contacts JSON source. Profile-local source declarations conflict
with `--enable-network-source` and with the external source-governance fixture;
they require the contacts domain and write only source id, content hash, license
label, and source-policy hash to manifest metadata and per-record attribution.
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

The candidate-processing boundary is orchestration-ready because it returns
structured per-candidate samples, rejections, review records, tool proposal
records, and accepted duplicate signatures for the synchronous pipeline to merge.
It is not concurrency-safe yet. A future orchestration plan must define
per-candidate environment checkpoint/reset isolation, curated tool registry
mutation rules for tool-expansion reruns, deterministic duplicate admission when
candidates complete out of order, and manifest/quality-report merge ordering for
durable queues.
