# Design

## Design Goal

Build an Agent data synthesis framework that produces executable, verifiable, versioned training trajectories. A valid output sample must preserve the relationship among environment state, available tools, task intent, actions, observations, final answer, verification result, and lineage metadata.

## Core Invariants

- **Executable first:** tasks, tools, and verifiers should be runnable whenever possible.
- **Generation and verification are separate:** never let the same component both invent and certify a sample without an independent check.
- **Environment-tool-task consistency:** generated tasks must be grounded in the environment and only require tools that exist or are explicitly synthesized.
- **Curriculum-aware generation:** data should cover difficulty levels from simple single-tool tasks to ambiguous, multi-step, branching tasks.
- **Quality is multidimensional:** track executable success, semantic clarity, logical consistency, diversity, coverage, and cost.
- **Lineage is mandatory:** every output sample must reference source seed, environment version, tool version, generator version, verifier version, and quality gate decisions.
- **Remote LLM boundary:** LLM calls go through a configured remote OpenAI-compatible API; this project does not deploy or manage local LLM clusters.

## Bounded Contexts

### Seed Intake

Owns source registration, task taxonomy selection, domain constraints, and seed normalization. It should not execute tools or validate trajectories.

### Environment Synthesis

Owns executable environment construction, state schema, fixture generation, reset/checkpoint behavior, and environment versioning.

Environment implementations also satisfy the internal runtime boundary. Contacts
and mobile fixtures expose `runtime_metadata_v1`, checkpoint/restore, and
candidate-local rebuild semantics through the same protocol while keeping
domain-owned SQLite state and tool behavior inside their domain modules.

### Tool Registry

Owns tool schemas, typed parameters, return types, side-effect declarations, dependency graph edges, and compatibility rules.

### Task Curriculum

Owns task generation, difficulty scoring, ambiguity controls, persona controls, and progression rules.

`CandidateTask` remains the compatibility wrapper for deterministic and remote
task generators, task expansion, rejections, and public artifact assembly. The
pipeline derives internal task contracts from it before execution: task intent,
policy hints, expected final-answer evidence, and expected state checks are
separate internal records.

### Trajectory Execution

Owns policy execution, tool call recording, observation capture, retries, and error classification.

Scripted contacts and mobile policies can consume internal policy hints while
the public policy-generator API continues to accept `CandidateTask`. This keeps
deterministic trajectories stable while reducing coupling between generator-era
task records and execution planning.

Execution can now derive internal `episode_log_v1` evidence from existing
trajectories. Episode evidence records ordered actions, observations,
state-change summaries, final responses, runtime identity, policy identity, and
verifier identity for diagnostics and opt-in quality scoring. It is not part of
the default dataset sample schema and is not a release artifact.

### Verification

Owns executable checks, logical checks, LLM-as-judge checks, diversity checks, and human review routing.

The exact-answer/state verifier reads internal expected-outcome and
expected-state contracts. Compatibility wrappers still accept `CandidateTask`,
and verifier ids, versions, check names, sample schemas, and episode schemas
remain stable.

### Episode Quality

Owns the first non-synthesis consumer of runtime episode evidence. It reads
opt-in `episodes.jsonl` records, validates the `episode_log_v1` contract, scores
transition completeness and state-change support, and writes
`episode_quality_report_v1` summaries without raw arguments, observations,
final responses, prompts, provider payloads, credentials, source payloads, or
host paths. It consumes `synthesis.runtime` and `synthesis.episodes`; it does
not own candidate admission, dataset release, profile promotion, reward model
training, executable replay, or Agentic RL rollout collection.

### Episode Replay

Owns the first execution-facing consumer of runtime episode evidence. It reads
opt-in `episodes.jsonl` records, validates `episode_log_v1`, rebuilds fresh
contacts/mobile fixture runtimes, re-executes action transitions through
`ToolRegistry.execute()`, compares replayed observation and state-change hashes,
and writes `episode_replay_report_v1` summaries without raw arguments,
observations, final responses, prompts, provider payloads, credentials, source
payloads, or host paths. It consumes `synthesis.runtime`, `synthesis.episodes`,
`synthesis.episode_quality`, and `synthesis.domain_pipeline`; it does not own
candidate admission, dataset release, profile promotion, reward model training,
external MCP environment servers, async orchestration, or AWM runtime package
extraction.

### Dataset Assembly

Owns canonical output format, split assignment, versioning, deduplication, manifest generation, and export adapters for training.

### Orchestration

Owns job lifecycle, queues, concurrency, cancellation, retries, metrics, and worker placement.

## Required Sample Shape

Each final sample should contain:

- `environment`: environment id, version, state snapshot or reset recipe.
- `tools`: tool schemas, versions, dependencies, and side-effect metadata.
- `task`: natural language instruction, structured constraints, difficulty score, and expected capabilities.
- `trajectory`: ordered thought/action/observation/final-response events or a policy-compatible equivalent.
- `verifier`: verifier id, executable checks, logical checks, and result details.
- `quality`: executable rate, success outcome, clarity score, diversity tags, and review status.
- `lineage`: seed ids, generator versions, model ids, prompt/config hashes, and timestamps.

## First Implementation Bias

Start local and deterministic:

- SQLite-backed environments.
- Domain packs own their domain state, tool registry, deterministic candidates,
  and scripted policy generation. The synchronous pipeline owns shared synthesis
  flow: domain selection, candidate-local isolation, execution, verification,
  deterministic merge, and artifact assembly.
- Runtime metadata is lifecycle evidence, not dataset or release metadata.
  Runtime-aware code should use `runtime_metadata()` for environment identity,
  reset recipe class, state backend, and checkpoint strategy; sample assembly
  continues to use `metadata()` for the public dataset environment field.
- Episode-quality reporting is a repo-local, synchronous runtime evidence
  consumer. It proves the episode boundary can serve another data-quality
  reader while keeping full AWM runtime package extraction deferred.
- Episode-replay reporting is a repo-local, synchronous execution consistency
  consumer. It proves the current runtime boundary can serve a non-synthesis
  executor that rebuilds fixture runtimes and calls registries directly, while
  keeping full AWM runtime package extraction deferred.
- Task-intent, policy-hint, expected-outcome, and expected-state contracts are
  internal only. They de-risk future reward/RL/runtime consumers without
  changing `CandidateTask.export()`, `samples.jsonl`, `rejections.jsonl`, or
  episode report schemas.
- Python callable tools with explicit schemas.
- Local job runner with resumable manifests.
- Remote LLM provider adapter configured by `AGENT_DATA_LLM_BASE_URL`, `AGENT_DATA_API_KEY`, and `AGENT_DATA_LLM_MODEL`.
- Executable verification before LLM-as-judge verification.
- JSONL output plus a dataset manifest.

Distributed Ray-style orchestration, MCP servers, and multi-model routing should be added after local contracts are stable. These additions may scale workers and route provider calls, but they should not turn the project into a local LLM serving platform.
