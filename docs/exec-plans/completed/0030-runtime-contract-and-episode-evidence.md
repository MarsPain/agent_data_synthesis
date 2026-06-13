# Plan 0030: Runtime Contract and Episode Evidence

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

## Status

Planned on 2026-06-13. Completed on 2026-06-13.

## Goal

Implement the first internal phase of the future AWM runtime boundary by making
environment lifecycle, runtime metadata, and episode evidence explicit across
the contacts and mobile domains without extracting a separate runtime package or
changing default dataset output semantics.

## Architecture

Plan 0029 introduced a second deterministic domain and proved that the
synchronous pipeline can run contacts and mobile through a shared domain bundle.
This plan tightens that internal boundary: domain environments satisfy a narrow
runtime protocol, runtime metadata is separated from dataset/release metadata,
and current trajectories can be converted into sanitized episode logs for
future replay, reward/data-quality scoring, or Agentic RL consumers.

The implementation remains repo-local. Data synthesis stays the only production
consumer in this plan; a small diagnostic episode-evidence builder may prove
that another consumer can read the contract, but reward model training, RL
rollout collection, external MCP servers, and package extraction remain out of
scope.

## Tech Stack

- Python standard library: `dataclasses`, `typing.Protocol`, `hashlib`,
  `json`, `pathlib`, and `unittest`.
- Existing modules: `synthesis.domain_pipeline`, `synthesis.environments`,
  `synthesis.mobile_environment`, `synthesis.tools`, `synthesis.mobile_tools`,
  `synthesis.execution`, `synthesis.candidate_processing`,
  `synthesis.datasets`, `synthesis.contracts`, `synthesis.verification`, and
  `main.py`.
- New focused modules:
  - `synthesis.runtime` for runtime protocols and metadata records.
  - `synthesis.episodes` for transition and episode evidence construction.
- Verification through `uv run python scripts/validate_docs.py` and
  `uv run python -m unittest`.

## Basis

- [../completed/0029-mobile-agent-second-domain-pipeline-probe.md](../completed/0029-mobile-agent-second-domain-pipeline-probe.md)
  added the `mobile_messages_fixture` domain and a minimal
  `DomainPipelineBundle`.
- [../../generated/mobile-domain-pipeline-pressure.md](../../generated/mobile-domain-pipeline-pressure.md)
  records the remaining pressure: `CandidateTask` still mixes intent,
  execution hints, expected answer, and expected state; MCP adapters and
  source-governed input are still contacts-only; the domain bundle is not yet an
  AWM runtime package.
- [../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md](../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md)
  defines the broader target: a shared runtime boundary with reset,
  checkpoint/restore, adapter compatibility, and episode evidence.
- [../../DESIGN.md](../../DESIGN.md) treats environment synthesis, tool
  registry, trajectory execution, verification, and dataset assembly as
  separate bounded contexts.

## Why This Plan Now

0029 satisfied one meaningful trigger from plan 0025: a second domain now
exercises the same pipeline. That is enough to stabilize the internal runtime
boundary, but not enough to split a runtime package or implement a second
production consumer.

The next useful step is therefore a controlled Phase 1:

- make the lifecycle contract explicit before more domains copy implicit
  methods;
- make runtime metadata inspectable and testable before release or profile
  metadata leaks into it;
- define sanitized episode evidence before reward/data-quality replay or RL
  asks for it under time pressure;
- keep async orchestration, semantic duplicate detection, external MCP
  environment servers, and full AWM extraction deferred until their own
  triggers are met.

## Scope

- Add an internal `EnvironmentRuntime` protocol covering identity, version,
  sanitized metadata, checkpoint, restore, rebuild/reset, and database-backed
  reset recipe semantics.
- Add `runtime_metadata_v1` as a small runtime-owned record distinct from
  dataset manifests, profile decisions, release reports, release packs, and
  release cards.
- Adapt `ContactEnvironment` and `MobileMessagesEnvironment` to satisfy the
  runtime protocol without changing their existing `metadata()`, checkpoint,
  restore, or rebuild behavior.
- Replace the local `PipelineEnvironment` protocol in
  `synthesis.domain_pipeline` with the shared runtime protocol.
