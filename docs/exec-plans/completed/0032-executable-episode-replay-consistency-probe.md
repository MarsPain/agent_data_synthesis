# Plan 0032: Executable Episode Replay Consistency Probe

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

## Status

Planned on 2026-06-13. Completed on 2026-06-13.

## Goal

Add an opt-in executable episode replay consumer that rebuilds contacts and
mobile runtimes from `episode_log_v1`, re-executes action transitions through
the runtime tool registry, and writes a sanitized `episode_replay_report.json`
without changing default dataset outputs or extracting an `awm_runtime` package.

## Architecture

Plan 0030 created the internal runtime contract and `episode_log_v1`. Plan 0031
added a non-executing data-quality consumer that validates and scores episode
evidence. This plan adds a stronger, execution-facing consumer: replay accepted
and rejected executable episodes against a fresh runtime and compare replayed
observations/state changes with the original episode evidence.

The replay consumer remains repo-local and synchronous. It must depend on
`synthesis.runtime`, `synthesis.episodes`, `synthesis.episode_quality`, and
`synthesis.domain_pipeline`, not on dataset release admission, profile
promotion, reward training, Agentic RL, async orchestration, or a separate
runtime package. Its job is to produce concrete package-boundary evidence for
deferred plan 0025 by showing which runtime methods an execution consumer needs.

## Tech Stack

- Python standard library: `dataclasses`, `json`, `pathlib`, `collections`,
  and `unittest`.
- Existing modules: `synthesis.episodes`, `synthesis.episode_quality`,
  `synthesis.runtime`, `synthesis.domain_pipeline`, `synthesis.contracts`,
  `synthesis.pipeline`, `synthesis.datasets`, `synthesis.seeds`,
  `synthesis.tasks`, `synthesis.mobile_tasks`, and `main.py`.
- New focused module: `synthesis.episode_replay` for replay execution, report
  construction, report writing, and sanitized replay summaries.
- Verification through `uv run python scripts/validate_docs.py` and
  `uv run python -m unittest`.

## Basis

- [../completed/0030-runtime-contract-and-episode-evidence.md](../completed/0030-runtime-contract-and-episode-evidence.md)
  added `runtime_metadata_v1`, shared contacts/mobile runtime protocol
  coverage, and sanitized `episode_log_v1` evidence.
- [../completed/0031-episode-replay-and-data-quality-scoring-consumer.md](../completed/0031-episode-replay-and-data-quality-scoring-consumer.md)
  added opt-in `episodes.jsonl` export and `episode_quality_report_v1` scoring,
  but explicitly excluded replaying actions against fresh runtime state.
- [../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md](../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md)
  keeps AWM runtime extraction deferred until stronger replay, reward/RL,
  external MCP, or cross-consumer package-boundary pressure appears.
- [../../generated/mobile-domain-pipeline-pressure.md](../../generated/mobile-domain-pipeline-pressure.md)
  records that executable replay, reward-label export, Agentic RL rollout
  collection, external MCP environment servers, mobile source-governed input,
  and the `CandidateTask` split remain unresolved.
- [../../DESIGN.md](../../DESIGN.md) separates environment synthesis, tool
  registry, trajectory execution, verification, dataset assembly, and runtime
  lifecycle evidence as bounded contexts.

## Why This Plan Now

The project is intentionally moving toward an AWM runtime split, but plan 0025
warns against physical extraction without real consumer pressure. `episode
quality` proved that another module can read the evidence contract; it did not
prove that another module can execute against the runtime contract.

Executable replay is the narrowest useful pressure test:

- it checks that `episode_log_v1` carries enough action evidence to re-run tools
  against fresh contacts/mobile runtime state;
- it checks that runtime reset/rebuild and registry construction are reusable by
  a non-synthesis consumer;
- it identifies whether observation hashes and state-change hashes remain stable
  under replay;
- it records which runtime methods are actually used before a future
  `awm_runtime` extraction plan;
- it keeps reward labels, RL rollout collection, external MCP servers, async
  orchestration, semantic duplicate detection, and package extraction deferred.

## Scope

- Add `episode_replay_report_v1` as an opt-in artifact.
- Add `synthesis.episode_replay` with deterministic replay over existing
  `episode_log_v1` records.
- Reuse `episodes.jsonl` from plan 0031. When replay is requested from the CLI,
  request pipeline episode export in the same way episode-quality reporting
  already does.
- Rebuild a fresh domain runtime for each replayed episode based on
  `runtime.runtime_id`.
