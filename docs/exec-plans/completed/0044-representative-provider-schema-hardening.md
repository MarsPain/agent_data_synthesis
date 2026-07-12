# Plan 0044: Representative Provider Schema Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make strict real-provider task generation diagnosable and reliable
enough to complete bounded three-domain probes, while allowing zero-accepted
runs to finish their reporting path truthfully.

**Architecture:** Keep the domain-owned generation specifications and strict
`TaskContract` admission boundary from Plan 0043. Add a closed sanitized schema
failure taxonomy at that boundary, reduce provider batches to five candidates,
make the full output contract machine-readable in the prompt, and distinguish
required release thresholds from possibly empty observed coverage.

**Tech Stack:** Python standard library (`dataclasses`, `json`, `typing`), the
existing OpenAI-compatible provider and role registry, domain generation
specifications, dataset-release contracts, `unittest`, and the documentation
validator.

---

## Status

Completed on 2026-07-12 after all three domains passed independent two-candidate
provider probes. Full 100-candidate representative retries are now allowed but
require separate cost authorization and fresh post-run evidence validation.

Approved design:
[representative-provider-schema-hardening.md](../../design-docs/representative-provider-schema-hardening.md).

## Why This Plan

The first paid contacts, mobile, and workspace representative attempts reached
the provider and received JSON, but every first batch failed before execution
with `llm_response_schema_error`. The persisted rejection contains only
`ValueError`, so the operator cannot tell whether the provider returned extra
keys, invalid tools, malformed arguments, an unsupported state check, or the
wrong batch size.

Each zero-accepted run then failed a second time while validating
`dataset_release_report.json`: required release thresholds must remain non-empty,
but the validator incorrectly imposes the same rule on observed coverage. The
pipeline therefore loses the truthful `ineligible` or `insufficient_evidence`
report that should describe an empty benchmark run.

The repair must improve provider adherence and diagnostics without persisting
provider content, weakening task contracts, or presenting a partial batch as
representative evidence.

## Scope

- Keep exact-key, exact-tool, typed-argument, expected-state, and exact-count
  validation fail-closed.
- Add the twelve reason codes approved by the design and persist only the fixed
  reason code on a generation-stage rejection.
- Replace the prompt's key-name hint with a complete machine-readable output
  contract derived from each domain specification.
- Set all supported domain specifications to at most five candidates per call.
- Accept empty observed task-type and tool-combination coverage while preserving
  non-empty required threshold declarations.
- Ensure zero-accepted runs produce a non-passing completeness decision and a
  valid dataset release report.
- Prove compatibility locally, then run two-candidate paid probes in all three
  domains before allowing any 100-candidate retry.
- Update canonical backend, data, security, roadmap, and plan-lifecycle docs.

## Out Of Scope

- Provider-specific structured-output capability negotiation.
- Deleting unknown keys, coercing values, repairing arguments, or inventing
  missing expected-state evidence.
- Persisting raw responses, response excerpts, prompts, grounding context,
  provider-derived exception messages, credentials, or headers.
- Retrying a strict schema failure automatically inside the same paid probe.
- Async orchestration, durable queues, semantic similarity, model training, or
  changing benchmark profiles into release candidates.

## Existing Boundaries To Preserve

- `synthesis.domain_generation` owns provider-output interpretation and domain
  generation-spec validation.
- `synthesis.llm` owns transport failures and the provider-facing error envelope;
  schema reasons are optional subordinate evidence and do not replace `cause`.
- `synthesis.datasets` owns rejection assembly and must copy only approved fixed
  diagnostics.
- `synthesis.contracts` owns persisted artifact allowlists and must reject an
  unknown schema reason or a reason attached to the wrong rejection cause.
- Domain modules own task types, required tools, tool schemas, grounding context,
  and expected-state vocabularies.
- `synthesis.dataset_release` owns completeness decisions; empty observations
  are evidence of missing coverage, never evidence of passing coverage.
- Checked-in `run_profile_v3` JSON and its hashes remain unchanged.

## Contract Decisions

### Sanitized Schema Reason Envelope

`LLMProviderError` gains one optional fixed field:

