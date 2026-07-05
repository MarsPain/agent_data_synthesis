# Plan 0033: Task Intent, Policy, and Verifier Contract Split

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

## Status

Planned on 2026-06-14. Completed on 2026-06-14.

## Goal

Split the overloaded `CandidateTask` responsibilities into explicit internal
task-intent, policy-hint, expected-answer, and expected-state contracts while
preserving the current public dataset artifacts, default CLI behavior, contacts
and mobile deterministic profiles, and opt-in episode quality/replay consumers.

## Architecture

`CandidateTask` currently mixes user intent, domain metadata, execution hints,
branch plans, expected final answers, expected environment state, and generation
lineage. That shape worked for a contacts-only prototype, but plans 0029-0032
made the pressure visible: two domains now share runtime metadata and episode
evidence, and non-synthesis consumers replay or score episodes without needing
dataset-generation internals.

This plan introduces a narrow internal contract layer in `synthesis.task_contracts`
and migrates execution, verification, and episode construction to read that
layer. `CandidateTask` remains as the compatibility input/output wrapper for
generators, samples, rejections, LLM task generation, and existing tests until a
later plan has evidence that the public schema should change.

## Tech Stack

- Python standard library: `dataclasses`, `typing`, `collections.abc`, and
  `unittest`.
- Existing modules: `synthesis.tasks`, `synthesis.mobile_tasks`,
  `synthesis.execution`, `synthesis.verification`,
  `synthesis.candidate_processing`, `synthesis.episodes`,
  `synthesis.contracts`, `synthesis.pipeline`, and `synthesis.domain_pipeline`.
- New focused module: `synthesis.task_contracts` for task intent,
  execution-policy hints, expected outcome records, compatibility conversion,
  and contract validation helpers.
- Verification through `uv run python scripts/validate_docs.py` and
  `uv run python -m unittest`.

## Basis

- [0029-mobile-agent-second-domain-pipeline-probe.md](0029-mobile-agent-second-domain-pipeline-probe.md)
  added the `mobile_messages_fixture` domain and documented that `CandidateTask`
  still mixes task intent, execution hints, expected answer, and expected state.
- [0030-runtime-contract-and-episode-evidence.md](0030-runtime-contract-and-episode-evidence.md)
  introduced `runtime_metadata_v1` and `episode_log_v1` while keeping the full
  AWM runtime extraction deferred.
- [0031-episode-replay-and-data-quality-scoring-consumer.md](0031-episode-replay-and-data-quality-scoring-consumer.md)
  added the first repo-local non-synthesis consumer of episode evidence.
- [0032-executable-episode-replay-consistency-probe.md](0032-executable-episode-replay-consistency-probe.md)
  proved executable replay can rebuild fixture runtimes and execute action
  transitions, but explicitly left the `CandidateTask` split unresolved.
- [../indexes/0025-awm-runtime-boundary-and-shared-environment-kernel.md](../indexes/0025-awm-runtime-boundary-and-shared-environment-kernel.md)
  remains deferred until reward/RL workflows, external MCP environment servers,
  or stronger cross-consumer package-boundary pressure justify extraction. This
  plan is a pre-extraction de-risking step, not the extraction itself.
- [../../generated/mobile-domain-pipeline-pressure.md](../../generated/mobile-domain-pipeline-pressure.md)
  records that executable replay is now present, while reward-label export,
  Agentic RL rollout collection, external MCP environment servers, mobile
  source-governed input, and the `CandidateTask` split remain unresolved.
- [../../DESIGN.md](../../DESIGN.md) separates task curriculum, trajectory
  execution, verification, environment synthesis, dataset assembly, episode
  quality, and episode replay as bounded contexts.

## Why This Plan Now

The recent runtime and episode work made the next coupling point explicit.
Contacts and mobile domains can now emit, score, and replay episode evidence
through a shared runtime boundary, but the upstream task shape still makes
execution and verification depend on a generator-era record.

The next useful step is to create small, stable internal contracts that answer:

- what is the task asking for;
- what policy or tool hints may be used to solve it;
- what final-answer evidence is expected;
- what environment-state evidence is expected;
- what compatibility data must remain on `CandidateTask` for current callers.