- Replay only `action` transitions. Ignore original `observation`,
  `state_change`, and `final_response` transitions as commands, but compare
  replayed evidence against them.
- Execute replay through the selected domain bundle's `ToolRegistry.execute()`.
- Compare:
  - replay action availability;
  - replay execution success;
  - observation hash consistency for the next matching observation transition
    with the same tool name;
  - state-change hash consistency for state-changing tools when the original
    episode contains a matching `state_change` transition;
  - final-response presence for accepted episodes without trying to regenerate
    model text.
- Add report decisions:
  - `passed`: all replayed episodes pass required checks;
  - `watch`: optional evidence checks fail while replay execution succeeds;
  - `failed`: required replay execution or contract checks fail;
  - `insufficient_evidence`: no episode logs are available.
- Attach `episode_replay_report` and `episodes` artifact names to the manifest
  only when the opt-in replay report is written.
- Update canonical docs and plan indexes to record that executable replay is an
  AWM runtime extraction evidence step, not full runtime extraction.

## Out of Scope

- Creating a separate `awm_runtime` package or repository.
- Reward model training, scalar reward fitting, pairwise preference generation,
  PPO/DPO/GRPO, or Agentic RL rollout collection.
- Treating replay success as downstream model-quality proof.
- Making `episode_replay_report.json` a dataset release admission gate.
- Replaying through external MCP environment servers.
- Replaying network-source or profile-local contacts inputs from raw source
  payloads. This plan should use fixture-backed runtime reset recipes only.
- Splitting `CandidateTask` into separate task-intent, policy-hint,
  expected-answer, and expected-state records.
- Implementing semantic duplicate detection from `TD-0002`.
- Adding async queues, cancellation, resumption, or per-role cost tracking from
  plan 0014.

## Contracts

### Replay Inputs

Replay consumes validated `episode_log_v1` records from `episodes.jsonl`.

Rules:

- The replay module must call `validate_episode_log_record()` before replaying
  each record.
- Supported `runtime.runtime_id` values are `contacts_fixture` and
  `mobile_messages_fixture`.
- Unsupported runtimes must not crash the whole report; they produce a failed
  episode summary with `runtime_supported`.
- Replay uses fixture reset recipes only. It must not fetch network sources,
  read profile-local source paths, or reconstruct environments from raw source
  payloads.
- Replay must not execute original final-response text, verifier metadata,
  provider prompts, provider payloads, credentials, or source payloads.

### `episode_replay_report.json`

Expected shape:

```json
{
  "schema_version": "episode_replay_report_v1",
  "dataset_version": "dataset_foundation_v1",
  "inputs": {
    "manifest_path": "manifest.json",
    "episodes_path": "episodes.jsonl"
  },
  "observed": {
    "episode_count": 3,
    "replayed": 3,
    "runtime_counts": {
      "contacts_fixture": 2,
      "mobile_messages_fixture": 1
    },
    "tool_names": ["lookup_contact_email", "create_phone_reminder"]
  },
  "checks": [
    {
      "name": "contract_valid",
      "status": "passed",
      "passed": 3,
      "failed": 0,
      "required": true
    }
  ],
  "episode_summaries": [
    {
      "episode_id": "episode_sample_candidate_contacts_alice",
      "candidate_id": "candidate_contacts_alice",
      "runtime_id": "contacts_fixture",
      "outcome_status": "accepted",
      "action_count": 1,
      "replayed_action_count": 1,
      "observation_match_count": 1,
      "observation_mismatch_count": 0,
      "state_change_match_count": 0,
      "state_change_mismatch_count": 0,
      "final_response_count": 1,
      "tool_names": ["lookup_contact_email"],
      "failed_checks": []
    }
  ],
  "runtime_boundary_evidence": {
    "runtime_methods_used": ["rebuild", "runtime_metadata"],
    "registry_methods_used": ["execute"],
    "requires_external_package": false,
    "extraction_signal": "internal_boundary_sufficient"
  },
  "decision": {
    "status": "passed",
    "reasons": [],
    "triggered_by": []
  }
}
```

Validation rules:

- `schema_version` must be `episode_replay_report_v1`.
- `decision.status` must be one of `passed`, `watch`, `failed`, or
  `insufficient_evidence`.
- `inputs` paths must be relative artifact names, not absolute host paths.
- `runtime_boundary_evidence.runtime_methods_used` and
  `registry_methods_used` must contain fixed allowlist values only.
