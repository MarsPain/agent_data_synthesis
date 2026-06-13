# Plan 0031: Episode Replay and Data-Quality Scoring Consumer

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

## Status

Planned on 2026-06-13. Completed on 2026-06-13.

## Goal

Add the first real non-synthesis consumer of `episode_log_v1` by replaying and
scoring sanitized contacts and mobile episode evidence against the internal
runtime boundary, without changing default dataset outputs or extracting a
separate AWM runtime package.

## Architecture

Plan 0030 made `runtime_metadata_v1` and `episode_log_v1` available internally,
but the only reader is a diagnostic summary helper. This plan turns episode
evidence into an opt-in quality artifact: collect internal episode logs from
candidate processing, validate them, score their transition completeness and
state-support evidence, and write a compact `episode_quality_report.json`.

The new consumer remains repo-local and synchronous. It must depend on
`synthesis.runtime`, `synthesis.episodes`, and validation contracts, not on
dataset release admission, profile promotion, release packs, or future
orchestration. Its job is to prove the runtime/episode boundary is useful to a
second consumer before full plan 0025 is activated.

## Tech Stack

- Python standard library: `dataclasses`, `json`, `pathlib`, `statistics`,
  `collections`, and `unittest`.
- Existing modules: `synthesis.episodes`, `synthesis.runtime`,
  `synthesis.contracts`, `synthesis.candidate_processing`,
  `synthesis.pipeline`, `synthesis.datasets`, `synthesis.domain_pipeline`,
  `synthesis.verification`, and `main.py`.
- New focused module: `synthesis.episode_quality` for report contracts,
  scoring, JSONL writing/reading, and artifact generation.
- Verification through `uv run python scripts/validate_docs.py` and
  `uv run python -m unittest`.

## Basis

- [../completed/0030-runtime-contract-and-episode-evidence.md](../completed/0030-runtime-contract-and-episode-evidence.md)
  added shared contacts/mobile runtime metadata, internal episode logs, and a
  diagnostic episode summary helper.
- [../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md](../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md)
  requires at least one additional consumer, such as reward/data-quality
  evaluation or Agentic RL, before considering package extraction.
- [../../generated/mobile-domain-pipeline-pressure.md](../../generated/mobile-domain-pipeline-pressure.md)
  records that episode evidence remains in-memory only and is not yet replay,
  reward/data-quality, RL, or release infrastructure.
- [../../DESIGN.md](../../DESIGN.md) separates trajectory execution,
  verification, dataset assembly, and runtime lifecycle evidence as bounded
  contexts.

## Why This Plan Now

The framework has just crossed an architectural threshold: two domains now share
the same runtime protocol and can emit sanitized episode evidence. That makes it
possible to test whether the boundary supports another consumer without
building async orchestration, distributed workers, reward model training, or an
external MCP server.

The most useful next step is a narrow data-quality consumer:

- it validates that `episode_log_v1` is complete enough for replay-like
  inspection;
- it identifies missing action/observation/final-response/state-change evidence
  before these logs become release or RL inputs;
- it gives plan 0025 concrete second-consumer evidence while keeping extraction
  deferred;
- it creates pressure for the later `CandidateTask` contract split only where
  scoring proves the mixed task/policy/expected-state record is insufficient.

## Scope

- Add `episode_quality_report_v1` as an opt-in artifact.
- Add `episodes.jsonl` as an opt-in sanitized internal evidence export used only
  when the episode-quality report is requested.
- Preserve default `uv run python main.py` behavior: no episode JSONL and no
  episode-quality report are written unless explicitly requested.
- Extend `PipelineResult` with an optional `episode_logs_path`.
- Collect admitted internal episode logs from `ProvisionalCandidateOutcome`
  records after deterministic merge, including accepted outcomes and rejected
  attempts that have executable trajectories.
- Do not write episode logs into `samples.jsonl`, `rejections.jsonl`, or the
  default manifest.
- Score each episode with deterministic checks:
  - `contract_valid`: episode contract validation passed;
  - `has_action`: at least one action transition exists;
  - `has_observation`: at least one observation transition exists;
  - `has_final_response`: accepted episodes contain exactly one final response;
  - `accepted_has_no_error`: accepted episodes contain no error transitions;
  - `state_change_supported`: episodes with state-changing tools contain at
    least one `state_change` transition;
  - `runtime_known`: runtime id is one of `contacts_fixture` or
    `mobile_messages_fixture`.
