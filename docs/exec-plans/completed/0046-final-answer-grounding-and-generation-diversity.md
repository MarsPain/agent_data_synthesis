# Plan 0046: Final-Answer Grounding And Generation Diversity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Commit
> policy:** do not commit after individual tasks; all plan changes are
> committed once in Task 11 after the whole plan completes.

**Goal:** Remediate the two quality defects evidenced by the `_30_v4` paid gate:
workspace/mobile candidates rejected as `verification_failed` because provider
final answers are ungrounded, and contacts candidates rejected as
`quality_duplicate` because batch prompts carry no content-level diversity.

**Architecture:** Keep one shared fail-closed generation kernel. Make final
answers groundable by contract: primary-observation answers are validated
against grounding observation values at generation time, and
state-tool-observation answers are derived deterministically from validated
expected-state arguments instead of being predicted by the provider. Make batch
prompts vary by contract: deterministic per-batch task-type focus, grounding
windows, and prior-instruction exclusion lists, all declared as domain-owned
data and rendered by the shared prompt builder.

**Tech Stack:** Python standard library (`dataclasses`, `json`, `re`), the
existing `DomainGenerationSpec`/`DomainTaskTypeSpec`, OpenAI-compatible
provider and role registry, domain tool registries and scripted policies,
`unittest`, campaign evidence contracts, and the documentation validator.

---

## Status

Completed on 2026-07-19. This plan follows completed
[Plan 0045](0045-domain-parameterized-multi-batch-generation-reliability.md)
and the authorized `_30_v4` paid gate evidence under
`artifacts/representative-campaign-30-v4/`.

## Evidence And Problem Statement

The `_30_v4` gate generated 30/30 candidates in every domain with
domain-correct provenance, and its representative scale evidence classified all
three domains as `representative` with decision
`improve_generation_or_verification`. Two quality defects dominate:

**Defect 1 — ungrounded final answers.** Workspace accepted 9 and rejected 21,
all 21 on check `final_response_contains_expected_answer`. Every rejected
record's `final_answer_contains` is a literal field name (`item_id` x10,
`task_id` x8, `summary` x2, `comment_id` x1) instead of an observation value.
Mobile rejected 4 the same way (all `snippet`). Root causes:

- The prompt instruction "Copy final_answer_contains from an allowed field in
  the selected task type's declared observation source"
  (`synthesis/domain_generation.py:278`) is ambiguous; the provider copies the
  field identifier rather than resolving the field against grounding
  observations. The parser passes the value through with no semantic check
  (`synthesis/domain_generation.py:584-586`).
- For workspace mutating task types the correct answer is structurally
  unknowable to the provider: `final_answer_source` is
  `state_tool_observation`, but the prompt contains no state-tool observation,
  and the values are environment-minted IDs
  (`synthesis/workspace_environment.py:214,266`) derived from expected-state
  arguments the provider already supplies. All 9 mutating-type candidates in
  the gate failed.

**Defect 2 — no content diversity.** Contacts accepted 8 and rejected 22 as
`quality_duplicate` (worsening across campaigns: 12, then 16, then 22). Root
causes:

- The provider request hardcodes `"temperature": 0`
  (`synthesis/llm.py:139`) and every batch prompt is byte-identical except
  `batch_index`/`candidate_id_prefix`; v4 lineage shows ~93% provider prefix
  cache hits across batches.
- The contacts task space is saturated: the default fixture has exactly 2
  contacts (`synthesis/environments.py:92-93`), the spec has 2 task types, and
  arguments must be copied verbatim from grounding rows, so the legal space is
  ~4 combinations against a 30-candidate target.
- The merge-time duplicate signature
  (`synthesis/quality.py:89-101`) is exact normalized instruction plus tool
  sequence; it catches literal repeats only. Semantic dedup (TD-0002) remains
  deferred and is not this plan's scope.

Adjacent minor evidence: mobile recorded 2 `tool_runtime_error` rejections
from expected-state references that do not exist in grounding (for example an
invented `source_message_id`). These are the same ungrounded-value class and
are covered by the reference-grounding contract below.

## Scope

- Derive `final_answer_contains` deterministically for
  `state_tool_observation` task types from validated expected-state arguments;
  the provider emits an exact sentinel instead of predicting environment IDs.