This improves architecture robustness and extensibility before reward labels,
Agentic RL rollouts, external MCP runtimes, or more domains place stronger
pressure on the same boundary.

## Scope

- Add `synthesis.task_contracts` with:
  - `TaskIntent`;
  - `PolicyHint`;
  - `ExpectedOutcome`;
  - `ExpectedStateCheck`;
  - `TaskContract`;
  - `task_contract_from_candidate(...)`;
  - `validate_task_contract(...)`;
  - `candidate_from_task_contract(...)` only where round-trip compatibility is
    needed by tests or migration helpers.
- Keep `CandidateTask` as the accepted generator and public artifact wrapper in
  this plan.
- Preserve `CandidateTask.export()` output shape so `samples.jsonl`,
  `rejections.jsonl`, release packs, and profile decisions do not change.
- Migrate scripted contacts and mobile policy generation to consume
  `TaskContract` or `PolicyHint` internally while preserving compatibility
  wrappers that accept `CandidateTask`.
- Migrate verification state checks to consume `ExpectedOutcome` and
  `ExpectedStateCheck` internally while preserving `ExactAnswerVerifier.verify`
  compatibility with `CandidateTask`.
- Migrate episode construction call sites to receive contract-derived policy
  and verifier identity without adding raw task instructions, expected answers,
  or expected state to `episode_log_v1`.
- Add tests proving contacts and mobile contracts are domain-aware, safe to
  validate, and stable under the existing deterministic pipeline.
- Update canonical docs and generated pressure notes to record that this plan
  reduces plan 0025 risk but does not activate full AWM runtime extraction.

## Out of Scope

- Changing the public dataset sample schema or `CandidateTask.export()` shape.
- Removing `CandidateTask` from LLM task generation, deterministic task
  generation, task expansion, rejections, or public artifact assembly.
- Changing `episode_log_v1`, `episode_quality_report_v1`, or
  `episode_replay_report_v1` schemas.
- Implementing reward-label export, reward model training, preference
  optimization, PPO/DPO/GRPO, or Agentic RL rollout collection.
- Creating a separate `awm_runtime` package or repository.
- Implementing external MCP environment servers or mobile MCP adapter support.
- Implementing mobile source-governed input.
- Implementing semantic duplicate detection from `TD-0002`.
- Adding async queues, cancellation, resumption, or per-role cost tracking from
  plan 0014.

## Contracts

### `TaskIntent`

Internal dataclass representing what the task asks for, not how to solve or
verify it.

Expected fields:

```python
@dataclass(frozen=True)
class TaskIntent:
    candidate_id: str
    instruction: str
    domain_id: str
    task_type: str
    difficulty: Mapping[str, object]
    required_capabilities: tuple[str, ...] = ()
    seed_ids: tuple[str, ...] = ()
    lineage: Mapping[str, object] = field(default_factory=dict)
```

Rules:

- `candidate_id`, `instruction`, `domain_id`, and `task_type` must be non-empty
  strings.
- `domain_id` values initially supported by compatibility conversion are
  `contacts_fixture` and `mobile_messages_fixture`.
- `difficulty` remains a sanitized mapping; the conversion must preserve the
  current `CandidateTask.difficulty` mapping.
- `TaskIntent` must not contain tool arguments, branch plans, expected answers,
  expected state, provider payloads, prompts, credentials, source payloads, or
  host paths.

### `PolicyHint`

Internal dataclass representing allowed execution hints for scripted or LLM
policy generation.

Expected fields:

```python
@dataclass(frozen=True)
class PolicyHint:
    required_tools: tuple[str, ...]
    primary_tool: str | None = None
    primary_arguments: Mapping[str, object] = field(default_factory=dict)
    branch_plan: Mapping[str, object] | None = None
```

Rules:

- `required_tools` must contain non-empty tool names when supplied.
- `primary_tool` must be either absent or one of the required tools.
- `primary_arguments` must be sanitized and must not contain credentials,
  provider payloads, source payloads, or host paths.
- `branch_plan`, when present, must continue to pass the existing branch-plan
  validator in `synthesis.contracts`.

### `ExpectedOutcome`

Internal dataclass representing final-answer expectations.

Expected fields:

```python
@dataclass(frozen=True)
class ExpectedOutcome:
    final_answer_contains: str
```

Rules:

- `final_answer_contains` must be a non-empty string.
- The verifier may still implement exact substring semantics in this plan.
  Richer verifier semantics are a later plan.

### `ExpectedStateCheck`

Internal dataclass representing environment-state expectations without encoding
domain-specific branches inside the verifier entrypoint.

Expected fields:

```python
@dataclass(frozen=True)
class ExpectedStateCheck:
    check_type: str
    expected: Mapping[str, object]
```

Initial `check_type` values:

- `contact_followup`;
- `mobile_reminder`;
- `mobile_draft_reply`.

Rules:

- `check_type` must be one of the allowlisted values.
- `expected` must be sanitized and must retain the existing expected-state
  semantics for contacts follow-up, mobile reminders, and mobile draft replies.
- Verification result names remain unchanged in this plan so quality reports and
  tests remain stable.

### `TaskContract`

Internal aggregate passed through execution and verification boundaries.

Expected fields:

```python
@dataclass(frozen=True)
class TaskContract:
    intent: TaskIntent
    policy_hint: PolicyHint
    expected_outcome: ExpectedOutcome
    expected_state: tuple[ExpectedStateCheck, ...] = ()
    compatibility: Mapping[str, object] = field(default_factory=dict)
```

Rules:

- Contract validation must reject missing intent, missing expected outcome,
  unsupported domains, unsupported state checks, unsafe values, and branch plans
  that fail the current branch contract.
- `compatibility` may contain only stable compatibility fields needed to rebuild
  a `CandidateTask` during this plan. It must not become a dumping ground for
  new behavior.

## File Map

- Create `synthesis/task_contracts.py`:
  dataclasses, conversion helpers, validation helpers, safety checks, and
  compatibility export helpers.
- Modify `synthesis/tasks.py`:
  add a `contract()` compatibility method or helper import path for
  `CandidateTask`, and update deterministic contacts generation only where
  needed to make domain/task-type conversion explicit.
- Modify `synthesis/mobile_tasks.py`:
  route scripted mobile policy generation through contract-aware helpers while
  keeping `scripted_mobile_solution_policy(task: CandidateTask)` compatible.
- Modify `synthesis/execution.py`:
  route scripted contacts policy generation through contract-aware helpers while
  keeping `execute_candidate(task: CandidateTask, ...)` compatible.
- Modify `synthesis/verification.py`:
  add contract-aware expected-answer and expected-state verification helpers
  while preserving `ExactAnswerVerifier.verify(task: CandidateTask, ...)`.
- Modify `synthesis/candidate_processing.py`:
  convert validated `CandidateTask` records into `TaskContract` once per
  candidate attempt and pass the contract to policy/verification helpers where
  supported.
- Modify `synthesis/episodes.py` only if episode construction needs to accept a
  contract-derived identity or summary. Do not add task instructions, expected
  answers, or expected state to episode exports.
- Modify `synthesis/contracts.py` only if reusable allowlists or safety
  validation helpers should be centralized. Prefer keeping task-contract-only
  rules in `synthesis.task_contracts` unless other modules need them.
- Add `tests/test_task_contracts.py`.
- Extend `tests/test_mobile_pipeline.py`, `tests/test_foundation_pipeline.py`,
  `tests/test_candidate_processing.py`, `tests/test_episode_quality.py`, and
  `tests/test_episode_replay.py`.
- Update [../../DESIGN.md](../../DESIGN.md),
  [../../DATA.md](../../DATA.md), [../../BACKEND.md](../../BACKEND.md),
  [../../ROADMAP.md](../../ROADMAP.md),
  [../../generated/mobile-domain-pipeline-pressure.md](../../generated/mobile-domain-pipeline-pressure.md),
  [../indexes/0025-awm-runtime-boundary-and-shared-environment-kernel.md](../indexes/0025-awm-runtime-boundary-and-shared-environment-kernel.md),
  [README.md](README.md), and [../../PLANS.md](../../PLANS.md).

## Implementation Tasks

### Task 1: Add Task-Contract Unit Tests