- Aggregate per-runtime and per-outcome counts, pass rates, tool names, and
  failed check names.
- Add report decisions:
  - `passed`: all scored episodes pass required checks;
  - `watch`: at least one optional diagnostic check fails while contracts remain
    valid;
  - `failed`: any required check fails or any episode contract is invalid;
  - `insufficient_evidence`: no episode logs are available.
- Attach `episode_quality_report` and `episodes` artifact names to the manifest
  only when the opt-in report is written.
- Update canonical docs and plan indexes to record that this is the first real
  runtime/episode consumer, but still not full AWM runtime extraction.

## Out of Scope

- Reward model training, scalar reward fitting, pairwise preference generation,
  RL rollout collection, PPO/DPO/GRPO, or GPU infrastructure.
- External MCP environment servers or a separate `awm_runtime` package.
- Replaying actions by mutating a fresh runtime state. This plan is a
  deterministic episode-evidence scoring consumer; executable state replay can
  be a later plan if scoring exposes the need.
- Persisting episode logs by default.
- Treating `episode_quality_report.json` as dataset release admission,
  profile-promotion, or downstream model-quality proof.
- Implementing semantic duplicate detection from `TD-0002`.
- Splitting `CandidateTask` into intent/policy/expected-state records.
- Adding async queues, cancellation, resumption, or per-role cost tracking from
  plan 0014.

## Contracts

### `episodes.jsonl`

Each line is one validated `episode_log_v1` record already defined by plan 0030.
The file is written only when episode-quality reporting is requested.

Rules:

- The file must contain no raw source payloads, prompts, provider payloads,
  headers, API keys, environment variables, local profile paths, source paths,
  or arbitrary host paths.
- Records are sorted by candidate sequence order through the same deterministic
  merge/admission ordering used by the pipeline.
- If an outcome is converted to a duplicate rejection during merge, do not
  fabricate a new episode. Keep the original accepted-attempt episode out of
  `episodes.jsonl` unless the sample is admitted, so the report matches public
  sample/rejection counts.

### `episode_quality_report.json`

Expected shape:

```json
{
  "schema_version": "episode_quality_report_v1",
  "dataset_version": "dataset_foundation_v1",
  "inputs": {
    "manifest_path": "manifest.json",
    "episodes_path": "episodes.jsonl"
  },
  "observed": {
    "episode_count": 3,
    "accepted": 3,
    "rejected": 0,
    "failed": 0,
    "runtime_counts": {
      "contacts_fixture": 3
    },
    "tool_names": ["lookup_contact_email", "record_contact_followup"]
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
      "observation_count": 1,
      "state_change_count": 0,
      "final_response_count": 1,
      "error_count": 0,
      "tool_names": ["lookup_contact_email"],
      "failed_checks": []
    }
  ],
  "decision": {
    "status": "passed",
    "reasons": [],
    "triggered_by": []
  }
}
```

Validation rules:

- `schema_version` must be `episode_quality_report_v1`.
- `decision.status` must be one of `passed`, `watch`, `failed`, or
  `insufficient_evidence`.
- `inputs` paths must be relative artifact names, not absolute host paths.
- `episode_summaries` may include ids, counts, runtime ids, outcome status,
  tool names, and failed check names only; it must not include raw instructions,
  arguments, observations, final responses, source payloads, provider payloads,
  prompts, credentials, or host paths.
- `checks[].name` must come from a fixed allowlist.

## File Map

- Create `synthesis/episode_quality.py`:
  `EPISODES_FILENAME`, `EPISODE_QUALITY_REPORT_FILENAME`,
  `EpisodeQualityThresholds`, `write_episode_logs`, `read_episode_logs`,
  `build_episode_quality_report`, `write_episode_quality_report`, and scoring
  helpers.
- Modify `synthesis/contracts.py`:
  add `EPISODE_QUALITY_DECISION_STATUSES`,
  `EPISODE_QUALITY_CHECK_NAMES`,
  `validate_episode_quality_report_record`, and manifest artifact keys
  `episodes` plus `episode_quality_report`.