```python
class LLMProviderError(RuntimeError):
    def __init__(
        self,
        *,
        cause: str = "llm_provider_error",
        error_class: str = "LLMProviderError",
        retryable: bool = False,
        retry_count: int = 0,
        lineage: dict[str, object] | None = None,
        schema_reason: str | None = None,
    ) -> None:
        super().__init__(f"Remote LLM generation failed: {error_class}")
        self.cause = cause
        self.error_class = error_class
        self.retryable = retryable
        self.retry_count = retry_count
        self.lineage = dict(lineage) if lineage else {}
        self.schema_reason = schema_reason
```

For domain task-contract validation, `cause` remains
`llm_response_schema_error`, `error_class` remains local and sanitized, and
`schema_reason` is exactly one of:

```python
LLM_RESPONSE_SCHEMA_REASONS = {
    "response_shape_mismatch",
    "provider_record_keys_mismatch",
    "invalid_task_type",
    "invalid_required_tools",
    "invalid_primary_tool",
    "invalid_tool_arguments",
    "invalid_difficulty",
    "invalid_expected_state",
    "invalid_required_capabilities",
    "unsafe_provider_value",
    "duplicate_candidate_id",
    "batch_count_mismatch",
}
```

The persisted rejection adds only:

```json
{
  "candidate_id": "generation_stage",
  "cause": "llm_response_schema_error",
  "details": {
    "error_class": "DomainGenerationValidationError",
    "schema_reason": "invalid_tool_arguments",
    "retry_count": 0,
    "retry_eligible": false
  }
}
```

It never copies the caught exception message or provider values.

### Complete Prompt Contract

The prompt payload replaces `output_item_keys` with an `output_contract` object
that declares the exact response shape, record fields, field JSON types,
non-empty and uniqueness rules, task-type/tool coupling, primary-tool ordering,
read-only versus mutating expected-state behavior, forbidden fields, and exact
requested count. Tool arguments remain defined only by the domain-provided
curated tool schemas.

### Empty Release Evidence

The contract uses `_require_sequence` for
`release_completeness.observed.task_types` and
`release_completeness.observed.tool_combinations`, then validates every present
item as a non-empty string. It continues using
`_require_non_empty_string_sequence` for both required threshold lists.

The builder already computes missing required coverage from set difference.
With empty observations and non-empty thresholds, both coverage checks are
triggered and completeness is `insufficient_evidence`; the enclosing benchmark
release decision remains `ineligible` because profile purpose is checked first.

## File Map

- Modify `synthesis/contracts.py`
  - own the persisted reason-code allowlist, validate schema diagnostics, and
    allow empty observed release-coverage sequences only.
- Modify `synthesis/llm.py`
  - add the optional sanitized `schema_reason` field to `LLMProviderError`.
- Modify `synthesis/domain_generation.py`
  - add `DomainGenerationValidationError`, full prompt contract, reason-specific
    validation, exact-count classification, and the global batch ceiling of 5.
- Modify `synthesis/domain_pipeline.py`, `synthesis/mobile_tasks.py`, and
  `synthesis/workspace_tasks.py`
  - make every domain generation specification explicitly use batch size 5.
- Modify `synthesis/datasets.py`
  - persist the fixed schema reason without provider-derived text.
- Modify `synthesis/dataset_release.py`
  - make the empty-coverage non-passing behavior explicit and stable.
- Modify `tests/test_domain_generation.py`
  - cover prompt structure, all twelve reason codes, batch sizing, and redaction.
- Modify `tests/test_llm_provider.py`, `tests/test_contracts.py`,
  `tests/test_dataset_release.py`, and `tests/test_cli.py`
  - cover error-envelope compatibility and the zero-accepted reporting path.
- Modify `docs/BACKEND.md`, `docs/DATA.md`, `docs/SECURITY.md`,
  `docs/ROADMAP.md`, `docs/README.md`, `docs/PLANS.md`, `AGENTS.md`, and the
  active/completed plan indexes.

## Implementation Tasks

### Task 1: Introduce The Sanitized Schema Error Contract

**Files:**

- Modify: `synthesis/contracts.py`
- Modify: `synthesis/llm.py`
- Modify: `synthesis/datasets.py`
- Test: `tests/test_llm_provider.py`
- Test: `tests/test_contracts.py`

