# Plan 0043: Domain-Aware Representative Generation And Campaign Readiness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Replace the contacts-only remote task generator with a bounded,
domain-aware task-contract generator for contacts, mobile messages, and
workspace tasks, then make representative campaign eligibility explicit and
verifiable by Plan 0042's evidence consumer.

**Architecture:** Add domain-owned generation specifications and one shared LLM
task-contract generator. Build the generator only after the selected domain
pipeline bundle exists, preserve the existing `TaskContract` compatibility
boundary, record sanitized generation-contract evidence in run-profile metadata,
and require that evidence before `synthesis.scale_evidence` classifies a run as
representative.

**Tech Stack:** Python standard library (`dataclasses`, `hashlib`, `json`,
`pathlib`, `typing`), existing OpenAI-compatible provider/role registry,
`TaskContract`, domain pipeline bundles, JSON run profiles, `unittest`, and the
documentation validator.

---

## Status

Completed on 2026-07-11.

Validation evidence:

- `UV_CACHE_DIR=/tmp/uv-cache uv run python -m unittest` — 562 tests passed.
- `UV_CACHE_DIR=/tmp/uv-cache uv run python scripts/validate_docs.py` — passed.
- No real-provider campaign was run; the repository is campaign-ready and plan
  0014 plus TD-0002 remain deferred.

Approved design:
[domain-aware-representative-generation.md](../../design-docs/domain-aware-representative-generation.md).

## Why This Plan

Plan 0042 completed diagnostic-versus-representative evidence aggregation and
explicitly recorded domain-representative generation/evidence as the next
candidate direction. No real representative campaign was supplied, so async
orchestration plan 0014 and semantic duplicate debt TD-0002 remain deferred.

The repository currently accepts `generation.mode: llm` for any run-profile
domain, and `main.py` injects the same remote candidate generator into the
selected pipeline. That generator still emits a contacts-only prompt naming
`lookup_contact_email`, Alice Zhang, Ben Carter, and exact fixture email values.
Mobile and workspace bundles own different tools, task types, state transitions,
and scripted policy behavior. Treating the existing generator as a three-domain
representative workload would therefore produce invalid or misleading evidence.

The scale-evidence classifier also treats any valid `generation_mode: llm` run
as representative. It does not yet require a fulfilled target count, a domain
generation-spec version, an allowed remote-context policy, or an explicit
computed eligibility decision. This plan closes both gaps before any scale
threshold can activate infrastructure or data-quality work.

## Scope

- Add `run_profile_v3` for representative LLM generation while preserving v1/v2
  loading and the legacy profile-free `--use-llm` path.
- Require `generation.target_candidate_count` and
  `generation.context_policy: synthetic_fixture` for v3 LLM profiles.
- Reject v3 LLM generation when a profile-local source is declared; raw source
  rows must not be sent to a remote provider in this plan.
- Define immutable shared generation records for task types, tool contracts,
  bounded grounding context, batch limits, and expected-state vocabulary.
- Let contacts, mobile, and workspace owners build their own generation
  specifications from curated synthetic fixture data and registered tools.
- Generate structured `TaskContract` records through the existing remote
  `task_generation` role, validate them, and convert them into `CandidateTask`
  only through the existing compatibility boundary.
- Enforce bounded synchronous batches, exact target fulfillment, globally unique
  candidate ids, and sanitized generation failures.
- Build LLM generator factories after domain-bundle selection instead of before
  environment construction.
- Record sanitized generation-contract metadata without prompts, grounding rows,
  source payloads, tool arguments, credentials, or host paths.
- Require that metadata before Plan 0042 evidence may classify a run as
  `representative`.
- Add three checked-in operator profiles for 100-candidate representative
  campaigns and smaller fake-provider test profiles created in temporary
  directories.
- Preserve synchronous execution, existing release admission, and default
  deterministic fixture behavior.

## Out Of Scope

- Sending profile-local contacts, messages, workspace documents, tasks, or
  comments to the remote provider.
- `governed_source_opt_in` remote disclosure; only `synthetic_fixture` is
  supported in version 1 of this boundary.
- LLM-generated solution policies, verifiers, tools, environments, executable
  code, or branch plans.
- Async orchestration, durable queues, cancellation, resumption, distributed
  workers, dashboards, or plan 0014 implementation.
- Embeddings, vector stores, clustering, semantic similarity scoring, or TD-0002
  implementation.
- Model training, fine-tuning, reward-model training, Agentic RL, or calls to a
  training service.
- External MCP servers, browser automation, real-user integrations, or a fourth
  domain.
- Automatically activating another plan or changing dataset-release admission
  based on representative evidence.
- Requiring a paid real-provider campaign to complete this implementation plan.

## Existing Boundaries To Preserve

- `synthesis.run_profiles` owns profile parsing, version compatibility, and
  sanitized profile metadata.
- `synthesis.domain_pipeline` owns environment, registry, verifier, fixture
  generator, and policy-generator selection for each domain.
- Domain modules own their task semantics and grounding-context construction.
- `synthesis.roles` and `synthesis.llm` own provider invocation, retries, prompt
  hashing, and sanitized provider lineage.
- `synthesis.task_contracts` owns task-intent, policy-hint, expected-outcome, and
  expected-state validation.
- `synthesis.pipeline` owns candidate execution and dataset artifact assembly.
- `synthesis.profile_decisions` owns the existing async and semantic-duplicate
  threshold values and decisions.
