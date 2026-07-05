# Plan 0034: Reward Label Export and Runtime Scoring Consumer

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status

Completed on 2026-06-14.

## Goal

Add an opt-in reward-label export and deterministic runtime scoring consumer
over `episode_log_v1` so contacts and mobile episodes can produce sanitized
scalar and preference-ready training signals without training a reward model,
changing dataset release admission, or extracting an AWM runtime package.

## Architecture

Plans 0030 through 0033 made runtime metadata, episode evidence, executable
replay, and task/policy/verifier contracts explicit. This plan adds the next
consumer layer: `synthesis.reward_labels` reads validated episodes plus optional
episode-quality and episode-replay reports, derives deterministic label records,
and writes a compact report describing label coverage and failure causes.

The implementation stays synchronous and repo-local. Reward labels are
evidence artifacts for future reward-model or Agentic RL work; they are not
model training, not release admission, not profile promotion, and not proof of
downstream model quality.

## Tech Stack

- Python standard library: `dataclasses`, `json`, `pathlib`, `statistics`,
  `collections`, and `unittest`.
- Existing modules: `synthesis.episodes`, `synthesis.episode_quality`,
  `synthesis.episode_replay`, `synthesis.task_contracts`,
  `synthesis.contracts`, `synthesis.datasets`, `synthesis.pipeline`,
  `synthesis.domain_pipeline`, and `main.py`.
- New focused module: `synthesis.reward_labels`.
- Verification through `uv run python scripts/validate_docs.py` and
  `uv run python -m unittest`.

## Basis

- [../completed/0030-runtime-contract-and-episode-evidence.md](../completed/0030-runtime-contract-and-episode-evidence.md)
  added `runtime_metadata_v1` and `episode_log_v1`.
- [../completed/0031-episode-replay-and-data-quality-scoring-consumer.md](../completed/0031-episode-replay-and-data-quality-scoring-consumer.md)
  added opt-in episode JSONL export and `episode_quality_report_v1`.
- [../completed/0032-executable-episode-replay-consistency-probe.md](../completed/0032-executable-episode-replay-consistency-probe.md)
  added opt-in executable replay and `episode_replay_report_v1`.
- [../completed/0033-task-intent-policy-verifier-contract-split.md](../completed/0033-task-intent-policy-verifier-contract-split.md)
  split task intent, policy hints, expected final-answer evidence, and expected
  state checks internally while preserving public artifact schemas.
- [../indexes/0025-awm-runtime-boundary-and-shared-environment-kernel.md](../indexes/0025-awm-runtime-boundary-and-shared-environment-kernel.md)
  keeps package extraction deferred until reward/RL workflows, external MCP
  environment servers, or stronger cross-consumer pressure justify it. This
  plan supplies reward-label consumer evidence without extracting.
- [../../generated/mobile-domain-pipeline-pressure.md](../../generated/mobile-domain-pipeline-pressure.md)
  records reward-label export and Agentic RL rollout collection as unresolved
  pressure after plans 0030 through 0033.

## Why This Plan Now

The repository has enough runtime and episode infrastructure to support a
reward-oriented consumer, but not enough evidence to justify package extraction
or RL rollout infrastructure. Reward-label export is the narrowest next step
that tests whether the current boundaries can produce training-adjacent signals:

- it consumes the same `episodes.jsonl` used by quality and replay reports;
- it depends on replay/quality evidence instead of rereading raw samples;
- it makes accepted, rejected, state-changing, and replay-consistent episodes
  machine-labelable;
- it records missing evidence as explicit label exclusions;
- it gives deferred plan 0025 stronger reward/RL pressure while keeping the
  implementation local and reversible.

## Scope

- Add `reward_labels.jsonl` as an opt-in sanitized artifact.
- Add `reward_label_report.json` as an opt-in summary and decision artifact.
- Add `synthesis.reward_labels` with deterministic scalar labels and
  preference-ready grouping metadata over validated `episode_log_v1` records.