- [x] **Step 1: Write failing error-envelope and rejection-contract tests.**

  Add a test constructing `LLMProviderError` with
  `schema_reason="invalid_tool_arguments"` and assert
  `assemble_generation_stage_rejection()` preserves that fixed value. Add table
  tests proving rejection validation accepts every allowlisted reason, rejects
  `provider_said_bad_email`, rejects a schema reason on `llm_provider_error`,
  and rejects `llm_response_schema_error` without a schema reason when the
  rejection candidate is `generation_stage`.

- [x] **Step 2: Run the focused tests and confirm the new assertions fail.**

  Run:

  ```bash
  uv run python -m unittest tests.test_llm_provider tests.test_contracts
  ```

  Expected: failures show that `LLMProviderError` does not accept
  `schema_reason` and rejection validation does not enforce the new contract.

- [x] **Step 3: Add the shared allowlist and optional error field.**

  Define `LLM_RESPONSE_SCHEMA_REASONS` in `synthesis/contracts.py`. Add
  `schema_reason: str | None = None` to `LLMProviderError.__init__` and assign it
  without deriving or formatting provider content. Keep all existing call sites
  source-compatible because the new argument is optional.

- [x] **Step 4: Persist and validate only the fixed reason.**

  In `assemble_generation_stage_rejection`, add `details["schema_reason"]` only
  when `error.schema_reason` is non-null. In `validate_rejection_record`, require
  an allowlisted reason exactly when the record is the generation-stage
  `llm_response_schema_error`; forbid `schema_reason` for other causes.

- [x] **Step 5: Run focused tests.**

  Run the command from Step 2. Expected: all tests pass and legacy provider
  errors still serialize without a schema reason.

- [x] **Step 6: Commit the error-envelope boundary.**

  ```bash
  git add synthesis/contracts.py synthesis/llm.py synthesis/datasets.py tests/test_llm_provider.py tests/test_contracts.py
  git commit -m "feat: add sanitized provider schema reasons"
  ```

### Task 2: Classify Strict Domain-Generation Validation Failures

**Files:**

- Modify: `synthesis/domain_generation.py`
- Test: `tests/test_domain_generation.py`

- [x] **Step 1: Add a synthetic fixture for each reason code.**

  Start from the existing valid provider record and create one mutation per
  reason: wrong top-level shape, extra record key, unknown task type, wrong
  required tools, wrong primary tool, schema-invalid primary arguments,
  non-object difficulty, missing or duplicated state evidence, empty or
  duplicated capabilities, an unsafe key/path-like value, duplicate candidate
  id, and wrong batch count. Assert only the fixed `schema_reason`; also assert
  serialized errors and rejections exclude the injected field values.

- [x] **Step 2: Run the focused test and verify failure.**

  ```bash
  uv run python -m unittest tests.test_domain_generation
  ```

  Expected: the current generator reports only `ValueError` and no fixed reason.

- [x] **Step 3: Add a reason-carrying local validation exception.**

  Implement:

  ```python
  class DomainGenerationValidationError(ValueError):
      def __init__(self, reason: str) -> None:
          if reason not in LLM_RESPONSE_SCHEMA_REASONS:
              raise ValueError("unsupported domain generation schema reason")
          super().__init__(reason)
          self.reason = reason
  ```

  Provider-derived values must not be interpolated into this exception.

- [x] **Step 4: Map each strict check to exactly one reason.**

  Split validation into focused functions for response shape, exact record keys,
  task-type/tool coupling, primary arguments, difficulty, expected state,
  required capabilities, and safe values. Convert lower-level
  `TypeError`/`ValueError`/`KeyError` failures at the nearest boundary into the
  approved fixed reason while retaining the original exception only as an
  in-memory `__cause__`.

- [x] **Step 5: Classify duplicate and count failures at batch scope.**

  Use `duplicate_candidate_id` for both within-batch and cross-batch collisions.
  Use `batch_count_mismatch` when a shaped batch does not contain exactly the
  requested count. Wrap `DomainGenerationValidationError` as
  `LLMProviderError(cause="llm_response_schema_error",
  error_class="DomainGenerationValidationError", retryable=False,
  retry_count=_retry_count(result.lineage), lineage=result.lineage,
  schema_reason=exc.reason)`.

- [x] **Step 6: Run focused tests.**

  Run the command from Step 2. Expected: all twelve reasons pass, no provider
  value appears in persisted diagnostics, and a failed batch contributes no
  candidates.

- [ ] **Step 7: Commit reason-specific validation.**

  ```bash
  git add synthesis/domain_generation.py tests/test_domain_generation.py
  git commit -m "feat: classify strict generation schema failures"
  ```

