# Plan 0045: Domain-Parameterized Multi-Batch Generation Reliability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make strict three-domain provider generation reliable and diagnosable
across repeated batches, without weakening task admission or treating domain
semantics as if every environment had the same generation complexity.

**Architecture:** Keep one shared fail-closed generation kernel, but make its
batch identity and diagnostic contracts explicit. Extend each domain task-type
specification with final-answer evidence ownership and expected-state tool
ownership, use domain-owned batch sizes, and require provider candidate IDs to
belong to a deterministic per-batch namespace.

**Tech Stack:** Python standard library (`dataclasses`, `json`, `typing`), the
existing `DomainGenerationSpec`, OpenAI-compatible provider and role registry,
domain tool registries and scripted policies, `unittest`, campaign evidence
contracts, and the documentation validator.

---

## Status

Completed on 2026-07-18.

Local implementation Tasks 1-7 are complete as of 2026-07-12. The authorized
sequential paid 30-candidate gate ran on 2026-07-17: contacts and mobile passed
generation admission, while workspace failed closed in batch 9 with fixed reason
`invalid_required_capabilities`. The plan remains active and representative
scale evidence was not built. Task 8A local remediation is complete as of
2026-07-17. The authorized `_30_v3` gate started on 2026-07-18: contacts passed,
but mobile accepted samples exposed missing fixture provenance, so the gate
stopped before workspace and scale evidence was not built. Task 8B local
remediation is complete. The authorized `_30_v4` gate then generated 30/30 in
all three domains with domain-correct accepted/rejected provenance, and the
representative scale evidence was built and validated. Its quality decision is
`improve_generation_or_verification`; generation reliability is complete while
contacts diversity and workspace verification quality remain follow-up work.

This plan follows completed
[Plan 0044](../completed/0044-representative-provider-schema-hardening.md) and
the paid 30-candidate campaign evidence under
`artifacts/representative-campaign-30/`.

## Evidence And Problem Statement

Plan 0044 established strict provider task contracts, fixed sanitized schema
reasons, five-candidate global batch ceilings, replayable grounding arguments,
explicit expected-state schemas, and truthful zero-accepted reporting. All
three domains passed independent two-candidate probes.

The first three-domain 30-candidate campaign then separated three different
failure classes:

- Contacts generated 30/30 and was representative-eligible, but accepted 18
  and rejected 12 exact duplicates. This is a quality/diversity signal, not a
  task-contract generation failure.
- Concurrent mobile and workspace calls exhausted provider retries with
  sanitized `ReadTimeout`. Serial reruns removed the transport failure.
- Serial mobile then failed fail-closed with `invalid_expected_state`.
- Serial workspace failed fail-closed with `duplicate_candidate_id`.

The two-candidate probes and 30-candidate failures show that module isolation is
working, but the shared generator does not yet model repeated-batch identity or
domain-specific contract complexity. Identical temperature-zero prompts have no
batch namespace, and the current fixed schema reason does not say which expected
state invariant failed.

## Scope

- Preserve one shared provider generation kernel and strict `TaskContract`
  admission.
- Add fixed sanitized schema details for expected-state failures and duplicate
  candidate IDs without persisting provider values.
- Add `invalid_candidate_id` to the closed schema-reason taxonomy.
- Give every provider batch a deterministic one-based ordinal and candidate-ID
  prefix; validate the prefix before admitting a record.
- Distinguish within-batch from across-batch candidate-ID collisions.
- Keep the global maximum at five, keep contacts batches at five, and set mobile
  and workspace domain batches to two.
- Make final-answer evidence source/fields and expected-state mutating-tool
  ownership explicit in every `DomainTaskTypeSpec`.
- Keep replayable grounding arguments paired with their observations and expose
  only prompt-safe domain contracts.
- Prove 30-candidate behavior with deterministic fake providers before any paid
  retry.
- Run paid retries serially and build representative scale evidence only after
  all three output directories validate.
- Update canonical backend, data, security, architecture/roadmap, and plan
  lifecycle documentation.

## Out Of Scope

- Accepting a partial provider batch after any record fails validation.
- Deleting unknown keys, coercing values, repairing expected state, renaming
  candidate IDs, or inventing final-answer evidence.
- Automatic retry of strict schema failures inside the same paid run.
- Persisting raw responses, excerpts, prompts, provider field values, grounding
  rows, credentials, headers, or provider-derived exception messages.
- Provider-specific structured-output capability negotiation.
- Embedding-based or semantic duplicate detection. Contacts exact-duplicate
  evidence may activate a later quality plan, but this plan does not implement
  that subsystem.
- Async queues or distributed orchestration. Paid verification remains serial.
- Contacts diversity repair or semantic duplicate detection. The 2026-07-17
  campaign confirms this remains a follow-up quality concern rather than a
  generation-contract remediation item.

## Boundaries To Preserve

- `synthesis.domain_generation` owns generic batching, prompt construction,
  provider-output interpretation, and strict batch admission.
- Domain modules own tool order, grounding cases, expected-state ownership,
  final-answer evidence fields, and effective batch size.
- `synthesis.llm` owns the sanitized provider error envelope.
- `synthesis.datasets` copies only approved fixed diagnostics into rejection
  artifacts.
- `synthesis.contracts` owns all persisted reason/detail allowlists.
- `synthesis.candidate_processing` and domain scripted policies remain the
  execution boundary; the generator must not reproduce their implementation.
- A failed batch contributes zero candidates and cannot be representative
  evidence.
- Checked-in `run_profile_v3` profile JSON and profile config hashes remain
  unchanged.

## Contract Decisions

### Fixed Schema Detail