- Add an `episode_log_v1` contract that maps existing execution trajectories
  into ordered transition records with action, observation, state-change,
  final-response, error, runtime metadata, and policy/verifier references.
- Add optional in-memory episode evidence construction for accepted samples and
  selected rejected attempts without changing the default sample schema.
- Add focused contract validation and redaction tests for runtime metadata and
  episode logs.
- Update canonical docs to describe the internal runtime boundary and the
  remaining criteria for completing full plan 0025.

## Out of Scope

- Creating a separate `awm_runtime` package or repository.
- Implementing reward model training, preference optimization, Agentic RL
  rollout collection, distributed workers, or GPU infrastructure.
- Replacing the local MCP-compatible contacts adapter with an external MCP
  environment server.
- Making mobile MCP adapters or mobile source-governed input available.
- Splitting `CandidateTask` into separate task-intent, policy-hint, expected
  answer, and expected-state records. This plan should document that pressure
  but not execute the schema migration.
- Changing dataset release admission, release pack verification, release
  quality audit behavior, profile promotion, held-out evaluation thresholds, or
  semantic duplicate detection.
- Changing default `uv run python main.py` artifacts unless explicitly needed
  to preserve existing contracts.

## Runtime Contract

Add `synthesis.runtime.EnvironmentRuntime` as the narrow internal protocol:

```python
class EnvironmentRuntime(Protocol):
    database_path: Path

    def metadata(self) -> EnvironmentMetadata: ...
    def runtime_metadata(self) -> RuntimeMetadata: ...
    def checkpoint(self) -> object: ...
    def restore_checkpoint(self, checkpoint: object) -> None: ...
    def rebuild(self, output_dir: Path) -> "EnvironmentRuntime": ...
```

`RuntimeMetadata` should export:

```json
{
  "schema_version": "runtime_metadata_v1",
  "runtime_id": "contacts_fixture",
  "runtime_version": "env_contacts_v1",
  "environment_id": "contacts_fixture",
  "environment_version": "env_contacts_v1",
  "reset_recipe": "sqlite_fixture:contacts",
  "state_backend": "sqlite",
  "checkpoint_strategy": "sqlite_backup",
  "source_provenance": {},
  "sandbox_policy": {},
  "adapter": {}
}
```

Rules:

- `source_provenance`, `sandbox_policy`, and `adapter` are optional sanitized
  mappings.
- Runtime metadata must not contain dataset version, profile purpose, profile
  promotion, dataset release status, release pack status, local profile paths,
  raw source payloads, provider prompts, provider payloads, headers, API keys,
  or environment variables.
- `metadata()` remains available for current sample assembly. New runtime-aware
  code should prefer `runtime_metadata()` when it needs lifecycle evidence.

## Episode Contract

Add `episode_log_v1` as an internal evidence record:

```json
{
  "schema_version": "episode_log_v1",
  "episode_id": "episode_sample_candidate_contacts_alice",
  "candidate_id": "candidate_contacts_alice",
  "runtime": {
    "schema_version": "runtime_metadata_v1",
    "runtime_id": "contacts_fixture",
    "runtime_version": "env_contacts_v1"
  },
  "policy": {
    "policy_id": "policy_candidate_contacts_alice",
    "role": "scripted_solution_policy"
  },
  "verifier": {
    "id": "exact_answer",
    "version": "exact_answer_v1"
  },
  "transitions": [
    {
      "transition_index": 1,
      "event_type": "action",
      "tool_name": "lookup_contact_email",
      "arguments_hash": "sha256:...",
      "arguments": {"name": "Alice Zhang"}
    },
    {
      "transition_index": 2,
      "event_type": "observation",
      "tool_name": "lookup_contact_email",
      "observation_hash": "sha256:...",
      "observation": {"email": "alice.zhang@example.test"}
    },
    {
      "transition_index": 3,
      "event_type": "final_response",
      "content_hash": "sha256:...",
      "content": "Alice Zhang's email is alice.zhang@example.test."
    }
  ],
  "outcome": {
    "status": "accepted",
    "failure_cause": null
  }
}
```

Rules:

