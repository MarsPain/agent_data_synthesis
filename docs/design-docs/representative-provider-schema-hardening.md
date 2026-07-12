# Representative Provider Schema Hardening Design

## Status

Approved for implementation on 2026-07-12.

This design follows the real-provider failure observed after completion of
[domain-aware representative generation](domain-aware-representative-generation.md).
It hardens that boundary before another three-domain representative campaign.

## Purpose

The first real provider attempt used the checked-in `run_profile_v3` benchmark
profiles for contacts, mobile messages, and workspace tasks. Every domain made
a remote provider call, but the first generated batch failed strict task-contract
validation with `llm_response_schema_error`. The failure artifact retained the
safe error class and provider lineage but not a precise sanitized schema reason,
so the repository could not distinguish an unexpected key from an invalid tool
argument, wrong task type, or batch-count mismatch.

All three runs then reached a second failure while writing
`dataset_release_report.json`. Because generation produced zero accepted
samples, the observed task-type and tool-combination coverage lists were empty.
The release-completeness validator rejected those empty observations instead of
allowing the report to record `insufficient_evidence`.

The objective is to make real-provider generation diagnosable and safely
retryable without weakening task contracts, persisting provider payloads, or
mistaking an empty benchmark run for a release candidate.

## Evidence And Root Cause Boundary

The following facts are established by sanitized artifacts from all three
failed runs:

- provider configuration and network access succeeded;
- each provider returned a JSON response with token usage and lineage;
- parsing failed before any candidate entered execution;
- each run emitted one `generation_stage` rejection with cause
  `llm_response_schema_error` and error class `ValueError`;
- accepted count was zero, so observed release coverage was empty; and
- the CLI terminated in release-completeness contract validation rather than
  writing the expected ineligible or insufficient-evidence report.

Raw provider responses were intentionally not persisted. Therefore the exact
provider field mismatch cannot be reconstructed after the fact. The repair must
improve future sanitized diagnostics rather than introduce raw-response logging.

## Decision

Keep provider output validation strict, reduce the maximum generated batch from
20 candidates to 5, describe the complete output contract in the prompt, and
propagate one fixed sanitized schema reason code when parsing fails. Separately,
allow empty observed coverage lists in release-completeness reports while
retaining non-empty required threshold lists.

After local verification, run a paid probe of exactly two candidates in each
domain. Only if all three probes complete generation, execution, and reporting
will the operator restart the three 100-candidate representative runs. A failed
probe stops the workflow before full campaign cost is incurred.

## Alternatives Considered

### Normalize malformed provider output

The parser could delete unknown keys, reorder tools, coerce values, or fill
missing state checks. This may increase apparent success, but it would allow the
framework to invent task semantics that the provider did not supply. It would
also weaken the fail-closed boundary used to classify representative evidence.
This option is rejected.

### Use provider-specific JSON Schema enforcement

The client could depend on a provider-specific structured-output or JSON Schema
API. This can provide strong syntax guarantees, but it would narrow the current
OpenAI-compatible provider boundary and require capability negotiation that the
repository does not yet model. This option remains possible future work and is
not required for this repair.

### Strict validation with bounded batches and sanitized reasons

This option retains provider portability and the existing security posture. It
improves generation reliability by limiting response size, makes failures
actionable without storing payloads, and changes only the invalid empty-report
behavior. This is the selected approach.

## Architecture

### Prompt contract

`synthesis.domain_generation` continues to own generic provider mechanics. Its
prompt will include a machine-readable output contract in addition to the
domain task types, tool schemas, and grounding context already present.

The output contract must declare:

- the response object contains exactly `task_contracts`;
- `task_contracts` contains exactly the requested number of records;
- every record contains exactly the existing provider record keys;
- the JSON type and non-empty rule for every field;
- `required_tools` exactly matches the selected task-type declaration;
- `primary_tool` is the first required tool;
- read-only task types use an empty `expected_state` list;
- state-mutating task types provide the declared expected-state check; and
- no Markdown fences, commentary, lineage, source, provider, path, prompt, or
  credential fields are allowed.

The prompt contract does not contain new domain allowlists. Domain-owned
generation specifications remain the source of task types, tools, schemas, and
expected-state vocabularies.

### Batch size

Every supported domain generation specification will set
`max_candidates_per_call` to 5. A 100-candidate run therefore uses 20 successful
provider batches per domain. Exact target fulfillment, global candidate-id
uniqueness, and fail-closed partial-batch behavior remain unchanged.