- `synthesis.scale_evidence` consumes validated evidence; it does not recompute
  profile decisions or mutate plan lifecycle state.
- Profile-free `--use-llm` remains a contacts-compatible diagnostic path and is
  never representative because it has no v3 profile contract.
- Manifests and reports persist hashes and fixed metadata only. Provider prompts,
  grounding context, source rows, credentials, headers, and local paths remain
  excluded.

## Contract Decisions

### Run Profile V3

Representative operator profiles use this generation fragment:

```json
{
  "schema_version": "run_profile_v3",
  "profile_id": "contacts-representative-llm-100",
  "dataset_version": "dataset_contacts_representative_llm_100_v1",
  "profile_purpose": "benchmark",
  "seed": {
    "seed_id": "seed_contacts_representative_llm_100",
    "domain": "contacts_fixture",
    "description": "Generate grounded executable contacts tasks.",
    "task_taxonomy": ["contact_lookup", "contact_followup"]
  },
  "generation": {
    "mode": "llm",
    "target_candidate_count": 100,
    "context_policy": "synthetic_fixture"
  },
  "features": {}
}
```

`run_profile_v3` rejects unknown generation keys. For v3, `llm` requires a
positive target and exactly `synthetic_fixture`; non-LLM modes reject
`context_policy`. V3 LLM profiles reject `source` entirely. V1/v2 parsing and
hash behavior remain unchanged for existing files.

### Domain Generation Specification

The shared internal record has this shape:

```python
@dataclass(frozen=True)
class DomainTaskTypeSpec:
    task_type: str
    required_tools: tuple[str, ...]
    allowed_expected_state_checks: tuple[str, ...] = ()


@dataclass(frozen=True)
class DomainGenerationSpec:
    schema_version: str
    domain_id: str
    task_types: tuple[DomainTaskTypeSpec, ...]
    tools: tuple[Mapping[str, object], ...]
    grounding_context: Mapping[str, object]
    context_policy: str
    max_candidates_per_call: int
```

`grounding_context` is ephemeral. Specification export for lineage includes only
schema version, domain id, task-type names, tool name/version/schema hashes,
context policy, grounding-context hash, and batch limit.

### Provider Output

Each provider call returns exact-key JSON:

```json
{
  "task_contracts": [
    {
      "candidate_id": "candidate_mobile_maya_reminder_001",
      "instruction": "Find Maya's launch time and create a reminder.",
      "task_type": "mobile_reminder_creation",
      "difficulty": {
        "level": "medium",
        "tool_count": 2,
        "constraint_count": 2,
        "state_changes": 1,
        "ambiguity": "none",
        "recovery_paths": 0
      },
      "required_capabilities": ["message_search", "reminder_creation"],
      "required_tools": ["search_messages", "create_reminder"],
      "primary_tool": "search_messages",
      "primary_arguments": {"query": "launch", "participant": "Maya"},
      "final_answer_contains": "10:00",
      "expected_state": [
        {
          "check_type": "mobile_reminder",
          "expected": {"title": "Maya launch", "due_at": "1970-01-02T10:00:00Z"}
        }
      ]
    }
  ]
}
```

The response cannot set lineage, domain id, context policy, provider metadata,
source metadata, branch plans, or arbitrary compatibility fields. Those values
are supplied or derived locally.

### Sanitized Generation Evidence

V3 run-profile metadata adds:

```json
{
  "generation_contract": {
    "spec_version": "domain_generation_spec_v1",
    "context_policy": "synthetic_fixture",
    "target_candidate_count": 100,
    "generated_candidate_count": 100,
    "target_fulfilled": true,
    "representative_eligible": true,
    "reason_codes": [],
    "grounding_context_hash": "sha256:0000000000000000000000000000000000000000000000000000000000000000"
  }
}
```

Allowed ineligible reason codes are:

- `profile_contract_not_representative`;
- `generation_spec_missing_or_mismatched`;
- `context_policy_not_allowed`;
- `source_backed_remote_context_not_allowed`;
- `target_candidate_count_unfulfilled`; and
- `generation_evidence_missing`.

No report stores grounding-context values or the provider prompt.

## File Map

- Create `synthesis/domain_generation.py`
  - Own shared specification records, validation, safe prompt construction,
    provider-output parsing, bounded batch generation, and sanitized generation
    evidence construction.
- Modify `synthesis/tasks.py`
  - Keep `CandidateTask` compatibility and legacy contacts generation helpers;
    remove the contacts-only prompt from the shared v3 path.
- Modify `synthesis/mobile_tasks.py`
  - Add mobile task-type declarations and synthetic grounding builder.
- Modify `synthesis/workspace_tasks.py`
  - Add workspace task-type declarations and synthetic grounding builder.
- Modify `synthesis/domain_pipeline.py`
  - Attach a validated generation specification to every supported domain
    bundle.
- Modify `synthesis/pipeline.py`
  - Accept a post-bundle candidate-generator factory and attach generation
    contract results to sanitized run metadata.
- Modify `synthesis/run_profiles.py`
  - Add `run_profile_v3`, strict generation context-policy parsing, and v3
    compatibility rules.
- Modify `main.py`
  - Build LLM generator factories from v3 profiles and selected domain bundles.
- Modify `synthesis/contracts.py`
  - Validate the new sanitized manifest/report generation-contract fields.
- Modify `synthesis/scale_evidence.py`
  - Require valid generation-contract evidence for representative
    classification.