- Transition hashes must be deterministic over sorted sanitized JSON.
- Accepted deterministic fixtures may keep the same sanitized arguments,
  observations, state-change summaries, and final-response content already
  present in sample trajectories.
- Episode logs must never include raw source payloads, local profile paths,
  provider prompts, provider payloads, headers, API keys, environment variables,
  or arbitrary host paths.
- Episode logs are not release artifacts in this plan. If persisted later, that
  must be a separate opt-in plan or a narrow follow-up.

## File Map

- Create `synthesis/runtime.py`:
  `RuntimeMetadata`, `EnvironmentRuntime`, `runtime_metadata_from_environment`,
  `validate_runtime_metadata_safety`, and export helpers.
- Create `synthesis/episodes.py`:
  `EpisodeTransition`, `EpisodeLog`, `build_episode_log`, deterministic hashing,
  trajectory-to-transition mapping, and redaction helpers.
- Modify `synthesis/environments.py`:
  add `runtime_metadata()` to `ContactEnvironment`; preserve existing
  `metadata()`, checkpoint, restore, and rebuild behavior.
- Modify `synthesis/mobile_environment.py`:
  add `runtime_metadata()` to `MobileMessagesEnvironment`; preserve existing
  SQLite fixture behavior.
- Modify `synthesis/domain_pipeline.py`:
  import `EnvironmentRuntime` from `synthesis.runtime` and remove the local
  `PipelineEnvironment` protocol.
- Modify `synthesis/contracts.py`:
  validate `runtime_metadata_v1` and `episode_log_v1`, including redaction
  guardrails and allowed status/event values.
- Modify `synthesis/candidate_processing.py`:
  build episode evidence inside `ProvisionalCandidateOutcome` only where it can
  be produced without changing existing sample/rejection shapes.
- Modify `synthesis/datasets.py` only if accepted sample assembly needs to pass
  runtime metadata into episode construction. Do not alter the default sample
  schema.
- Add `tests/test_runtime_contract.py`.
- Add `tests/test_episode_logs.py`.
- Extend `tests/test_mobile_pipeline.py` and
  `tests/test_foundation_pipeline.py` only for runtime-boundary regression
  coverage.
- Update [../../DESIGN.md](../../DESIGN.md),
  [../../DATA.md](../../DATA.md), [../../BACKEND.md](../../BACKEND.md),
  [../../ROADMAP.md](../../ROADMAP.md), and
  [../../generated/mobile-domain-pipeline-pressure.md](../../generated/mobile-domain-pipeline-pressure.md).

## Implementation Tasks

### Task 1: Add Runtime Contract Tests

- [x] Add `tests/test_runtime_contract.py`.
- [x] Test that `ContactEnvironment.create_fixture(tmp_path)` exposes
  `runtime_metadata()` with `schema_version: runtime_metadata_v1`,
  `runtime_id: contacts_fixture`, `state_backend: sqlite`, and no absolute
  database path.
- [x] Test that `MobileMessagesEnvironment.create_fixture(tmp_path)` exposes
  `runtime_metadata()` with `runtime_id: mobile_messages_fixture`,
  `state_backend: sqlite`, and no real-device data claims.
- [x] Test checkpoint/restore/rebuild through the shared runtime protocol for
  both domains.
- [x] Test that runtime metadata validation rejects dataset-release,
  profile-decision, local-path, prompt, header, API key, and environment-variable
  fields.
- [x] Run `uv run python -m unittest tests.test_runtime_contract` and confirm
  the tests fail before implementation.

### Task 2: Implement `synthesis.runtime`

- [x] Create `synthesis/runtime.py`.
- [x] Define immutable `RuntimeMetadata` with an `export()` method.
- [x] Define `EnvironmentRuntime` as a `Protocol` with the methods listed in
  this plan.
- [x] Add `runtime_metadata_from_environment(...)` for common conversion from
  existing `EnvironmentMetadata`.
- [x] Add `validate_runtime_metadata_safety(record)` to reject forbidden keys
  recursively.
- [x] Add `runtime_metadata()` methods to `ContactEnvironment` and
  `MobileMessagesEnvironment`.
- [x] Run `uv run python -m unittest tests.test_runtime_contract` and confirm it
  passes.

### Task 3: Move Domain Pipeline to the Shared Runtime Protocol