The batch limit is part of sanitized generation-spec metadata and therefore
remains visible without revealing prompt or grounding values.

### Sanitized schema failure taxonomy

Introduce a domain-generation validation error carrying one reason from this
closed taxonomy:

- `response_shape_mismatch`: the top-level response is not the exact
  `task_contracts` object or the field is not a list;
- `provider_record_keys_mismatch`: a task record has missing or extra keys;
- `invalid_task_type`: the record names an undeclared domain task type;
- `invalid_required_tools`: required tools do not exactly match the task type;
- `invalid_primary_tool`: the primary tool is not the declared first tool;
- `invalid_tool_arguments`: primary or expected-state arguments violate the
  curated tool schema;
- `invalid_difficulty`: difficulty is not a valid mapping;
- `invalid_expected_state`: state evidence is missing, duplicated, malformed,
  or unsupported;
- `invalid_required_capabilities`: capabilities are empty, malformed, or
  duplicated;
- `unsafe_provider_value`: a provider record contains a forbidden key, unsafe
  path-like value, credential-like value, or unsupported value type;
- `duplicate_candidate_id`: candidate identifiers repeat within or across
  batches; and
- `batch_count_mismatch`: a validly shaped batch does not contain exactly the
  requested number of contracts.

Only the reason code is propagated into the sanitized generation-stage
rejection. The rejection must not include raw task records, field values, tool
arguments, provider payloads, prompts, grounding context, response excerpts, or
exception messages derived from provider content.

Existing public cause semantics remain `llm_response_schema_error`; consumers
that only understand the cause continue to work. The new reason is subordinate
diagnostic evidence, not a new admission decision.

### Empty release evidence

Release-completeness threshold declarations remain non-empty because every
supported domain has required task types and tool combinations. Observed
coverage differs: a failed or empty run can legitimately observe no accepted
task type and no accepted tool combination.

The contract will therefore accept empty sequences only for:

- `release_completeness.observed.task_types`; and
- `release_completeness.observed.tool_combinations`.

The release-completeness builder must record a non-passing decision when either
observed list is empty. The enclosing dataset-release decision remains
`ineligible` for benchmark profiles or `insufficient_evidence` when required
evidence is missing. Empty observations can never produce `passed`.

## Data Flow

```text
run_profile_v3 benchmark profile
  -> domain generation specification with batch limit 5
  -> complete machine-readable output contract
  -> remote OpenAI-compatible JSON call
  -> strict provider task-contract validation
     -> valid: existing CandidateTask execution and quality gates
     -> invalid: fixed sanitized schema reason, no raw payload persistence
  -> manifest, quality, evaluation, and profile decisions
  -> release completeness accepts truthful empty observed coverage
  -> ineligible or insufficient-evidence release report instead of exception
```

## Probe And Retry Workflow

### Local verification gate

Before any further paid call:

1. Run focused domain-generation, contract, dataset-release, and CLI tests.
2. Run the complete unit suite.
3. Run the documentation validator.
4. Confirm no test or artifact contains raw provider responses or secrets.

### Three-domain paid probe

Create runtime-only `run_profile_v3` benchmark profiles under `artifacts/` with
the same domain specifications and context policy as the representative
profiles, but with distinct profile/dataset ids and
`target_candidate_count: 2`.

Run contacts, mobile messages, and workspace tasks independently with the full
evaluation, profile-decision, dataset-release, and release-quality-audit flags.
For each probe, require:

- process exit code zero;
- generated and target counts both equal 2;
- `target_fulfilled` and `representative_eligible` are true;
- samples and reports pass their existing contracts;
- no generation-stage rejection exists; and
- no raw prompt, grounding context, provider payload, authorization header, API
  key, or local secret appears in persisted artifacts.

If any probe fails, stop. Preserve only sanitized artifacts and investigate its
reason code before another paid attempt.

### Representative retry

If all probes pass, start the existing three 100-candidate profiles in separate
persistent background sessions. Keep one log per domain and record the session
identifier outside dataset artifacts. Do not overwrite a previous successful
representative output directory.

After completion, verify all required artifacts and then build
`representative_scale_evidence_v1`. The evidence report, rather than the mere
fact that a retry occurred, determines whether generation quality,
semantic-duplicate detection, or async orchestration is the next development
priority.

## Error Handling

- Provider transport, HTTP, timeout, rate-limit, and JSON-decoding failures keep
  the existing bounded provider retry policy.