`DomainGenerationValidationError` and `LLMProviderError` gain an optional fixed
`schema_detail`. It is allowed only for the matching top-level reason:

```python
LLM_RESPONSE_SCHEMA_DETAILS = {
    "invalid_expected_state": {
        "expected_state_not_list",
        "expected_state_item_keys_mismatch",
        "expected_state_check_type_invalid",
        "expected_state_check_duplicate",
        "expected_state_expected_not_object",
        "expected_state_missing",
        "expected_state_arguments_invalid",
    },
    "duplicate_candidate_id": {
        "within_batch",
        "across_batch",
    },
    "invalid_candidate_id": {
        "batch_prefix_mismatch",
    },
}
```

The persisted generation-stage rejection may contain only the fixed reason and
detail. It must not contain the invalid ID, expected-state record, tool
arguments, field path from provider content, or caught exception message.

### Domain Task-Type Semantics

Extend `DomainTaskTypeSpec` without adding domain-name branches to the shared
generator:

```python
@dataclass(frozen=True)
class DomainTaskTypeSpec:
    task_type: str
    required_tools: tuple[str, ...]
    allowed_expected_state_checks: tuple[str, ...] = ()
    expected_state_tool: str | None = None
    final_answer_source: str = "primary_observation"
    final_answer_fields: tuple[str, ...] = ()
```

Allowed final-answer sources are `primary_observation` and
`state_tool_observation`. A read-only task must not declare
`expected_state_tool`. A mutating task must declare exactly one registered
state-mutating tool and at least one allowed expected-state check. Every final
answer field must be a non-empty safe identifier.

The three domains declare:

- Contacts lookup/follow-up: primary observation, field `email`.
- Mobile search/reminder/draft: primary observation, fields `message_id` and
  `snippet`; mutating tasks own `create_phone_reminder` or
  `draft_message_reply` respectively.
- Workspace search: primary observation, fields `item_id` and `summary`.
- Workspace task creation: state-tool observation, field `task_id`, owned by
  `create_workspace_task`.
- Workspace comment update: state-tool observation, field `comment_id`, owned by
  `add_workspace_comment`.

### Per-Batch Identity

Add an internal immutable batch context:

```python
@dataclass(frozen=True)
class DomainGenerationBatchContext:
    batch_index: int
    candidate_id_prefix: str


def build_generation_batch_context(
    spec: DomainGenerationSpec,
    *,
    batch_index: int,
) -> DomainGenerationBatchContext:
    safe_domain = spec.domain_id.removesuffix("_fixture")
    return DomainGenerationBatchContext(
        batch_index=batch_index,
        candidate_id_prefix=f"{safe_domain}_b{batch_index:03d}_",
    )
```

The prompt declares the exact prefix and forbids candidate IDs outside it. The
parser validates the prefix. Because every successful batch has a different
prefix and IDs remain unique within a batch, cross-batch identity collisions
become structurally impossible without weakening the existing global collision
check.

### Domain Batch Policy

`MAX_CANDIDATES_PER_CALL` remains `5`. Effective domain values become:

```text
contacts_fixture          5
mobile_messages_fixture   2
workspace_tasks_fixture   2
```

The choice is evidence-backed: all complex-domain two-candidate probes passed,
while five-record mobile/workspace campaign batches exposed nested-state and
identity adherence failures. Sanitized generation-spec metadata continues to
publish the effective value.

## File Map

- Modify `synthesis/contracts.py`
  - add `invalid_candidate_id`, the fixed detail mapping, and persisted
    rejection validation.
- Modify `synthesis/llm.py`
  - add optional `schema_detail` to `LLMProviderError`.
- Modify `synthesis/datasets.py`
  - copy a non-null fixed schema detail only.
- Modify `synthesis/domain_generation.py`
  - extend task-type semantics, add batch context/prefix validation, classify
    expected-state details, and pass effective domain batch contracts into the
    prompt.
- Modify `synthesis/tasks.py`
  - declare contacts final-answer evidence and retain batch size five.
- Modify `synthesis/mobile_tasks.py`
  - declare mobile evidence/state ownership and batch size two.
- Modify `synthesis/workspace_tasks.py`
  - declare workspace evidence/state ownership and batch size two.
- Modify `synthesis/pipeline.py`
  - preserve sanitized batch index/requested-count evidence on generation-stage
    failures if the shared generator does not already attach it.
- Modify `tests/test_contracts.py`
  - cover reason/detail allowlists and forbidden combinations.
- Modify `tests/test_llm_provider.py`
  - cover optional error-envelope compatibility.
- Modify `tests/test_domain_generation.py`
  - cover semantic specs, batch namespaces, expected-state details, domain batch
    sizes, and 30-candidate multi-batch generation.
- Modify `tests/test_cli.py`
  - cover sanitized failed-batch metadata and full report-chain behavior.
- Modify `docs/ARCHITECTURE.md`, `docs/BACKEND.md`, `docs/DATA.md`,
  `docs/SECURITY.md`, and `docs/ROADMAP.md`
  - document parameterized domain semantics and multi-batch identity.
- Modify `AGENTS.md`, `docs/README.md`, `docs/PLANS.md`, and plan indexes
  - maintain lifecycle navigation.

## Implementation Tasks

### Task 1: Add Fixed Diagnostic Details

**Files:**

- Modify: `synthesis/contracts.py`
- Modify: `synthesis/llm.py`
- Modify: `synthesis/datasets.py`
- Test: `tests/test_contracts.py`
- Test: `tests/test_llm_provider.py`

