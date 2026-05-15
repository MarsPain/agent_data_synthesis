# Agent Data Synthesis Framework Design

## Purpose

This document turns the source analysis in [../references/agent-data-synthesis-pdf-analysis.md](../references/agent-data-synthesis-pdf-analysis.md) into a development architecture for this repository. It should guide implementation until a more specific design supersedes it.

## System Thesis

The framework should generate complete Agent training records by constructing an executable world, exposing typed tools, generating tasks grounded in that world, running trajectories, validating outcomes independently, and exporting accepted samples with quality and lineage metadata.

The central design object is not a prompt. It is a verified trajectory:

```text
seed -> environment -> tools -> task -> trajectory -> verifier -> accepted sample -> dataset version
```

## MVP Divergence From The Source PDF

The MVP intentionally narrows the PDF architecture so the first implementation can prove local contracts before adding high-risk automation. These are staging choices, not changes to the target architecture:

- **Environment synthesis:** the PDF describes a sandboxed synthesis Agent that can use search and shell tools to gather real-world data and build domain databases. The MVP starts from local configs and fixture data until provenance, licensing, network logging, and sandbox controls are implemented.
- **LLM execution:** the MVP is LLM-driven, but LLM inference is outside this repository. Generation, refinement, candidate solution policy, and optional judge calls must use a remote OpenAI-compatible API configured by `LLM_BASE_URL`, `API_KEY`, and `LLM_MODEL`; the project will not provision or manage local LLM clusters.
- **Generated code:** the PDF uses executable Python as an intermediate representation for tasks, tools, solutions, and verifiers. The MVP should prefer structured tools and scripted verifiers where possible, then introduce generated code only behind isolation and audit controls.
- **Distributed orchestration:** the PDF includes Matrix-style distributed workers, row-level scheduling, dynamic control flow, and monitoring. The MVP keeps this local and durable first; later scaling must preserve task state, per-role metrics, and resumability.
- **Self-evolution:** the PDF points toward models acting as generators and verifiers in a self-improving loop. The MVP should record the failure and quality signals that make this possible later, without trusting self-judged samples as accepted data.

## Architecture Layers

### 1. Seed and Domain Layer

Responsibilities:

- Register domain descriptions, source documents, task taxonomies, and target capabilities.
- Normalize source materials into stable seed records.
- Track seed provenance and eligibility.

Early implementation:

- Use local YAML or JSON domain configs.
- Store normalized seed metadata in manifests.
- Avoid crawling or network-dependent seed ingestion until provenance rules are implemented.

### 2. Environment Layer

Responsibilities:

- Build executable environments with deterministic reset behavior.
- Own state schema, fixture data, business rules, and environment versions.
- Provide checkpoints for retry and branch exploration.