### Task 3: Make Provider Output Easier To Satisfy

**Files:**

- Modify: `synthesis/domain_generation.py`
- Modify: `synthesis/domain_pipeline.py`
- Modify: `synthesis/mobile_tasks.py`
- Modify: `synthesis/workspace_tasks.py`
- Test: `tests/test_domain_generation.py`

- [x] **Step 1: Write failing prompt and batching tests.**

  Parse `build_domain_generation_prompt()` as JSON and assert it declares exact
  response keys, exact requested count, every record field's JSON type and
  non-empty rule, exact `required_tools`, first-tool `primary_tool`, empty
  read-only expected state, required mutating expected state, forbidden fields,
  and JSON-only output. Assert every domain spec exports
  `max_candidates_per_call == 5` and a target of 12 produces provider request
  sizes `[5, 5, 2]`.

- [x] **Step 2: Run the focused test and verify failure.**

  ```bash
  uv run python -m unittest tests.test_domain_generation
  ```

  Expected: the prompt exposes only `output_item_keys` and domain specs still
  permit 20 candidates per call.

- [x] **Step 3: Replace the prompt hint with a complete output contract.**

  Build the contract deterministically from `_PROVIDER_RECORD_KEYS`, domain task
  declarations, and curated tool schemas. Keep grounding values in the prompt
  but never in exported metadata. Do not add provider-specific JSON Schema
  request parameters.

- [x] **Step 4: Reduce the shared ceiling and all domain specifications to 5.**

  Set `MAX_CANDIDATES_PER_CALL = 5`, update the spec validation error text, and
  set the contacts, mobile, and workspace builders explicitly to that ceiling.
  Preserve `sanitized_generation_spec_metadata()` so the effective batch size
  remains visible.

- [x] **Step 5: Run focused and compatibility tests.**

  ```bash
  uv run python -m unittest tests.test_domain_generation tests.test_run_profiles tests.test_scale_evidence
  ```

  Expected: all tests pass, checked-in profile hashes remain stable, and a
  100-candidate run now requires twenty successful provider batches.

- [ ] **Step 6: Commit prompt and batch hardening.**

  ```bash
  git add synthesis/domain_generation.py synthesis/domain_pipeline.py synthesis/mobile_tasks.py synthesis/workspace_tasks.py tests/test_domain_generation.py
  git commit -m "feat: harden provider generation contract"
  ```

### Task 4: Preserve Truthful Zero-Accepted Release Reporting

**Files:**

- Modify: `synthesis/contracts.py`
- Modify: `synthesis/dataset_release.py`
- Test: `tests/test_contracts.py`
- Test: `tests/test_dataset_release.py`

- [x] **Step 1: Write failing empty-observation tests.**

  Add contract tests where both observed coverage lists are `[]` and required
  threshold lists remain non-empty. Add negative tests proving an empty required
  task-type or tool-combination list still fails. Add a report-builder test with
  zero accepted samples and one generation-stage rejection; assert both coverage
  triggers are present, completeness is `insufficient_evidence`, and the dataset
  release decision is `ineligible` for a benchmark profile.

- [x] **Step 2: Run focused tests and verify contract failure.**

  ```bash
  uv run python -m unittest tests.test_contracts tests.test_dataset_release
  ```

  Expected: report validation rejects the empty observed sequences.

- [x] **Step 3: Separate observed-sequence validation from thresholds.**

  In `_validate_release_completeness`, keep non-empty validation for
  `thresholds.required_task_types` and
  `thresholds.required_tool_combinations`. Validate observed coverage with
  `_require_sequence` plus per-item `_require_non_empty_string`, including
  duplicate rejection if the current contract requires unique coverage keys.

- [x] **Step 4: Make the non-passing builder invariant explicit.**

  Preserve the existing set-difference checks in
  `_release_completeness_decision`. Add a defensive invariant that a `passed`
  decision requires both required threshold sets to be non-empty and fully
  covered; do not synthesize fallback observed keys from thresholds.

- [x] **Step 5: Run focused tests.**

  Run the command from Step 2. Expected: empty observed coverage validates but
  cannot pass; empty thresholds remain invalid.

