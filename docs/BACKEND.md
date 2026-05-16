# Backend

## Backend Shape

The first backend should be a local Python pipeline with explicit modules and durable artifacts. "Local" means local orchestration, environment execution, tool execution, and artifact management. LLM-backed generation, solution policy, refinement, and optional judge steps must call a configured remote OpenAI-compatible API. Avoid introducing a web service until there is a concrete need for remote execution or interactive control.

## Proposed Module Boundaries

- `synthesis.seeds`: source registration and normalized seed records.
- `synthesis.environments`: environment builders, reset/checkpoint operations, and state adapters.
- `synthesis.tools`: tool definitions, schema generation, registry, and dependency graph.
- `synthesis.tasks`: task generation, difficulty scoring, curriculum policies,
  and candidate-level generation lineage attachment.
- `synthesis.execution`: trajectory runner, retry policy, and event capture.
- `synthesis.verification`: executable, logical, and judge-based validators.
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

Provider calls should record model id, base URL host, prompt or config hash, token
and cost metadata when available, retry count, and error class. Transient
transport failures, timeouts, HTTP 429, and HTTP 5xx responses may be retried
within a bounded local budget. Secrets must never be written to manifests,
trajectories, exports, or logs.

## Job Lifecycle

1. Register seeds and target domain.
2. Build or load an environment version.
3. Build or load a tool registry version.
4. Generate candidate tasks by curriculum policy.
5. If remote generation fails after configuration, write a classified generation
   rejection plus manifest and quality report artifacts.
6. Execute candidate solutions against the environment.
7. Verify outputs independently.
8. Apply dataset-quality gates such as exact duplicate detection and logical
   consistency checks.
9. Route failed samples by error class and optional review policy.
10. Export accepted samples, rejections, quality reports, and lineage.

## Scaling Direction

Start with a local async runner. Move to an actor or queue-based runner only when local orchestration cannot satisfy throughput goals. The Matrix pattern from the PDF should guide the later distributed form: task state travels with messages; workers stay role-specific and mostly stateless. Scaling should increase pipeline throughput and provider-call routing without adding local LLM cluster deployment as a project responsibility.