- [x] Add `tests/test_task_contracts.py`.
- [x] Add `test_contacts_candidate_converts_to_task_contract`:
  build `candidate_contacts_alice` from `generate_foundation_candidates`,
  convert it with `task_contract_from_candidate`, and assert:
  - `intent.domain_id == "contacts_fixture"`;
  - `intent.task_type == "contact_lookup"`;
  - `policy_hint.primary_tool == "lookup_contact_email"`;
  - `policy_hint.primary_arguments == {"name": "Alice Zhang"}`;
  - `expected_outcome.final_answer_contains == "alice.zhang@example.test"`;
  - `expected_state == ()`.
- [x] Add `test_contacts_followup_preserves_state_check`:
  convert `candidate_contacts_alice_followup` and assert one state check with
  `check_type == "contact_followup"` and expected name/note values unchanged.
- [x] Add `test_mobile_candidates_convert_to_domain_specific_contracts`:
  convert `candidate_mobile_maya_reminder` and
  `candidate_mobile_alex_draft_reply`, then assert:
  - both intents use `domain_id == "mobile_messages_fixture"`;
  - reminder state check type is `mobile_reminder`;
  - draft state check type is `mobile_draft_reply`;
  - required mobile tools are preserved in `PolicyHint.required_tools`.
- [x] Add `test_branch_plan_policy_hint_validates_existing_branch_contract`:
  convert `candidate_mobile_delivery_branch_fallback`, validate the contract,
  then mutate `branch_plan["schema_version"]` to an unsupported value and assert
  `ContractValidationError`.
- [x] Add `test_task_contract_rejects_unsafe_values`:
  create a contract whose `policy_hint.primary_arguments` contains
  `{"api_key": "secret-test-key"}` and assert validation rejects it.
- [x] Run:

```bash
uv run python -m unittest tests.test_task_contracts
```

Expected result: tests fail because `synthesis.task_contracts` does not exist.

### Task 2: Implement `synthesis.task_contracts`

- [x] Create `synthesis/task_contracts.py`.
- [x] Add `TaskIntent`, `PolicyHint`, `ExpectedOutcome`,
  `ExpectedStateCheck`, and `TaskContract` dataclasses with frozen instances.
- [x] Add allowlists:
  - `SUPPORTED_TASK_CONTRACT_DOMAINS = ("contacts_fixture", "mobile_messages_fixture")`;
  - `SUPPORTED_EXPECTED_STATE_CHECKS = ("contact_followup", "mobile_reminder", "mobile_draft_reply")`.
- [x] Add `task_contract_from_candidate(candidate: CandidateTask) -> TaskContract`.
  Conversion rules:
  - contacts seed domains `contacts` and `contacts_fixture` normalize to
    `contacts_fixture`;
  - mobile constraints domain `mobile_messages_fixture` normalizes to
    `mobile_messages_fixture`;
  - missing contacts task type with `lookup_contact_email` becomes
    `contact_lookup`;
  - `constraints["task_type"]` wins when present;
  - `constraints["required_tools"]` wins when present, otherwise use
    `candidate.tool_name`;
  - `candidate.tool_name` and `candidate.arguments` become the primary policy
    hint;
  - `candidate.expected_answer` becomes `ExpectedOutcome.final_answer_contains`;
  - each supported key in `candidate.expected_state` becomes one
    `ExpectedStateCheck`.
- [x] Add `validate_task_contract(contract: TaskContract) -> TaskContract`.
  It should return the contract on success and raise `ContractValidationError`
  on invalid or unsafe records.
- [x] Add `candidate_from_task_contract(contract: TaskContract) -> CandidateTask`
  only for compatibility tests. It should reconstruct fields from
  `contract.compatibility` and validated contract data.
- [x] Add local safety checks matching existing runtime/episode rules:
  reject keys or string values that include API keys, authorization, credentials,
  provider payloads, provider prompts, raw payload/source values, profile paths,
  absolute paths, `/Users/`, `/private/`, `/tmp/`, `sk-live`, `sk-test`, or
  `secret-test-key`.
- [x] Run:

```bash
uv run python -m unittest tests.test_task_contracts
```

Expected result: task-contract tests pass.

### Task 3: Add Candidate Compatibility Entry Point

- [x] Modify `synthesis/tasks.py`.
- [x] Add a small method on `CandidateTask`:

```python
def contract(self) -> "TaskContract":
    from synthesis.task_contracts import task_contract_from_candidate

    return task_contract_from_candidate(self)
```