- [ ] **Step 6: Commit release-report hardening.**

  ```bash
  git add synthesis/contracts.py synthesis/dataset_release.py tests/test_contracts.py tests/test_dataset_release.py
  git commit -m "fix: report empty release evidence truthfully"
  ```

### Task 5: Prove The Full Failure Path And Redaction Boundary

**Files:**

- Modify: `tests/test_cli.py`
- Modify: `tests/test_domain_generation.py`

- [x] **Step 1: Add a fake-provider CLI regression test.**

  Run a temporary `run_profile_v3` benchmark with target count 2 and a fake
  provider response containing one controlled schema violation. Request
  evaluation, profile decision, dataset release, and release quality audit.
  Assert process completion follows the documented non-passing path, all
  requested reports exist, accepted count is zero, the rejection contains the
  expected fixed reason, and the release decision is not `passed`.

- [x] **Step 2: Add a persisted-artifact denylist assertion.**

  Concatenate samples, rejections, manifest, quality, evaluation, profile
  decision, dataset release, and audit artifacts. Assert the string excludes the
  fake raw response marker, prompt text, grounding names/values, authorization,
  bearer tokens, API keys, local absolute paths, and the original exception
  message.

- [x] **Step 3: Run focused CLI tests and fix only integration defects.**

  ```bash
  uv run python -m unittest tests.test_cli tests.test_domain_generation
  ```

  Expected: the schema failure is diagnosable, reports are valid, and no raw
  provider-derived text is persisted.

- [ ] **Step 4: Commit the end-to-end regression.**

  ```bash
  git add tests/test_cli.py tests/test_domain_generation.py
  git commit -m "test: cover provider schema failure reporting"
  ```

### Task 6: Update Canonical Documentation And Verify Locally

**Files:**

- Modify: `docs/BACKEND.md`
- Modify: `docs/DATA.md`
- Modify: `docs/SECURITY.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/README.md`
- Modify: `docs/PLANS.md`
- Modify: `docs/exec-plans/active/README.md`
- Modify: `AGENTS.md`

- [x] **Step 1: Document the runtime and data-contract changes.**

  Record the five-candidate batch ceiling, full prompt contract, schema reason
  taxonomy, zero-accepted report behavior, and probe gate. State explicitly that
  raw provider content and provider-derived exception messages remain forbidden.

- [x] **Step 2: Run focused tests, then the complete suite.**

  ```bash
  uv run python -m unittest tests.test_domain_generation tests.test_llm_provider tests.test_contracts tests.test_dataset_release tests.test_cli
  uv run python -m unittest
  ```

  Expected: both commands exit zero.

- [x] **Step 3: Validate documentation.**

  ```bash
  uv run python scripts/validate_docs.py
  ```

  Expected: `Documentation validation passed.`

- [x] **Step 4: Scan tests and tracked documentation for forbidden retained material.**

  ```bash
  rg -n "provider_payload|raw_payload|Authorization:|Bearer [A-Za-z0-9._-]+|AGENT_DATA_API_KEY=" tests docs synthesis
  ```

  Expected: only intentional denylist/security-policy references appear; no raw
  provider fixture or credential value is present.

- [ ] **Step 5: Commit implementation documentation.**

  ```bash
  git add AGENTS.md docs/BACKEND.md docs/DATA.md docs/SECURITY.md docs/ROADMAP.md docs/README.md docs/PLANS.md docs/exec-plans/active/README.md
  git commit -m "docs: document provider schema hardening"
  ```

### Task 7: Run The Paid Probe Gate Before Representative Retry

**Runtime outputs:**

- Create: `artifacts/provider-probes/contacts-profile.json`
- Create: `artifacts/provider-probes/mobile-profile.json`
- Create: `artifacts/provider-probes/workspace-profile.json`
- Create: `artifacts/provider-probes/contacts/`
- Create: `artifacts/provider-probes/mobile/`
- Create: `artifacts/provider-probes/workspace/`

