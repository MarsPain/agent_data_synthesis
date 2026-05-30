# Plan 0017: Configurable Run Profiles and Scale Probe

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status

Planned on 2026-05-29. Completed on 2026-05-29.

## Goal

Add declarative run profiles and a deterministic scale-probe path so the
synchronous foundation pipeline can be configured, repeated, and measured before
activating async orchestration or semantic duplicate detection.

## Architecture

The plan adds a narrow run-profile boundary above the existing synchronous
pipeline. A profile describes seed metadata, generation mode, target candidate
count, and existing opt-in feature flags; the pipeline consumes validated values
without changing default behavior. The first scale probe remains deterministic
and contacts-domain-only so artifact changes are reproducible and useful as
evidence for later decisions about plan 0014 or `TD-0002`.

## Tech Stack

- Python standard library dataclasses, JSON parsing, hashing, and unittest.
- Existing local pipeline modules under `synthesis/`.
- Existing artifact validation through `scripts/validate_docs.py` and
  `uv run python -m unittest`.

---

## Basis

This plan is derived from the current MVP gap and the explicit deferral of
async orchestration.

- [../../PLANS.md](../../PLANS.md) has no completed successor after
  [../completed/0016-candidate-execution-boundary-and-orchestration-readiness.md](../completed/0016-candidate-execution-boundary-and-orchestration-readiness.md)
  and keeps
  [../deferred/0014-async-local-orchestration-with-durable-queues.md](../deferred/0014-async-local-orchestration-with-durable-queues.md)
  deferred until single runs exceed about 10 minutes or 100+ candidates.
- [../../product-specs/framework-mvp.md](../../product-specs/framework-mvp.md)
  says the MVP begins with a user-provided domain config and optional seed
  records, but the current CLI primarily exposes fixed foundation fixture flags.
- [../../BACKEND.md](../../BACKEND.md) states that the candidate-processing
  boundary is orchestration-ready but not concurrency-safe. Async work still
  requires environment isolation, curated tool registry mutation rules,
  deterministic duplicate admission for out-of-order completion, and artifact
  merge ordering.
- [../../ROADMAP.md](../../ROADMAP.md) places async orchestration after the
  candidate execution boundary, but the deferred plan's rationale says the
  current fixture scale does not justify durable queues yet.
- [../tech-debt/README.md](../tech-debt/README.md) keeps `TD-0002` semantic
  duplicate detection unresolved until dataset volume or curriculum benchmark
  signals justify implementation.

## Scope

- Add a versioned `run_profile_v1` JSON contract for local foundation runs.
- Add a profile loader that validates schema, applies explicit defaults, and
  computes a stable config hash without writing secrets.
- Allow `main.py --run-profile <path>` to configure the existing synchronous
  pipeline while preserving all current CLI flags and default behavior.
- Add a deterministic scale-probe candidate generator for contacts-domain runs
  with a configurable `target_candidate_count`.
- Record sanitized run-profile metadata in `manifest.json` so runs are
  attributable without storing raw credentials or large input blobs. Add
  quality-report slices only if the implementation can do so without wider data
  plumbing.
- Add tests and fixture profiles that prove profile runs are reproducible and
  that default runs remain unchanged.
- Update docs with the profile contract, synchronous scale-probe workflow, and
  decision criteria for when to revisit plan 0014 or `TD-0002`.

## Out of Scope

- Implementing async orchestration, durable queues, cancellation, or resumption
  from plan 0014.
- Implementing semantic duplicate detection from `TD-0002`.
- Building a general domain/environment builder beyond the existing contacts
  foundation environment.
- Enabling external MCP servers, browser automation, arbitrary generated tool
  handlers, generated environment builders, or generated verifiers.
- Changing default `uv run python main.py` output paths, accepted/rejected
  counts, artifact schemas, or feature-flag semantics.
- Writing raw API keys, authorization headers, source payloads, raw fetched
  source URLs, or provider prompts into manifests or quality reports.

## Proposed Run Profile Contract

The first profile format should stay deliberately small:

```json
{
  "schema_version": "run_profile_v1",
  "profile_id": "foundation_scale_probe_25",
  "dataset_version": "dataset_foundation_scale_probe_25",
  "seed": {
    "seed_id": "seed_contacts_v1",
    "domain": "contacts",
    "description": "Synthetic contact lookup and follow-up tasks.",
    "task_taxonomy": ["contact_lookup", "contact_followup"]
  },
  "generation": {
    "mode": "deterministic_scale_probe",
    "target_candidate_count": 25
  },
  "features": {
    "enable_branching": false,
    "enable_task_expansion": false,
    "enable_refinement": false,
    "enable_mcp_adapter": false,
    "enable_sandbox_fixture": false,
    "enable_source_governance_fixture": false
  }
}
```

