# Plan 0018: Profile-Driven Source Admission and Contacts Environment Overrides

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

## Status

Completed on 2026-05-30.

## Completion Evidence

- Validation passed with `uv run python scripts/validate_docs.py`.
- Full unit suite passed with `uv run python -m unittest` (170 tests).
- Deterministic fixture commands completed for default foundation,
  `foundation-fixture`, and profile-local contacts source runs.
- Profile-local source artifacts were checked for raw local path and contacts
  email leakage across manifest, source events, quality report, and rejections.
- Plan 0014 remains deferred: the new run stays synchronous at 3 candidates and
  does not cross the documented runtime or volume triggers.
- `TD-0002` remains unresolved: this slice does not introduce a new
  semantic-duplicate benchmark signal.

## Goal

Allow a run profile to declare a governed local contacts JSON source that builds
the contacts environment through the existing source-policy and pipeline
boundaries, while preserving default fixture behavior and sanitized artifacts.

## Architecture

This plan extends the synchronous run-profile boundary from plan 0017 without
creating a second execution path. `synthesis.run_profiles` owns versioned profile
parsing and sanitized profile metadata, `synthesis.sources` owns local-file
source admission and contacts payload conversion, and `main.py` translates the
validated profile into the existing `run_foundation_pipeline()` arguments. The
pipeline continues to consume `SourceBundle`, `ContactsEnvironmentInput`, and
source-event records exactly as the controlled network path already does.

## Tech Stack

- Python standard library dataclasses, JSON parsing, hashing, and pathlib.
- Existing source-governance, contacts environment, run-profile, pipeline, and
  dataset artifact modules under `synthesis/`.
- Existing validation through `scripts/validate_docs.py` and `uv run python -m
  unittest`.

---

## Basis

This plan follows the evidence from
[../completed/0017-configurable-run-profiles-and-scale-probe.md](../completed/0017-configurable-run-profiles-and-scale-probe.md)
and keeps
[../deferred/0014-async-local-orchestration-with-durable-queues.md](../deferred/0014-async-local-orchestration-with-durable-queues.md)
deferred.

- Before this plan was opened, [../../PLANS.md](../../PLANS.md) had no active
  successor after plan 0017.
- [../../product-specs/framework-mvp.md](../../product-specs/framework-mvp.md)
  starts the MVP user flow with a run profile, then environment construction.
  Plan 0017 made the profile configurable, but the default contacts environment
  still comes from fixed fixture rows unless the user separately enables the
  controlled network-source CLI path.
- [../../BACKEND.md](../../BACKEND.md) already lets
  `run_foundation_pipeline()` accept a `ContactsEnvironmentInput` and
  `SourceBundle`; plan 0018 should route profile-declared local source material
  into that existing boundary.
- [../../DATA.md](../../DATA.md) requires manifests and source events to remain
  sanitized. A profile may identify a local source file for execution, but
  artifacts must store content hashes, source ids, license outcomes, and policy
  hashes rather than raw file paths or payloads.
- Plan 0017's completion evidence stayed below the async trigger: 25 candidates,
  synchronous/local execution, and no semantic-duplicate benchmark signal. The
  next higher-ROI slice is making user-provided local data usable under the same
  governance controls.

## Scope

- Add `run_profile_v2` support while preserving all existing `run_profile_v1`
  profiles and artifacts.
- Add an optional profile `source` block for local contacts JSON files.
- Validate local source declarations early:
  - `kind` must be `local_contacts_json`;
  - `path` must be a relative path resolved from the profile file directory;
  - `path` must not contain parent-directory traversal;
  - the file must have a `.json` suffix;
  - `max_bytes` must be a positive integer and default to `65536`;
  - `license_label` must be one of the existing source license labels;
  - `source_id` must be a non-empty stable id.
- Add a local-file source builder that reads the declared JSON payload within the
  byte budget, computes a content hash, creates a `local_file` source bundle,
  validates source policy, converts the payload to `ContactsEnvironmentInput`,
  and emits sanitized source events.