- [ ] **Step 1: Write failing reason/detail contract tests.**

  Add table tests that accept every declared `(schema_reason, schema_detail)`
  pair and reject:

  ```python
  invalid_pairs = (
      ("invalid_expected_state", "across_batch"),
      ("duplicate_candidate_id", "expected_state_missing"),
      ("invalid_candidate_id", "within_batch"),
      ("invalid_expected_state", "provider_returned_bad_state"),
  )
  ```

  Assert `schema_detail` is forbidden on `llm_provider_error`, and assert an
  `LLMProviderError` constructed with
  `schema_detail="expected_state_missing"` preserves only that fixed value in
  `assemble_generation_stage_rejection()`.

- [ ] **Step 2: Run focused tests and verify RED.**

  ```bash
  uv run python -m unittest tests.test_contracts tests.test_llm_provider
  ```

  Expected: failures show that `invalid_candidate_id`, `schema_detail`, and the
  detail mapping do not exist.

- [ ] **Step 3: Add the closed detail mapping and optional error field.**

  Implement the exact `LLM_RESPONSE_SCHEMA_DETAILS` mapping from Contract
  Decisions, add `invalid_candidate_id` to `LLM_RESPONSE_SCHEMA_REASONS`, and
  extend the provider error constructor:

  ```python
  def __init__(
      self,
      *,
      cause: str = "llm_provider_error",
      error_class: str = "LLMProviderError",
      retryable: bool = False,
      retry_count: int = 0,
      lineage: dict[str, object] | None = None,
      schema_reason: str | None = None,
      schema_detail: str | None = None,
  ) -> None:
      ...
      self.schema_reason = schema_reason
      self.schema_detail = schema_detail
  ```

- [ ] **Step 4: Persist and validate only matching fixed details.**

  In `assemble_generation_stage_rejection`, add `schema_detail` only when
  non-null. In `validate_rejection_record`, reject a detail unless it belongs to
  `LLM_RESPONSE_SCHEMA_DETAILS[schema_reason]`; forbid details on all other
  rejection causes.

- [ ] **Step 5: Run focused tests and verify GREEN.**

  Run the command from Step 2. Expected: all tests pass and existing schema
  reasons without a detail remain source-compatible.

- [ ] **Step 6: Commit the diagnostic contract.**

  ```bash
  git add synthesis/contracts.py synthesis/llm.py synthesis/datasets.py tests/test_contracts.py tests/test_llm_provider.py
  git commit -m "feat: add sanitized generation schema details"
  ```

### Task 2: Make Domain Task Semantics Explicit

**Files:**

- Modify: `synthesis/domain_generation.py`
- Modify: `synthesis/tasks.py`
- Modify: `synthesis/mobile_tasks.py`
- Modify: `synthesis/workspace_tasks.py`
- Test: `tests/test_domain_generation.py`
- Test: `tests/test_mobile_pipeline.py`
- Test: `tests/test_workspace_pipeline.py`

- [ ] **Step 1: Write failing semantic-spec tests.**

  For every domain bundle, assert each task type declares non-empty
  `final_answer_fields`; mutating types declare the exact mutating tool; and
  read-only types declare no expected-state tool. Parse the prompt and assert
  every `task_type_contract` contains:

  ```python
  {
      "final_answer": {
          "source": task_type.final_answer_source,
          "allowed_fields": list(task_type.final_answer_fields),
          "invented_text_allowed": False,
      },
      "expected_state_tool": task_type.expected_state_tool,
  }
  ```

  Add mobile/workspace policy tests proving the declared evidence field appears
  in the final response and in the selected observation source.

- [ ] **Step 2: Run focused tests and verify RED.**

  ```bash
  uv run python -m unittest tests.test_domain_generation tests.test_mobile_pipeline tests.test_workspace_pipeline
  ```

  Expected: `DomainTaskTypeSpec` lacks the semantic fields and prompt records do
  not expose them.

- [ ] **Step 3: Extend `DomainTaskTypeSpec` and validate invariants.**

  Add the fields from Contract Decisions. Define:

  ```python
  FINAL_ANSWER_SOURCES = {
      "primary_observation",
      "state_tool_observation",
  }
  ```

  Validation must require registered tools, a state-mutating
  `expected_state_tool` for mutating task types, no state tool for read-only
  types, an allowed final-answer source, and unique non-empty safe evidence
  fields.

- [ ] **Step 4: Populate every domain declaration exactly.**

  Use the mappings in Contract Decisions. Do not inspect `domain_id` in the
  shared prompt builder; it must consume only the task-type specification.

- [ ] **Step 5: Render semantic ownership in the prompt contract.**

  Replace the global final-answer prose rule with the per-task-type mapping from
  Step 1. Keep JSON-only output, exact record keys, replayable grounding
  arguments, and exact expected-state tool schemas.

- [ ] **Step 6: Run focused tests and verify GREEN.**

  Run the command from Step 2. Expected: all domain semantic specs validate and
  domain policies preserve their declared evidence.

- [ ] **Step 7: Commit domain semantics.**

  ```bash
  git add synthesis/domain_generation.py synthesis/tasks.py synthesis/mobile_tasks.py synthesis/workspace_tasks.py tests/test_domain_generation.py tests/test_mobile_pipeline.py tests/test_workspace_pipeline.py
  git commit -m "feat: declare domain generation evidence semantics"
  ```

### Task 3: Add Deterministic Per-Batch Candidate Identity

**Files:**

- Modify: `synthesis/domain_generation.py`
- Test: `tests/test_domain_generation.py`

- [ ] **Step 1: Write failing batch-context tests.**

  Add tests for indexes `1`, `2`, and `15` and assert prefixes:

  ```python
  assert build_generation_batch_context(spec, batch_index=1).candidate_id_prefix == "contacts_b001_"
  assert build_generation_batch_context(spec, batch_index=2).candidate_id_prefix == "contacts_b002_"
  assert build_generation_batch_context(spec, batch_index=15).candidate_id_prefix == "contacts_b015_"
  ```

  Reject zero, negative, and boolean indexes. Parse the prompt and assert the
  response contract requires the exact prefix.