- Add three files under `tests/fixtures/run_profiles/`
  - `contacts-representative-llm-100.json`
  - `mobile-messages-representative-llm-100.json`
  - `workspace-tasks-representative-llm-100.json`
- Add `tests/test_domain_generation.py`
  - Cover shared contracts, parsing, batching, safety, and all three domains.
- Modify `tests/test_run_profiles.py`, `tests/test_llm_provider.py`,
  `tests/test_foundation_pipeline.py`, `tests/test_mobile_pipeline.py`,
  `tests/test_workspace_pipeline.py`, `tests/test_scale_evidence.py`,
  `tests/test_contracts.py`, and `tests/test_cli.py`.
- Modify canonical and lifecycle docs listed in Task 8.

## Implementation Tasks

### Task 1: Lock Compatibility And Add Run Profile V3

**Files:**

- Modify: `synthesis/run_profiles.py`
- Modify: `tests/test_run_profiles.py`
- Modify: `tests/test_cli.py`

- [x] **Step 1: Write compatibility tests before changing profile parsing.**

  Add tests proving every checked-in v1/v2 profile loads with its current
  `config_hash`, the profile-free `--use-llm` validation behavior is unchanged,
  and current deterministic commands do not acquire generation-contract fields.
  Capture representative existing hashes in the test instead of regenerating
  expected values from the implementation under test.

- [x] **Step 2: Write failing v3 profile tests.**

  Add exact cases for:

  ```python
  def test_v3_llm_requires_target_and_synthetic_context_policy(self) -> None:
      profile = load_profile_mapping({
          "schema_version": "run_profile_v3",
          "profile_id": "mobile-representative-test",
          "dataset_version": "dataset_mobile_representative_test",
          "profile_purpose": "benchmark",
          "seed": mobile_seed_mapping(),
          "generation": {
              "mode": "llm",
              "target_candidate_count": 2,
              "context_policy": "synthetic_fixture",
          },
          "features": {},
      })
      self.assertEqual(profile.generation.target_candidate_count, 2)
      self.assertEqual(profile.generation.context_policy, "synthetic_fixture")
  ```

  Also assert fixed validation failures for missing target, zero target, missing
  policy, unknown policy, extra generation keys, `context_policy` on fixture
  modes, non-benchmark v3 LLM purpose, and any v3 LLM profile with `source`.

- [x] **Step 3: Run the focused tests and confirm RED.**

  ```bash
  uv run python -m unittest tests.test_run_profiles tests.test_cli
  ```

  Expected: FAIL because `run_profile_v3` and `context_policy` are unsupported.

- [x] **Step 4: Implement strict v3 parsing without changing v1/v2 canonical bytes.**

  Extend the records with:

  ```python
  RUN_PROFILE_SCHEMA_VERSIONS = {
      "run_profile_v1",
      "run_profile_v2",
      "run_profile_v3",
  }
  GENERATION_CONTEXT_POLICIES = {"synthetic_fixture"}

  @dataclass(frozen=True)
  class RunProfileGeneration:
      mode: str
      target_candidate_count: int | None = None
      context_policy: str | None = None
  ```

  Pass `schema_version` and `profile_purpose` into generation compatibility
  validation. Include `context_policy` in canonical mappings only for v3 so old
  profile hashes remain byte-for-byte stable.

- [x] **Step 5: Run the profile and CLI tests and confirm GREEN.**

  ```bash
  uv run python -m unittest tests.test_run_profiles tests.test_cli
  ```

  Expected: PASS.

- [x] **Step 6: Commit the profile contract change during implementation.**

  ```bash
  git add synthesis/run_profiles.py tests/test_run_profiles.py tests/test_cli.py
  git commit -m "feat: add representative LLM run profile contract"
  ```

### Task 2: Add Shared And Domain-Owned Generation Specifications

**Files:**

- Create: `synthesis/domain_generation.py`
- Modify: `synthesis/tasks.py`
- Modify: `synthesis/mobile_tasks.py`
- Modify: `synthesis/workspace_tasks.py`
- Modify: `synthesis/domain_pipeline.py`
- Add: `tests/test_domain_generation.py`
- Modify: `tests/test_mobile_pipeline.py`
- Modify: `tests/test_workspace_pipeline.py`

- [x] **Step 1: Write failing shared-spec validation tests.**

  Cover duplicate task types, empty tool sets, task tools absent from the
  registry export, unsupported state-check names, non-synthetic context policy,
  unsafe keys/values, absolute paths, credential-like strings, empty grounding
  context, and non-positive or excessive per-call batch limits. Use a maximum of
  `20` candidates per provider call for v1.

- [x] **Step 2: Write failing domain ownership tests.**

  Assert that each bundle exposes `generation_spec` and that:

  ```python
  self.assertEqual(contacts.generation_spec.domain_id, "contacts_fixture")
  self.assertEqual(mobile.generation_spec.domain_id, "mobile_messages_fixture")
  self.assertEqual(workspace.generation_spec.domain_id, "workspace_tasks_fixture")
  self.assertIn("contact_followup", task_type_names(contacts.generation_spec))
  self.assertIn("mobile_reminder_creation", task_type_names(mobile.generation_spec))
  self.assertIn("workspace_task_creation", task_type_names(workspace.generation_spec))
  ```

  Assert exported tools exactly match each bundle registry's curated tool names
  and schemas. Assert fixture contexts contain only their documented synthetic
  identifiers/content and pass the unsafe-value scanner.