- Route profile-declared local contacts sources through `main.py` into
  `run_foundation_pipeline()` using existing `source_bundle`,
  `contacts_environment_input`, `source_events`, and `enable_source_audit`
  arguments.
- Extend manifest run-profile metadata validation to accept sanitized
  `run_profile_v2` metadata with optional source summary fields.
- Add fixture profiles and tests proving:
  - existing `run_profile_v1` profiles remain valid;
  - profile-local source runs build the environment from the declared JSON;
  - raw local paths and raw contacts payloads are not written to manifests,
    source events, quality reports, or rejection metadata;
  - accepted samples may contain task-relevant observations and final responses
    from the admitted environment, but source-audit artifacts must remain
    payload-free;
  - source-policy and environment-input failures produce classified rejections
    or CLI errors without partial unsafe artifacts.
- Update canonical docs and plan indexes.

## Out of Scope

- Async orchestration, durable queues, cancellation, or resumption from plan
  0014.
- Semantic duplicate detection from `TD-0002`.
- Network source declaration inside profiles. The current `--enable-network-source`
  CLI path remains separate and explicit.
- General domain/environment generation beyond contacts.
- Arbitrary local file ingestion, recursive directories, glob patterns, CSV,
  YAML, SQLite imports, binary payloads, or compressed archives.
- External MCP server discovery, browser automation, credential brokering, or
  generated environment/tool/verifier handlers.
- Persisting raw local file paths, raw payloads, contact names from source
  events, authorization headers, provider prompts, API keys, or other
  secret-like fields in metadata artifacts.

## Proposed Profile Contract

`run_profile_v1` remains valid and unchanged. `run_profile_v2` adds the optional
`source` block:

```json
{
  "schema_version": "run_profile_v2",
  "profile_id": "foundation_profile_local_contacts",
  "dataset_version": "dataset_profile_local_contacts",
  "seed": {
    "seed_id": "seed_contacts_profile_local_v1",
    "domain": "contacts",
    "description": "Profile-driven contacts source run.",
    "task_taxonomy": ["contact_lookup", "contact_followup"]
  },
  "generation": {
    "mode": "foundation_fixture",
    "target_candidate_count": null
  },
  "features": {
    "enable_branching": false,
    "enable_task_expansion": false,
    "enable_refinement": false,
    "enable_mcp_adapter": false,
    "enable_sandbox_fixture": false,
    "enable_source_governance_fixture": false
  },
  "source": {
    "kind": "local_contacts_json",
    "source_id": "source_profile_contacts_v1",
    "path": "contacts-profile.json",
    "license_label": "cc-by-4.0",
    "max_bytes": 65536
  }
}
```

The profile's canonical config hash includes the `source` declaration, including
the relative path string, but sanitized artifact metadata must not persist the
raw path. Runtime source provenance is based on the admitted source bundle and
content hash.

Sanitized `manifest.run_profile` for `run_profile_v2` should contain only:

```json
{
  "schema_version": "run_profile_v2",
  "profile_id": "foundation_profile_local_contacts",
  "generation_mode": "foundation_fixture",
  "target_candidate_count": null,
  "config_hash": "sha256:...",
  "enabled_features": [],
  "source": {
    "kind": "local_contacts_json",
    "source_id": "source_profile_contacts_v1",
    "content_hash": "sha256:...",
    "license_label": "cc-by-4.0",
    "source_policy_hash": "sha256:..."
  }
}
```

## File Map

- Modify `synthesis/run_profiles.py`:
  - support `run_profile_v1` and `run_profile_v2`;
  - add `RunProfileSource`;
  - validate local contacts source declarations;
  - resolve source paths relative to the profile file directory without storing
    raw paths in sanitized metadata;
  - include source declaration in the stable config hash.
- Modify `synthesis/contracts.py`:
  - allow `local_file` source kind;
  - validate sanitized `run_profile_v2` manifest metadata and source summary;
  - keep `run_profile_v1` metadata valid.