- Reuse `episodes.jsonl`; when reward-label reporting is requested from the
  CLI, request pipeline episode export exactly as episode-quality and
  episode-replay reporting already do.
- Optionally consume existing in-memory or freshly built episode-quality and
  episode-replay reports to assign label reasons and confidence.
- Attach `episodes`, `reward_labels`, and `reward_label_report` to the manifest
  only when the opt-in report is explicitly requested.
- Preserve default `uv run python main.py` behavior: no reward labels, no
  reward-label report, and no manifest reward artifacts by default.
- Update canonical docs to describe reward labels as local evidence artifacts,
  not release gates or trained reward models.

## Out of Scope

- Training a reward model, fitting scalar reward parameters, or running model
  evaluation against learned reward models.
- Pairwise preference optimization, DPO, PPO, GRPO, online RL, rollout
  collection, GPU infrastructure, or distributed workers.
- Creating an `awm_runtime` package or moving runtime code out of this repo.
- External MCP environment servers or mobile MCP adapter support.
- Mobile source-governed input.
- Semantic duplicate detection from `TD-0002`.
- Async orchestration, durable queues, cancellation, or per-role cost tracking
  from plan 0014.
- Changing `samples.jsonl`, `rejections.jsonl`, `episode_log_v1`,
  `episode_quality_report_v1`, `episode_replay_report_v1`, dataset release
  admission, profile promotion, or default CLI output.

## Contracts

### `reward_labels.jsonl`

Each line is one validated `reward_label_v1` record. Records are aligned to
episodes, not raw samples. They are sorted in the same deterministic candidate
order as `episodes.jsonl`.

Expected shape:

```json
{
  "schema_version": "reward_label_v1",
  "label_id": "reward_label_candidate_contacts_alice",
  "episode_id": "episode_sample_candidate_contacts_alice",
  "candidate_id": "candidate_contacts_alice",
  "runtime_id": "contacts_fixture",
  "outcome_status": "accepted",
  "scalar_reward": 1.0,
  "label_status": "usable",
  "label_source": {
    "quality_report": "episode_quality_report_v1",
    "replay_report": "episode_replay_report_v1"
  },
  "components": {
    "outcome": 1.0,
    "contract": 1.0,
    "execution": 1.0,
    "state_support": 1.0,
    "replay_consistency": 1.0
  },
  "preference_group": {
    "group_id": "pref_contacts_fixture_contact_lookup",
    "rank": 1,
    "tie_breaker": "candidate_contacts_alice"
  },
  "reasons": [
    "accepted_episode",
    "quality_checks_passed",
    "replay_checks_passed"
  ]
}
```

Validation rules:

- `schema_version` must be `reward_label_v1`.
- `label_status` must be one of `usable`, `excluded`, or `insufficient_evidence`.
- `scalar_reward` must be a number from `0.0` to `1.0`.
- `components` may contain only fixed component names:
  `outcome`, `contract`, `execution`, `state_support`, and
  `replay_consistency`.
- `runtime_id` must initially be `contacts_fixture` or
  `mobile_messages_fixture`.
- `label_source` may contain schema names and relative artifact names only; it
  must not contain absolute paths.
- `preference_group` is deterministic grouping metadata only. It must not
  include task instructions, final answers, tool arguments, observations,
  expected state, or raw trajectory content.
- Records must not include raw source payloads, prompts, provider payloads,
  headers, API keys, environment variables, local profile paths, arbitrary host
  paths, raw arguments, observations, or final responses.

### Reward Scoring Semantics

Initial deterministic component scores:

- `outcome`: `1.0` for accepted episodes, `0.0` for failed/rejected episodes.
- `contract`: `1.0` when the episode contract is valid, otherwise excluded.
- `execution`: `1.0` when action and observation evidence is present and
  required replay checks pass, `0.5` when quality checks pass but replay
  evidence is absent, `0.0` when required execution or replay checks fail.
- `state_support`: `1.0` when no state-changing tool is used or state-change
  support/match evidence passes, `0.0` when state-changing tools lack support.