- [ ] **Step 2: Write failing prefix-admission tests.**

  Starting from a valid record, assert `contacts_b001_task_01` passes batch 1,
  while `task_01` and `contacts_b002_task_01` raise:

  ```python
  DomainGenerationValidationError(
      "invalid_candidate_id",
      detail="batch_prefix_mismatch",
  )
  ```

  Assert two identical IDs in one response produce detail `within_batch` and a
  collision with a prior successful batch produces detail `across_batch`.

- [ ] **Step 3: Run focused tests and verify RED.**

  ```bash
  uv run python -m unittest tests.test_domain_generation
  ```

  Expected: batch context/prefix APIs and detail-aware exceptions are missing.

- [ ] **Step 4: Implement immutable batch context and prompt contract.**

  Implement `DomainGenerationBatchContext` and
  `build_generation_batch_context()` exactly as specified. Extend
  `build_domain_generation_prompt()` with a required `batch_context` keyword
  for generator calls and render:

  ```python
  "batch_context": {
      "batch_index": batch_context.batch_index,
      "candidate_id_prefix": batch_context.candidate_id_prefix,
  }
  ```

  Add `starts_with` to the candidate-ID field contract and state that alternative
  prefixes are forbidden.

- [ ] **Step 5: Validate prefix and classify collision location.**

  Pass `candidate_id_prefix` through parser functions. Validate it immediately
  after reading a non-empty candidate ID. Raise fixed detail `within_batch` in
  `parse_domain_task_contracts`; retain the global `candidate_ids` set in
  `generate_domain_llm_candidates` and raise `across_batch` there.

- [ ] **Step 6: Make every generator call batch-aware.**

  Derive `batch_index = provider_call_count + 1` before invoking the registry.
  Add only `batch_index` and `requested_candidate_count` to the sanitized error
  lineage; never add prior IDs or the provider response.

- [ ] **Step 7: Run focused tests and verify GREEN.**

  Run the command from Step 3. Expected: all tests pass and 30 candidates from a
  deterministic temperature-zero fake provider have unique batch-prefixed IDs.

- [ ] **Step 8: Commit batch identity.**

  ```bash
  git add synthesis/domain_generation.py tests/test_domain_generation.py
  git commit -m "feat: namespace provider candidates by batch"
  ```

### Task 4: Classify Expected-State Failures Precisely

**Files:**

- Modify: `synthesis/domain_generation.py`
- Test: `tests/test_domain_generation.py`
- Test: `tests/test_cli.py`

- [ ] **Step 1: Add one failing fixture per expected-state detail.**

  Use a valid mobile reminder record and mutate exactly one property for each
  detail: non-list state, wrong item keys, unsupported check type, duplicated
  check, non-object expected value, missing state, and tool-schema-invalid
  expected arguments. Assert the top-level reason remains
  `invalid_expected_state` except `expected_state_arguments_invalid`, which also
  remains subordinate to that reason rather than changing to
  `invalid_tool_arguments`.

- [ ] **Step 2: Add a CLI redaction regression.**

  Inject a marker into an invalid expected-state record. Assert the rejection
  contains only the fixed reason/detail plus existing sanitized lineage and does
  not contain the marker, expected-state mapping, prompt, grounding values, or
  original exception text.

- [ ] **Step 3: Run focused tests and verify RED.**

  ```bash
  uv run python -m unittest tests.test_domain_generation tests.test_cli
  ```

  Expected: all expected-state failures currently collapse to one reason without
  a fixed detail.

- [ ] **Step 4: Raise details at the nearest validation boundary.**

  Update `_provider_expected_state()` so each branch raises the exact detail from
  Task 1. Retain the lower-level exception only as in-memory `__cause__`. Do not
  format the invalid check type, index, keys, or argument values into the public
  exception.

- [ ] **Step 5: Run focused tests and verify GREEN.**

  Run the command from Step 3. Expected: every detail is stable and persisted
  artifacts remain redacted.

- [ ] **Step 6: Commit expected-state diagnostics.**

  ```bash
  git add synthesis/domain_generation.py tests/test_domain_generation.py tests/test_cli.py
  git commit -m "feat: classify expected-state schema failures"
  ```

### Task 5: Apply Domain-Owned Batch Sizes

**Files:**

- Modify: `synthesis/tasks.py`
- Modify: `synthesis/mobile_tasks.py`
- Modify: `synthesis/workspace_tasks.py`
- Test: `tests/test_domain_generation.py`
- Test: `tests/test_run_profiles.py`
- Test: `tests/test_scale_evidence.py`

- [ ] **Step 1: Write failing domain batch-policy tests.**

  Assert effective values are contacts `5`, mobile `2`, and workspace `2`.
  Drive target `30` with a prefix-aware fake provider and assert request sizes:

  ```python
  {
      "contacts_fixture": [5, 5, 5, 5, 5, 5],
      "mobile_messages_fixture": [2] * 15,
      "workspace_tasks_fixture": [2] * 15,
  }
  ```

  Assert all 30 IDs are unique and every request's prefix matches its one-based
  batch index.

- [ ] **Step 2: Run focused tests and verify RED.**

  ```bash
  uv run python -m unittest tests.test_domain_generation tests.test_run_profiles tests.test_scale_evidence
  ```

  Expected: mobile/workspace still export five and repeated calls lack distinct
  batch prefixes.