For a teaching-oriented explanation of this environment model, see [architecture-explainers.md](architecture-explainers.md#awm-environment-model).

Early implementation:

- Use SQLite databases and Python environment classes.
- Model business rules as code plus database constraints.
- Export reset recipes so samples can be reproduced.

Later implementation:

- Add MCP-compatible environment servers.
- Add container isolation for generated environments.
- Add environment templates and cacheable base states.

### 3. Tool Layer

Responsibilities:

- Register tools with typed input schemas, return schemas, side-effect metadata, and version ids.
- Maintain a tool dependency graph for valid composition.
- Support dynamic tool proposals when generation failures reveal missing capability.

Early implementation:

- Python callables with Pydantic-style or JSON Schema metadata.
- Tool calls recorded as structured trajectory events.
- Explicit side-effect labels: read-only, state-mutating, external, destructive.

### 4. Task and Curriculum Layer

Responsibilities:

- Generate grounded tasks that are feasible in the current environment.
- Score difficulty across multiple dimensions.
- Ensure coverage across skills, domains, personas, tools, and long-tail cases.
- Preserve enough taxonomy metadata to support AgentInstruct-style skill coverage and seed expansion.

Difficulty dimensions:

- Number of required tools.
- Number of constraints.
- Amount of missing or ambiguous information.
- State mutation requirements.
- Branching or fallback paths.
- Need for recovery from tool errors.
- Global consistency requirements across steps.

AgentInstruct-style refinement contracts:

- Raw seeds should be transformable into normalized intermediate records before task generation.
- Task generation should be taxonomy-driven, with explicit skill, subskill, domain, persona, and interaction-mode tags.
- Multiple generator roles may propose variants, but their outputs must pass common schema and feasibility checks before refinement.
- Refinement should separate suggestion from editing: one role proposes complexity, clarity, or diversity changes; another role applies and validates them.
- Feedback may route a failed item back to seed transformation, task generation, or refinement instead of only retrying the final trajectory.
- Multi-turn dialogue tasks should encode user persona traits such as domain knowledge, patience, communication style, progressive disclosure, corrections, and requirement changes.

### 5. Trajectory Execution Layer

Responsibilities:

- Execute a candidate policy or generated solution against the environment.
- Capture ordered events: thought, action, observation, final response, error, retry, and state change.
- Classify failures without losing diagnostic logs.

Early implementation:

- Start with remote LLM-generated candidate policies where LLM access is configured, and keep scripted policies available for smoke tests and deterministic fixtures.
- Enforce timeouts and deterministic seeds.
- Preserve raw execution logs outside training exports when needed for debugging.

### 6. Verification Layer

Responsibilities:

- Verify candidates independently from the generator.
- Combine executable checks, logical checks, schema checks, diversity checks, and optional judge checks.
- Route uncertain samples to human review.

Verifier types:

- Existence checks: returned entities exist in the environment.
- Constraint checks: budgets, dates, city matches, inventory, permissions, and other task constraints hold.
- State checks: expected mutations occurred and invalid mutations did not.
- Consistency checks: observations support final answer.
- Format checks: output matches training format.
- Diversity checks: sample is not a near-duplicate and covers target distribution cells.

### 7. Dataset Assembly Layer

Responsibilities:

- Build accepted samples from verified artifacts.
- Assign dataset versions and splits.
- Emit JSONL, manifest, quality report, and rejected-candidate diagnostics.
- Support incremental regeneration when seeds, tools, environments, or verifiers change.

Acceptance rule:

A sample is accepted only if it passes required executable checks and has complete lineage. Judge-only acceptance is not enough for tool or environment tasks.

### 8. Orchestration Layer

Responsibilities:

- Run jobs, workers, retries, queues, cancellation, and metrics.
- Preserve durable state for resumability.
- Scale from local execution to actor-based distributed execution.

Early implementation:

- Local job runner with a durable run directory.
- Async execution for independent candidates.
- Metrics emitted as JSON or CSV.
- Remote LLM provider adapter shared by generator, refinement, policy, and judge roles.

Later implementation:

- Matrix-inspired actor workers.
- Message-carried task state.
- Ray or queue-backed distributed execution.
- Configuration-driven control flow with explicit role definitions, resource requirements, and routing rules.
- Row-level scheduling so slow candidates do not block unrelated candidates.
- Message offloading for large dialogue histories or execution logs.
- Monitoring for queue depth, async backlog, token throughput, GPU/CPU utilization, verifier yield, failure classes, and cost by role.

Even in later distributed forms, this project should scale orchestration workers and provider-call routing rather than becoming a local LLM serving or cluster management system.

## Canonical Generation Loop

1. Load domain config and seed records.
2. Build or select environment version.
3. Register tools and dependency graph.
4. Generate candidate task with difficulty metadata through the remote LLM provider.
5. Generate or select candidate solution policy through the remote LLM provider, with scripted fallback only for fixtures and smoke tests.
6. Execute policy and capture trajectory.
7. Run independent verifiers.
8. If failed, classify root cause.
9. If failure is repairable, regenerate task, solution, verifier, tool, or environment.
10. If accepted, assemble sample and update dataset manifest.

## Failure Taxonomy

- `task_infeasible`: task cannot be satisfied in the environment.
- `tool_missing`: required capability has no tool.
- `tool_schema_error`: generated call violates schema.
- `tool_runtime_error`: tool failed during execution.
- `solution_logic_error`: trajectory did not satisfy constraints.
- `verifier_bug`: verifier contradicts environment or task semantics.
- `environment_bug`: state or business rules are inconsistent.
- `quality_duplicate`: sample adds little distribution value.
- `unsafe_generated_code`: generated code violates sandbox policy.
- `infrastructure_error`: timeout, unavailable worker, or storage failure.

## Data Contracts

The data contracts in [../DATA.md](../DATA.md) are mandatory for accepted samples. Implementation should define typed models for:

- SeedRecord
- EnvironmentSpec
- ToolSpec
- TaskSpec
- TrajectoryEvent
- VerificationResult
- QualityReport
- LineageRecord
- DatasetManifest

## Quality Gates

Minimum gates for MVP:

- Schema validation passes.
- Environment reset succeeds.
- All required tools execute in a smoke test.
- Candidate trajectory executes without unclassified exceptions.
- Independent verifier passes.
- Sample lineage is complete.
- Sample is not a duplicate by exact task and tool sequence.

Recommended later gates:

- Semantic duplicate detection.
- LLM-as-judge clarity and relevance checks.
- Long-tail coverage targets.
- Human review routing by uncertainty.
- Downstream model evaluation.
- Curriculum effectiveness checks against model learning curves.
- Transfer-gain checks on held-out Agent tasks.
- Quality trend monitoring by domain, difficulty, and tool combination.

## Security and Isolation

Generated code and tools are untrusted. Follow [../SECURITY.md](../SECURITY.md). The first version should avoid arbitrary generated code execution where a structured tool or scripted verifier can express the same behavior. When generated code is required, run it with strict timeouts and limited access.

## Implementation Sequence

1. Create package skeleton and typed data models.
2. Implement local run directory and manifest format.
3. Implement remote LLM provider adapter from `LLM_BASE_URL`, `API_KEY`, and `LLM_MODEL`.
4. Implement a small SQLite environment fixture.
5. Implement tool registry over that fixture.
6. Implement LLM-backed task generator for a constrained demo domain.
7. Implement trajectory runner and event capture.
8. Implement independent verifier checks.
9. Implement JSONL export and quality report.
10. Add failure classification and retry loop.
11. Add curriculum expansion and diversity metrics.

## Open Decisions

- Whether typed models should use Pydantic or standard dataclasses plus `jsonschema`.
- Whether the first demo domain should be travel planning, e-commerce, or database operations.
- What minimum sandbox is acceptable before executing generated code.
