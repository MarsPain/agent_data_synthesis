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

### Tool Registry

Owns tool schemas, typed parameters, return types, side-effect declarations, dependency graph edges, and compatibility rules.

### Task Curriculum

Owns task generation, difficulty scoring, ambiguity controls, persona controls, and progression rules.

### Trajectory Execution

Owns policy execution, tool call recording, observation capture, retries, and error classification.

### Verification

Owns executable checks, logical checks, LLM-as-judge checks, diversity checks, and human review routing.

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
- Python callable tools with explicit schemas.
- Local job runner with resumable manifests.
- Remote LLM provider adapter configured by `LLM_BASE_URL`, `API_KEY`, and `LLM_MODEL`.
- Executable verification before LLM-as-judge verification.
- JSONL output plus a dataset manifest.

Distributed Ray-style orchestration, MCP servers, and multi-model routing should be added after local contracts are stable. These additions may scale workers and route provider calls, but they should not turn the project into a local LLM serving platform.