- [ ] **Step 3: Set domain-owned effective limits.**

  Keep contacts `max_candidates_per_call=5`. Set mobile and workspace to `2`
  directly in their generation-spec builders. Do not lower the shared global
  ceiling and do not change checked-in run profiles.

- [ ] **Step 4: Run focused tests and verify GREEN.**

  Run the command from Step 2. Expected: all tests pass and checked-in v3 profile
  hashes remain stable.

- [ ] **Step 5: Commit domain batch policies.**

  ```bash
  git add synthesis/tasks.py synthesis/mobile_tasks.py synthesis/workspace_tasks.py tests/test_domain_generation.py tests/test_run_profiles.py tests/test_scale_evidence.py
  git commit -m "fix: bound complex domain provider batches"
  ```

### Task 6: Prove The 30-Candidate Path Locally

**Files:**

- Modify: `tests/test_domain_generation.py`
- Modify: `tests/test_cli.py`

- [ ] **Step 1: Add a deterministic multi-batch provider.**

  Implement a test-only client that parses `batch_context.candidate_id_prefix`
  and emits exactly the requested count with valid domain records. It must return
  the same semantic template for identical prompts so the test proves changing
  batch context, not model randomness, prevents identity collisions.

- [ ] **Step 2: Cover all three 30-candidate domains.**

  Run each supported domain through `generate_domain_llm_candidates` and assert:

  ```python
  result.target_candidate_count == 30
  result.generated_candidate_count == 30
  len({candidate.candidate_id for candidate in result.candidates}) == 30
  ```

  Assert the exact provider-call counts are 6, 15, and 15.

- [ ] **Step 3: Preserve fail-closed behavior.**

  Make batch 3 emit one wrong prefix and assert the complete generation raises
  `llm_response_schema_error` with reason `invalid_candidate_id`, detail
  `batch_prefix_mismatch`, batch index `3`, and no partial candidates or provider
  values in the resulting rejection.

- [ ] **Step 4: Run focused tests.**

  ```bash
  uv run python -m unittest tests.test_domain_generation tests.test_cli
  ```

  Expected: all local 30-candidate paths pass and the injected failure remains
  fail-closed and redacted.

- [ ] **Step 5: Commit multi-batch regression coverage.**

  ```bash
  git add tests/test_domain_generation.py tests/test_cli.py
  git commit -m "test: cover strict 30-candidate generation"
  ```

### Task 7: Update Canonical Documentation And Verify

**Files:**

- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/BACKEND.md`
- Modify: `docs/DATA.md`
- Modify: `docs/SECURITY.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/README.md`
- Modify: `docs/PLANS.md`
- Modify: `docs/exec-plans/active/README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Document the parameterized kernel boundary.**

  State that code ownership is decoupled while domain semantics remain explicit
  data. Document task-type evidence ownership, expected-state tool ownership,
  deterministic batch prefixes, domain batch sizes, and fixed schema details.

- [ ] **Step 2: Document security and failure semantics.**

  Reaffirm that no raw response, prior candidate IDs, prompt, grounding row,
  provider value, or exception message is persisted. State that batch index,
  requested count, fixed reason, and fixed detail are allowed diagnostics.

- [ ] **Step 3: Run focused and complete tests.**

  ```bash
  uv run python -m unittest tests.test_domain_generation tests.test_llm_provider tests.test_contracts tests.test_run_profiles tests.test_scale_evidence tests.test_cli
  uv run python -m unittest
  ```

  Expected: both commands exit zero.

- [ ] **Step 4: Validate documentation and scan retained material.**

  ```bash
  uv run python scripts/validate_docs.py
  rg -n "provider_payload|raw_payload|Authorization:|Bearer [A-Za-z0-9._-]+|AGENT_DATA_API_KEY=" tests docs synthesis
  ```

  Expected: documentation validation passes; scan matches are limited to
  intentional denylist fixtures, security policies, and validators.

- [ ] **Step 5: Commit implementation documentation.**

  ```bash
  git add AGENTS.md docs/ARCHITECTURE.md docs/BACKEND.md docs/DATA.md docs/SECURITY.md docs/ROADMAP.md docs/README.md docs/PLANS.md docs/exec-plans/active/README.md
  git commit -m "docs: document multi-batch generation reliability"
  ```

### Task 8: Run The Sequential Paid 30-Candidate Gate

**Runtime outputs:**

- Create: `artifacts/representative-campaign-30-v2/contacts-profile.json`
- Create: `artifacts/representative-campaign-30-v2/mobile-profile.json`
- Create: `artifacts/representative-campaign-30-v2/workspace-profile.json`
- Create: `artifacts/representative-campaign-30-v2/campaign.json`
- Create: `artifacts/representative-campaign-30-v2/contacts/`
- Create: `artifacts/representative-campaign-30-v2/mobile/`
- Create: `artifacts/representative-campaign-30-v2/workspace/`

- [x] **Step 1: Create fresh runtime-only profiles.**

  Derive them from the checked-in representative profiles, use target count 30,
  and use unique profile/dataset/seed IDs ending in `_30_v2`. Keep purpose
  `benchmark`, mode `llm`, and context policy `synthetic_fixture`.

- [x] **Step 2: Run contacts, mobile, and workspace serially.**

  For each domain run:

  ```bash
  uv run python main.py --run-profile <profile> --use-llm --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --write-release-quality-audit --output-dir <domain-output>
  ```

  Start the next domain only after the prior process exits and its artifacts
  validate. Stop on any transport or generation-stage failure; do not
  automatically retry a strict schema failure.

- [ ] **Step 3: Require generation success, not 100% sample acceptance.**

  For each domain require exit zero, generated/target 30/30,
  `target_fulfilled=true`, `representative_eligible=true`, no generation-stage
  rejection, and valid requested reports. Candidate-level quality rejections are
  evidence and do not invalidate generation success.