- `replay_consistency`: `1.0` when replay evidence passes, `0.5` when replay
  evidence is not provided, `0.0` when replay required checks fail.

Initial scalar reward:

```text
0.35 * outcome
+ 0.20 * contract
+ 0.20 * execution
+ 0.15 * state_support
+ 0.10 * replay_consistency
```

Rules:

- Invalid episode contracts produce `label_status: excluded` and no public raw
  error payload.
- No episodes produce an empty `reward_labels.jsonl` and
  `reward_label_report.decision.status: insufficient_evidence`.
- Accepted episodes with passed quality and replay evidence should score `1.0`.
- Accepted episodes without replay evidence may be `usable` but must record
  `replay_evidence_absent` and a lower replay component.
- Failed/rejected execution attempts may be labelable as negative examples when
  the episode contract is valid and the failure cause is sanitized.
- If quality or replay summaries are inconsistent with the episode ids, labels
  must be `insufficient_evidence`, not guessed.

### `reward_label_report.json`

Expected shape:

```json
{
  "schema_version": "reward_label_report_v1",
  "dataset_version": "dataset_foundation_v1",
  "inputs": {
    "manifest_path": "manifest.json",
    "episodes_path": "episodes.jsonl",
    "episode_quality_report_path": "episode_quality_report.json",
    "episode_replay_report_path": "episode_replay_report.json",
    "reward_labels_path": "reward_labels.jsonl"
  },
  "observed": {
    "episode_count": 3,
    "label_count": 3,
    "usable": 3,
    "excluded": 0,
    "insufficient_evidence": 0,
    "runtime_counts": {
      "contacts_fixture": 3
    },
    "average_scalar_reward": 1.0
  },
  "checks": [
    {
      "name": "labels_present",
      "status": "passed",
      "passed": 3,
      "failed": 0,
      "required": true
    }
  ],
  "label_summaries": [
    {
      "label_id": "reward_label_candidate_contacts_alice",
      "episode_id": "episode_sample_candidate_contacts_alice",
      "candidate_id": "candidate_contacts_alice",
      "runtime_id": "contacts_fixture",
      "label_status": "usable",
      "scalar_reward": 1.0,
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

- `schema_version` must be `reward_label_report_v1`.
- `decision.status` must be one of `passed`, `watch`, `failed`, or
  `insufficient_evidence`.
- `inputs` paths must be relative artifact names or `null`, never absolute host
  paths.
- `checks[].name` must come from a fixed allowlist:
  `labels_present`, `label_contract_valid`, `episode_contract_valid`,
  `quality_evidence_aligned`, `replay_evidence_aligned`,
  `usable_label_coverage`, and `sanitized_summaries`.
- `label_summaries` may include ids, runtime id, status, scalar reward, and
  failed check names only. They must not include instructions, expected
  answers, expected state, tool arguments, observations, final responses,
  source payloads, provider payloads, prompts, credentials, or host paths.

Decision rules:

- `insufficient_evidence`: no episode logs are available.
- `failed`: label contract validation fails, required episode contracts fail,
  or no usable labels remain after exclusions.
- `watch`: usable labels exist but replay evidence is absent, optional replay
  checks fail, or some labels are excluded.
- `passed`: all labels are usable and required/optional evidence is aligned.

## File Map

- Create `synthesis/reward_labels.py`:
  `REWARD_LABELS_FILENAME`, `REWARD_LABEL_REPORT_FILENAME`,
  `RewardLabelThresholds`, `build_reward_labels`,
  `write_reward_labels`, `read_reward_labels`,
  `build_reward_label_report`, `write_reward_label_report`, and sanitized
  scoring helpers.
- Modify `synthesis/contracts.py`:
  add reward-label statuses, report decision statuses, component/check
  allowlists, manifest artifact keys `reward_labels` and
  `reward_label_report`, `validate_reward_label_record`, and
  `validate_reward_label_report_record`.
- Modify `synthesis/datasets.py`:
  add `attach_reward_labels_to_manifest(...)` and
  `attach_reward_label_report_to_manifest(...)`.
- Modify `main.py`:
  add `--write-reward-label-report`; when enabled, request episode export,
  build or reuse episode-quality/replay evidence, write `reward_labels.jsonl`,
  write `reward_label_report.json`, attach artifacts to the manifest, and print
  the reward-label report path.
- Add `tests/test_reward_labels.py`.
- Extend `tests/test_contracts.py`, `tests/test_cli.py`,
  `tests/test_foundation_pipeline.py`, and `tests/test_mobile_pipeline.py`.
- Update [../../DATA.md](../../DATA.md), [../../DESIGN.md](../../DESIGN.md),
  [../../BACKEND.md](../../BACKEND.md), [../../ROADMAP.md](../../ROADMAP.md),
  [../../generated/mobile-domain-pipeline-pressure.md](../../generated/mobile-domain-pipeline-pressure.md),
  [../indexes/0025-awm-runtime-boundary-and-shared-environment-kernel.md](../indexes/0025-awm-runtime-boundary-and-shared-environment-kernel.md),
  [../../PLANS.md](../../PLANS.md), [README.md](README.md),
  [../../README.md](../../README.md), and [../../../README.md](../../../README.md).

## Implementation Tasks

### Task 1: Add Reward-Label Unit Tests

- [ ] Add `tests/test_reward_labels.py`.
- [ ] Reuse the episode fixture pattern from `tests/test_episode_quality.py`
  and `tests/test_episode_replay.py` to build contacts and mobile
  `episode_log_v1` records through `build_domain_pipeline_bundle`,
  `execute_candidate`, and `build_episode_log` followed by `export()`.
- [ ] Add `test_builds_usable_label_for_passed_contacts_episode`:
  build a contacts episode, quality report, replay report, and labels; assert:
  - first label has `schema_version == "reward_label_v1"`;
  - `candidate_id == "candidate_contacts_alice"`;
  - `runtime_id == "contacts_fixture"`;
  - `label_status == "usable"`;
  - `scalar_reward == 1.0`;
  - reasons include `accepted_episode`, `quality_checks_passed`, and
    `replay_checks_passed`.
- [ ] Add `test_mobile_state_change_label_uses_state_support`:
  use `candidate_mobile_maya_reminder`; assert `runtime_id` is
  `mobile_messages_fixture`, component `state_support == 1.0`, and
  `label_status == "usable"`.
- [ ] Add `test_missing_replay_evidence_creates_watchable_usable_label`:
  build labels with a quality report and without a replay report; assert
  `components.replay_consistency == 0.5`,
  `reasons` contains `replay_evidence_absent`, and the report decision is
  `watch`.
- [ ] Add `test_empty_episodes_returns_insufficient_evidence_report`:
  call `build_reward_label_report(dataset_version="dataset_empty",
  episodes=(), labels=())`; assert decision status is `insufficient_evidence`
  and `observed.label_count == 0`.
- [ ] Add `test_reward_label_contract_rejects_raw_content_and_absolute_paths`:
  mutate a valid label with `label_source.artifact_path = "/tmp/reward.jsonl"`
  and with `preference_group.instruction = "Find Alice"`; both must raise
  `ContractValidationError`.
- [ ] Add `test_reward_label_report_rejects_sensitive_summary_content`:
  mutate a valid report with `label_summaries[0]["observation"] = {"email":
  "alice.zhang@example.test"}` and assert `ContractValidationError`.
- [ ] Run:

```bash
uv run python -m unittest tests.test_reward_labels
```

- [ ] Confirm tests fail because `synthesis.reward_labels` and reward-label
  contracts do not exist yet.

### Task 2: Add Reward-Label Contracts

- [ ] Modify `synthesis/contracts.py`.
- [ ] Add constants:

```python
REWARD_LABEL_STATUSES = {"usable", "excluded", "insufficient_evidence"}
REWARD_LABEL_DECISION_STATUSES = {
    "passed",
    "watch",
    "failed",
    "insufficient_evidence",
}
REWARD_LABEL_COMPONENT_NAMES = {
    "outcome",
    "contract",
    "execution",
    "state_support",
    "replay_consistency",
}
REWARD_LABEL_CHECK_NAMES = {
    "labels_present",
    "label_contract_valid",
    "episode_contract_valid",
    "quality_evidence_aligned",
    "replay_evidence_aligned",
    "usable_label_coverage",
    "sanitized_summaries",
}
```

- [ ] Add `reward_labels` and `reward_label_report` to
  `MANIFEST_ARTIFACT_KEYS`.
- [ ] Implement `validate_reward_label_record(record)`:
  require schema, ids, supported status, scalar range, runtime id, fixed
  component names, relative label source values, sanitized reasons, and
  sanitized preference-group fields.
- [ ] Implement `validate_reward_label_report_record(record)`:
  require schema, dataset version, relative inputs, observed counts, allowlisted
  checks, sanitized summaries, and allowlisted decision status.
- [ ] Extend `tests/test_contracts.py` with focused valid/invalid fixtures for
  both contracts and manifest artifact keys.
- [ ] Run:

```bash
uv run python -m unittest tests.test_contracts tests.test_reward_labels
```

- [ ] Confirm contract tests pass and reward-label implementation tests still
  fail on missing builder functions.

### Task 3: Implement `synthesis.reward_labels`

- [ ] Create `synthesis/reward_labels.py`.
- [ ] Define constants:

```python
REWARD_LABELS_FILENAME = "reward_labels.jsonl"
REWARD_LABEL_REPORT_FILENAME = "reward_label_report.json"
KNOWN_REWARD_RUNTIMES = frozenset({"contacts_fixture", "mobile_messages_fixture"})
STATE_CHANGING_TOOLS = frozenset(
    {"record_contact_followup", "create_phone_reminder", "draft_message_reply"}
)
```

- [ ] Define `RewardLabelThresholds` with weights:
  `outcome=0.35`, `contract=0.20`, `execution=0.20`,
  `state_support=0.15`, and `replay_consistency=0.10`.
- [ ] Implement `build_reward_labels` with this public signature:

```python
def build_reward_labels(
    *,
    episodes: Sequence[Mapping[str, object]],
    episode_quality_report: Mapping[str, object] | None = None,
    episode_replay_report: Mapping[str, object] | None = None,
    thresholds: RewardLabelThresholds = RewardLabelThresholds(),
) -> tuple[dict[str, object], ...]
```

- [ ] Build lookup maps from quality/replay `episode_summaries` by
  `episode_id`. If a summary is absent for an episode, record
  `quality_evidence_absent` or `replay_evidence_absent`.
- [ ] For each valid episode, compute component scores using the scoring
  semantics in this plan, round scalar rewards to six decimal places, validate
  with `validate_reward_label_record`, and return deterministic tuple ordering.
- [ ] For invalid episode contracts, produce an excluded label with sanitized
  ids where possible and reason `episode_contract_invalid`.
- [ ] Implement `write_reward_labels` and `read_reward_labels` with these
  public signatures:

```python
def write_reward_labels(path: Path, labels: Sequence[Mapping[str, object]]) -> Path