- Modify `synthesis/sources.py`:
  - add a local profile contacts-source request/result boundary;
  - read local contacts JSON under a byte budget;
  - build a `SourceBundle` with `source_kind="local_file"`;
  - convert the payload with the existing contacts payload parser;
  - emit sanitized source events and environment-source admission events.
- Modify `main.py`:
  - translate profile source declarations into `source_bundle`,
    `contacts_environment_input`, `source_events`, and `enable_source_audit`;
  - reject profile source declarations that conflict with
    `--enable-network-source` or `enable_source_governance_fixture`.
- Modify `synthesis/datasets.py` only if manifest serialization needs to pass
  the source summary from source admission into `run_profile_metadata`.
- Modify `synthesis/pipeline.py` only if the source summary must be appended
  after source-policy hashing. Prefer preparing complete sanitized metadata in
  `main.py` before calling the pipeline.
- Add fixture files:
  - `tests/fixtures/run_profiles/profile-local-contacts.json`;
  - `tests/fixtures/run_profiles/contacts-profile.json`;
  - `tests/fixtures/run_profiles/profile-local-contacts-bad-license.json`;
  - `tests/fixtures/run_profiles/profile-local-contacts-bad-schema.json`.
- Modify tests:
  - `tests/test_run_profiles.py` for v1 compatibility, v2 source validation,
    path rules, source hash stability, and sanitized metadata;
  - `tests/test_source_governance.py` for local-file source admission,
    rejection, content hashing, and source events;
  - `tests/test_cli.py` for profile-local source CLI behavior and conflict
    rejection;
  - `tests/test_foundation_pipeline.py` for environment override artifacts and
    redaction;
  - `tests/test_contracts.py` for `run_profile_v2` manifest metadata.
- Update docs:
  - [../../DATA.md](../../DATA.md);
  - [../../BACKEND.md](../../BACKEND.md);
  - [../../ROADMAP.md](../../ROADMAP.md);
  - [../../product-specs/framework-mvp.md](../../product-specs/framework-mvp.md);
  - [../../PLANS.md](../../PLANS.md);
  - [README.md](README.md) in this active plan bucket when the plan is accepted.

## Implementation Tasks

### Task 1: Lock Existing Profile Behavior

- [x] Add characterization tests proving both existing fixture profiles still
  load and produce the same sanitized metadata:
  - `tests/fixtures/run_profiles/foundation-fixture.json`;
  - `tests/fixtures/run_profiles/foundation-scale-probe-25.json`.
- [x] Assert `schema_version == "run_profile_v1"` remains accepted by
  `load_run_profile()`.
- [x] Assert v1 `RunProfile.sanitized_metadata()` contains no `source` key.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_run_profiles tests.test_cli tests.test_foundation_pipeline
  ```

  Expected result: existing run-profile behavior passes before v2 work begins.

### Task 2: Add `run_profile_v2` Source Records

- [x] Add immutable `RunProfileSource` to `synthesis/run_profiles.py` with:
  - `kind: str`;
  - `source_id: str`;
  - `relative_path: str`;
  - `resolved_path: Path`;
  - `license_label: str`;
  - `max_bytes: int`.
- [x] Add `RUN_PROFILE_SCHEMA_VERSIONS = {"run_profile_v1", "run_profile_v2"}`.
- [x] Keep v1 requiring no `source` block.
- [x] For v2, make `source` optional; when present, validate it as the
  `local_contacts_json` contract.
- [x] Reject:
  - absolute paths;
  - paths containing `..`;
  - non-JSON suffixes;
  - non-positive `max_bytes`;
  - unknown source keys;
  - unsupported `kind`;
  - unsupported `license_label`;
  - empty `source_id`.
- [x] Include source declaration in `RunProfile.canonical()` for v2 config
  hashing.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_run_profiles
  ```

  Expected result: v1 and v2 profile validation tests pass.

### Task 3: Build Local Profile Contacts Source Admission

- [x] Extend `synthesis.contracts.SOURCE_KINDS` with `local_file`.
- [x] Add `ProfileLocalContactsSourceRequest` or equivalent dataclass to
  `synthesis.sources`.
- [x] Implement a builder such as
  `build_profile_local_contacts_source_input(request)`.