- [x] **Step 1: Create runtime-only two-candidate profiles.**

  Create these exact JSON objects under `artifacts/provider-probes/`:

  ```json
  {
    "schema_version": "run_profile_v3",
    "profile_id": "contacts_provider_probe_2",
    "dataset_version": "dataset_contacts_provider_probe_2_v1",
    "profile_purpose": "benchmark",
    "seed": {
      "seed_id": "seed_contacts_provider_probe_2",
      "domain": "contacts_fixture",
      "description": "Generate grounded executable contacts tasks.",
      "task_taxonomy": ["contact_lookup", "contact_followup"]
    },
    "generation": {
      "mode": "llm",
      "target_candidate_count": 2,
      "context_policy": "synthetic_fixture"
    },
    "features": {}
  }
  ```

  Save it as `contacts-profile.json`.

  Save this as `mobile-profile.json`:

  ```json
  {
    "schema_version": "run_profile_v3",
    "profile_id": "mobile_messages_provider_probe_2",
    "dataset_version": "dataset_mobile_messages_provider_probe_2_v1",
    "profile_purpose": "benchmark",
    "seed": {
      "seed_id": "seed_mobile_messages_provider_probe_2",
      "domain": "mobile_messages_fixture",
      "description": "Generate grounded executable mobile message tasks.",
      "task_taxonomy": ["mobile_message_search", "mobile_reminder_creation", "mobile_draft_reply"]
    },
    "generation": {
      "mode": "llm",
      "target_candidate_count": 2,
      "context_policy": "synthetic_fixture"
    },
    "features": {}
  }
  ```

  Save this as `workspace-profile.json`:

  ```json
  {
    "schema_version": "run_profile_v3",
    "profile_id": "workspace_tasks_provider_probe_2",
    "dataset_version": "dataset_workspace_tasks_provider_probe_2_v1",
    "profile_purpose": "benchmark",
    "seed": {
      "seed_id": "seed_workspace_tasks_provider_probe_2",
      "domain": "workspace_tasks_fixture",
      "description": "Generate grounded executable workspace tasks.",
      "task_taxonomy": ["workspace_item_search", "workspace_task_creation", "workspace_comment_update"]
    },
    "generation": {
      "mode": "llm",
      "target_candidate_count": 2,
      "context_policy": "synthetic_fixture"
    },
    "features": {}
  }
  ```

- [x] **Step 2: Run contacts, then mobile, then workspace independently.**

  Run these exact commands in order:

  ```bash
  uv run python main.py --run-profile artifacts/provider-probes/contacts-profile.json --use-llm --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --write-release-quality-audit --output-dir artifacts/provider-probes/contacts
  uv run python main.py --run-profile artifacts/provider-probes/mobile-profile.json --use-llm --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --write-release-quality-audit --output-dir artifacts/provider-probes/mobile
  uv run python main.py --run-profile artifacts/provider-probes/workspace-profile.json --use-llm --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --write-release-quality-audit --output-dir artifacts/provider-probes/workspace
  ```

  Expected for each domain: exit zero, generated and target count 2,
  `target_fulfilled=true`, `representative_eligible=true`, no generation-stage
  rejection, and all requested reports validate.

- [x] **Step 3: Stop immediately on the first failed probe.**

  Preserve only sanitized artifacts, inspect `details.schema_reason`, and return
  to the relevant earlier task. Do not run another paid domain or a 100-candidate
  retry until the cause is understood and local regression coverage is added.

- [x] **Step 4: Audit successful probe artifacts for secrets and raw provider material.**

  Confirm no prompt, grounding payload, raw provider response, response excerpt,
  authorization header, API key, or local secret appears in any probe artifact.

- [x] **Step 5: Record probe evidence without committing runtime artifacts.**

  Add sanitized exit status, generated count, rejection count, report validation,
  and artifact paths to this plan's completion evidence. Keep `artifacts/`
  untracked.

### Task 8: Close The Plan Or Gate The Full Campaign

**Files:**

- Move: `docs/exec-plans/active/0044-representative-provider-schema-hardening.md`
  to `docs/exec-plans/completed/0044-representative-provider-schema-hardening.md`
- Modify: `docs/PLANS.md`
- Modify: `docs/exec-plans/active/README.md`
- Modify: `docs/exec-plans/completed/README.md`
- Modify: `docs/README.md`
- Modify: `AGENTS.md`

- [x] **Step 1: Require all three probe results before closing.**

  If any probe failed, leave this plan active with the fixed sanitized reason and
  do not run the representative campaign. If all probes passed, record their
  counts and report-validation evidence.

- [x] **Step 2: Move the accepted plan to completed and update lifecycle maps.**

  Mark the completion date, test count, docs validation result, and probe result.
  State that 100-candidate runs are now allowed but are not themselves proof of
  quality until post-run evidence validation succeeds.