def read_reward_labels(path: Path) -> tuple[dict[str, object], ...]
```

  Match `episode_quality.write_episode_logs` behavior: one sorted-key JSON
  object per line, newline at EOF, skip blank lines on read, validate each
  record.
- [ ] Implement `build_reward_label_report` with this public signature:

```python
def build_reward_label_report(
    *,
    dataset_version: str,
    episodes: Sequence[Mapping[str, object]],
    labels: Sequence[Mapping[str, object]],
    manifest_path: Path | None = None,
    episodes_path: Path | None = None,
    episode_quality_report_path: Path | None = None,
    episode_replay_report_path: Path | None = None,
    reward_labels_path: Path | None = None,
) -> dict[str, object]
```

- [ ] Implement `write_reward_label_report` as the JSON writer wrapper
  that validates the report before writing.
- [ ] Ensure summaries omit raw task and transition content by construction.
- [ ] Run:

```bash
uv run python -m unittest tests.test_reward_labels tests.test_contracts
```

- [ ] Confirm tests pass.

### Task 4: Wire Manifest Helpers and CLI

- [ ] Modify `synthesis/datasets.py` to add:

```python
def attach_reward_labels_to_manifest(
    *,
    manifest_path: Path,
    labels_path: Path,
) -> None:
    _attach_artifact_to_manifest(
        manifest_path=manifest_path,
        artifact_key="reward_labels",
        artifact_path=labels_path,
    )