- `episode_summaries` may include ids, counts, runtime ids, outcome status,
  tool names, and failed check names only. They must not include raw
  instructions, arguments, observations, final responses, source payloads,
  provider payloads, prompts, credentials, or host paths.
- `checks[].name` must come from a fixed allowlist.
- The manifest may reference `episode_replay_report` only when the report is
  explicitly written.

## Check Semantics

Required checks:

- `contract_valid`: every replayed episode satisfies `episode_log_v1`.
- `runtime_supported`: runtime id maps to a known fixture domain.
- `runtime_rebuilt`: a fresh runtime bundle can be built for replay.
- `actions_replayed`: every action transition executes successfully.
- `accepted_has_final_response`: accepted episodes contain exactly one original
  final-response transition.

Optional diagnostic checks:

- `observation_hash_match`: replayed observation hashes match original
  observation hashes for corresponding action/observation pairs.
- `state_change_hash_match`: replayed state-change hashes match original
  state-change hashes for state-changing tools.
- `runtime_metadata_stable`: fresh runtime metadata id/version match the
  episode runtime id/version.

Decision rules:

- No episodes means `insufficient_evidence`.
- Any required check failure means `failed`.
- Required checks passing with optional failures means `watch`.
- All checks passing means `passed`.

## File Map

- Create `synthesis/episode_replay.py`:
  `EPISODE_REPLAY_REPORT_FILENAME`, `EpisodeReplayThresholds`,
  `build_episode_replay_report`, `write_episode_replay_report`,
  `replay_episode`, runtime selection helpers, transition matching helpers, and
  sanitized report helpers.
- Modify `synthesis/contracts.py`:
  add `EPISODE_REPLAY_DECISION_STATUSES`,
  `EPISODE_REPLAY_CHECK_NAMES`,
  `EPISODE_REPLAY_RUNTIME_METHODS`,
  `EPISODE_REPLAY_REGISTRY_METHODS`,
  `validate_episode_replay_report_record`, and manifest artifact key
  `episode_replay_report`.
- Modify `synthesis/datasets.py`:
  add `attach_episode_replay_report_to_manifest(...)`.
- Modify `main.py`:
  add `--write-episode-replay-report`; when enabled, request pipeline episode
  export, read `episodes.jsonl`, write `episode_replay_report.json`, attach
  `episodes` and `episode_replay_report` to the manifest, and print the report
  path.
- Modify `synthesis/episode_quality.py` only if common JSONL helpers need to be
  reused without importing quality scoring decisions into replay. Prefer
  importing `read_episode_logs` from `synthesis.episode_quality` to avoid
  duplicate JSONL parsing.
- Add `tests/test_episode_replay.py`.
- Extend `tests/test_contracts.py`, `tests/test_cli.py`,
  `tests/test_foundation_pipeline.py`, and `tests/test_mobile_pipeline.py`.
- Update [../../DATA.md](../../DATA.md), [../../DESIGN.md](../../DESIGN.md),
  [../../BACKEND.md](../../BACKEND.md), [../../ROADMAP.md](../../ROADMAP.md),
  [../../generated/mobile-domain-pipeline-pressure.md](../../generated/mobile-domain-pipeline-pressure.md),
  [../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md](../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md),
  [README.md](README.md), and [../../PLANS.md](../../PLANS.md).

## Implementation Tasks

### Task 1: Add Replay Report Contract Tests

- [x] Add `tests/test_episode_replay.py`.
- [x] Build helper `_episode(candidate_id: str)` by following
  `tests/test_episode_quality.py`: create the proper domain bundle, select the
  matching deterministic candidate, execute its scripted policy, and call
  `build_episode_log(...).export()`.
- [x] Add `test_builds_passed_replay_report_for_contacts_lookup`.
  Expected assertions:
  - `schema_version == "episode_replay_report_v1"`;
  - `observed.episode_count == 1`;
  - `observed.replayed == 1`;
  - first summary has `runtime_id == "contacts_fixture"`;
  - first summary has `replayed_action_count == 1`;
  - first summary has `observation_mismatch_count == 0`;
  - `decision.status == "passed"`.
- [x] Add `test_mobile_state_change_replay_matches_state_change_evidence`.
  Use `candidate_mobile_maya_reminder` and assert:
  - `runtime_id == "mobile_messages_fixture"`;
  - `state_change_match_count == 1`;
  - `state_change_mismatch_count == 0`;
  - `decision.status == "passed"`.