- Reword the final-answer prompt rule and render per-task-type grounded
  field-to-value examples.
- Add a generation-stage grounding gate for primary-observation final answers
  with a new fixed reason `invalid_final_answer` and fixed details.
- Add bounded expected-state reference grounding for domain-declared reference
  fields with a new fixed `invalid_expected_state` detail.
- Add deterministic per-batch diversity axes: single-task-type focus rotation,
  domain-owned grounding windows, and bounded prior-instruction exclusion
  lists.
- Add a bounded optional provider temperature knob; the v5 gate keeps
  temperature 0 so mechanical axes are measured first.
- Enlarge the default contacts fixture additively so the representative task
  space exceeds the target count.
- Prove all behavior with deterministic fake providers before any paid call.
- Run one serial paid `_30_v5` gate and rebuild representative scale evidence.
- Update canonical backend, data, security, architecture/roadmap, and plan
  lifecycle documentation.

## Out Of Scope

- Semantic or embedding-based duplicate detection (TD-0002 stays deferred; its
  activation trigger remains dataset volume or curriculum-benchmark signals).
- Changing the merge-time duplicate signature or release admission rules.
- Auto-retry of strict schema failures inside a paid run; a failed batch still
  contributes zero candidates.
- Wiring seed transformation/task expansion into the representative path.
- Async queues or distributed orchestration (plan 0014 stays deferred).
- Changing checked-in `run_profile_v3` profile JSON or profile config hashes.
- Changing domain batch sizes (contacts 5, mobile 2, workspace 2 stay).
- Persisting prompts, raw responses, grounding rows, prior candidate IDs, or
  provider-derived exception text. Exclusion lists travel in prompts only;
  persisted lineage records counts, not text.
- Mobile `tool_runtime_error` remediation beyond the reference-grounding gate.

## Boundaries To Preserve

- `synthesis.domain_generation` owns generic batching, prompt construction,
  provider-output interpretation, derivation mechanics, diversity axes, and
  strict batch admission. No domain-name branches.
- Domain modules own tool order, grounding cases, task-type declarations,
  derivation templates, reference-field declarations, and grounding window
  sizes as data.
- `synthesis.workspace_environment` owns ID minting; the shared slugify
  primitive lives in one neutral module imported by both sides.
- `synthesis.llm` owns the sanitized provider error envelope and the bounded
  temperature configuration surface.
- `synthesis.contracts` owns all persisted reason/detail allowlists.
- `synthesis.candidate_processing` and domain scripted policies remain the
  execution boundary; the generator must not reproduce their implementation.
- Checked-in `run_profile_v3` profile JSON and profile config hashes remain
  unchanged.

## Contract Decisions

### Derived Final Answers For State-Tool-Observation Types

Extend `DomainTaskTypeSpec` with an optional derivation template:

```python
@dataclass(frozen=True)
class DomainTaskTypeSpec:
    task_type: str
    required_tools: tuple[str, ...]
    allowed_expected_state_checks: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ()
    expected_state_tool: str | None = None
    final_answer_source: str = "primary_observation"
    final_answer_fields: tuple[str, ...] = ()
    final_answer_derivation: str | None = None
```

- `final_answer_derivation` is allowed only when
  `final_answer_source == "state_tool_observation"`; when present it must be a
  non-empty template whose placeholders reference fields of the mutating
  tool's argument schema.
- Placeholder syntax: `{field}` copies the expected-state value verbatim;
  `{field|stable_id}` applies the shared slugify transform (lowercase,
  alphanumeric characters kept, everything else becomes `_`, leading/trailing
  `_` stripped). These are the only two transforms.
- Workspace declarations become
  `task_{title|stable_id}` for `workspace_task_creation` and
  `comment_{task_id}_{comment|stable_id}` for `workspace_comment_update`,
  exactly matching environment minting
  (`synthesis/workspace_environment.py:214,266`).
- Move the slugify rule into one neutral module (for example
  `synthesis/stable_ids.py`) imported by both `synthesis.workspace_environment`
  and `synthesis.domain_generation`, so minting and derivation cannot drift.