- Modify `synthesis/datasets.py`:
  add `attach_episodes_to_manifest(...)` and
  `attach_episode_quality_report_to_manifest(...)`.
- Modify `synthesis/candidate_processing.py`:
  add episode-log fields to `CandidateMergeResult` and make
  `merge_candidate_outcomes()` return only admitted sample/rejection-aligned
  episode logs.
- Modify `synthesis/pipeline.py`:
  extend `PipelineResult` with `episode_logs_path`, add a
  `write_episode_logs: bool = False` parameter, collect base/expanded merge
  episode logs, and write `episodes.jsonl` only when requested.
- Modify `main.py`:
  add `--write-episode-quality-report`; when enabled, request pipeline episode
  export, write `episode_quality_report.json`, attach both artifacts to the
  manifest, and print the report path.
- Add `tests/test_episode_quality.py`.
- Extend `tests/test_contracts.py`, `tests/test_candidate_processing.py`,
  `tests/test_foundation_pipeline.py`, `tests/test_mobile_pipeline.py`, and
  `tests/test_cli.py`.
- Update [../../DATA.md](../../DATA.md), [../../DESIGN.md](../../DESIGN.md),
  [../../BACKEND.md](../../BACKEND.md), [../../ROADMAP.md](../../ROADMAP.md),
  [../../generated/mobile-domain-pipeline-pressure.md](../../generated/mobile-domain-pipeline-pressure.md),
  [../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md](../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md),
  [../active/README.md](README.md), and [../../PLANS.md](../../PLANS.md).

## Implementation Tasks

### Task 1: Add Episode-Quality Contract Tests

- [x] Add `tests/test_episode_quality.py`.
- [x] Write a passing fixture builder `_episode(...)` that creates minimal valid
  `episode_log_v1` records for contacts and mobile by reusing
  `synthesis.episodes.build_episode_log`.
- [x] Add `test_builds_passed_report_from_valid_contacts_episodes`.
  Expected assertions:
  - `schema_version == "episode_quality_report_v1"`;
  - `observed.episode_count == 2`;
  - `observed.runtime_counts.contacts_fixture == 2`;
  - `decision.status == "passed"`;
  - summaries omit `arguments`, `observation`, `content`, `instruction`, and
    `final_response`.
- [x] Add `test_mobile_state_change_episode_passes_state_change_support`.
  Use `candidate_mobile_maya_reminder` and assert the summary has
  `runtime_id == "mobile_messages_fixture"`, `state_change_count == 1`, and no
  failed checks.
- [x] Add `test_missing_episodes_returns_insufficient_evidence`.
  Call `build_episode_quality_report(dataset_version="dataset_empty",
  episodes=())` and assert `decision.status == "insufficient_evidence"`.
- [x] Add `test_report_contract_rejects_sensitive_content_and_absolute_paths`.
  Mutate a valid report with `inputs.episodes_path = "/tmp/episodes.jsonl"` and
  with `episode_summaries[0]["content"] = "secret-test-key"`; both must raise
  `ContractValidationError`.
- [x] Run:

```bash
uv run python -m unittest tests.test_episode_quality
```

- [x] Confirm tests fail because `synthesis.episode_quality` and the report
  contract do not exist yet.

### Task 2: Implement `synthesis.episode_quality`

- [x] Create `synthesis/episode_quality.py`.
- [x] Add constants:

```python
EPISODES_FILENAME = "episodes.jsonl"
EPISODE_QUALITY_REPORT_FILENAME = "episode_quality_report.json"
STATE_CHANGING_TOOLS = frozenset({"record_contact_followup", "create_phone_reminder", "draft_message_reply"})
KNOWN_RUNTIMES = frozenset({"contacts_fixture", "mobile_messages_fixture"})
```

- [x] Implement `write_episode_logs(path: Path, episodes: Sequence[Mapping[str, object]]) -> Path`.
  It must validate each episode with `validate_episode_log_record`, write one
  sorted-key JSON object per line, and end the file with a newline.
- [x] Implement `read_episode_logs(path: Path) -> tuple[dict[str, object], ...]`.
  It must skip blank lines, parse JSON objects, validate each episode, and
  raise `ValueError("episode log line N must be a JSON object")` for malformed
  lines.