- [x] Add `test_missing_episodes_returns_insufficient_evidence`.
  Call `build_episode_replay_report(dataset_version="dataset_empty",
  episodes=())` and assert `decision.status == "insufficient_evidence"`.
- [x] Add `test_replay_report_contract_rejects_raw_content_and_absolute_paths`.
  Mutate a valid report with `inputs.episodes_path = "/tmp/episodes.jsonl"` and
  with `episode_summaries[0]["arguments"] = {"name": "Alice Zhang"}`; both must
  raise `ContractValidationError`.
- [x] Run:

```bash
uv run python -m unittest tests.test_episode_replay
```

- [x] Confirm tests fail because `synthesis.episode_replay` and the report
  contract do not exist yet.

### Task 2: Add Replay Report Contracts

- [x] Modify `synthesis/contracts.py`.
- [x] Add:

```python
EPISODE_REPLAY_DECISION_STATUSES = {
    "passed",
    "watch",
    "failed",
    "insufficient_evidence",
}
EPISODE_REPLAY_CHECK_NAMES = {
    "contract_valid",
    "runtime_supported",
    "runtime_rebuilt",
    "actions_replayed",
    "accepted_has_final_response",
    "observation_hash_match",
    "state_change_hash_match",
    "runtime_metadata_stable",
}
EPISODE_REPLAY_RUNTIME_METHODS = {"rebuild", "runtime_metadata"}
EPISODE_REPLAY_REGISTRY_METHODS = {"execute"}
```

- [x] Add `"episode_replay_report"` to `MANIFEST_ARTIFACT_KEYS`.
- [x] Add `validate_episode_replay_report_record(record)` that mirrors
  `validate_episode_quality_report_record` but validates the replay-specific
  fields, check-name allowlist, summary allowlist, and
  `runtime_boundary_evidence`.
- [x] Summary allowed keys must be exactly:

```python
{
    "episode_id",
    "candidate_id",
    "runtime_id",
    "outcome_status",
    "action_count",
    "replayed_action_count",
    "observation_match_count",
    "observation_mismatch_count",
    "state_change_match_count",
    "state_change_mismatch_count",
    "final_response_count",
    "tool_names",
    "failed_checks",
}
```

- [x] Run:

```bash
uv run python -m unittest tests.test_episode_replay tests.test_contracts
```

- [x] Confirm replay tests still fail only because the replay builder is not
  implemented.

### Task 3: Implement `synthesis.episode_replay`

- [x] Create `synthesis/episode_replay.py`.
- [x] Add constants:

```python
EPISODE_REPLAY_REPORT_FILENAME = "episode_replay_report.json"
SUPPORTED_REPLAY_RUNTIMES = frozenset({"contacts_fixture", "mobile_messages_fixture"})
STATE_CHANGING_TOOLS = frozenset(
    {"record_contact_followup", "create_phone_reminder", "draft_message_reply"}
)
```

- [x] Add `EpisodeReplayThresholds` with required checks:

```python
_REQUIRED_CHECKS = frozenset(
    {
        "contract_valid",
        "runtime_supported",
        "runtime_rebuilt",
        "actions_replayed",
        "accepted_has_final_response",
    }
)
```

- [x] Implement runtime selection with fixture seeds:

```python
def _seed_for_runtime(runtime_id: str) -> DomainSeed:
    if runtime_id == "contacts_fixture":
        return foundation_seed()
    if runtime_id == "mobile_messages_fixture":
        return DomainSeed(
            seed_id="seed_mobile_messages_v1",
            domain="mobile_messages_fixture",
            description="Synthetic phone messages, reminders, and draft replies.",
            task_taxonomy=(
                "mobile_message_lookup",
                "mobile_message_to_reminder",
                "mobile_draft_reply",
                "mobile_branch_fallback",
            ),
        )
    raise ValueError(f"unsupported replay runtime: {runtime_id}")
```

- [x] Implement `replay_episode(record, replay_root)`:
  - validate the record;
  - create a fresh bundle under `replay_root / candidate_id`;
  - iterate action transitions in order;
  - call `bundle.registry.execute(tool_name, dict(arguments))`;
  - hash replay observations with
    `synthesis.episodes.deterministic_content_hash`;
  - compare against the next original observation transition for the same tool;
  - compare state-changing tool results against the next original
    `state_change` transition for the same tool when present;
  - return a sanitized summary and failed-check list.
- [x] Implement `build_episode_replay_report(...)` with the contract shape above
  and call `validate_episode_replay_report_record(report)` before returning.