Only these generation modes are in scope:

- `foundation_fixture`: current deterministic foundation candidates.
- `deterministic_scale_probe`: deterministic contacts candidates up to
  `target_candidate_count`.
- `llm`: existing remote LLM-backed candidate generation.

Profile fields should be translated into existing pipeline arguments instead of
creating a second runtime path.

## File Map

- Create `synthesis/run_profiles.py` for run-profile records, validation,
  defaults, sanitized export metadata, and stable config hashing.
- Modify `main.py` to parse `--run-profile`, merge profile values with existing
  CLI defaults, and keep current flags working without a profile.
- Modify `synthesis/pipeline.py` to accept an optional seed override and optional
  sanitized run-profile metadata for artifact writing.
- Modify `synthesis/tasks.py` to add the deterministic scale-probe candidate
  generator and keep `generate_foundation_candidates()` unchanged.
- Modify `synthesis/datasets.py` and `synthesis/contracts.py` to validate and
  write optional manifest run-profile metadata.
- Modify `synthesis/quality.py` if implementation adds `run_profile_id` or
  `generation_mode` slices to quality reports.
- Add `tests/test_run_profiles.py` for profile parsing, validation, config
  hashing, and deterministic scale-probe generation.
- Modify `tests/test_cli.py`, `tests/test_foundation_pipeline.py`, and
  `tests/test_quality_reporting.py` for profile CLI behavior, artifact
  stability, and optional manifest/report metadata.
- Add fixture profiles under `tests/fixtures/run_profiles/`.
- Update [../../DATA.md](../../DATA.md), [../../BACKEND.md](../../BACKEND.md),
  [../../ROADMAP.md](../../ROADMAP.md), and [../../product-specs/framework-mvp.md](../../product-specs/framework-mvp.md)
  only where the implemented profile contract becomes canonical.
- Update this plan as tasks complete. When accepted, move it to
  `docs/exec-plans/completed/` and update [../../PLANS.md](../../PLANS.md).

## Implementation Tasks

### Task 1: Lock Current CLI and Artifact Behavior

- [x] Add characterization coverage proving `uv run python main.py` still uses
  the existing foundation defaults when no `--run-profile` is provided.
- [x] Cover these existing paths before adding profile behavior:
  - default foundation run;
  - `--enable-branching`;
  - `--enable-task-expansion`;
  - `--enable-mcp-adapter`;
  - `--enable-sandbox-fixture`;
  - controlled network source with `--mock-source-fixture`.
- [x] Normalize volatile output directories and dataset ids in artifact
  comparisons. Do not weaken assertions to file-existence checks only.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_foundation_pipeline tests.test_cli
  ```

  Expected result: all selected tests pass before profile implementation begins.

### Task 2: Define Run Profile Records and Validation

- [x] Create `synthesis/run_profiles.py`.
- [x] Add immutable records for profile seed, generation, features, and the
  complete run profile.
- [x] Add `load_run_profile(path: Path) -> RunProfile` that:
  - rejects missing or unsupported `schema_version`;
  - rejects empty `profile_id` or `dataset_version`;
  - accepts only `foundation_fixture`, `deterministic_scale_probe`, or `llm`
    generation modes;
  - requires `target_candidate_count` to be a positive integer for
    `deterministic_scale_probe`;
  - rejects unsupported feature keys instead of silently ignoring them;
  - normalizes missing feature flags to `False`.
- [x] Add `RunProfile.sanitized_metadata()` with only `schema_version`,
  `profile_id`, `generation_mode`, `target_candidate_count`, `config_hash`, and
  enabled feature names.
- [x] Add a stable hash over canonical JSON for the profile. The hash must not
  include secrets from environment variables.
- [x] Add tests for valid profiles, invalid schema versions, invalid generation
  modes, invalid counts, unknown feature keys, default feature normalization, and
  hash stability.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_run_profiles
  ```

  Expected result: new profile contract tests pass.

### Task 3: Add Deterministic Scale-Probe Generation

- [x] Add `generate_scale_probe_candidates(seed: DomainSeed, target_candidate_count: int)`.
- [x] Generate candidates using only the existing contacts fixture tools and
  verifiers. Use deterministic candidate ids such as
  `candidate_scale_probe_0001`.
- [x] Preserve curriculum ordering by returning candidates through
  `order_candidates_by_curriculum()`.