- [x] **Step 3: Run the new tests and confirm RED.**

  ```bash
  uv run python -m unittest tests.test_domain_generation tests.test_mobile_pipeline tests.test_workspace_pipeline
  ```

  Expected: FAIL because generation specifications do not exist.

- [x] **Step 4: Implement shared immutable specification records and validators.**

  Add the exact records from `Contract Decisions` and these constants:

  ```python
  DOMAIN_GENERATION_SPEC_VERSION = "domain_generation_spec_v1"
  SYNTHETIC_CONTEXT_POLICY = "synthetic_fixture"
  MAX_CANDIDATES_PER_CALL = 20
  ```

  Expose exact callables `validate_domain_generation_spec(spec) -> None`,
  `sanitized_generation_spec_metadata(spec) -> dict[str, object]`, and
  `grounding_context_hash(spec) -> str`. The metadata function returns only the
  fields permitted by `Domain Generation Specification`; the hash function uses
  canonical sorted-key compact JSON and prefixes the lowercase SHA-256 digest
  with `sha256:`.

  Reuse the repository's existing unsafe key/string vocabulary where practical;
  do not add a generic `utils` module.

- [x] **Step 5: Implement the three domain builders.**

  Contacts declares lookup and follow-up tasks; mobile declares message search,
  reminder creation, and draft reply; workspace declares search, task creation,
  and comment update. Each builder receives its concrete fixture environment and
  registry, reads only bounded synthetic fixture records, and returns one
  validated spec. Source-backed environments raise
  `source_backed_remote_context_not_allowed` before prompt construction.

- [x] **Step 6: Attach specs to `DomainPipelineBundle`.**

  Extend the dataclass and preserve specs during bundle rebuild:

  ```python
  @dataclass(frozen=True)
  class DomainPipelineBundle:
      domain_id: str
      environment: EnvironmentRuntime
      registry: ToolRegistry
      verifier: ExactAnswerVerifier
      candidate_generator: CandidateGenerator
      policy_generator: PolicyGenerator
      registry_builder: RegistryBuilder
      generation_spec: DomainGenerationSpec
      adapter_shim: LocalRuntimeAdapterShim | None = None
  ```

- [x] **Step 7: Run focused generation and domain tests.**

  ```bash
  uv run python -m unittest tests.test_domain_generation tests.test_mobile_pipeline tests.test_workspace_pipeline tests.test_domain_pack_contract
  ```

  Expected: PASS.

- [x] **Step 8: Commit the domain specification boundary during implementation.**

  ```bash
  git add synthesis/domain_generation.py synthesis/tasks.py synthesis/mobile_tasks.py synthesis/workspace_tasks.py synthesis/domain_pipeline.py tests/test_domain_generation.py tests/test_mobile_pipeline.py tests/test_workspace_pipeline.py
  git commit -m "feat: add domain-owned generation specifications"
  ```

### Task 3: Generate And Validate Structured Task Contracts

**Files:**

- Modify: `synthesis/domain_generation.py`
- Modify: `synthesis/task_contracts.py`
- Modify: `synthesis/tasks.py`
- Modify: `tests/test_domain_generation.py`
- Modify: `tests/test_task_contracts.py`
- Modify: `tests/test_llm_provider.py`

- [x] **Step 1: Write failing prompt-boundary tests.**

  Assert the prompt is deterministic and contains the selected domain id,
  task-type specs, curated tool schemas, bounded grounding context, requested
  batch size, and exact output keys. Assert it does not contain `AGENT_DATA`,
  authorization headers, host paths, source paths, provider payload labels, or
  fields that invite model-supplied lineage.

- [x] **Step 2: Write failing provider-output parser tests.**

  Add valid contacts/mobile/workspace records and reject unknown/extra keys,
  mismatched task types, missing required tools, unregistered tools, invalid tool
  arguments, unsupported expected-state checks, missing state checks for
  state-mutating task types, provider-supplied lineage/source/domain fields,
  duplicate ids, and branch plans.

- [x] **Step 3: Write execution-compatibility tests.**

  For each domain, convert a parsed contract with
  `candidate_from_task_contract`, run its existing scripted policy generator on a
  rebuilt environment, and verify it with the existing verifier. Include at
  least these task classes:

  - contacts lookup and follow-up;
  - mobile read-only search and reminder creation;
  - workspace read-only search and task creation.

- [x] **Step 4: Run focused tests and confirm RED.**

  ```bash
  uv run python -m unittest tests.test_domain_generation tests.test_task_contracts tests.test_llm_provider
  ```

  Expected: FAIL because the shared prompt/parser APIs do not exist.

- [x] **Step 5: Implement prompt construction and strict parsing.**

  Add public internal APIs with these exact signatures:

  - `build_domain_generation_prompt(spec: DomainGenerationSpec, *, requested_candidate_count: int) -> str`
  - `task_contract_from_provider_record(raw: Mapping[str, object], *, seed: DomainSeed, spec: DomainGenerationSpec, generation_lineage: Mapping[str, object]) -> TaskContract`
  - `parse_domain_task_contracts(content: Mapping[str, object], *, seed: DomainSeed, spec: DomainGenerationSpec, generation_lineage: Mapping[str, object]) -> list[TaskContract]`

  The prompt function serializes the validated spec with sorted-key compact
  JSON and exact output instructions. The item parser enforces the provider
  output contract, constructs local intent/policy/outcome/state records, calls
  `validate_task_contract`, and returns it. The collection parser requires
  exactly `{"task_contracts": [...]}`, rejects duplicate candidate ids, and
  delegates every item to the item parser.

  Construct local compatibility fields from the validated contract; never copy
  arbitrary compatibility or lineage mappings from the response.

