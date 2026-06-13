# Plan 0025: AWM Runtime Boundary and Shared Environment Kernel

## Status

Planned on 2026-06-09. **Deferred** after plan 0031 supplied a second
repo-local data-quality consumer of episode evidence. Extraction still waits
for stronger pressure from executable replay, reward-label/training workflows,
Agentic RL rollout execution, external MCP environment servers, or clear
cross-consumer package-boundary criteria.

## Goal

Prepare the current environment layer to become a shared AWM runtime kernel
without prematurely splitting it into a separate repository or package.

## Decision

Adopt the staged extraction path:

1. First stabilize the AWM runtime boundary inside this repository.
2. Keep data synthesis as the first consumer while preventing dataset-specific
   concerns from leaking into the environment runtime.
3. Add additional consumers against the same runtime interface. Plan 0031 adds
   the first repo-local episode data-quality scoring consumer, but it does not
   replay actions against fresh runtime state or drive reward/RL workflows.
4. Split the runtime into a separate project only after the shared contract is
   validated by multiple consumers whose needs justify a package boundary.

The intended future split is an `awm_runtime`-style project or package, not a
contacts-domain fixture project. The shared unit should be the execution
contract, adapter surface, state lifecycle, and episode logging model.

## Basis

- [../../design-docs/architecture-explainers.md](../../design-docs/architecture-explainers.md#awm-environment-model)
  defines the AWM environment model as a code-backed world with state, tools,
  observations, and independent verification.
- [../../DESIGN.md](../../DESIGN.md) treats environment synthesis, tool
  registry, trajectory execution, verification, and dataset assembly as separate
  bounded contexts.
- [../completed/0013-mcp-compatible-environment-tool-adapters.md](../completed/0013-mcp-compatible-environment-tool-adapters.md)
  added the first local MCP-compatible environment/tool adapter.
- [../completed/0021-candidate-isolation-and-deterministic-merge.md](../completed/0021-candidate-isolation-and-deterministic-merge.md)
  established per-candidate environment, registry, and adapter isolation.
- Future reward-model-driven data quality evaluation and Agentic RL both need
  reproducible environment reset, tool/action execution, observation records,
  state inspection, and episode-level evidence. Those needs overlap with data
  synthesis, but their training loops and evaluation policies must remain
  separate from the environment runtime.
- [../completed/0031-episode-replay-and-data-quality-scoring-consumer.md](../completed/0031-episode-replay-and-data-quality-scoring-consumer.md)
  adds an opt-in `episode_quality_report_v1` consumer over `episode_log_v1`.
  This supplies second-consumer evidence for sanitized episode scoring, but it
  deliberately excludes executable replay, reward model training, Agentic RL,
  external MCP servers, and package extraction.

## Trigger Conditions

Move this plan from `deferred/` to `active/` when one of these is true:

- reward-model-driven Agent data quality evaluation needs to replay
  trajectories against executable environment state or produce reward labels
  beyond the repo-local episode-quality scoring report;
- Agentic RL needs reset/step/checkpoint/restore or rollout logging over the
  same environments used for synthesis;
- more domain environments or adapters start duplicating lifecycle,
  reset/checkpoint, or episode-log behavior beyond the contacts/mobile shared
  protocol;
- external MCP environment servers become an implementation target rather than
  a manifest-only compatibility contract.

Do not activate this plan merely to make the repository look modular. The split
is justified by consumer pressure, not by package aesthetics.

## Scope

- Define a narrow `EnvironmentRuntime` protocol or equivalent internal
  interface for environment identity, version, metadata, reset, checkpoint,
  restore, tool/action execution compatibility, and manifest export.
- Separate reusable runtime concepts from domain-specific environment packs:
  contacts remains a domain environment, not the runtime abstraction.
- Make the data synthesis pipeline depend on the runtime boundary instead of
  directly depending on contacts-specific implementation details where practical.
- Define an episode/transition log shape that can serve:
  - SFT-style accepted trajectory export;
  - reward-model scoring and pairwise or scalar quality labels;
  - Agentic RL rollout replay and debugging.
- Keep verifier and reward hooks attachable to environment state without making
  the runtime own dataset release, profile promotion, reward model training, or
  RL algorithms.
- Preserve source provenance, sandbox policy, environment version, reset recipe,
  and adapter lineage in runtime metadata.
- Document extraction criteria for when the internal runtime boundary is stable
  enough to become a separate project or package.

## Out of Scope

- Creating a separate repository or publishing a package during this plan.
- Rewriting the current contacts environment from scratch.
- Implementing reward model training, preference optimization, RL algorithms,
  distributed rollout workers, or GPU training infrastructure.
- Replacing the existing local MCP-compatible shim with an external MCP server.
- Changing dataset release admission, profile promotion, source governance, or
  quality-report decisions except where they consume runtime metadata.
- Treating AWM runtime success as proof of downstream model improvement.

## Architecture

The desired boundary is:

```text
environment pack -> EnvironmentRuntime -> tool/action adapter -> episode log
                                      -> verifier/reward hooks
                                      -> synthesis / quality / RL consumers
```

`EnvironmentRuntime` owns execution-facing environment lifecycle:

- identity and version metadata;
- deterministic reset or rebuild;
- checkpoint and restore;
- source provenance and sandbox/admission metadata;
- compatibility with typed tool/action adapters;
- transition or episode evidence emitted from interactions.

Domain environment packs own domain-specific state and rules:

- contacts schema and fixture/source input loading;
- future e-commerce, travel, support, file-system, browser, or other simulated
  worlds;
- domain-specific validators and business rules.

Consumers remain separate:

- data synthesis generates tasks, trajectories, accepted samples, and dataset
  manifests;
- reward/data-quality evaluation scores or compares existing trajectories;
- Agentic RL performs rollout collection and policy optimization;
- adapters expose runtime operations through local, MCP-compatible, or future
  service boundaries.

## File Map

- Modify `synthesis/environments.py` only as needed to introduce runtime-facing
  protocol types or to move contacts-specific behavior behind the boundary.
- Modify `synthesis/tools.py` so tool registries depend on runtime-compatible
  checkpoint/restore behavior rather than contacts-only assumptions.
- Modify `synthesis/mcp.py` to consume the runtime metadata contract instead of
  hard-coding more contacts-specific manifest behavior.
- Modify `synthesis/execution.py` and `synthesis/candidate_processing.py` only
  where execution should consume a runtime boundary or emit reusable episode
  events.
- Add tests that prove existing contacts synthesis behavior is unchanged after
  the boundary is introduced.
- Update [../../DESIGN.md](../../DESIGN.md),
  [../../DATA.md](../../DATA.md), [../../BACKEND.md](../../BACKEND.md), and
  [../../ROADMAP.md](../../ROADMAP.md) when the implementation activates.

## Implementation Tasks

### Task 1: Specify the Runtime Contract

- [ ] Add tests for a minimal runtime contract covering metadata, checkpoint,
  restore, rebuild/reset semantics, and source provenance.
- [ ] Define the contract in code using a `Protocol`, dataclass boundary, or
  small abstract type that does not import dataset assembly or profile logic.
- [ ] Adapt `ContactEnvironment` to satisfy the contract without changing its
  public behavior.
- [ ] Run contacts environment, MCP adapter, candidate isolation, and foundation
  pipeline tests to prove behavior is unchanged.

### Task 2: Separate Runtime Metadata From Dataset Metadata

- [ ] Identify metadata currently shared by environment, adapter, lineage,
  quality reports, and manifests.
- [ ] Keep environment identity, version, reset recipe, source provenance, and
  sandbox/admission metadata in runtime-owned records.
- [ ] Keep dataset version, sample/rejection artifacts, profile purpose,
  profile promotion, and release admission outside the runtime.
- [ ] Add contract tests that reject runtime records containing dataset-release
  or profile-decision fields.

### Task 3: Add a Reusable Episode Log Contract

- [ ] Define an episode/transition record shape with action/tool request,
  observation, side-effect summary, error classification, pre/post checkpoint or
  state reference, and runtime metadata.
- [ ] Map current trajectory execution events into the episode shape without
  changing exported sample semantics.
- [ ] Add tests showing the same episode record can support verifier checks and
  reward/data-quality scoring inputs.
- [ ] Keep raw prompts, provider headers, API keys, environment variables, and
  arbitrary source payloads out of episode exports.

### Task 4: Validate a Second Consumer Before Any Split

- [ ] Implement or prototype one second consumer against the runtime boundary:
  reward/data-quality replay, reward-label export, or Agentic RL rollout
  collection.
- [ ] Record which runtime methods the consumer needed and which proposed
  methods were unused.
- [ ] Remove unused runtime surface area before considering package extraction.
- [ ] Document whether the boundary is stable enough for a separate project.

### Task 5: Decide Whether to Extract a Separate Project

- [ ] Evaluate extraction only after data synthesis and at least one additional
  consumer both use the same runtime boundary.
- [ ] Require cross-consumer tests that run against the contacts environment and
  one additional environment or adapter shape.
- [ ] If extraction is justified, create a new plan for package/repository
  extraction, versioning, migration, and compatibility shims.
- [ ] If extraction is not justified, keep the runtime as an internal package
  boundary and revisit after the next consumer or domain environment lands.

## Validation

When activated, this plan must be validated with:

```bash
uv run python scripts/validate_docs.py
uv run python -m unittest tests.test_mcp_adapters tests.test_candidate_merge tests.test_candidate_processing tests.test_foundation_pipeline
```

Add focused tests for any new runtime contract or episode-log module introduced
by the implementation.

## Completion Criteria

- The current contacts environment still supports existing data synthesis
  workflows without behavior changes.
- The pipeline consumes a stable runtime boundary for environment lifecycle
  operations.
- Runtime metadata no longer carries dataset-release or profile-decision
  concerns.
- Episode logs are reusable by synthesis, reward/data-quality evaluation, and
  Agentic RL design without exporting secret or raw source material.
- A follow-up extraction decision is documented with evidence from at least two
  consumers.