- [ ] **Step 3: Commit lifecycle closure.**

  ```bash
  git add AGENTS.md docs/README.md docs/PLANS.md docs/exec-plans/active/README.md docs/exec-plans/completed/README.md docs/exec-plans/completed/0044-representative-provider-schema-hardening.md
  git commit -m "docs: complete provider schema hardening plan"
  ```

- [ ] **Step 4: Start full representative retries only after closure.**

  Use fresh output directories and separate persistent sessions for the existing
  100-candidate profiles. Verify all required artifacts before building
  `representative_scale_evidence_v1`; let that evidence select the next quality
  or orchestration priority.

## Acceptance Criteria

- All supported domains use at most five candidates per provider call.
- The prompt declares the complete strict output contract and exact batch count.
- Every provider schema failure emits exactly one approved fixed reason code.
- The public cause remains `llm_response_schema_error`.
- No raw provider content or provider-derived exception message is persisted.
- Empty observed release coverage validates but can never pass completeness.
- Empty required threshold lists remain invalid.
- A zero-accepted benchmark run completes its report chain with a non-passing
  decision instead of raising a release-contract exception.
- Existing v1/v2 behavior and checked-in v3 profile hashes remain stable.
- Focused tests, the full unit suite, and documentation validation pass.
- Contacts, mobile, and workspace each pass a two-candidate paid probe before
  any 100-candidate retry begins.

## Completion Evidence

Record exact test counts, documentation validation, three probe exit statuses,
generated/target counts, sanitized artifact paths, and any post-run campaign
decision here when the plan is completed.

Local implementation evidence recorded on 2026-07-12 before paid probes:

- Focused schema/reporting/CLI suite: 199 tests passed.
- Complete unit suite: 573 tests passed.
- Documentation validation: `Documentation validation passed.`
- Fake-provider zero-accepted path: exit zero, accepted 0, rejected 1, all
  requested reports present, fixed `provider_record_keys_mismatch` reason, and
  persisted-artifact denylist assertions passed.
- All-three successful paid probe evidence remains pending; this plan stays
  active and no 100-candidate retry is authorized yet.
- Contacts paid probe: process exit zero, generated/accepted count 0 of target 2,
  rejection count 1, fixed reason `invalid_primary_tool`, valid evaluation,
  profile-decision, dataset-release, and release-quality-audit reports under
  `artifacts/provider-probes/contacts/`; dataset release is `ineligible` and
  completeness is `insufficient_evidence`.
- The failed contacts artifacts passed the raw provider/prompt/grounding/secret
  scan. Mobile and workspace were not called, as required by the first-failure
  stop rule.
- A post-failure RED/GREEN regression now makes `primary_tool ==
  required_tools[0]` explicit both as a critical rule and as exact per-task-type
  record values. The refreshed compatibility suite passed 44 tests, the complete
  suite passed 573 tests, and documentation validation passed.
- A second contacts probe generated 2/2 but exposed one `solution_logic_error`.
  The prompt now requires grounded final-answer evidence; contacts then passed
  2/2 with zero rejections under
  `artifacts/provider-probes/contacts-retry-grounded-answer/`.
- Mobile failures exposed two independent local contract gaps: mutating policy
  responses discarded primary search evidence, and grounding results omitted
  the executable search arguments that produced them. Evidence-preserving mobile
  responses plus replayable domain grounding were covered by RED/GREEN tests.
  Mobile then passed 2/2 with zero rejections under
  `artifacts/provider-probes/mobile-retry-grounded-arguments/`.
- Workspace first stopped with fixed reason `invalid_expected_state`. Expanding
  each mutating task-type contract with exact expected-state items, its mutating
  tool name, and the complete curated schema produced a 2/2 zero-rejection pass
  under `artifacts/provider-probes/workspace-retry-expected-state-schema/`.
- All three successful probe directories passed sample, manifest, evaluation,
  profile-decision, dataset-release, and release-quality-audit contract
  validation. Each manifest records target/generated 2/2,
  `target_fulfilled=true`, `representative_eligible=true`, and no reason codes.
  Raw response, prompt, grounding-payload, credential, authorization, and local
  path scans were clean.
- Final local verification: 574 unit tests passed; documentation validation
  reported `Documentation validation passed.` No 100-candidate run was started.