- [x] **Step 6: Validate primary tool arguments before execution.**

  Expose a narrow `ToolRegistry.validate_arguments(tool_name, arguments)` method
  or equivalent domain-specific call using the existing `_validate_arguments`
  implementation. Do not duplicate JSON-schema validation in the generator.

- [x] **Step 7: Preserve the legacy contacts response parser.**

  Keep `generate_llm_backed_candidates(seed, client)` working for the
  profile-free compatibility path. Name the new path
  `generate_domain_llm_candidates` so tests and callers cannot confuse legacy
  diagnostic generation with v3 representative generation.

- [x] **Step 8: Run focused contract/provider tests.**

  ```bash
  uv run python -m unittest tests.test_domain_generation tests.test_task_contracts tests.test_llm_provider tests.test_tools
  ```

  Expected: PASS.

- [x] **Step 9: Commit structured generation during implementation.**

  ```bash
  git add synthesis/domain_generation.py synthesis/task_contracts.py synthesis/tasks.py synthesis/tools.py tests/test_domain_generation.py tests/test_task_contracts.py tests/test_llm_provider.py tests/test_tools.py
  git commit -m "feat: generate domain-aware task contracts"
  ```

### Task 4: Add Bounded Synchronous Batch Generation

**Files:**

- Modify: `synthesis/domain_generation.py`
- Modify: `synthesis/pipeline.py`
- Modify: `main.py`
- Modify: `tests/test_domain_generation.py`
- Modify: `tests/test_foundation_pipeline.py`
- Modify: `tests/test_cli.py`

- [x] **Step 1: Write failing batch tests.**

  Use a fake role registry/client that records requested counts. Assert targets
  `1`, `20`, `21`, and `45` produce call sizes `[1]`, `[20]`, `[20, 1]`, and
  `[20, 20, 5]`. Assert candidate ids are unique across batches and returned in
  deterministic curriculum/id order.

- [x] **Step 2: Write failing underfill/overflow/error tests.**

  Assert an empty batch, fewer contracts than requested, more contracts than
  requested, duplicate cross-batch id, malformed second batch, and provider
  failure after a successful first batch all fail the generation stage. No
  partial accepted dataset may claim the target was fulfilled.

- [x] **Step 3: Write failing post-bundle factory tests.**

  Prove the factory receives the selected domain bundle and its generation spec:

  ```python
  captured = []

  def factory(bundle):
      captured.append(bundle.generation_spec.domain_id)
      return bundle.candidate_generator

  run_foundation_pipeline(
      output_dir,
      seed_override=mobile_seed(),
      candidate_generator_factory=factory,
  )
  self.assertEqual(captured, ["mobile_messages_fixture"])
  ```

  Reject passing both `candidate_generator` and
  `candidate_generator_factory`.

- [x] **Step 4: Run focused tests and confirm RED.**

  ```bash
  uv run python -m unittest tests.test_domain_generation tests.test_foundation_pipeline tests.test_cli
  ```

  Expected: FAIL because bounded generation and the post-bundle factory do not
  exist.

- [x] **Step 5: Implement exact-target batch generation.**

  Add this result record:

  ```python
  @dataclass(frozen=True)
  class DomainGenerationResult:
      candidates: tuple[CandidateTask, ...]
      target_candidate_count: int
      generated_candidate_count: int
      provider_call_count: int
      spec_metadata: Mapping[str, object]

  ```

  Add exact callable
  `generate_domain_llm_candidates(seed: DomainSeed, client: object, *, spec: DomainGenerationSpec, target_candidate_count: int, role_registry: RoleRegistry | None = None) -> DomainGenerationResult`.
  It calculates each request as
  `min(spec.max_candidates_per_call, remaining)`, invokes the existing role,
  requires the response length to equal that request, accumulates unique ids,
  and returns only after `generated_candidate_count == target_candidate_count`.

  Any non-exact batch result raises sanitized `LLMProviderError` with cause
  `llm_response_schema_error`; do not introduce a provider-specific exception.

- [x] **Step 6: Add the candidate-generator factory boundary.**

  In `synthesis.pipeline`, define:

  ```python
  CandidateGeneratorFactory = Callable[[DomainPipelineBundle], CandidateGenerator]
  ```

  Resolve the domain bundle first, invoke the factory once, then generate
  candidates. Extend the internal generator result handling so the dataset
  writer receives sanitized generation-contract metadata, while ordinary
  candidate generators continue returning `list[CandidateTask]` unchanged.

- [x] **Step 7: Wire v3 profiles in `main.py`.**

  Replace `_profile_candidate_generator` with a factory decision:

  - no profile plus `--use-llm`: legacy contacts diagnostic generator;
  - v3 LLM profile: domain-aware generator with its exact target and selected
    bundle spec;
  - deterministic scale probe: existing generated-count lambda;
  - fixture modes: bundle-owned fixture generator.

  Ensure profile-local source rejection occurs before any provider client is
  invoked.