- [x] Modify `synthesis/domain_pipeline.py` to import `EnvironmentRuntime`.
- [x] Remove the local `PipelineEnvironment` protocol.
- [x] Type `RegistryBuilder` and `DomainPipelineBundle.environment` against
  `EnvironmentRuntime`.
- [x] Preserve contacts and mobile bundle behavior exactly.
- [x] Run:

```bash
uv run python -m unittest tests.test_mobile_pipeline tests.test_foundation_pipeline tests.test_candidate_processing
```

- [x] Confirm default contacts output remains contacts-only and the mobile
  profile still uses `mobile_messages_fixture`.

### Task 4: Add Runtime Metadata and Episode Contract Validators

- [x] Modify `synthesis/contracts.py`.
- [x] Add `validate_runtime_metadata_record(record)` with strict allowed
  top-level keys and required fields.
- [x] Add `validate_episode_log_record(record)` with strict event type,
  transition index, hash, runtime, policy, verifier, and outcome checks.
- [x] Reject unsupported episode outcomes. Allowed values are `accepted`,
  `rejected`, and `failed`.
- [x] Reject unsupported transition event types. Allowed values are `action`,
  `observation`, `state_change`, `final_response`, and `error`.
- [x] Extend `tests/test_runtime_contract.py` and add early
  `tests/test_episode_logs.py` contract tests.
- [x] Run:

```bash
uv run python -m unittest tests.test_contracts tests.test_runtime_contract tests.test_episode_logs
```

### Task 5: Implement Episode Evidence Builder

- [x] Create `synthesis/episodes.py`.
- [x] Define immutable `EpisodeTransition` and `EpisodeLog` records with
  `export()` methods.
- [x] Implement deterministic `sha256:` hashing over sanitized sorted JSON.
- [x] Implement `build_episode_log(...)` from candidate id, runtime metadata,
  policy, verifier, execution trajectory, and accepted/rejected outcome.
- [x] Map existing trajectory events:
  - `action` to action transitions with sanitized arguments and argument hash;
  - `observation` to observation transitions with sanitized observation and
    observation hash;
  - `state_change` to state-change transitions with sanitized change and hash;
  - `final_response` to final-response transitions with content and content
    hash.
- [x] Add redaction tests proving episode exports exclude local paths, source
  paths, prompts, headers, API keys, provider payloads, and environment
  variables.
- [x] Run `uv run python -m unittest tests.test_episode_logs`.

### Task 6: Attach Episode Evidence Internally Without Changing Sample Schema

- [x] Extend `ProvisionalCandidateOutcome` in
  `synthesis.candidate_processing` with an optional
  `episode_log: dict[str, object] | None = None`.
- [x] Build an accepted episode log after verification succeeds and sample
  assembly has enough policy/verifier/runtime context.
- [x] Build rejected episode logs only for execution attempts that have a
  trajectory available without requiring new execution side effects. If a
  rejection has no trajectory, leave `episode_log` unset.
- [x] Ensure `merge_candidate_outcomes()` continues to sort and admit samples
  exactly as before.
- [x] Do not write `episode_log` into `samples.jsonl`, `rejections.jsonl`, or
  `manifest.json` in this plan.
- [x] Add tests proving accepted contacts and mobile candidates produce internal
  episode logs while exported sample JSON remains byte-shape compatible with the
  existing sample contract.
- [x] Run:

```bash
uv run python -m unittest tests.test_candidate_processing tests.test_mobile_pipeline tests.test_foundation_pipeline
```

### Task 7: Add a Diagnostic Episode Evidence Reader

- [x] Add a small test-only or module-level helper in `synthesis.episodes` named
  `summarize_episode_for_quality(record)`.
- [x] The helper should read `episode_log_v1` and return deterministic counts:
  action count, observation count, state-change count, final-response count,
  tool names, runtime id, and outcome status.
- [x] This helper is the diagnostic second-consumer probe for the contract. It
  must not train a reward model, run an RL loop, or write release artifacts.
- [x] Add tests showing the helper works for contacts and mobile episode logs
  without importing dataset release, profile decision, or run-profile modules.
- [x] Document that this is evidence-reader pressure only, not sufficient to
  complete full plan 0025 Task 4.