- Provider contract for derived types: the prompt renders
  `"value_contract": "sentinel"` in the task type's `final_answer` block and
  the record must contain the exact literal
  `DERIVED_FINAL_ANSWER_SENTINEL = "$derived_from_expected_state$"`.
  Anything else fails with `invalid_final_answer` /
  `final_answer_sentinel_mismatch`. After expected-state validation succeeds,
  the parser replaces the sentinel with the derived value; derivation failure
  fails closed with `invalid_final_answer` /
  `final_answer_derivation_failed`.
- Contacts and mobile keep primary-observation answers and declare no
  derivation.

### Grounded Final-Answer Prompt Contract

Replace the ambiguous prose rule with an explicit value-resolution rule:

- For primary-observation types: "`final_answer_contains` must be a substring
  copied from the `observation` value of one `grounding_context` entry, using
  one of the declared `allowed_fields`; copying the field name itself is
  forbidden."
- Each task type's prompt block gains a `final_answer.example` mapping built
  from the first grounding entry, for example
  `{"field": "item_id", "value": "project_alpha"}`.

### Generation-Stage Final-Answer Grounding Gate

Add `invalid_final_answer` to `LLM_RESPONSE_SCHEMA_REASONS` with details:

```python
"invalid_final_answer": {
    "final_answer_field_name_literal",
    "final_answer_not_grounded",
    "final_answer_sentinel_mismatch",
    "final_answer_derivation_failed",
}
```

For primary-observation task types, `task_contract_from_provider_record`
rejects a record whose `final_answer_contains` equals a declared field name
(`final_answer_field_name_literal`) or is not a substring of any grounding
observation value under the declared allowed fields
(`final_answer_not_grounded`). The grounding walker is domain-neutral: it
collects string values from the `observation` mapping of every entry in every
top-level grounding list. Persist only the fixed reason/detail.

### Expected-State Reference Grounding

Extend `DomainTaskTypeSpec` with a bounded declaration:

```python
expected_state_reference_fields: tuple[tuple[str, str], ...] = ()
```

Each pair maps an expected-state field to a grounding observation field whose
values are legal references. Declarations:

- Mobile reminder: `(("source_message_id", "message_id"),)`.
- Mobile draft reply: `(("thread_id", "thread_id"),)`.
- Workspace comment update: `(("task_id", "item_id"),)`.

A declared reference value that appears in no grounding observation fails with
`invalid_expected_state` / `expected_state_reference_not_grounded`. Undeclared
fields remain unchecked. Persist only the fixed detail.

### Per-Batch Diversity Axes

The generation loop derives all axes deterministically from the spec and batch
index; no profile or CLI knobs:

- **Task-type focus rotation.** Batch `i` renders only the single task type
  `spec.task_types[(i - 1) % len(spec.task_types)]` in the prompt's
  `task_types` list. The parser still validates against the full spec.
- **Grounding window.** `DomainGenerationSpec` gains
  `grounding_window_size: int | None = None` (domain-owned; `None` disables
  sharding). When set and the grounding context has exactly one top-level list
  of entries, batch `i` renders only the window of that size starting at
  `((i - 1) * window_size) % entry_count` with wraparound. Sanitized spec
  metadata and `grounding_context_hash` continue to cover the full spec.
- **Exclusion list.** The prompt gains
  `"diversity_contract": {"excluded_instructions": [...]}` carrying the
  instructions of up to the 20 most recently admitted candidates, with the
  rule "do not repeat or paraphrase these instructions". Persisted batch
  lineage may record only `excluded_instruction_count`.
- Instruction text is **not** a parse-level rejection cause; exact repeats
  remain merge-time `quality_duplicate` evidence so one repeat cannot kill a
  paid batch.

Domain declarations: contacts `grounding_window_size=2` (after fixture
enlargement), mobile `2`, workspace `2`; focus rotation and exclusion lists
apply to all three domains.

### Bounded Temperature Knob

`LLMConfig` gains `temperature: float | None = None`, sourced from optional
`AGENT_DATA_LLM_TEMPERATURE`, validated to a finite float in `[0.0, 1.0]`;
invalid values raise `LLMConfigurationError`. When unset the request keeps
`"temperature": 0` (current behavior). Lineage gains a non-secret
`"temperature"` field; the config fingerprint and hash are unchanged. The v5
paid gate runs at temperature 0 so the mechanical axes are measured without a
confounding variable; residual duplicates at 0 motivate a separately
authorized non-zero follow-up.