- [x] Add `test_candidate_task_contract_method_matches_converter` to
  `tests/test_task_contracts.py`:
  convert one contacts candidate with both `candidate.contract()` and
  `task_contract_from_candidate(candidate)` and assert equality.
- [x] Run:

```bash
uv run python -m unittest tests.test_task_contracts tests.test_contracts
```

Expected result: tests pass and no public candidate contract validation changes.

### Task 4: Make Scripted Contacts Policy Contract-Aware

- [x] Modify `synthesis/execution.py`.
- [x] Add `scripted_solution_policy_from_contract(contract: TaskContract) ->
  SolutionPolicy`.
- [x] Keep `scripted_solution_policy(task: CandidateTask) -> SolutionPolicy`
  as a compatibility wrapper that calls `task.contract()` and delegates to the
  contract-aware helper.
- [x] Implement contacts behavior from `TaskContract`:
  - branch plans still return a `SolutionPolicy` with `branch_plan`;
  - `task_type == "contact_followup"` still performs lookup plus
    `record_contact_followup`;
  - `compatibility["probe_case"] == "logical_support_failure"` still produces
    the existing logical-support failure behavior;
  - default contacts lookup still uses the primary tool, primary arguments, and
    existing final-response template.
- [x] Add tests to `tests/test_task_contracts.py`:
  - `test_contacts_policy_from_contract_matches_existing_lookup_policy`;
  - `test_contacts_followup_policy_from_contract_keeps_state_change_step`.
- [x] Run:

```bash
uv run python -m unittest tests.test_task_contracts tests.test_foundation_pipeline tests.test_candidate_processing
```

Expected result: tests pass with unchanged contacts pipeline behavior.

### Task 5: Make Scripted Mobile Policy Contract-Aware

- [x] Modify `synthesis/mobile_tasks.py`.
- [x] Add `scripted_mobile_solution_policy_from_contract(contract:
  TaskContract) -> SolutionPolicy`.
- [x] Keep `scripted_mobile_solution_policy(task: CandidateTask) ->
  SolutionPolicy` as a compatibility wrapper that calls `task.contract()`.
- [x] Implement mobile behavior from contract values:
  - branch plans still return a branch-plan policy;
  - `mobile_message_to_reminder` still performs search plus
    `create_phone_reminder`;
  - `mobile_draft_reply` still performs search plus `draft_message_reply`;
  - default mobile lookup still searches messages and returns the existing
    message-found final response.
- [x] Add tests to `tests/test_task_contracts.py`:
  - `test_mobile_reminder_policy_from_contract_keeps_two_steps`;
  - `test_mobile_draft_policy_from_contract_keeps_draft_step`;
  - `test_mobile_branch_policy_from_contract_keeps_branch_plan`.
- [x] Run:

```bash
uv run python -m unittest tests.test_task_contracts tests.test_mobile_pipeline
```

Expected result: tests pass with unchanged mobile pipeline behavior.

### Task 6: Make Verification Contract-Aware

- [x] Modify `synthesis/verification.py`.
- [x] Add `verify_contract(contract: TaskContract, execution:
  ExecutionResult, *, environment: Any | None = None) -> VerificationResult`.
- [x] Keep `ExactAnswerVerifier.verify(task: CandidateTask, execution:
  ExecutionResult, *, environment: Any | None = None)` compatible by converting
  `task.contract()` internally.
- [x] Move final-answer checking to read
  `contract.expected_outcome.final_answer_contains`.
- [x] Move state checking to iterate over `contract.expected_state` rather than
  branching on raw `CandidateTask.expected_state`.
- [x] Preserve existing check names:
  - `final_response_contains_expected_answer`;
  - `contact_followup_state_matches_expected`;
  - `mobile_reminder_state_matches_expected`;
  - `mobile_draft_reply_state_matches_expected`.
- [x] Add tests to `tests/test_task_contracts.py`:
  - `test_verifier_uses_expected_outcome_from_contract`;
  - `test_verifier_uses_mobile_state_check_from_contract`;
  - `test_verifier_rejects_unsupported_state_check`.
- [x] Run:

```bash
uv run python -m unittest tests.test_task_contracts tests.test_foundation_pipeline tests.test_mobile_pipeline
```

Expected result: tests pass and quality report check names remain stable.