- Strict task-contract failures do not retry automatically within the same paid
  probe; they produce one sanitized reason and stop that domain run.
- A failed provider batch never contributes partial candidates to
  representative eligibility.
- A zero-accepted run completes its reporting path with a non-passing decision
  rather than raising a contract exception.
- A background representative process that exits non-zero is reported as
  failed; it is not silently restarted.
- Full 100-candidate retries require all three two-candidate probes to pass.

## Testing Strategy

Use red-green-refactor cycles for each behavior change.

### Domain generation tests

- Prompt tests assert the complete output contract and batch limit 5.
- Parser tests cover every sanitized reason code with synthetic records.
- Generator tests cover within-batch duplicates, cross-batch duplicates, and
  batch-count mismatch without exposing provider values.
- Regression tests assert generation-stage rejections contain the fixed reason
  but not exception text, raw provider content, prompts, or grounding context.

### Release reporting tests

- Contract tests accept empty observed task-type and tool-combination lists.
- Contract tests continue rejecting empty required threshold lists.
- Dataset-release tests build a report from zero accepted samples and assert a
  non-passing completeness decision.
- CLI tests assert a generation-stage failure still writes a valid dataset
  release report and exits through the documented pipeline behavior.

### Compatibility tests

- Existing deterministic v1/v2 profiles retain hashes and behavior.
- Existing v3 profile hashes remain stable because only runtime generation-spec
  batching changes; checked-in profile JSON is unchanged.
- Existing release-candidate reports with non-empty coverage remain unchanged.
- Scale-evidence classification continues requiring fulfilled, consistent v3
  generation-contract evidence.

## File Map

- Modify `synthesis/domain_generation.py`
  - add the output-contract prompt shape, sanitized schema validation error, and
    reason propagation at the shared generation boundary;
- Modify `synthesis/domain_pipeline.py`, `synthesis/mobile_tasks.py`, and
  `synthesis/workspace_tasks.py`
  - set every supported domain specification batch limit to 5;
- Modify `synthesis/tasks.py` or the existing generation-stage rejection adapter
  - persist the fixed sanitized schema reason without changing the public cause;
- Modify `synthesis/contracts.py`
  - allow empty observed release coverage while preserving non-empty threshold
    declarations and secret scanning;
- Modify `synthesis/dataset_release.py`
  - ensure empty accepted coverage produces a valid non-passing decision;
- Modify `tests/test_domain_generation.py`, `tests/test_contracts.py`,
  `tests/test_dataset_release.py`, and `tests/test_cli.py`
  - add red-green regression coverage for both production failures;
- Update `docs/BACKEND.md`, `docs/DATA.md`, `docs/SECURITY.md`, and
  `docs/ROADMAP.md` during implementation;
- Add a versioned execution plan under `docs/exec-plans/active/` only after this
  design is reviewed.

## Acceptance Criteria

- Provider task contracts remain strict; no automatic key dropping, coercion,
  semantic completion, or argument repair is introduced.
- All supported domains use at most 5 candidates per provider call.
- Provider schema failures persist exactly one allowed sanitized reason code.
- No raw provider payload or provider-derived exception message is persisted.
- Zero accepted samples produce valid quality, evaluation, profile-decision,
  dataset-release, and release-audit artifacts where applicable.
- Empty observed release coverage can never pass release completeness.
- Focused tests, the full unit suite, and documentation validation pass before
  paid probes.
- Contacts, mobile, and workspace probes each generate exactly 2 candidates and
  complete the reporting chain before any 100-candidate retry starts.
- Full representative retries run only after all three probes pass and require
  fresh post-run artifact verification.

## Out Of Scope

- Persisting or sampling raw provider responses for debugging.
- Provider-specific JSON Schema capability negotiation.
- Automatic repair or normalization of malformed provider task contracts.
- Async orchestration, durable queues, cancellation, or resumption.
- Semantic duplicate detection, embeddings, or clustering.
- Changing dataset release admission so benchmark profiles become releaseable.
- Model training, downstream training-service calls, or automatic plan
  activation.

## Documentation Impact

This file is the canonical design record for the repair. The implementation
change set must keep code, tests, `docs/BACKEND.md`, `docs/DATA.md`,
`docs/SECURITY.md`, `docs/ROADMAP.md`, and the execution-plan lifecycle in
lockstep. Root entrypoints change only if operator commands or plan navigation
change.