### Contacts Fixture Enlargement

Add four contacts to the default fixture (`synthesis/environments.py`),
preserving the existing two rows byte-identically. Deterministic candidates,
held-out suites, and local profiles keep working against the original
entities; tests that assert exactly two contacts are updated to the enlarged
set. Grounding context grows to six rows, giving a legal task space of 6
entities x 2 task types with window-2 rotation across six batches.

## File Map

- Modify `synthesis/contracts.py`
  - add `invalid_final_answer` and its fixed details; add
    `expected_state_reference_not_grounded` to the `invalid_expected_state`
    detail set.
- Create `synthesis/stable_ids.py`
  - single shared slugify primitive.
- Modify `synthesis/workspace_environment.py`
  - import the shared slugify; minting output unchanged.
- Modify `synthesis/domain_generation.py`
  - spec/spec-field validation, derivation templates and sentinel parsing,
    grounding walker and final-answer gate, reference grounding, prompt
    rewording with examples, task-type focus, grounding windows, exclusion
    lists.
- Modify `synthesis/llm.py`
  - optional bounded `temperature` config and request plumbing.
- Modify `synthesis/tasks.py`, `synthesis/mobile_tasks.py`,
  `synthesis/workspace_tasks.py`
  - domain declarations: derivations, reference fields, window sizes.
- Modify `synthesis/environments.py`
  - additive contacts fixture rows.
- Modify `tests/test_contracts.py`, `tests/test_domain_generation.py`,
  `tests/test_llm_provider.py`, `tests/test_mobile_pipeline.py`,
  `tests/test_workspace_pipeline.py`, `tests/test_foundation_pipeline.py`,
  `tests/test_cli.py`, plus any fixture-size-asserting tests
  - cover new contracts and update enlargement ripples.
- Modify `docs/ARCHITECTURE.md`, `docs/BACKEND.md`, `docs/DATA.md`,
  `docs/SECURITY.md`, `docs/ROADMAP.md`, `docs/README.md`, `docs/PLANS.md`,
  `AGENTS.md`
  - document grounding and diversity contracts and lifecycle state.

## Implementation Tasks

### Task 1: Add Fixed Final-Answer And Reference Diagnostics

**Files:**

- Modify: `synthesis/contracts.py`
- Test: `tests/test_contracts.py`

- [x] **Step 1: Write failing taxonomy tests.**

  Accept every new `(reason, detail)` pair; reject cross-wired pairs such as
  `("invalid_final_answer", "within_batch")`,
  `("invalid_expected_state", "final_answer_not_grounded")`, and
  `("duplicate_candidate_id", "final_answer_sentinel_mismatch")`; assert
  rejection validation persists only matching fixed details.

- [x] **Step 2: Verify RED, implement, verify GREEN.**

  ```bash
  uv run python -m unittest tests.test_contracts
  ```

### Task 2: Derive State-Tool Final Answers Deterministically

**Files:**

- Create: `synthesis/stable_ids.py`
- Modify: `synthesis/workspace_environment.py`
- Modify: `synthesis/domain_generation.py`
- Modify: `synthesis/workspace_tasks.py`
- Test: `tests/test_domain_generation.py`
- Test: `tests/test_workspace_pipeline.py`

- [x] **Step 1: Write failing derivation tests.**

  Assert environment minting equals the shared slugify composition; assert
  workspace specs declare the exact derivation templates; assert a provider
  record with the sentinel yields the derived `task_id`/`comment_id`; assert
  any non-sentinel value fails with `final_answer_sentinel_mismatch`; assert
  derivation from invalid expected state fails with
  `final_answer_derivation_failed`.

- [x] **Step 2: Verify RED.**

  ```bash
  uv run python -m unittest tests.test_domain_generation tests.test_workspace_pipeline
  ```

- [x] **Step 3: Implement the shared slugify and derivation.**

  Create `synthesis/stable_ids.py`; rewire workspace minting to it (output
  unchanged); extend `DomainTaskTypeSpec` validation; render the sentinel
  contract in the prompt; derive after expected-state validation in
  `task_contract_from_provider_record`.

- [x] **Step 4: Verify GREEN.**

  ```bash
  uv run python -m unittest tests.test_domain_generation tests.test_workspace_pipeline
  ```