### Task 7: Convert Once in Candidate Processing

- [x] Modify `synthesis/candidate_processing.py`.
- [x] After `validate_candidate_task(raw_task)` and `_ensure_generation_lineage`,
  compute `task_contract = task.contract()`.
- [x] Validate the contract before execution. If validation fails, return
  `assemble_candidate_schema_rejection(error=exc)` with the existing rejection
  path.
- [x] Pass `task_contract` to contract-aware policy or verification helpers only
  where the called APIs support it. Keep compatibility wrappers available so
  this task does not require a broad signature break.
- [x] Do not add `TaskContract`, `ExpectedOutcome`, or expected-state payloads
  to `ProvisionalCandidateOutcome`; the plan preserves current outcome and
  artifact shapes.
- [x] Add tests to `tests/test_candidate_processing.py`:
  - accepted contacts candidate still assembles the same sample task export;
  - invalid contract produces a schema rejection;
  - mobile accepted candidate still produces an internal episode log.
- [x] Run:

```bash
uv run python -m unittest tests.test_candidate_processing tests.test_foundation_pipeline tests.test_mobile_pipeline
```

Expected result: tests pass and default artifacts remain shape-compatible.

### Task 8: Guard Episode Quality and Replay Against Schema Drift

- [x] Extend `tests/test_episode_quality.py`.
- [x] Add a regression proving `episode_quality_report_v1` summaries still omit:
  `instruction`, `expected_answer`, `expected_state`, `arguments`,
  `observation`, and `content`.
- [x] Extend `tests/test_episode_replay.py`.
- [x] Add a regression proving `episode_replay_report_v1` summaries still omit:
  `instruction`, `expected_answer`, `expected_state`, `arguments`,
  `observation`, and `content`.
- [x] Keep `synthesis/episodes.py` unchanged unless a regression shows the
  contract split changed episode construction. If it must change, only pass
  contract-derived candidate or policy identity; do not export more task
  content.
- [x] Run:

```bash
uv run python -m unittest tests.test_episode_quality tests.test_episode_replay tests.test_episode_logs
```

Expected result: episode consumers pass and sanitized report shapes are
unchanged.

### Task 9: Preserve CLI and Artifact Compatibility

- [x] Run default contacts pipeline:

```bash
uv run python main.py --output-dir artifacts/foundation-task-contract-split
```

Expected result: command exits 0 and writes manifest, samples, rejections, and
quality report without episode artifacts unless requested.

- [x] Run mobile profile:

```bash
uv run python main.py --run-profile tests/fixtures/run_profiles/mobile-agent-fixture.json --output-dir artifacts/mobile-task-contract-split
```

Expected result: command exits 0 and accepted mobile samples still include
`environment.id: mobile_messages_fixture`.

- [x] Run episode replay profile:

```bash
uv run python main.py --run-profile tests/fixtures/run_profiles/mobile-agent-fixture.json --write-episode-quality-report --write-episode-replay-report --output-dir artifacts/mobile-task-contract-replay
```

Expected result: command exits 0 and writes `episodes.jsonl`,
`episode_quality_report.json`, and `episode_replay_report.json`.

- [x] Run CLI tests:

```bash
uv run python -m unittest tests.test_cli
```

Expected result: CLI tests pass.

### Task 10: Update Canonical Docs and Plan Evidence

- [x] Update [../../DESIGN.md](../../DESIGN.md):
  add a short note under Task Curriculum and Trajectory Execution that
  task-intent, policy hints, expected outcome, and expected state now have
  internal contracts while `CandidateTask` remains the compatibility wrapper.
- [x] Update [../../DATA.md](../../DATA.md):
  document that public sample/rejection schemas remain unchanged and internal
  task contracts are not exported by default.
- [x] Update [../../BACKEND.md](../../BACKEND.md):
  document that the synchronous pipeline converts candidate tasks to internal
  task contracts before execution/verification.
- [x] Update [../../ROADMAP.md](../../ROADMAP.md):
  add plan 0033 under Stage 4 as a pre-extraction contract split for future
  reward/RL/runtime consumers.
- [x] Update [../../generated/mobile-domain-pipeline-pressure.md](../../generated/mobile-domain-pipeline-pressure.md):
  move the `CandidateTask` split from unresolved to partially resolved, and
  keep reward labels, Agentic RL, external MCP, and mobile source-governed input
  unresolved.