- [x] Implement `write_episode_replay_report(path, *, dataset_version, episodes,
  manifest_path=None, episodes_path=None)` that writes sorted, indented JSON and
  returns the path.
- [x] Ensure summaries never include raw arguments, observations, final response
  content, prompts, provider payloads, source payloads, credentials, or host
  paths.
- [x] Run:

```bash
uv run python -m unittest tests.test_episode_replay
```

- [x] Confirm contacts and mobile replay tests pass.

### Task 4: Attach Replay Artifacts to CLI and Manifest

- [x] Modify `synthesis/datasets.py` to add:

```python
def attach_episode_replay_report_to_manifest(
    *,
    manifest_path: Path,
    report_path: Path,
) -> None:
    _attach_artifact_to_manifest(
        manifest_path=manifest_path,
        artifact_key="episode_replay_report",
        artifact_path=report_path,
    )
```

- [x] Modify `main.py` imports:
  - import `attach_episode_replay_report_to_manifest`;
  - import `EPISODE_REPLAY_REPORT_FILENAME` and
    `write_episode_replay_report`.
- [x] Add CLI flag:

```python
parser.add_argument(
    "--write-episode-replay-report",
    action="store_true",
    help="Write episode_replay_report.json by replaying sanitized episode logs against fresh runtimes.",
)
```

- [x] In `run_foundation_pipeline(...)`, request episode export when either
  episode-quality or episode-replay reporting is enabled:

```python
write_episode_logs=(
    args.write_episode_quality_report
    or args.write_episode_replay_report
),
```

- [x] After the episode-quality block, add replay report writing:

```python
episode_replay_report_path = None
if args.write_episode_replay_report:
    assert result.episode_logs_path is not None
    episodes = read_episode_logs(result.episode_logs_path)
    episode_replay_report_path = result.manifest_path.parent / EPISODE_REPLAY_REPORT_FILENAME
    episode_replay_report_path = write_episode_replay_report(
        episode_replay_report_path,
        dataset_version=args.dataset_version,
        episodes=episodes,
        manifest_path=result.manifest_path,
        episodes_path=result.episode_logs_path,
    )
    attach_episodes_to_manifest(
        manifest_path=result.manifest_path,
        episodes_path=result.episode_logs_path,
    )
    attach_episode_replay_report_to_manifest(
        manifest_path=result.manifest_path,
        report_path=episode_replay_report_path,
    )
```

- [x] Extend final stdout printing to include
  `episode_replay_report=<path>` when the report is written.
- [x] Run:

```bash
uv run python -m unittest tests.test_cli
```

- [x] Confirm CLI tests pass after adding test coverage in Task 5.

### Task 5: Add Pipeline and CLI Coverage

- [x] Extend `tests/test_cli.py` with
  `test_main_can_write_episode_replay_report`.
  Run `main.py` with:

```bash
uv run python main.py --write-episode-replay-report --output-dir <tmpdir> --dataset-version dataset_cli_episode_replay
```

  Assert:
  - `episodes.jsonl` exists;
  - `episode_replay_report.json` exists;
  - manifest artifacts include `episodes == "episodes.jsonl"`;
  - manifest artifacts include
    `episode_replay_report == "episode_replay_report.json"`;
  - stdout contains `episode_replay_report=`.
- [x] Extend `tests/test_cli.py` with
  `test_mobile_profile_can_write_episode_replay_report`.
  Use the existing mobile run-profile fixture pattern from the
  episode-quality CLI test and assert report decision is `passed`.
- [x] Extend `tests/test_foundation_pipeline.py` to verify default runs still do
  not write `episode_replay_report.json`.
- [x] Extend `tests/test_mobile_pipeline.py` to verify replay report generation
  from mobile episode logs covers at least one state-changing tool.
- [x] Run:

```bash
uv run python -m unittest tests.test_episode_replay tests.test_cli tests.test_foundation_pipeline tests.test_mobile_pipeline
```

- [x] Confirm all focused tests pass.

### Task 6: Update Canonical Docs

- [x] Update [../../DATA.md](../../DATA.md):
  document `episode_replay_report_v1`, opt-in artifact behavior, safe summary
  fields, and manifest attachment key.
- [x] Update [../../DESIGN.md](../../DESIGN.md):
  document replay as the first execution-facing runtime/episode consumer after
  episode-quality scoring.
- [x] Update [../../BACKEND.md](../../BACKEND.md):
  document that replay remains synchronous and local, and that async
  orchestration remains deferred.
- [x] Update [../../ROADMAP.md](../../ROADMAP.md):
  record plan 0032 as active or completed depending on final implementation
  state.