### Task 3: Ground Primary-Observation Final Answers

**Files:**

- Modify: `synthesis/domain_generation.py`
- Modify: `synthesis/tasks.py`
- Modify: `synthesis/mobile_tasks.py`
- Test: `tests/test_domain_generation.py`
- Test: `tests/test_mobile_pipeline.py`

- [x] **Step 1: Write failing grounding-gate tests.**

  For every domain: a record whose `final_answer_contains` equals a field name
  fails with `final_answer_field_name_literal`; a value absent from all
  grounding observations fails with `final_answer_not_grounded`; a value drawn
  from a grounding observation passes; assert the prompt renders the reworded
  rule and a per-task-type `final_answer.example`.

- [x] **Step 2: Verify RED, implement, verify GREEN.**

  ```bash
  uv run python -m unittest tests.test_domain_generation tests.test_mobile_pipeline
  ```

### Task 4: Ground Expected-State References

**Files:**

- Modify: `synthesis/domain_generation.py`
- Modify: `synthesis/mobile_tasks.py`
- Modify: `synthesis/workspace_tasks.py`
- Test: `tests/test_domain_generation.py`
- Test: `tests/test_mobile_pipeline.py`
- Test: `tests/test_workspace_pipeline.py`

- [x] **Step 1: Write failing reference tests.**

  Declared reference values absent from grounding fail with
  `invalid_expected_state` / `expected_state_reference_not_grounded`; values
  drawn from grounding pass; undeclared fields remain unchecked.

- [x] **Step 2: Verify RED, implement, verify GREEN.**

  ```bash
  uv run python -m unittest tests.test_domain_generation tests.test_mobile_pipeline tests.test_workspace_pipeline
  ```

### Task 5: Add Per-Batch Diversity Axes

**Files:**

- Modify: `synthesis/domain_generation.py`
- Modify: `synthesis/tasks.py`
- Modify: `synthesis/mobile_tasks.py`
- Modify: `synthesis/workspace_tasks.py`
- Test: `tests/test_domain_generation.py`

- [x] **Step 1: Write failing axis tests.**

  Drive a 30-candidate fake-provider run per domain and assert: batch `i`
  renders only `task_types[(i - 1) % len(task_types)]`; grounding windows
  slide deterministically with wraparound; batch `i > 1` carries prior
  instructions in `diversity_contract.excluded_instructions` capped at 20;
  sanitized metadata and `grounding_context_hash` still cover the full spec;
  persisted lineage carries only `excluded_instruction_count`.

- [x] **Step 2: Verify RED, implement, verify GREEN.**

  ```bash
  uv run python -m unittest tests.test_domain_generation
  ```

### Task 6: Add The Bounded Temperature Knob

**Files:**

- Modify: `synthesis/llm.py`
- Test: `tests/test_llm_provider.py`

- [x] **Step 1: Write failing knob tests.**

  Assert unset env keeps `"temperature": 0`; valid env values plumb through;
  non-float, non-finite, and out-of-range values raise
  `LLMConfigurationError`; lineage carries the numeric value and the config
  hash is unchanged.

- [x] **Step 2: Verify RED, implement, verify GREEN.**

  ```bash
  uv run python -m unittest tests.test_llm_provider
  ```

### Task 7: Enlarge The Contacts Fixture Additively

**Files:**

- Modify: `synthesis/environments.py`
- Modify: affected tests asserting the two-contact fixture
- Test: `tests/test_foundation_pipeline.py`
- Test: `tests/test_domain_generation.py`

- [x] **Step 1: Add four contacts and update ripples.**

  Preserve the two existing rows byte-identically; keep deterministic
  candidates, held-out suites, and local profiles behaviorally stable; update
  tests that assert fixture size or exhaustive name lists.

- [x] **Step 2: Run focused and full suites.**

  ```bash
  uv run python -m unittest tests.test_foundation_pipeline tests.test_domain_generation
  uv run python -m unittest
  ```

### Task 8: Prove The 30-Candidate Path Locally

**Files:**

- Modify: `tests/test_domain_generation.py`
- Modify: `tests/test_cli.py`

- [x] **Step 1: Extend the deterministic multi-batch provider.**

  The fake provider reads the focused task type, grounding window, and
  exclusion list from the prompt and emits distinct grounded instructions per
  batch with sentinel-compliant derived answers where required.