- [x] **Step 4: Audit successful artifacts.**

  Validate samples, rejections, manifest, evaluation, profile decision, dataset
  release, and release audit. Scan for prompts, raw responses, grounding payloads,
  authorization data, credentials, and local paths.

- [ ] **Step 5: Build representative scale evidence.**

  ```bash
  uv run python scripts/write_representative_scale_evidence.py \
    --campaign artifacts/representative-campaign-30-v2/campaign.json \
    --output artifacts/representative-campaign-30-v2/representative_scale_evidence.json
  ```

  Validate the evidence and record whether contacts duplicates activate a later
  diversity plan. Do not claim that generation success proves dataset quality.

### Task 8A: Remediate Paid-Gate Contract Findings

The 2026-07-17 paid gate exposed three bounded contract defects that must be
fixed before Task 8 can be retried. These are part of 0045 because they prevent
the implemented domain semantics and campaign evidence from matching runtime
behavior; contacts duplicate-quality remediation remains out of scope.

**Root-cause evidence:**

- Workspace stopped in batch 9 with `invalid_required_capabilities`. The prompt
  currently permits any non-empty unique capability strings instead of binding
  them to the selected task-type contract.
- All four mobile verification failures were draft-reply candidates whose
  expected answer was `message_id`; the scripted draft-reply final response
  contains `body` and primary-observation `snippet`, not `message_id`.
- Mobile and workspace rejections carried `bundle_contacts_fixture` because
  `run_foundation_pipeline()` constructs the contacts fixture source bundle for
  every domain when no explicit source bundle is supplied.

**Contract decisions:**

- Extend `DomainTaskTypeSpec` with a non-empty unique
  `required_capabilities: tuple[str, ...]`. Domain declarations own the exact
  values, the prompt renders them in each task-type contract, and provider
  records must match exactly. The shared generator must not infer capabilities
  from domain names.
- Add fixed `invalid_required_capabilities` details:
  `required_capabilities_not_list`, `required_capabilities_empty`,
  `required_capabilities_duplicate`, and
  `required_capabilities_contract_mismatch`. Persist only the fixed detail.
- Keep mobile search and reminder evidence fields `message_id` and `snippet`.
  Restrict mobile draft-reply primary-observation evidence to `snippet`, which
  is present in both the selected primary observation and actual final response.
- Parameterize the default fixture source bundle by normalized domain identity.
  Contacts retains its existing fixture IDs and hashes; mobile and workspace
  receive domain-correct source/bundle/origin identities. Source governance owns
  this mapping; the generation kernel remains domain-branch free.

**Files:**

- Modify: `synthesis/contracts.py`
- Modify: `synthesis/domain_generation.py`
- Modify: `synthesis/tasks.py`
- Modify: `synthesis/mobile_tasks.py`
- Modify: `synthesis/workspace_tasks.py`
- Modify: `synthesis/sources.py`
- Modify: `synthesis/pipeline.py`
- Test: `tests/test_contracts.py`
- Test: `tests/test_domain_generation.py`
- Test: `tests/test_mobile_pipeline.py`
- Test: `tests/test_foundation_pipeline.py`
- Test: `tests/test_cli.py`

- [x] **Step 1: Write failing capability ownership tests.**

  Assert every task type declares exact non-empty capabilities, the prompt binds
  them into `exact_record_values`, malformed list shapes receive the fixed
  detail, and well-formed mismatches receive
  `required_capabilities_contract_mismatch`.

- [x] **Step 2: Implement exact capability ownership and diagnostics.**

  Extend the immutable task-type spec, populate all domain declarations, render
  exact prompt values, validate provider records against the selected task type,
  and preserve the fixed detail through the sanitized rejection envelope.

- [x] **Step 3: Write failing mobile evidence-policy regression.**

  Construct a generated mobile draft-reply contract and prove every allowed
  final-answer field is present in the selected observation source and in the
  executed final response. The pre-fix `message_id` declaration must fail.

- [x] **Step 4: Restrict draft-reply evidence to executable fields.**

  Set mobile draft-reply allowed fields to `snippet` only. Keep search and
  reminder declarations unchanged and do not add mixed-source evidence unless a
  future design requires it.

- [x] **Step 5: Write failing domain fixture provenance tests.**

  Run contacts, mobile, and workspace fixture pipelines without explicit source
  bundles and assert rejection/source provenance uses the matching domain
  fixture identity. Preserve existing contacts fixture IDs and hashes.

- [x] **Step 6: Parameterize default fixture provenance.**

  Make `build_fixture_source_bundle()` accept the normalized domain identity and
  have `run_foundation_pipeline()` pass the selected seed domain. Reject unknown
  domains rather than silently attributing them to contacts.

- [x] **Step 7: Prove the remediation locally.**

  Run focused tests, all three deterministic 30-candidate paths, the complete
  unit suite, documentation validation, and retained-material scanning. Record
  exact counts before requesting authorization for any new paid gate.

- [ ] **Step 8: Re-run the paid gate under one code version.**

  After separate cost authorization, use fresh `_30_v3` profile/dataset/seed
  identities. Re-run contacts, mobile, and workspace serially because capability
  prompt contracts change for all domains. Build representative scale evidence
  only if every domain generates 30/30 with valid domain-correct provenance.

  The authorized `_30_v3` attempt stopped after mobile on 2026-07-18 because
  accepted mobile samples omitted fixture provenance. Do not reuse `_30_v3` for
  another paid attempt.

### Task 8B: Preserve Fixture Provenance Across Candidate Isolation