- [x] Implement `build_episode_quality_report(...)` with this signature:

```python
def build_episode_quality_report(
    *,
    dataset_version: str,
    episodes: Sequence[Mapping[str, object]],
    manifest_path: Path | None = None,
    episodes_path: Path | None = None,
) -> dict[str, object]:
    ...
```

- [x] Implement deterministic per-episode summaries using
  `summarize_episode_for_quality(record)` plus local `error_count` and
  `failed_checks`.
- [x] Required checks:
  - `contract_valid`;
  - `has_action`;
  - `has_observation`;
  - `accepted_has_final_response`;
  - `accepted_has_no_error`;
  - `state_change_supported`;
  - `runtime_known`.
- [x] Decision logic:
  - no episodes -> `insufficient_evidence`;
  - any `contract_valid`, `has_action`, `has_observation`,
    `accepted_has_final_response`, or `accepted_has_no_error` failure ->
    `failed`;
  - any `state_change_supported` or `runtime_known` failure -> `watch`;
  - otherwise -> `passed`.
- [x] Add `write_episode_quality_report(...)` that writes
  `episode_quality_report.json` and validates it before writing.
- [x] Run:

```bash
uv run python -m unittest tests.test_episode_quality
```

- [x] Confirm the new module tests pass.

### Task 3: Add Report Contract and Manifest Attachments

- [x] Modify `synthesis/contracts.py`.
- [x] Add manifest artifact keys `episodes` and `episode_quality_report`.
- [x] Add:

```python
EPISODE_QUALITY_DECISION_STATUSES = {"passed", "watch", "failed", "insufficient_evidence"}
EPISODE_QUALITY_CHECK_NAMES = {
    "contract_valid",
    "has_action",
    "has_observation",
    "accepted_has_final_response",
    "accepted_has_no_error",
    "state_change_supported",
    "runtime_known",
}
```

- [x] Implement `validate_episode_quality_report_record(record)`.
  Validate the expected report shape, relative input paths, non-negative counts,
  fixed check names, allowed statuses, and absence of secret/path/prompt/raw
  payload material using the same defensive scan style as release-quality
  validation.
- [x] Modify `synthesis/datasets.py`.
- [x] Add:

```python
def attach_episodes_to_manifest(*, manifest_path: Path, episodes_path: Path) -> None:
    _attach_artifact_to_manifest(
        manifest_path=manifest_path,
        artifact_key="episodes",
        artifact_path=episodes_path,
    )


def attach_episode_quality_report_to_manifest(*, manifest_path: Path, report_path: Path) -> None:
    _attach_artifact_to_manifest(
        manifest_path=manifest_path,
        artifact_key="episode_quality_report",
        artifact_path=report_path,
    )
```

- [x] Extend `tests/test_contracts.py` so a valid manifest accepts
  `episodes: "episodes.jsonl"` and
  `episode_quality_report: "episode_quality_report.json"`.
- [x] Extend `tests/test_episode_quality.py` to call
  `validate_episode_quality_report_record`.
- [x] Run:

```bash
uv run python -m unittest tests.test_contracts tests.test_episode_quality
```

### Task 4: Preserve Merge Semantics While Returning Episode Logs

- [x] Modify `synthesis.candidate_processing.CandidateMergeResult` to include:

```python
episode_logs: tuple[dict[str, object], ...] = ()
```

- [x] In `merge_candidate_outcomes()`, append `outcome.episode_log` only when:
  - `outcome.sample is not None`;
  - the sample is admitted rather than converted to a duplicate rejection;
  - `outcome.episode_log is not None`.
- [x] For non-duplicate rejected outcomes, append `outcome.episode_log` when it
  exists.
- [x] Do not append an episode for merge-created duplicate rejections. This keeps
  `episodes.jsonl` aligned to admitted sample/rejection artifacts rather than
  provisional attempts.
- [x] Add `tests/test_candidate_processing.py::test_merge_returns_episode_logs_for_admitted_outcomes_only`.
  Build two duplicate accepted outcomes with different sequence indexes and
  fake `episode_log` ids; assert the merge returns one sample, one duplicate
  rejection, and only the first episode id.
- [x] Run:

```bash
uv run python -m unittest tests.test_candidate_processing tests.test_candidate_merge
```