- [x] **Step 2: Cover all three 30-candidate domains.**

  Assert 30/30 generation, exact provider-call counts (6, 15, 15), unique
  grounded final answers, zero field-name literals, and per-type coverage
  consistent with focus rotation.

- [x] **Step 3: Prove the new gates fail closed.**

  Inject a field-name literal, an ungrounded value, a sentinel mismatch, and
  an ungrounded reference; assert each aborts its batch with the exact fixed
  reason/detail and no partial candidates or provider values in the rejection.

- [x] **Step 4: Run focused and complete tests, validate docs.**

  ```bash
  uv run python -m unittest tests.test_domain_generation tests.test_cli
  uv run python -m unittest
  uv run python scripts/validate_docs.py
  ```

### Task 9: Update Canonical Documentation

**Files:**

- Modify: `docs/ARCHITECTURE.md`
- Modify: `docs/BACKEND.md`
- Modify: `docs/DATA.md`
- Modify: `docs/SECURITY.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/README.md`
- Modify: `AGENTS.md`

- [x] **Step 1: Document the grounding contracts.**

  Derived state-tool answers and the sentinel contract, the primary-observation
  grounding gate, reference grounding, and the fixed reason/detail additions.

- [x] **Step 2: Document the diversity contracts and knob.**

  Focus rotation, grounding windows, exclusion-list privacy boundary (counts
  only in persisted lineage), the bounded temperature env var, and the
  contacts fixture enlargement.

- [x] **Step 3: Run tests, docs validation, and retained-material scan.**

  ```bash
  uv run python -m unittest
  uv run python scripts/validate_docs.py
  rg -n "provider_payload|raw_payload|Authorization:|Bearer [A-Za-z0-9._-]+|AGENT_DATA_API_KEY=" tests docs synthesis
  ```

### Task 10: Run The Serial Paid `_30_v5` Gate

**Runtime outputs:**

- Create: `artifacts/representative-campaign-30-v5/` profiles, campaign
  contract, per-domain output directories, and scale evidence.

- [x] **Step 1: Create fresh runtime-only `_30_v5` profiles.**

  Derive from the checked-in representative profiles with unique
  profile/dataset/seed IDs ending in `_30_v5`; keep purpose `benchmark`, mode
  `llm`, context policy `synthetic_fixture`; do not set
  `AGENT_DATA_LLM_TEMPERATURE` (gate runs at 0).

- [x] **Step 2: Run contacts, mobile, and workspace serially.**

  ```bash
  uv run python main.py --run-profile <profile> --use-llm --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --write-release-quality-audit --output-dir <domain-output>
  ```

  Stop on any transport or generation-stage failure; do not auto-retry strict
  schema failures. This step requires separate cost authorization.

- [x] **Step 3: Audit successful artifacts.**

  Require exit zero, 30/30 generated, `target_fulfilled=true`,
  `representative_eligible=true`, domain-correct provenance, and valid report
  chains. Scan for prompts, raw responses, grounding payloads, exclusion-list
  text, authorization data, credentials, and local paths.

- [x] **Step 4: Build representative scale evidence.**

  ```bash
  uv run python scripts/write_representative_scale_evidence.py \
    --campaign artifacts/representative-campaign-30-v5/campaign.json \
    --output artifacts/representative-campaign-30-v5/representative_scale_evidence.json
  ```

  Record the quality decision. Expected remediation signals: zero
  field-name-literal final-answer rejections, materially lower contacts exact
  duplicates, and zero ungrounded-reference `tool_runtime_error` events. Do
  not claim dataset-quality success unless the evidence supports it.