- [x] The builder must:
  - read at most `max_bytes + 1` bytes;
  - reject payloads larger than `max_bytes`;
  - compute `content_hash`;
  - create a `SourceBundle` with `source_kind="local_file"`;
  - set `origin_reference` to a sanitized stable alias such as
    `profile_local_file:<source_id>`;
  - set license decision to `allowed` for accepted labels;
  - use `filesystem_isolation="artifact_subdir"`;
  - set `generated_code_allowed=False`;
  - set `secret_redaction=True`;
  - call `validate_source_bundle()`;
  - convert the payload to `ContactsEnvironmentInput` with the existing contacts
    payload parser;
  - emit no raw payload, local path, contact names, or emails in source events.
- [x] Add tests proving accepted local contacts source material threads source
  provenance into samples and manifest source-policy hashes.
- [x] Add tests proving malformed JSON, oversized payloads, bad contacts schema,
  and rejected source policy produce classified failures without raw payload
  leakage.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_source_governance tests.test_contracts
  ```

  Expected result: source-governance contract tests pass.

### Task 4: Route Profile Sources Through the CLI

- [x] In `main.py`, when a loaded profile has a local contacts source, call the
  local profile source builder before `run_foundation_pipeline()`.
- [x] Pass the resulting `source_bundle`, `contacts_environment_input`,
  `source_events`, and `enable_source_audit=True`.
- [x] Reject these combinations with clear `argparse` errors:
  - profile source plus `--enable-network-source`;
  - profile source plus profile `enable_source_governance_fixture=true`;
  - profile source whose generation mode or feature flags would require a domain
    other than contacts.
- [x] Add CLI tests for:
  - successful `--run-profile tests/fixtures/run_profiles/profile-local-contacts.json`;
  - missing source file;
  - bad source license;
  - conflict with `--enable-network-source`;
  - manifest redaction of raw local paths and payload content.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_cli tests.test_foundation_pipeline
  ```

  Expected result: profile source CLI paths and default CLI paths pass.

### Task 5: Persist Sanitized Profile Source Metadata

- [x] Extend `RunProfile.sanitized_metadata()` or add a post-admission metadata
  merge helper so `manifest.run_profile.source` includes only:
  - `kind`;
  - `source_id`;
  - `content_hash`;
  - `license_label`;
  - `source_policy_hash`.
- [x] Update `validate_manifest_record()` so `run_profile_v1` metadata remains
  valid and `run_profile_v2` metadata accepts the source summary.
- [x] Add tests that reject `run_profile.source.path`, `raw_payload`,
  `authorization`, `api_key`, and contact payload values in manifest metadata.
- [x] Add tests proving non-profile and v1-profile manifests remain unchanged.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_contracts tests.test_foundation_pipeline tests.test_quality_reporting
  ```

  Expected result: artifact contract tests pass.

### Task 6: Add Fixture Profiles and Deterministic Artifact Checks

- [x] Add `tests/fixtures/run_profiles/contacts-profile.json` with at least:
  - `Alice Zhang` / `alice.zhang@example.test`;
  - `Ben Carter` / `ben.carter@example.test`;
  - `Clara Nguyen` / `clara.nguyen@example.test`;
  - `Devon Lee` / `devon.lee@example.test`.
- [x] Add `tests/fixtures/run_profiles/profile-local-contacts.json` pointing to
  `contacts-profile.json` with `schema_version="run_profile_v2"`.
- [x] Add negative fixture profiles for bad license and bad schema.
- [x] Add a deterministic run test that verifies profile-local source artifacts
  include:
  - `manifest.run_profile.schema_version == "run_profile_v2"`;
  - source-policy hashes;
  - `source_events.jsonl`;
  - accepted/rejected counts that are stable for the fixture;
  - no raw local path;
  - no raw contacts payload in source events or manifest metadata.
- [x] Run:

  ```bash
  uv run python main.py \
    --run-profile tests/fixtures/run_profiles/profile-local-contacts.json \
    --output-dir artifacts/foundation-profile-local-source
  ```

  Expected result: command completes synchronously and writes manifest, samples,
  rejections, quality report, and source events.

### Task 7: Docs and Plan Lifecycle Updates

- [x] Update [../../DATA.md](../../DATA.md) with `run_profile_v2`, local-file
  source provenance, and sanitized manifest source summary.
- [x] Update [../../BACKEND.md](../../BACKEND.md) with the profile-declared local
  source flow and conflict rules.
- [x] Update [../../product-specs/framework-mvp.md](../../product-specs/framework-mvp.md)
  so the MVP user flow maps user-provided contacts sources to profile-local
  source admission.
- [x] Update [../../ROADMAP.md](../../ROADMAP.md) to mark profile-driven local
  source admission as the next synchronous step after plan 0017.
- [x] Keep [../../../AGENTS.md](../../../AGENTS.md) compact; update only current
  active/latest completed plan references if they drift.
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
    --run-profile tests/fixtures/run_profiles/profile-local-contacts.json \
    --output-dir artifacts/foundation-profile-local-source
  ```