- [x] **Step 8: Run focused pipeline and CLI tests.**

  ```bash
  uv run python -m unittest tests.test_domain_generation tests.test_foundation_pipeline tests.test_cli tests.test_candidate_processing
  ```

  Expected: PASS.

- [x] **Step 9: Commit bounded generation wiring during implementation.**

  ```bash
  git add synthesis/domain_generation.py synthesis/pipeline.py main.py tests/test_domain_generation.py tests/test_foundation_pipeline.py tests/test_cli.py
  git commit -m "feat: add bounded domain LLM generation"
  ```

### Task 5: Persist Sanitized Generation Contract Evidence

**Files:**

- Modify: `synthesis/datasets.py`
- Modify: `synthesis/contracts.py`
- Modify: `synthesis/profile_decisions.py`
- Modify: `synthesis/dataset_release.py`
- Modify: `synthesis/release_pack.py`
- Modify: `tests/test_contracts.py`
- Modify: `tests/test_foundation_pipeline.py`
- Modify: `tests/test_profile_decisions.py`
- Modify: `tests/test_dataset_release.py`
- Modify: `tests/test_release_pack.py`

- [x] **Step 1: Write failing manifest contract tests.**

  Add the exact `generation_contract` shape from `Contract Decisions`. Validate
  exact keys, schema/spec version, allowed context policy, positive counts,
  `generated <= target`, `target_fulfilled == (generated == target)`, boolean
  eligibility, fixed reason-code vocabulary, and canonical lowercase SHA-256.

- [x] **Step 2: Write failing redaction tests.**

  Insert sentinels for prompt text, grounding rows, message bodies, workspace
  document bodies, source paths, provider headers, API keys, tool arguments, and
  host paths at every generation-contract level. Validators must reject them;
  successful artifacts must not contain the sentinel strings.

- [x] **Step 3: Write failing cross-artifact propagation tests.**

  Assert profile decision, dataset release, release pack, and standalone release
  verification preserve the same sanitized generation-contract mapping or its
  hash-bound profile metadata without changing their decision semantics.

- [x] **Step 4: Run focused tests and confirm RED.**

  ```bash
  uv run python -m unittest tests.test_contracts tests.test_foundation_pipeline tests.test_profile_decisions tests.test_dataset_release tests.test_release_pack
  ```

  Expected: FAIL because generation-contract metadata is not yet allowed.

- [x] **Step 5: Build generation evidence through one canonical function.**

  Add:

  ```python
  GENERATION_INELIGIBILITY_REASON_CODES = {
      "profile_contract_not_representative",
      "generation_spec_missing_or_mismatched",
      "context_policy_not_allowed",
      "source_backed_remote_context_not_allowed",
      "target_candidate_count_unfulfilled",
      "generation_evidence_missing",
  }

  ```

  Add exact callable
  `build_generation_contract_evidence(*, profile: RunProfile | None, spec_metadata: Mapping[str, object] | None, target_candidate_count: int | None, generated_candidate_count: int | None) -> dict[str, object]`.
  It derives `target_fulfilled`, eligibility, and the ordered fixed reason codes
  from those validated inputs; callers cannot pass either derived field.

  Compute eligibility locally. Do not accept a provider- or profile-supplied
  `representative_eligible` boolean.

- [x] **Step 6: Attach evidence to run-profile metadata before artifact writes.**

  Keep existing sample/rejection lineage compact: manifest-level sanitized
  metadata is canonical; per-record lineage may include only spec version,
  context policy, target fulfillment, and eligibility if required by current
  profile attribution behavior.

- [x] **Step 7: Update validators and compatible consumers.**

  Centralize validation in `synthesis.contracts`; consumers copy only validated
  sanitized fields. Do not make release admission depend on representative
  eligibility in this plan.

- [x] **Step 8: Run focused artifact tests.**

  ```bash
  uv run python -m unittest tests.test_contracts tests.test_foundation_pipeline tests.test_profile_decisions tests.test_dataset_release tests.test_release_pack
  ```

  Expected: PASS.

- [x] **Step 9: Commit generation evidence during implementation.**

  ```bash
  git add synthesis/datasets.py synthesis/contracts.py synthesis/profile_decisions.py synthesis/dataset_release.py synthesis/release_pack.py tests/test_contracts.py tests/test_foundation_pipeline.py tests/test_profile_decisions.py tests/test_dataset_release.py tests/test_release_pack.py
  git commit -m "feat: record representative generation evidence"
  ```

### Task 6: Harden Representative Classification

**Files:**

- Modify: `synthesis/scale_evidence.py`
- Modify: `synthesis/contracts.py`
- Modify: `tests/test_scale_evidence.py`
- Modify: `tests/test_contracts.py`

- [x] **Step 1: Replace the permissive classification tests with evidence tests.**

  Prove that `generation_mode: llm` alone is `insufficient_evidence`. A run is
  representative only when all required artifacts agree on domain/profile/
  dataset identity and validated generation-contract evidence says:

  ```python
  {
      "spec_version": "domain_generation_spec_v1",
      "context_policy": "synthetic_fixture",
      "target_candidate_count": 100,
      "generated_candidate_count": 100,
      "target_fulfilled": True,
      "representative_eligible": True,
      "reason_codes": [],
  }
  ```

- [x] **Step 2: Add negative classification cases.**

  Cover missing evidence, unfulfilled targets, non-empty reason codes, false
  eligibility, mismatched counts, unknown spec version, source-backed context,
  fixture generation modes at 100+ candidates, and cross-artifact metadata
  mismatch. Each produces `insufficient_evidence` and the campaign recommendation
  `expand_representative_evidence`.