**Verified evidence (2026-07-19):** The fresh benchmark profiles use LLM mode,
synthetic-fixture context, target 30, `_30_v5` profile/dataset/seed IDs, and
effective temperature `0.0`. Manifest timestamps show contacts, mobile, and
workspace completed serially before scale evidence was written. Every domain
generated 30/30 candidates with `target_fulfilled=true`,
`representative_eligible=true`, empty generation reason codes, and
domain-correct fixture provenance. Contacts accepted 27 and rejected 3 exact
duplicates; mobile accepted 28 and rejected 2 empty draft-body runtime errors;
workspace accepted all 30. There were zero final-answer verification failures,
zero field-name-literal failures, and zero ungrounded-reference runtime errors.
Logical provider-call counts were 6, 15, and 15; three successful bounded
transport retries made workspace's HTTP-attempt count 18. Rebuilding the scale
evidence from the campaign validated every report contract and hash chain and
matched the persisted evidence. The retained-material scan found no raw prompt,
raw response, grounding payload, exclusion text, credentials, or local paths.
The scale decision is `no_change_recommended` with no triggered development
signals. This is remediation evidence, not release readiness: all release
audits remain `watch`, semantic duplicate detection remains deferred, and the
benchmark-purpose datasets remain release-ineligible.

### Task 11: Close The Plan

**Files:**

- Move: `docs/exec-plans/active/0046-final-answer-grounding-and-generation-diversity.md`
  to `docs/exec-plans/completed/0046-final-answer-grounding-and-generation-diversity.md`
- Modify: `docs/PLANS.md`
- Modify: `docs/exec-plans/active/README.md`
- Modify: `docs/exec-plans/completed/README.md`
- Modify: `docs/README.md`
- Modify: `AGENTS.md`

- [x] **Step 1: Record exact completion evidence.**

  Test counts, docs validation, per-domain provider-call counts,
  generated/accepted/rejected counts by cause, gate temperature, artifact
  directory, and the scale-evidence decision.

- [x] **Step 2: Move the plan and update lifecycle maps.**

  If any paid domain failed closed, leave the plan active with the fixed
  reason/detail instead.

- [x] **Step 3: Commit the completed plan.**

  Commit all plan changes in one single commit now that every task is done
  (`artifacts/` is git-ignored, so runtime outputs are excluded):

  ```bash
  git add synthesis tests AGENTS.md docs
  git commit -m "feat: implement final-answer grounding and generation diversity"
  ```

**Completion evidence (2026-07-19):** `uv run python -m unittest` passed all
621 tests in 13.508 seconds; documentation validation and `git diff --check`
passed. The retained-material scan found only deliberate redaction-test values,
forbidden-key allowlists, and documented scan commands, with no real provider
payloads, credentials, or local paths retained. The paid artifacts live under
`artifacts/representative-campaign-30-v5/`. Contacts, mobile, and workspace each
generated 30/30 candidates at effective temperature `0.0`, with logical
provider-call counts 6, 15, and 15. Contacts accepted 27 and rejected 3 exact
duplicates; mobile accepted 28 and rejected 2 empty draft-body runtime errors;
workspace accepted 30 and rejected 0. Workspace used three successful bounded
transport retries, so its HTTP-attempt count was 18. Report-chain rebuilding
matched the persisted representative scale evidence, whose decision is
`no_change_recommended` with no triggered development signals. Release audits
remain `watch`, semantic duplicate detection remains deferred, and the
benchmark-purpose datasets remain release-ineligible.

## Acceptance Criteria

- Shared generation code contains no domain-name branches for derivation,
  grounding, or diversity semantics; all are domain-owned data.
- `state_tool_observation` final answers are derived deterministically and
  match environment minting exactly; the provider never predicts minted IDs.
- Primary-observation final answers equal a substring of a grounding
  observation value; field-name literals and ungrounded values reject their
  batch with fixed `invalid_final_answer` details.
- Declared expected-state references resolve against grounding or reject with
  `expected_state_reference_not_grounded`.
- Batch prompts vary deterministically: single-task-type focus rotation,
  sliding grounding windows, and capped exclusion lists; persisted lineage
  carries counts, not text.
- Temperature defaults to 0 and is bounded in `[0.0, 1.0]` when configured;
  config fingerprints are unchanged.
- Contacts fixture enlargement is additive; prior deterministic behavior for
  the original entities is preserved.
- Deterministic fake providers generate 30 grounded, axis-compliant candidates
  per domain with exact call counts 6, 15, and 15.
- A failed batch still contributes zero candidates; checked-in v3 profile
  hashes remain stable.
- Focused tests, full unit tests, documentation validation, and
  retained-material scans pass.
- The serial paid `_30_v5` gate generates 30/30 per domain with valid report
  chains before representative scale evidence is built, and the evidence
  decision is recorded without overstating dataset quality.