### Task 5: Add Opt-In Pipeline Episode Export

- [x] Modify `synthesis.pipeline.PipelineResult`:

```python
episode_logs_path: Path | None
```

- [x] Add `write_episode_logs: bool = False` to `run_foundation_pipeline(...)`.
- [x] Collect `base_merge.episode_logs` and `expanded_merge.episode_logs` into
  `episode_logs: list[dict[str, object]]`.
- [x] After `write_dataset_artifacts(...)`, if `write_episode_logs` is true,
  call:

```python
from synthesis.episode_quality import EPISODES_FILENAME, write_episode_logs as write_episode_log_jsonl

episode_logs_path = write_episode_log_jsonl(
    output_dir / EPISODES_FILENAME,
    episode_logs,
)
```

- [x] Return `episode_logs_path` in `PipelineResult`; return `None` on all
  early rejection paths where no candidate execution episode exists.
- [x] Do not attach the episode file to the manifest in `pipeline.py`; manifest
  attachment remains owned by CLI/report orchestration in `main.py`.
- [x] Extend `tests/test_foundation_pipeline.py`:
  - default run does not create `episodes.jsonl`;
  - `write_episode_logs=True` creates `episodes.jsonl`;
  - public `samples.jsonl` records still do not contain `episode_log`.
- [x] Extend `tests/test_mobile_pipeline.py`:
  - mobile profile with `write_episode_logs=True` creates mobile episode logs;
  - at least one record has `runtime.runtime_id == "mobile_messages_fixture"`;
  - state-changing mobile candidates include `state_change`.
- [x] Run:

```bash
uv run python -m unittest tests.test_foundation_pipeline tests.test_mobile_pipeline tests.test_episode_quality
```

### Task 6: Add CLI Report Flag

- [x] Modify `main.py` imports to include:

```python
from synthesis.datasets import attach_episode_quality_report_to_manifest, attach_episodes_to_manifest
from synthesis.episode_quality import (
    EPISODE_QUALITY_REPORT_FILENAME,
    build_episode_quality_report,
    read_episode_logs,
    write_episode_quality_report,
)
```

- [x] Add CLI flag:

```python
parser.add_argument(
    "--write-episode-quality-report",
    action="store_true",
    help="Write episodes.jsonl and episode_quality_report.json for runtime episode evidence scoring.",
)
```

- [x] Pass `write_episode_logs=args.write_episode_quality_report` into
  `run_foundation_pipeline(...)`.
- [x] After the pipeline returns, if `args.write_episode_quality_report` is true:
  - assert `result.episode_logs_path is not None`;
  - read episodes with `read_episode_logs(result.episode_logs_path)`;
  - write report to `output_dir / EPISODE_QUALITY_REPORT_FILENAME`;
  - attach `episodes` and `episode_quality_report` to the manifest;
  - include `episode_quality_report=...` in stdout.
- [x] Do not require evaluation, profile decision, dataset release, release
  pack, or release card flags.
- [x] Extend `tests/test_cli.py`:
  - default command does not write `episodes.jsonl` or
    `episode_quality_report.json`;
  - `--write-episode-quality-report` writes both files, attaches both artifact
    names to the manifest, and prints `episode_quality_report=`;
  - mobile profile plus `--write-episode-quality-report` writes a report whose
    `observed.runtime_counts.mobile_messages_fixture` is non-zero.
- [x] Run:

```bash
uv run python -m unittest tests.test_cli tests.test_episode_quality
```

### Task 7: Update Canonical Docs

- [x] Update [../../DATA.md](../../DATA.md) with `episodes.jsonl`,
  `episode_quality_report_v1`, allowed report fields, and redaction rules.
- [x] Update [../../DESIGN.md](../../DESIGN.md) to describe the episode-quality
  consumer as a separate data-quality bounded-context consumer of runtime
  evidence.
- [x] Update [../../BACKEND.md](../../BACKEND.md) to clarify the behavior is
  local, synchronous, and opt-in; async orchestration remains deferred.
- [x] Update [../../ROADMAP.md](../../ROADMAP.md) to add plan 0031 as the first
  real runtime/episode consumer before full AWM runtime extraction.