The `_30_v3` mobile run generated 30/30 and retained domain-correct provenance
on all eight rejections, but all 22 accepted samples omitted
`environment.source_provenance` and `lineage.source_provenance`. Contacts did
not exhibit this defect. Workspace was not called after the gate failed.

**Root cause:**

- Contacts fixture construction accepts source provenance and preserves it when
  rebuilding one isolated environment per candidate.
- Mobile and workspace fixture constructors created environments without the
  supplied provenance, and their `rebuild()` paths recreated fixture
  environments without forwarding provenance.
- The earlier Task 8A regression covered domain-correct generation-stage
  rejections but did not exercise an accepted sample through the isolated
  candidate-environment path.

**Files:**

- Modify: `synthesis/domain_pipeline.py`
- Modify: `synthesis/mobile_environment.py`
- Modify: `synthesis/workspace_environment.py`
- Test: `tests/test_foundation_pipeline.py`

- [x] **Step 1: Reproduce accepted-sample provenance loss.**

  Add an end-to-end three-domain regression requiring every accepted sample to
  carry the expected domain fixture bundle in both environment metadata and
  lineage. Verify RED only for mobile and workspace.

- [x] **Step 2: Preserve provenance through fixture construction and rebuild.**

  Make mobile and workspace fixture constructors accept the same optional
  domain-neutral provenance mapping as contacts. Pass it from the domain bundle
  and preserve it when rebuilding isolated per-candidate environments.

- [x] **Step 3: Verify the local repair.**

  Verify the new regression GREEN, run the related foundation/mobile/workspace
  and domain-boundary suite, then run the complete unit suite.

- [x] **Step 4: Run a fresh paid gate.**

  After separate cost authorization, create new `_30_v4`
  profile/dataset/seed identities and rerun all three domains serially. Do not
  mutate or reuse `_30_v3` artifacts. Build representative scale evidence only
  after all accepted samples and rejections have domain-correct provenance.

### Task 9: Close The Plan

**Files:**

- Move: `docs/exec-plans/active/0045-domain-parameterized-multi-batch-generation-reliability.md`
  to `docs/exec-plans/completed/0045-domain-parameterized-multi-batch-generation-reliability.md`
- Modify: `docs/PLANS.md`
- Modify: `docs/exec-plans/active/README.md`
- Modify: `docs/exec-plans/completed/README.md`
- Modify: `docs/README.md`
- Modify: `AGENTS.md`

- [x] **Step 1: Record exact completion evidence.**

  Record focused/full test counts, docs validation, each domain's provider-call
  count, generated/accepted/rejected counts, generation-contract decision,
  artifact directory, and representative-scale-evidence decision.

- [x] **Step 2: Move the plan and update lifecycle maps.**

  Mark the completion date and make 0045 the latest completed plan. If any paid
  domain failed, leave the plan active with its fixed reason/detail instead.

- [ ] **Step 3: Commit lifecycle closure.**

  ```bash
  git add AGENTS.md docs/README.md docs/PLANS.md docs/exec-plans/active/README.md docs/exec-plans/completed/README.md docs/exec-plans/completed/0045-domain-parameterized-multi-batch-generation-reliability.md
  git commit -m "docs: complete multi-batch generation reliability plan"
  ```

## Acceptance Criteria

- Shared generation code contains no contacts/mobile/workspace domain-name
  branches for evidence semantics.
- Every domain task type explicitly declares final-answer evidence ownership;
  mutating types explicitly declare their expected-state tool.
- Every domain task type explicitly declares exact required capabilities, and
  provider records match the selected task-type contract.
- Every provider batch has a deterministic, validated candidate-ID prefix.
- Duplicate IDs distinguish `within_batch` from `across_batch` without retaining
  the ID value.
- Expected-state failures emit one fixed sanitized detail without provider
  content.
- Contacts uses batches of five; mobile and workspace use batches of two.
- Deterministic fake providers generate 30 unique admitted candidates in every
  domain with exact target fulfillment.
- An invalid record still rejects its whole batch and contributes no partial
  representative evidence.
- Existing v1/v2 behavior and checked-in v3 profile hashes remain stable.
- Focused tests, full unit tests, documentation validation, and retained-material
  scans pass.
- Fresh serial paid contacts, mobile, and workspace runs each generate 30/30
  candidates with valid report chains before representative scale evidence is
  built.
- Default fixture provenance is domain-correct for contacts, mobile, and
  workspace in samples and rejections.
- Contacts exact duplicates remain visible as quality evidence rather than being
  confused with candidate-ID collisions.

## Completion Evidence

Local implementation evidence on 2026-07-12:

- The plan-focused suite passed 225 tests:
  `tests.test_domain_generation`, `tests.test_llm_provider`,
  `tests.test_contracts`, `tests.test_run_profiles`,
  `tests.test_scale_evidence`, and `tests.test_cli`.
- The complete unit suite passed 584 tests.
- `uv run python scripts/validate_docs.py` passed.
- The retained-material scan matched only intentional denylist fixtures,
  security policies, validators, and the scan commands recorded in plans.
- Deterministic fake-provider 30-candidate tests passed for contacts, mobile,
  and workspace with provider-call counts 6, 15, and 15 respectively. Each
  domain generated 30 unique batch-prefixed IDs and fulfilled its target.
- An injected batch-3 prefix mismatch failed closed with fixed reason/detail
  `invalid_candidate_id` / `batch_prefix_mismatch`; persisted rejection evidence
  retained only the sanitized batch index and requested count.

Authorized paid gate evidence on 2026-07-17:

- Runtime profiles and campaign input are under
  `artifacts/representative-campaign-30-v2/`; all four input contracts loaded
  successfully before provider calls.