def attach_reward_label_report_to_manifest(
    *,
    manifest_path: Path,
    report_path: Path,
) -> None:
    _attach_artifact_to_manifest(
        manifest_path=manifest_path,
        artifact_key="reward_label_report",
        artifact_path=report_path,
    )
```

- [ ] Modify `main.py` imports to include the new manifest helpers and
  reward-label writer functions.
- [ ] Add CLI flag:

```python
parser.add_argument(
    "--write-reward-label-report",
    action="store_true",
    help=(
        "Write reward_labels.jsonl and reward_label_report.json from sanitized "
        "episode evidence without training a reward model."
    ),
)
```

- [ ] Update the `write_episode_logs` request so reward labels also request
  episode export:

```python
write_episode_logs=(
    args.write_episode_quality_report
    or args.write_episode_replay_report
    or args.write_reward_label_report
)
```

- [ ] In the CLI flow, when `args.write_reward_label_report` is true:
  read `result.episode_logs_path`, build quality and replay reports in memory
  if they were not already written, write `reward_labels.jsonl`, write
  `reward_label_report.json`, attach `episodes`, `reward_labels`, and
  `reward_label_report` to the manifest, and print
  `reward_label_report=<path>`.
- [ ] Do not require users to also pass `--write-episode-quality-report` or
  `--write-episode-replay-report`; reward-label reporting may compute those
  reports in memory without attaching their artifacts unless their flags are
  explicitly supplied.
- [ ] Extend `tests/test_cli.py`:
  - default CLI output omits reward artifacts;
  - `--write-reward-label-report` writes `episodes.jsonl`,
    `reward_labels.jsonl`, and `reward_label_report.json`;
  - manifest references `episodes`, `reward_labels`, and
    `reward_label_report`;
  - stdout contains `reward_label_report=`;
  - mobile profile can write reward-label artifacts with
    `mobile_messages_fixture` labels.
- [ ] Run:

```bash
uv run python -m unittest tests.test_cli tests.test_reward_labels
```

- [ ] Confirm tests pass.

### Task 5: Add Pipeline Regression Coverage

- [ ] Extend `tests/test_foundation_pipeline.py` only if reward-label CLI
  support exposes a pipeline-level episode-export regression not already covered
  by CLI tests. Keep assertions focused on:
  - default pipeline result has `episode_logs_path is None`;
  - reward-label reporting requests episode logs through the existing
    `write_episode_logs` boundary.
- [ ] Extend `tests/test_mobile_pipeline.py` with a focused mobile reward-label
  fixture if CLI coverage cannot inspect mobile label records deeply enough.
- [ ] Do not change accepted/rejected sample schemas or default manifest
  artifacts.
- [ ] Run:

```bash
uv run python -m unittest tests.test_foundation_pipeline tests.test_mobile_pipeline tests.test_reward_labels
```

- [ ] Confirm tests pass.

### Task 6: Update Canonical Docs

- [ ] Update [../../DESIGN.md](../../DESIGN.md):
  add a `Reward Labels` bounded context after `Episode Replay` that explains
  reward labels consume episode, quality, and replay evidence but do not train
  reward models or own runtime extraction.
- [ ] Update [../../DATA.md](../../DATA.md):
  document `reward_labels.jsonl`, `reward_label_report.json`, manifest artifact
  keys, contract shapes, redaction rules, and non-claims.
- [ ] Update [../../BACKEND.md](../../BACKEND.md):
  add the CLI step for `--write-reward-label-report` and keep it distinct from
  reward training, RL rollout collection, and package extraction.
- [ ] Update [../../ROADMAP.md](../../ROADMAP.md):
  mark plan 0034 as the reward-label consumer step before full AWM runtime
  extraction.
- [ ] Update [../../generated/mobile-domain-pipeline-pressure.md](../../generated/mobile-domain-pipeline-pressure.md):
  record that reward-label export is resolved narrowly while Agentic RL rollout
  collection, external MCP environment servers, mobile source-governed input,
  semantic duplicate detection, async orchestration, and package extraction
  remain unresolved.
- [ ] Update
  [../indexes/0025-awm-runtime-boundary-and-shared-environment-kernel.md](../indexes/0025-awm-runtime-boundary-and-shared-environment-kernel.md):
  add plan 0034 as reward-label consumer evidence and keep extraction deferred
  unless a separate extraction decision finds stronger pressure.
- [ ] Update [../../PLANS.md](../../PLANS.md), [README.md](README.md),
  [../../README.md](../../README.md), and [../../../README.md](../../../README.md)
  if CLI examples or active/completed plan status changed during
  implementation.
- [ ] Run:

```bash
uv run python scripts/validate_docs.py
```

- [ ] Confirm documentation validation passes.

### Task 7: Full Verification

- [ ] Run:

```bash
uv run python scripts/validate_docs.py
uv run python -m unittest
uv run python main.py --write-reward-label-report --output-dir artifacts/foundation-reward-labels
uv run python main.py --run-profile tests/fixtures/run_profiles/mobile-agent-fixture.json --write-reward-label-report --output-dir artifacts/mobile-reward-labels
```

- [ ] Confirm:
  - docs validation passes;
  - unit tests pass;
  - contacts and mobile reward-label commands complete;
  - `reward_labels.jsonl` and `reward_label_report.json` are written only for
    opt-in runs;
  - default sample/rejection schemas remain unchanged;
  - manifests reference reward artifacts only for opt-in reward-label runs.

## Validation

Implementation must finish with:

```bash
uv run python scripts/validate_docs.py
uv run python -m unittest
uv run python main.py --write-reward-label-report --output-dir artifacts/foundation-reward-labels
uv run python main.py --run-profile tests/fixtures/run_profiles/mobile-agent-fixture.json --write-reward-label-report --output-dir artifacts/mobile-reward-labels
```

## Completion Criteria

- Default local synthesis remains unchanged and writes no reward-label artifacts.
- `--write-reward-label-report` writes validated `episodes.jsonl`,
  `reward_labels.jsonl`, and `reward_label_report.json`.
- Reward labels can be built for contacts and mobile fixture episodes.
- Reward-label report summaries are sanitized and contract-validated.
- Manifest reward artifact references appear only when explicitly requested.
- Dataset release admission, profile promotion, episode quality, episode replay,
  and public sample/rejection schemas remain unchanged.
- Plan 0025 remains deferred unless a later extraction decision plan finds
  stronger reward/RL, external MCP, or package-boundary pressure.

## Follow-Up

Plan 0035 later resolved the mobile source-governed input gap noted in this
plan's pressure analysis by adding a domain source importer boundary and
`local_mobile_messages_json` profile-local source support. Reward/RL rollout
collection, external MCP environment servers, semantic duplicate detection,
async orchestration, and full runtime package extraction remain deferred.

## Risks

- Reward labels may be mistaken for trained reward-model evidence. Keep artifact
  names and docs explicit: labels are deterministic evidence, not a model.
- Scalar weights can look more authoritative than they are. Keep them simple,
  fixed, documented, and easy to revise in a later plan.
- Computing quality/replay reports in memory can drift from persisted reports.
  Reuse the existing builders and validate id alignment before scoring labels.
- Report summaries can accidentally leak raw trajectory content. Build summaries
  from ids, counts, status, scalar values, and failed check names only.