- [x] **Step 3: Preserve activation priority tests.**

  With valid representative evidence, retain the current stable priority:
  insufficient evidence, quality/remediation, semantic duplicate detection,
  async orchestration, then no change. Classification hardening must not change
  profile thresholds or recompute decisions.

- [x] **Step 4: Run scale tests and confirm RED.**

  ```bash
  uv run python -m unittest tests.test_scale_evidence tests.test_contracts
  ```

  Expected: FAIL because the classifier currently checks only validity and
  generation mode.

- [x] **Step 5: Implement evidence-backed classification.**

  Replace the loose mapping API with an explicit validated input record or
  helper that reads generation-contract metadata from loaded artifacts. Return
  `diagnostic_only` for known deterministic generation modes and
  `insufficient_evidence` for incomplete/invalid LLM evidence. Return
  `representative` only for the complete v3 contract above.

- [x] **Step 6: Run scale and downstream regression tests.**

  ```bash
  uv run python -m unittest tests.test_scale_evidence tests.test_contracts tests.test_downstream_benchmark
  ```

  Expected: PASS.

- [x] **Step 7: Commit classifier hardening during implementation.**

  ```bash
  git add synthesis/scale_evidence.py synthesis/contracts.py tests/test_scale_evidence.py tests/test_contracts.py
  git commit -m "feat: require representative generation evidence"
  ```

### Task 7: Add Three-Domain Profiles And Mocked End-To-End Evidence

**Files:**