- [x] Include a controlled mix of lookup and follow-up candidates so the probe
  exercises single-step, multi-step, verification-failure, duplicate, and
  logical-support paths without changing foundation defaults.
- [x] Attach local generation lineage with a distinct config hash such as
  `scale-probe-local-v1`.
- [x] Add tests proving:
  - count equals `target_candidate_count`;
  - output is deterministic across repeated calls;
  - candidate ids are stable and unique;
  - generated candidates pass candidate contract validation before execution;
  - the probe includes enough variation to exercise at least lookup and
    follow-up task types.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_run_profiles tests.test_contracts
  ```

  Expected result: scale-probe contract tests pass.

### Task 4: Route Profiles Through the Synchronous Pipeline

- [x] Modify `run_foundation_pipeline()` to accept:

  ```python
  seed_override: DomainSeed | None = None
  run_profile_metadata: dict[str, object] | None = None
  ```

- [x] Use `seed_override or foundation_seed()` at the current seed creation
  boundary.
- [x] Keep `candidate_generator`, `task_expansion_generator`, `policy_generator`,
  and feature flags as the only execution controls. Do not create a separate
  profile-specific execution branch.
- [x] In `main.py`, add `--run-profile` and translate profile values into the
  existing `run_foundation_pipeline()` arguments.
- [x] Preserve existing CLI flags when no profile is supplied.
- [x] For profile runs, allow `--output-dir` to continue choosing the artifact
  directory. Use the profile `dataset_version` unless `--dataset-version` is
  explicitly supplied.
- [x] Reject unsupported combinations with clear `argparse` errors, especially:
  - `generation.mode="llm"` without `--use-llm` or profile-level LLM mode
    enablement;
  - `deterministic_scale_probe` with non-positive `target_candidate_count`;
  - source-governance fixture settings that conflict with controlled
    `--enable-network-source` inputs.
- [x] Add CLI tests for no-profile default behavior, successful profile run,
  dataset-version override, invalid profile path, invalid profile content, and
  deterministic scale-probe profile output.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_cli tests.test_foundation_pipeline tests.test_run_profiles
  ```

  Expected result: profile and non-profile CLI paths pass.

### Task 5: Persist Sanitized Run Metadata in Artifacts

- [x] Extend `write_dataset_artifacts()` with optional
  `run_profile_metadata: dict[str, object] | None = None`.
- [x] Add optional `manifest["run_profile"]` validation in
  `validate_manifest_record()`.
- [x] Include only sanitized profile metadata in `manifest.json`.
- [x] Add quality-report slices for `run_profile_id` and `generation_mode` only
  if they can be derived from sanitized manifest/sample/rejection metadata
  without duplicating raw profile content. If that requires wider plumbing, keep
  quality-report changes out of this plan and document the deferral.
- [x] Add tests proving default manifests do not include `run_profile`, while
  profile manifests include profile id, mode, target count, enabled features, and
  config hash.
- [x] Add tests proving no environment variable named like an API key or
  authorization header is serialized into profile metadata.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_foundation_pipeline tests.test_quality_reporting tests.test_contracts
  ```

  Expected result: artifact contract tests pass.

### Task 6: Add Fixture Profiles and Scale-Probe Validation Commands

- [x] Add `tests/fixtures/run_profiles/foundation-fixture.json`.
- [x] Add `tests/fixtures/run_profiles/foundation-scale-probe-25.json`.
- [x] Add a deterministic fixture test that runs the scale probe through
  `run_foundation_pipeline()` and verifies stable accepted/rejected counts,
  manifest metadata, rejection causes, and sample ordering.
- [x] Add a CLI test equivalent to:

  ```bash
  uv run python main.py \
    --run-profile tests/fixtures/run_profiles/foundation-scale-probe-25.json \
    --output-dir artifacts/foundation-scale-probe
  ```

- [x] Confirm the scale-probe output can be used to decide whether to activate
  plan 0014 or `TD-0002` by checking:
  - total candidate count;
  - total accepted/rejected count;
  - duplicate rejection count;
  - runtime remains synchronous and local;
  - manifest contains the run-profile config hash.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_run_profiles tests.test_cli tests.test_foundation_pipeline
  ```

  Expected result: fixture profile tests pass.

### Task 7: Docs and Plan Lifecycle Updates

- [x] Update [../../DATA.md](../../DATA.md) with the optional manifest
  `run_profile` metadata contract.
- [x] Update [../../BACKEND.md](../../BACKEND.md) with the synchronous
  run-profile boundary and state that it does not activate
  `synthesis.orchestration`.