- [x] Update [../../generated/mobile-domain-pipeline-pressure.md](../../generated/mobile-domain-pipeline-pressure.md):
  record which replay pressure is resolved and which pressures remain:
  reward-label export, Agentic RL rollout collection, external MCP servers,
  mobile source-governed input, and the `CandidateTask` split.
- [x] Update [../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md](../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md):
  state that plan 0032 supplies execution-facing consumer evidence, but that
  package extraction remains deferred until reward/RL, external MCP, or clearer
  cross-consumer package-boundary pressure appears.
- [x] Update [README.md](README.md) and [../../PLANS.md](../../PLANS.md) for plan
  lifecycle state.
- [x] Run:

```bash
uv run python scripts/validate_docs.py
```

- [x] Confirm documentation validation passes.

### Task 7: Full Verification and Completion

- [x] Run the focused report command:

```bash
uv run python main.py --write-episode-replay-report --output-dir artifacts/foundation-episode-replay
```

- [x] Inspect `artifacts/foundation-episode-replay/episode_replay_report.json`
  and confirm:
  - `schema_version == "episode_replay_report_v1"`;
  - `decision.status == "passed"`;
  - no summary contains `arguments`, `observation`, `content`, `instruction`,
    `final_response`, source payloads, provider payloads, credentials, or host
    paths.
- [x] Run the mobile profile command:

```bash
uv run python main.py --run-profile tests/fixtures/run_profiles/mobile-fixture-smoke.json --write-episode-replay-report --output-dir artifacts/mobile-episode-replay
```

- [x] Confirm mobile replay report includes `mobile_messages_fixture` and at
  least one state-changing tool.
- [x] Run:

```bash
uv run python -m unittest
uv run python scripts/validate_docs.py
```

- [x] If all checks pass, move this plan to `../completed/`, mark the completion
  date in this file and [../../PLANS.md](../../PLANS.md), and update
  [README.md](README.md) to keep the active/completed plan map current.

## Validation

- `uv run python -m unittest tests.test_episode_replay`
- `uv run python -m unittest tests.test_episode_replay tests.test_cli tests.test_foundation_pipeline tests.test_mobile_pipeline`
- `uv run python main.py --write-episode-replay-report --output-dir artifacts/foundation-episode-replay`
- `uv run python main.py --run-profile tests/fixtures/run_profiles/mobile-fixture-smoke.json --write-episode-replay-report --output-dir artifacts/mobile-episode-replay`
- `uv run python -m unittest`
- `uv run python scripts/validate_docs.py`

## Acceptance Criteria

- Default `uv run python main.py` writes no episode replay artifacts.
- `--write-episode-replay-report` writes `episodes.jsonl` and
  `episode_replay_report.json`, then attaches both to the manifest.
- Replay rebuilds fresh contacts and mobile fixture runtimes from supported
  runtime ids and executes action transitions through `ToolRegistry.execute()`.
- Accepted contacts and mobile fixture episodes replay successfully with
  matching observations and state-change evidence.
- Replay summaries contain only sanitized ids, counts, runtime/outcome fields,
  tool names, and failed check names.
- Replay report contracts reject absolute paths, raw arguments, observations,
  final-response content, source payloads, provider payloads, prompts,
  credentials, and host paths.
- `runtime_boundary_evidence` records the runtime and registry methods actually
  used and keeps `requires_external_package` false.
- Plan 0025 remains deferred after this plan unless a separate extraction
  decision plan finds stronger reward/RL, external MCP, or package-boundary
  pressure.
- Documentation validation and the unit suite pass.

## Risks

- Replay can be mistaken for reward evaluation. Keep the report name and docs
  focused on execution consistency, not model quality.
- Replaying from fixture reset recipes can hide source-governed environment
  gaps. Keep source replay out of scope and document that limitation.
- Observation matching can become brittle if tool outputs include timestamps or
  generated ids. Current contacts/mobile fixtures are deterministic; future
  domains should define stable replay comparison fields.
- State-changing tools may return observations that differ from state-change
  summaries. Compare each evidence type separately and report mismatches
  without exposing raw payloads.
- This plan can create pressure to extract `awm_runtime` prematurely. Treat
  replay as evidence, not as the extraction decision itself.

## Notes

This plan is deliberately narrower than plan 0025. It adds an execution-facing
consumer that makes the future AWM runtime package boundary more evidence-based,
but it does not create, publish, or migrate to a separate runtime package.
