# Backend

## Backend Shape

The first backend should be a local Python pipeline with explicit modules and durable artifacts. "Local" means local orchestration, environment execution, tool execution, and artifact management. LLM-backed generation, solution policy, refinement, and optional judge steps must call a configured remote OpenAI-compatible API. Avoid introducing a web service until there is a concrete need for remote execution or interactive control.

## Proposed Module Boundaries

- `synthesis.seeds`: source registration and normalized seed records.
- `synthesis.environments`: environment builders, reset/checkpoint operations, and state adapters.
- `synthesis.tools`: tool definitions, schema generation, registry, and dependency graph.
- `synthesis.tools`: tool definitions, schema generation, registry, dependency
  graph, capability-gap records, bounded tool proposals, and curated local tool
  admission.
- `synthesis.tasks`: task generation, difficulty scoring, curriculum policies,
  expected state declarations, and candidate-level generation lineage attachment.
- `synthesis.execution`: solution policy selection/parsing, ordered tool-step
  execution, trajectory runner, retry policy, and event capture.
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
- `synthesis.datasets`: sample assembly, manifests, artifact exports, generation
  failure rejection records, and quality report path plumbing.
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
`critic_refinement`, and the bounded `tool_generation` proposal role. Future
environment, verifier, judge, suggester, and editor roles are present as disabled
guardrails. `tool_generation` may only produce structured tool proposal records;
it does not produce executable code or installable packages. Provider lineage
should record role name, role version, output type, owner module, retry policy,
model id, base URL host, prompt or config hash, token and cost metadata when
available, retry count, and error class. Transient transport failures, timeouts,
HTTP 429, and HTTP 5xx responses may be retried within a bounded local budget.
Secrets must never be written to manifests, trajectories, exports, or logs.

## Job Lifecycle

1. Register seeds and target domain.
2. Build or load an environment version.
3. Build or load a tool registry version.
4. Resolve the role registry and generate candidate tasks by curriculum policy
   through the `task_generation` role when remote generation is enabled.
5. If remote generation fails after configuration, write a classified generation
   rejection plus manifest and quality report artifacts.
6. Generate or select a solution policy for each valid task, using the
   `solution_policy` role for remote policies and deterministic local lineage for
   scripted policies.
7. Execute policy steps against the environment and record action, observation,
   state-change, and final-response events.
8. Verify outputs and expected state changes independently.
9. For repairable verification or logical-support failures, optionally run one
   `critic_refinement` attempt and rerun validation, execution, verification,
   and quality gates through the normal path.
10. When execution exposes a capability gap such as a missing tool or schema
   mismatch, optionally request one `tool_generation` proposal, admit only a
   matching curated local implementation, and rerun through the normal execution,
   verification, and quality gates.
11. Apply dataset-quality gates such as exact duplicate detection and logical
   consistency checks.
12. Route failed samples by error class and optional review policy.
13. Export accepted samples, rejections, tool proposal events, quality reports,
   and lineage.

## Scaling Direction

Start with a local async runner. Move to an actor or queue-based runner only when local orchestration cannot satisfy throughput goals. The Matrix pattern from the PDF should guide the later distributed form: task state travels with messages; workers stay role-specific and mostly stateless. Scaling should increase pipeline throughput and provider-call routing without adding local LLM cluster deployment as a project responsibility.