- [x] Update
  [../indexes/0025-awm-runtime-boundary-and-shared-environment-kernel.md](../indexes/0025-awm-runtime-boundary-and-shared-environment-kernel.md):
  record plan 0033 as risk-reduction evidence for runtime extraction, but keep
  0025 deferred.
- [x] Update [../../PLANS.md](../../PLANS.md) and
  [README.md](README.md) when moving this plan to completed after acceptance.
  The accepted plan now lives in `completed/`, and the plan index points to the
  completed record.
- [x] Run:

```bash
uv run python scripts/validate_docs.py
```

Expected result: documentation validation passes.

### Task 11: Full Regression

- [x] Run focused unit tests:

```bash
uv run python -m unittest tests.test_task_contracts tests.test_candidate_processing tests.test_foundation_pipeline tests.test_mobile_pipeline tests.test_episode_quality tests.test_episode_replay tests.test_episode_logs tests.test_cli
```

Expected result: all focused tests pass.

- [x] Run the full suite:

```bash
uv run python -m unittest
```

Expected result: all tests pass.

- [x] Run docs validation:

```bash
uv run python scripts/validate_docs.py
```

Expected result: documentation validation passes.

## Validation

- `uv run python scripts/validate_docs.py`
- `uv run python -m unittest tests.test_task_contracts`
- `uv run python -m unittest tests.test_task_contracts tests.test_candidate_processing tests.test_foundation_pipeline tests.test_mobile_pipeline tests.test_episode_quality tests.test_episode_replay tests.test_episode_logs tests.test_cli`
- `uv run python -m unittest`
- `uv run python main.py --output-dir artifacts/foundation-task-contract-split`
- `uv run python main.py --run-profile tests/fixtures/run_profiles/mobile-agent-fixture.json --output-dir artifacts/mobile-task-contract-split`
- `uv run python main.py --run-profile tests/fixtures/run_profiles/mobile-agent-fixture.json --write-episode-quality-report --write-episode-replay-report --output-dir artifacts/mobile-task-contract-replay`

## Acceptance Criteria

- `CandidateTask` remains accepted by deterministic generators, LLM generators,
  task expansion, candidate processing, and public artifact assembly.
- New internal task contracts separate task intent, policy hints, expected final
  answer, and expected state.
- Contacts and mobile deterministic candidates convert to validated
  `TaskContract` records with domain-aware task types and state checks.
- Scripted contacts and mobile policies can be generated from the internal
  contract while existing compatibility wrappers keep public callers working.
- Verification reads expected answer and expected state through contract-aware
  helpers while preserving current verifier ids, versions, and check names.
- Default `samples.jsonl`, `rejections.jsonl`, `manifest.json`, and
  `quality_report.json` schemas do not change.
- `episode_log_v1`, `episode_quality_report_v1`, and
  `episode_replay_report_v1` do not gain raw task instructions, expected
  answers, expected state, provider payloads, credentials, source payloads, or
  host paths.
- Plan 0025 remains deferred, with this plan recorded as pre-extraction
  task/policy/verifier boundary evidence.
- Documentation validation and the full unit suite pass.

## Risks

- The compatibility layer can become permanent clutter. Keep `TaskContract`
  internal and document a later migration only after downstream consumers prove
  they need public schema changes.
- Over-splitting can add ceremony without behavior change. Limit this plan to
  current contacts/mobile needs and avoid richer verifier DSLs.
- Contract summaries can leak expected answers or state into episode reports.
  Add regression tests that episode quality/replay summaries stay sanitized.
- Refactoring policy generation can accidentally change deterministic
  trajectories. Compare contacts/mobile pipeline and episode replay behavior
  through focused regression tests.
- Moving validation rules into the wrong module can create new bounded-context
  coupling. Keep task-contract-specific validation in `synthesis.task_contracts`
  unless a rule is already shared by existing contracts.

## Notes

This plan improves architecture robustness and extensibility before larger
runtime work. It should make future reward-label export, Agentic RL rollout
collection, external MCP runtime integration, and eventual AWM runtime
extraction easier to reason about, but it deliberately does not implement those
features.