- Contacts used 6 provider calls, generated 30/30, set
  `target_fulfilled=true` and `representative_eligible=true`, accepted 16, and
  rejected 14 exact duplicates as `quality_duplicate`. Its complete requested
  report chain validated under
  `artifacts/representative-campaign-30-v2/contacts/`.
- Mobile used 15 provider calls, generated 30/30, set `target_fulfilled=true`
  and `representative_eligible=true`, accepted 26, and rejected 4 candidates as
  `verification_failed`. Its complete requested report chain validated under
  `artifacts/representative-campaign-30-v2/mobile/`.
- Workspace stopped fail-closed in provider batch 9 with requested count 2,
  accepted 0, and wrote one generation-stage rejection with cause
  `llm_response_schema_error`, fixed reason `invalid_required_capabilities`, and
  no schema detail. No partial candidates were retained. The sanitized failure
  report chain validated under
  `artifacts/representative-campaign-30-v2/workspace/`.
- Retained-material scanning across the campaign found no prompt, raw provider
  payload, authorization value, credential, host path, or candidate-prefix
  material.
- `representative_scale_evidence.json` was intentionally not built because all
  three domains did not pass the generation contract gate. Contacts duplicate
  evidence remains a visible quality signal, but no campaign-level development
  recommendation is valid until workspace generation succeeds in a separately
  authorized run.

The completion condition was satisfied by `_30_v4`: workspace generation
succeeded and representative scale evidence was built and validated.

Task 8A local remediation evidence on 2026-07-17:

- Capability ownership tests failed before implementation because
  `DomainTaskTypeSpec` had no `required_capabilities`; task-type prompts and
  parsers now require exact domain-owned capability tuples.
- `invalid_required_capabilities` now emits only one of four fixed details:
  not-list, empty, duplicate, or contract-mismatch.
- The mobile draft evidence regression failed while `message_id` was allowed;
  it passes after restricting draft-reply primary evidence to `snippet`, which
  is present in both the primary observation and scripted final response.
- Domain fixture provenance tests failed because the builder accepted no domain
  and the pipeline passed none. They now prove contacts, mobile, and workspace
  source IDs, bundle IDs, origins, and rejection attribution are domain-correct
  while preserving existing contacts identity.
- The first full-suite run caught workspace-specific mapping in the shared
  `synthesis.sources` module. The mapping was moved to the allowed
  `synthesis.domain_sources` registration boundary; the shared builder now
  consumes a domain-neutral immutable identity.
- The Task 8A focused suite passed 247 tests and includes deterministic
  three-domain 30-candidate generation. The complete suite passed 587 tests.
- No new paid calls were made for Task 8A. Step 8 requires separate authorization
  and fresh `_30_v3` identities after documentation and retained-material checks
  pass.

Authorized `_30_v3` gate and Task 8B evidence on 2026-07-18:

- All three new runtime profiles and the campaign contract loaded successfully
  under `artifacts/representative-campaign-30-v3/` before provider calls.
- Contacts used the expected six provider batches, generated 30/30, set
  `target_fulfilled=true` and `representative_eligible=true`, accepted 14, and
  rejected 16 candidates: 14 `quality_duplicate` and two `tool_runtime_error`.
  Its report chain and `bundle_contacts_fixture` sample/rejection provenance
  validated.
- Mobile used the expected 15 provider batches, generated 30/30, accepted 22,
  and rejected eight: one `quality_duplicate` and seven `verification_failed`.
  Its report chain loaded and all rejection provenance was
  `bundle_mobile_messages_fixture`, but all accepted samples omitted source
  provenance. The gate therefore failed before workspace and no representative
  scale evidence was built.
- The new accepted-sample provenance regression failed only for mobile and
  workspace before implementation, then passed after fixture construction and
  isolated-environment rebuild preserved provenance.
- The related foundation/mobile/workspace/domain-boundary suite passed 57 tests.
  The complete suite passed 588 tests.
- `_30_v3` remains immutable failure evidence. The separately authorized fresh
  `_30_v4` paid gate is recorded below.

Authorized `_30_v4` completion evidence on 2026-07-18:

- All three runtime profiles and the campaign contract loaded successfully
  under `artifacts/representative-campaign-30-v4/` before provider calls.
- Contacts used six provider batches, generated 30/30, set
  `target_fulfilled=true` and `representative_eligible=true`, accepted eight,
  and rejected 22 as `quality_duplicate`. Accepted and rejected artifacts use
  `bundle_contacts_fixture` provenance.
- Mobile used 15 provider batches, generated 30/30, set
  `target_fulfilled=true` and `representative_eligible=true`, accepted 24, and
  rejected six: two `tool_runtime_error` and four `verification_failed`.
  Accepted and rejected artifacts use `bundle_mobile_messages_fixture`
  provenance.
- Workspace used 15 provider batches, generated 30/30, set
  `target_fulfilled=true` and `representative_eligible=true`, accepted nine,
  and rejected 21 as `verification_failed`. Accepted and rejected artifacts use
  `bundle_workspace_tasks_fixture` provenance.
- All three requested report chains validated. Retained-material scanning found
  no raw prompt/response, provider payload, authorization value, credential,
  host path, candidate-prefix contract, or batch context.
- `representative_scale_evidence.json` validated and classifies all three
  domains as `representative`. Its decision is
  `improve_generation_or_verification` because representative quality evidence
  requires remediation; contacts recorded 22 exact duplicates, while mobile
  and workspace recorded zero exact duplicates.
- The generation-reliability goal is complete. The evidence does not claim
  dataset-quality success and leaves contacts diversity plus workspace
  verification quality for follow-up planning.