- [x] Confirm default and `foundation-fixture` profile outputs remain equivalent
  except for expected `manifest.run_profile` metadata.
- [x] Confirm profile-local source artifacts are redacted and attributable by
  source id, content hash, and source-policy hash.
- [x] Record whether the new local-source run changes the activation decision
  for plan 0014 or `TD-0002`. It should not unless candidate volume or runtime
  crosses the documented trigger.
- [x] Update this plan's task checkboxes during implementation.
- [x] When accepted as complete, move this file to `../completed/`, change
  status to completed with the completion date, and update
  [../../PLANS.md](../../PLANS.md), [README.md](README.md), and
  [../completed/README.md](../completed/README.md).

## Validation

- `uv run python scripts/validate_docs.py`
- `uv run python -m unittest`
- `uv run python main.py --run-profile tests/fixtures/run_profiles/profile-local-contacts.json --output-dir artifacts/foundation-profile-local-source`

## Acceptance Criteria

- Existing `run_profile_v1` profiles remain valid and produce unchanged
  sanitized metadata.
- `run_profile_v2` can declare a governed local contacts JSON source.
- Local source files are read only through explicit profile declarations, size
  limits, JSON suffix checks, relative-path checks, source-policy validation, and
  contacts input validation.
- Profile-local source runs build the contacts environment from the declared
  JSON through the existing synchronous pipeline.
- Source governance, sandbox policy, role guardrails, MCP adapter controls, and
  network-source controls remain enforced.
- Artifacts store only sanitized source ids, content hashes, license labels,
  source-policy hashes, and profile metadata; they do not store raw file paths,
  raw payloads in source-audit or profile metadata, contact names from source
  events, credentials, or prompts.
- Default `uv run python main.py` behavior and default artifact counts remain
  unchanged.
- Plan 0014 remains deferred unless the new evidence satisfies its trigger
  conditions.
- `TD-0002` remains unresolved unless the new evidence justifies a separate
  semantic duplicate detection plan.
- Documentation validation and the full unit suite pass.

## Risks

- Adding `run_profile_v2` can split configuration semantics from v1. Keep v1
  frozen and make v2 an additive parser path with explicit tests for both.
- Local file source support can accidentally leak workstation paths. Store the
  raw path only in memory and persist a source id plus content hash.
- Source-policy code currently treats only `external` as network-gated. Add
  `local_file` deliberately and test that it does not inherit network allowlist
  requirements while still enforcing sandbox and license policy.
- Environment overrides can make deterministic fixture tasks fail if the source
  omits expected contacts. That is acceptable when failures are classified and
  artifacts remain inspectable; tests should pin the expected counts for the
  fixture.
- Sanitized profile source metadata may need post-admission hashes that are not
  known during initial profile parsing. Prefer a small metadata merge helper over
  mutating the immutable profile record.

## Notes

This plan makes the local MVP materially more useful: a user can provide
contacts data through a profile and get governed, attributable, executable
artifacts. It deliberately stays synchronous and contacts-domain-only.