### Task 8: Update Canonical Docs and Plan State

- [x] Update [../../DESIGN.md](../../DESIGN.md) to describe the internal
  runtime boundary between domain packs and trajectory execution.
- [x] Update [../../DATA.md](../../DATA.md) with `runtime_metadata_v1` and
  `episode_log_v1` contracts and redaction rules.
- [x] Update [../../BACKEND.md](../../BACKEND.md) to state that runtime
  contract and episode evidence are local synchronous behavior, while async
  orchestration remains deferred.
- [x] Update [../../ROADMAP.md](../../ROADMAP.md) to mark plan 0030 as the
  narrow internal Phase 1 before full AWM runtime extraction.
- [x] Update [../../generated/mobile-domain-pipeline-pressure.md](../../generated/mobile-domain-pipeline-pressure.md)
  with which 0029 pressures were resolved by 0030 and which remain for future
  plans.
- [x] Keep [../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md](../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md)
  deferred unless a real replay, reward/data-quality, RL, or external MCP
  environment consumer is implemented.

### Task 9: Full Validation

- [x] Run documentation validation:

```bash
uv run python scripts/validate_docs.py
```

- [x] Run focused runtime and episode tests:

```bash
uv run python -m unittest tests.test_runtime_contract tests.test_episode_logs
```

- [x] Run affected pipeline tests:

```bash
uv run python -m unittest tests.test_candidate_processing tests.test_mobile_pipeline tests.test_foundation_pipeline tests.test_mcp_adapters tests.test_cli
```

- [x] Run the full suite:

```bash
uv run python -m unittest
```

- [x] Run the mobile profile command:

```bash
uv run python main.py --run-profile tests/fixtures/run_profiles/mobile-agent-fixture.json --output-dir artifacts/mobile-agent-fixture
```

- [x] Inspect the mobile artifacts for unchanged public output: mobile samples
  still carry `environment.id: mobile_messages_fixture`, mobile tools, accepted
  reminder/draft state changes, and no real-device data.

## Validation

This plan is complete only after these commands pass:

```bash
uv run python scripts/validate_docs.py
uv run python -m unittest tests.test_runtime_contract tests.test_episode_logs
uv run python -m unittest tests.test_candidate_processing tests.test_mobile_pipeline tests.test_foundation_pipeline tests.test_mcp_adapters tests.test_cli
uv run python -m unittest
uv run python main.py --run-profile tests/fixtures/run_profiles/mobile-agent-fixture.json --output-dir artifacts/mobile-agent-fixture
```

## Acceptance Criteria

- `ContactEnvironment` and `MobileMessagesEnvironment` both satisfy the same
  internal `EnvironmentRuntime` protocol.
- Runtime metadata is sanitized, contract-validated, and free of dataset release,
  profile decision, raw source, prompt, credential, and host-path fields.
- `synthesis.domain_pipeline` depends on the shared runtime protocol rather than
  a local contacts/mobile placeholder protocol.
- Accepted contacts and mobile executions can produce validated internal
  `episode_log_v1` records from existing trajectories.
- Episode evidence can be summarized by a diagnostic reader that does not import
  dataset release, profile decision, or run-profile modules.
- Default public artifacts remain unchanged unless a future plan explicitly
  adds opt-in episode-log persistence.
- Full plan 0025 remains deferred until a real replay, reward/data-quality,
  Agentic RL, or external MCP environment consumer uses the same boundary.
- Documentation validation and the full unit suite pass.

## Risks

- Runtime metadata can become a dumping ground for dataset decisions. Keep the
  validator strict and reject profile/release fields.
- Episode logs can accidentally duplicate sensitive trajectory material. Reuse
  only fields already allowed in sanitized samples and add explicit redaction
  tests.
- A diagnostic episode reader can be mistaken for a real second consumer. Name
  it and document it as evidence-reader pressure only.
- Generalizing too aggressively can turn this into full 0025. Keep package
  extraction, RL, external MCP servers, and mobile source ingestion out of this
  plan.
- Changing `ProvisionalCandidateOutcome` can disturb deterministic merge order.
  Add regression tests around sequence ordering and duplicate admission.