- [x] Update [../../generated/mobile-domain-pipeline-pressure.md](../../generated/mobile-domain-pipeline-pressure.md)
  to mark the in-memory-only episode pressure as partially resolved by the
  opt-in quality report, while executable replay/RL remain unresolved.
- [x] Update [../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md](../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md)
  to say 0031 supplies a second repo-local data-quality consumer, but package
  extraction still needs replay/adapter/RL pressure and extraction criteria.
- [x] Keep [../deferred/0014-async-local-orchestration-with-durable-queues.md](../deferred/0014-async-local-orchestration-with-durable-queues.md)
  deferred; this plan does not change candidate volume or runtime duration.
- [x] Run:

```bash
uv run python scripts/validate_docs.py
```

### Task 8: Full Validation

- [x] Run focused tests:

```bash
uv run python -m unittest tests.test_episode_quality tests.test_episode_logs tests.test_runtime_contract
```

- [x] Run affected pipeline and CLI tests:

```bash
uv run python -m unittest tests.test_candidate_processing tests.test_candidate_merge tests.test_foundation_pipeline tests.test_mobile_pipeline tests.test_cli tests.test_contracts
```

- [x] Run the full suite:

```bash
uv run python -m unittest
```

- [x] Run a default opt-in report command:

```bash
uv run python main.py --write-episode-quality-report --output-dir artifacts/foundation-episode-quality
```

- [x] Run a mobile opt-in report command:

```bash
uv run python main.py --run-profile tests/fixtures/run_profiles/mobile-agent-fixture.json --write-episode-quality-report --output-dir artifacts/mobile-episode-quality
```

- [x] Inspect both manifests and reports:
  - `manifest.json.artifacts.episodes == "episodes.jsonl"`;
  - `manifest.json.artifacts.episode_quality_report == "episode_quality_report.json"`;
  - default contacts report has `contacts_fixture` runtime counts;
  - mobile report has `mobile_messages_fixture` runtime counts;
  - no sample or rejection record contains `episode_log`;
  - no report contains raw source payloads, prompts, provider payloads,
    headers, API keys, local paths, or final-response text.

## Validation

This plan is complete only after these commands pass:

```bash
uv run python scripts/validate_docs.py
uv run python -m unittest tests.test_episode_quality tests.test_episode_logs tests.test_runtime_contract
uv run python -m unittest tests.test_candidate_processing tests.test_candidate_merge tests.test_foundation_pipeline tests.test_mobile_pipeline tests.test_cli tests.test_contracts
uv run python -m unittest
uv run python main.py --write-episode-quality-report --output-dir artifacts/foundation-episode-quality
uv run python main.py --run-profile tests/fixtures/run_profiles/mobile-agent-fixture.json --write-episode-quality-report --output-dir artifacts/mobile-episode-quality
```

## Acceptance Criteria

- `episodes.jsonl` and `episode_quality_report.json` are opt-in artifacts only.
- Default `uv run python main.py` public artifacts are unchanged.
- Accepted contacts and mobile episodes can be scored by a real
  data-quality consumer outside dataset assembly.
- Report summaries contain deterministic counts and check results, not raw
  instructions, arguments, observations, final-response text, prompts,
  provider payloads, credentials, or host paths.
- Manifest artifact references are added only when the report is explicitly
  written.
- `samples.jsonl`, `rejections.jsonl`, and the default manifest do not include
  `episode_log`.
- Plan 0025 remains deferred for package extraction, but its second-consumer
  evidence is updated to reference this plan.
- Plan 0014 remains deferred because this plan does not increase run duration
  or candidate volume.
- Documentation validation and the full unit suite pass.

## Risks

- Episode persistence can accidentally become a new default public dataset
  contract. Keep it behind `--write-episode-quality-report`.
- Report summaries can leak content if they include raw transitions. Summaries
  must export counts, ids, statuses, runtime ids, tool names, and failed check
  names only.
- Merge-created duplicate rejections can confuse episode/sample alignment.
  Only export episodes for admitted samples and actual rejected executions with
  trajectories.
- The word "replay" can imply state mutation. This plan scores replay-like
  episode evidence; executable state replay needs a later plan.
- A second consumer can be mistaken for runtime extraction readiness. Update
  plan 0025 with evidence and remaining blockers, but do not extract a package
  in this plan.