- Add: `tests/fixtures/run_profiles/contacts-representative-llm-100.json`
- Add: `tests/fixtures/run_profiles/mobile-messages-representative-llm-100.json`
- Add: `tests/fixtures/run_profiles/workspace-tasks-representative-llm-100.json`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_llm_provider.py`
- Modify: `tests/test_scale_evidence.py`
- Modify: `tests/fixtures/evidence_campaigns/three-domain-diagnostic.json`

- [x] **Step 1: Add and validate the three operator profiles.**

  Each uses `run_profile_v3`, `profile_purpose: benchmark`, its canonical domain,
  a domain-appropriate taxonomy, `mode: llm`, target `100`, context policy
  `synthetic_fixture`, no source, and no optional feature flags. Profile ids and
  dataset versions must be distinct and canonical.

- [x] **Step 2: Write mocked two-candidate CLI runs for every domain.**

  Tests create temporary v3 profiles with target `2`, patch the provider boundary
  with domain-valid responses, and request evaluation, profile decision, dataset
  release, release pack, and release-quality artifacts. Assert no real network
  call occurs.

- [x] **Step 3: Prove read-only and state-mutating behavior end to end.**

  The mobile response includes one search and one reminder/draft state change;
  workspace includes one search and one task/comment state change; contacts
  includes lookup and follow-up. Assert accepted samples have correct domain,
  policy, verifier, episode, and generation lineage.

- [x] **Step 4: Build a mocked representative three-domain campaign.**

  Use temporary artifact directories and exact fulfilled targets small enough
  for tests. Feed those directories into `build_representative_scale_evidence`
  and assert all domains classify as representative. Because the test counts are
  below activation thresholds and quality passes, expected recommendation is
  `no_change_recommended`.

- [x] **Step 5: Preserve the diagnostic campaign fixture.**

  The existing deterministic fixture campaign must still classify all domains
  as diagnostic and recommend `expand_representative_evidence` even if test data
  is mechanically expanded beyond 100 candidates.

- [x] **Step 6: Run CLI and campaign tests.**

  ```bash
  uv run python -m unittest tests.test_cli tests.test_llm_provider tests.test_scale_evidence tests.test_evaluation tests.test_profile_decisions tests.test_dataset_release tests.test_release_pack tests.test_release_quality
  ```

  Expected: PASS without network access.

- [x] **Step 7: Commit representative fixtures and evidence tests during implementation.**

  ```bash
  git add tests/fixtures/run_profiles/contacts-representative-llm-100.json tests/fixtures/run_profiles/mobile-messages-representative-llm-100.json tests/fixtures/run_profiles/workspace-tasks-representative-llm-100.json tests/fixtures/evidence_campaigns/three-domain-diagnostic.json tests/test_cli.py tests/test_llm_provider.py tests/test_scale_evidence.py
  git commit -m "test: cover three-domain representative generation"
  ```

### Task 8: Synchronize Documentation And Complete The Plan

**Files:**

- Modify: `README.md`
- Modify: `AGENTS.md`
- Modify: `ARCHITECTURE.md`
- Modify: `docs/README.md`
- Modify: `docs/BACKEND.md`
- Modify: `docs/DATA.md`
- Modify: `docs/SECURITY.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/PLANS.md`
- Modify: `docs/exec-plans/active/README.md`
- Move: `docs/exec-plans/active/0043-domain-aware-representative-generation-and-campaign-readiness.md` to `docs/exec-plans/completed/0043-domain-aware-representative-generation-and-campaign-readiness.md`

- [x] **Step 1: Document the generation boundary.**

  Update backend ownership, v3 profile semantics, task-contract provider output,
  synchronous batch behavior, representative eligibility, and the strict
  separation between ephemeral provider context and persisted sanitized
  evidence.

- [x] **Step 2: Document security and non-claims.**

  State that v1 supports synthetic fixture context only; profile-local source
  rows are never sent to the provider; prompts and grounding rows are not
  persisted; a mocked or real representative run does not automatically activate
  infrastructure, semantic duplicate detection, release admission, or model
  training.

- [x] **Step 3: Add operator commands without making them default.**

  Document one command per representative profile with explicit output
  directories and required evidence flags. Warn that the checked-in target of
  100 may incur provider cost and remains synchronous until evidence activates
  plan 0014.

- [x] **Step 4: Run focused verification.**

  ```bash
  uv run python -m unittest tests.test_run_profiles tests.test_domain_generation tests.test_task_contracts tests.test_llm_provider tests.test_foundation_pipeline tests.test_mobile_pipeline tests.test_workspace_pipeline tests.test_contracts tests.test_profile_decisions tests.test_scale_evidence tests.test_cli
  ```

  Expected: PASS.

- [x] **Step 5: Run the full suite and docs validator.**

  ```bash
  uv run python -m unittest
  uv run python scripts/validate_docs.py
  ```

  Expected: both commands exit `0` with no failures.

- [x] **Step 6: Record the evidence-backed next decision.**

  If no real provider campaign was run, state that the repository is campaign
  ready but plan 0014 and TD-0002 remain deferred. If a real campaign exists,
  record only sanitized classifications, recommendation, triggered signal names,
  counts, and runtime; do not copy prompts, grounding context, provider payloads,
  or source rows into docs.

- [x] **Step 7: Complete the lifecycle transition.**

  Mark every task complete, add completion date and exact validation evidence,
  move this file to `completed/`, update `docs/PLANS.md`, both plan bucket
  indexes, docs index, Roadmap, and `AGENTS.md`. Do not activate 0014 or TD-0002
  without an explicit representative evidence result and operator decision.

- [x] **Step 8: Commit completed implementation and docs.**

  ```bash
  git add README.md AGENTS.md ARCHITECTURE.md docs synthesis main.py tests
  git commit -m "feat: add domain-aware representative generation"
  ```

## Validation Commands

```bash
uv run python -m unittest tests.test_run_profiles tests.test_domain_generation tests.test_task_contracts tests.test_llm_provider tests.test_foundation_pipeline tests.test_mobile_pipeline tests.test_workspace_pipeline tests.test_contracts tests.test_profile_decisions tests.test_scale_evidence tests.test_cli
uv run python -m unittest
uv run python scripts/validate_docs.py
```

Real-provider commands are optional operational evidence. They must never be run
as part of the unit suite or plan completion without explicit provider
configuration and operator awareness of cost.

## Acceptance Criteria

- Existing v1/v2 profiles retain their canonical hashes and behavior.
- Profile-free `--use-llm` remains a contacts-compatible diagnostic path.
- V3 LLM profiles require a positive target, benchmark purpose, and
  `synthetic_fixture` context policy, and reject profile-local sources.
- Each domain owns a validated generation specification matching its curated
  tools, task types, and state-check vocabulary.
- The shared generator emits and validates `TaskContract` records for contacts,
  mobile, and workspace without provider-supplied lineage or source metadata.
- Mobile and workspace generated candidates cover both read-only and
  state-mutating execution through existing policies and verifiers.
- Batching is synchronous, bounded to at most 20 candidates per call, globally
  unique, deterministic, and exactly fulfills the declared target or fails.
- No partial batch result claims representative eligibility.
- Manifests and downstream artifacts contain only sanitized generation-contract
  metadata and hashes, never prompts, grounding rows, source payloads,
  credentials, headers, tool arguments, or host paths.
- `generation_mode: llm` alone is insufficient for representative
  classification.
- Only complete, consistent v3 generation evidence can support Plan 0042
  activation recommendations.
- Existing async and semantic-duplicate thresholds remain unchanged and owned by
  `synthesis.profile_decisions`.
- Default deterministic CLI behavior, release admission, release-pack
  verification, and downstream benchmark exchange remain compatible.
- Focused tests, the full unit suite, and documentation validation pass.
- Plan 0014 and TD-0002 remain deferred unless separately activated by real
  representative evidence and explicit operator direction.

## Risks And Mitigations

- **Synthetic fixture context may still be too narrow for useful diversity.**
  Record it explicitly as the context policy, require exact target/quality
  evidence, and let the campaign recommend generation improvement before scale
  infrastructure.
- **Tool schemas alone may produce unverifiable tasks.** Domain-owned task types
  and expected-state vocabularies constrain provider output before execution.
- **A remote prompt may leak governed source data.** Reject source-backed v3 LLM
  profiles in this plan and scan grounding context before provider invocation.
- **Large targets may amplify provider cost.** Bound calls to 20 candidates,
  keep real runs opt-in, expose target counts in profiles, and retain synchronous
  execution until measured evidence says otherwise.
- **Partial batches may be mistaken for representative scale.** Require exact
  target fulfillment and computed eligibility; fail closed on any later-batch
  error.
- **The new metadata may drift across artifacts.** Validate one canonical
  generation-contract shape and assert identity across manifest, decisions,
  release, pack, and scale evidence.
- **The shared module may accumulate domain allowlists.** Keep task semantics and
  grounding construction in domain owners; shared code validates only declared
  specifications.
- **A mocked campaign may be overclaimed.** Label it contract evidence only;
  real campaign recommendations remain optional operational inputs.