- [x] Update [../../product-specs/framework-mvp.md](../../product-specs/framework-mvp.md)
  so "domain config and optional seed records" maps to `run_profile_v1` for the
  current local MVP.
- [x] Update [../../ROADMAP.md](../../ROADMAP.md) to mark configurable run
  profiles and scale probing as the next synchronous step before async
  orchestration.
- [x] Keep [../../../AGENTS.md](../../../AGENTS.md) unchanged unless commands or
  operating rules change.
- [x] Run:

  ```bash
  uv run python scripts/validate_docs.py
  uv run python -m unittest
  ```

  Expected result: documentation validation and the full unit suite pass.

### Task 8: Completion Handoff

- [x] Run deterministic fixture commands:

  ```bash
  uv run python main.py --output-dir artifacts/foundation
  uv run python main.py \
    --run-profile tests/fixtures/run_profiles/foundation-fixture.json \
    --output-dir artifacts/foundation-profile
  uv run python main.py \
    --run-profile tests/fixtures/run_profiles/foundation-scale-probe-25.json \
    --output-dir artifacts/foundation-scale-probe
  ```

- [x] Confirm default and `foundation-fixture` profile outputs are equivalent
  except for expected profile metadata.
- [x] Record whether the scale-probe evidence triggers either:
  - plan 0014 activation criteria; or
  - `TD-0002` semantic duplicate detection criteria.
- [x] Update this plan's task checkboxes during implementation.
- [x] When accepted as complete, move this file to `../completed/`, change
  status to completed with the completion date, and update
  [../../PLANS.md](../../PLANS.md), [../active/README.md](README.md), and
  [../completed/README.md](../completed/README.md).

## Completion Evidence

Completed on 2026-05-29.

- `uv run python main.py --output-dir artifacts/foundation` produced
  `accepted=2 rejected=1`.
- `uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-fixture.json --output-dir artifacts/foundation-profile`
  produced `accepted=2 rejected=1`.
- Default and foundation-profile artifacts are equivalent after normalizing
  dataset ids and excluding expected `manifest.run_profile` metadata.
- `uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-scale-probe-25.json --output-dir artifacts/foundation-scale-probe`
  produced `accepted=14 rejected=11` over 25 candidates.
- Scale-probe rejection evidence: `quality_duplicate=3`,
  `verification_failed=4`, and `solution_logic_error=4`.
- Plan 0014 remains deferred: the probe is 25 candidates and remains
  synchronous/local, below the deferred-plan trigger of roughly 10 minutes or
  100+ candidates.
- `TD-0002` remains unresolved: this probe exercises exact duplicate rejection
  and does not provide volume or curriculum-benchmark evidence requiring
  semantic duplicate detection.

## Acceptance Criteria

- `uv run python main.py` remains synchronous and produces the same default
  deterministic artifacts as before this plan.
- `--run-profile` accepts a validated `run_profile_v1` JSON file and maps it to
  the existing synchronous pipeline.
- Profile runs can override seed metadata and dataset version without creating a
  parallel execution path.
- Deterministic scale-probe runs produce stable artifacts for a configured
  target candidate count.
- Manifest profile metadata is sanitized, hashed, validated, and absent from
  non-profile runs.
- Source governance, sandbox policy, role guardrails, MCP adapter controls, and
  network-source controls remain enforced.
- Plan 0014 remains deferred unless scale-probe evidence satisfies its trigger
  conditions.
- `TD-0002` remains unresolved unless scale-probe evidence justifies a separate
  semantic duplicate detection plan.
- `uv run python scripts/validate_docs.py` and `uv run python -m unittest` pass.

## Risks

- Profiles can become a second configuration system that contradicts CLI flags.
  Keep the profile translator small and explicit, and make unsupported
  combinations fail early.
- Scale-probe generation can accidentally weaken foundation fixture stability.
  Keep `generate_foundation_candidates()` unchanged and add a separate generator.
- Manifest profile metadata can leak sensitive values if raw profile files are
  copied into artifacts. Store only sanitized identifiers, enabled feature names,
  target count, mode, and config hash.
- Large deterministic probes can make unit tests slow. Keep fixture tests small
  and reserve larger manual probes for artifact-validation commands.
- Adding profile metadata to quality slices may require wider data plumbing than
  the plan needs. Prefer manifest metadata first and only add quality slices if
  the implementation remains narrow.

## Notes

This plan makes the local MVP configurable and measurable. It deliberately does
not implement durable queues, async execution, distributed scheduling, or
semantic duplicate detection.
