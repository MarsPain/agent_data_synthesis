# Plan 0035: Domain Source Admission Interface

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

## Status

Completed on 2026-06-14.

## Goal

Promote profile-local source ingestion from a contacts-only special case into a
domain-owned importer protocol so each domain can parse governed source payloads
into its own typed environment input without making the central pipeline
understand domain schemas.

## Architecture

Source governance remains framework-owned: profile-relative paths, byte
budgets, license labels, content hashes, source bundles, source-policy hashes,
and sanitized source events stay in the shared source layer. Domain semantics
move behind a narrow importer protocol: a domain importer receives admitted
bytes plus source-policy identity and returns a typed environment input owned by
that domain.

`synthesis.domain_pipeline` remains the place that selects a domain bundle, but
it should no longer expose a contacts-specific `contacts_environment_input`
parameter. The pipeline should pass a generic domain environment input into the
selected bundle; each domain builder validates the input type it accepts.
Contacts become the compatibility importer, and mobile messages provide the
first non-contacts importer used to prove the boundary is not a single-domain
abstraction.

## Tech Stack

- Python standard library: `dataclasses`, `json`, `pathlib`, `typing.Protocol`,
  `sqlite3`, and `unittest`.
- Existing modules: `synthesis.sources`, `synthesis.domain_pipeline`,
  `synthesis.environments`, `synthesis.mobile_environment`,
  `synthesis.run_profiles`, `synthesis.pipeline`, `synthesis.datasets`,
  `synthesis.contracts`, and `main.py`.
- New focused modules:
  - `synthesis.domain_sources` for importer protocols, generic import records,
    and source-kind/domain resolution helpers.
  - `synthesis.mobile_sources` for the mobile messages importer.
- Optional small module if useful during implementation:
  - `synthesis.contact_sources` for a contacts importer wrapper around the
    existing contacts JSON conversion logic. Keep this small; do not rewrite
    contacts source governance.
- Verification through `uv run python scripts/validate_docs.py` and
  `uv run python -m unittest`.

## Basis

- [../completed/0018-profile-driven-source-admission-and-contacts-environment-overrides.md](../completed/0018-profile-driven-source-admission-and-contacts-environment-overrides.md)
  added `run_profile_v2` with profile-local contacts JSON source admission, but
  the boundary is still contacts-specific.
- [../completed/0029-mobile-agent-second-domain-pipeline-probe.md](../completed/0029-mobile-agent-second-domain-pipeline-probe.md)
  introduced `mobile_messages_fixture` and the first internal domain bundle,
  proving the pipeline can run more than contacts.
- [../completed/0030-runtime-contract-and-episode-evidence.md](../completed/0030-runtime-contract-and-episode-evidence.md)
  made contacts and mobile environments satisfy a shared runtime protocol.
- [../completed/0033-task-intent-policy-verifier-contract-split.md](../completed/0033-task-intent-policy-verifier-contract-split.md)
  reduced generator-era task coupling before future domains and runtime
  consumers add more pressure.
- [../completed/0034-reward-label-export-and-runtime-scoring-consumer.md](../completed/0034-reward-label-export-and-runtime-scoring-consumer.md)
  added a training-signal consumer over contacts/mobile episode evidence while
  leaving mobile source-governed input unresolved.
- [../../generated/mobile-domain-pipeline-pressure.md](../../generated/mobile-domain-pipeline-pressure.md)
  records that source-governed environment input remains contacts-only.
- [../../DESIGN.md](../../DESIGN.md) separates source governance, environment
  synthesis, runtime metadata, task curriculum, trajectory execution,
  verification, and dataset assembly as bounded contexts.

## Why This Plan Now

The framework now has two domains and multiple repo-local runtime/episode
consumers. The remaining contacts-specific source path is the next central
coupling point: profile-local source declarations are parsed in `main.py`, the
pipeline accepts only `contacts_environment_input`, and `synthesis.sources`
turns payloads directly into contacts environment inputs.

This plan is high leverage because it draws the correct boundary before more
domains arrive:

- source governance should not know domain table schemas;
- the central pipeline should not grow one source branch per domain;
- domain modules should own payload-to-environment-input semantics;
- run-profile source metadata should stay sanitized and stable across domains;
- mobile source ingestion should validate the protocol without making mobile
  the product direction.

## Scope

- Add a domain source importer protocol for profile-local JSON source payloads.
- Keep shared source governance in `synthesis.sources`: path safety, byte
  budget, content hash, license policy, source bundle validation, source event
  creation, and sanitized source summaries.
- Move payload-to-environment-input conversion behind domain-owned importer
  implementations.
- Preserve the existing contacts profile-local source behavior and artifact
  semantics.
- Add a mobile messages environment input contract and importer as the first
  non-contacts importer.
- Replace pipeline and CLI contacts-specific source plumbing with generic
  domain source import plumbing.
- Keep default `uv run python main.py` behavior unchanged.
- Keep controlled network source ingestion contacts-only in this plan, but make
  sure the new local importer protocol does not block future network-backed
  domain importers.
- Update canonical docs and plan indexes.

## Out of Scope

- Real phone data, SMS, notification, calendar, browser, filesystem, or device
  integration.
- Arbitrary local file ingestion. `run_profile_v2.source.path` remains
  profile-relative, parent-traversal-free, `.json` only, and byte-budgeted.
- External MCP environment servers or mobile MCP adapter support.
- Controlled network source ingestion for mobile or arbitrary domains.
- A third domain probe.
- Agentic RL rollout collection, reward model training, preference
  optimization, or GPU/distributed infrastructure.
- Async orchestration, durable queues, cancellation, or per-role cost tracking
  from plan 0014.
- Semantic duplicate detection from `TD-0002`.
- Creating a separate `awm_runtime` package or changing dataset release
  admission.

## Contracts

### Domain Source Importer Protocol

Add a protocol shaped like this in `synthesis.domain_sources`:

```python
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from synthesis.sources import SourceBundle


@dataclass(frozen=True)
class ProfileLocalDomainSourceRequest:
    domain_id: str
    kind: str
    source_id: str
    path: Path
    license_label: str
    max_bytes: int


@dataclass(frozen=True)
class DomainSourceImport:
    domain_id: str
    source_kind: str
    source_bundle: SourceBundle
    environment_input: object
    events: list[dict[str, object]]
    source_summary: dict[str, object]


class DomainSourceImporter(Protocol):
    domain_id: str
    source_kind: str

    def build_environment_input(
        self,
        content: bytes,
        *,
        source_bundle_id: str,
        source_policy_hash: str,
    ) -> object:
        ...
```

Rules:

- `DomainSourceImporter` may parse domain payloads and construct typed
  environment inputs only.
- It must not read files, enforce license policy, create source bundles, write
  artifacts, fetch network data, inspect environment variables, or write source
  events.
- `DomainSourceImport.source_summary` must contain only `kind`, `source_id`,
  `content_hash`, `license_label`, and `source_policy_hash`.
- `DomainSourceImport.events` must contain sanitized `source_event_v1` records
  only.
- Unsupported `(domain_id, source.kind)` combinations must fail before
  environment construction with a clear `ControlledSourceFetchError` or
  `RunProfileValidationError`, not silently fall back to fixture data.

### Run Profile Source Kinds

Extend accepted local source kinds from:

```python
SOURCE_KINDS = {"local_contacts_json"}
```

to:

```python
SOURCE_KINDS = {
    "local_contacts_json",
    "local_mobile_messages_json",
}
```

Rules:

- `local_contacts_json` is valid only for contacts domains.
- `local_mobile_messages_json` is valid only for `mobile_messages_fixture`.
- Profile source metadata and per-record run-profile attribution remain
  sanitized; paths and raw payload rows must never appear in manifest, samples,
  rejections, source events, quality reports, episode logs, replay reports, or
  reward-label reports.

### Mobile Messages Environment Input

Add a typed input record in `synthesis.mobile_environment`:

```python
@dataclass(frozen=True)
class MobileMessagesEnvironmentInput:
    threads: tuple[MessageThreadRecord, ...]
    messages: tuple[MessageRecord, ...]
    reminders: tuple[ReminderRecord, ...] = ()
    draft_replies: tuple[DraftReplyRecord, ...] = ()
    source_bundle_id: str | None = None
    source_policy_hash: str | None = None

    def export(self) -> dict[str, object]:
        return {
            "schema_version": "mobile_messages_environment_input_v1",
            "threads": [thread.export() for thread in self.threads],
            "messages": [message.export() for message in self.messages],
            "reminders": [reminder.export() for reminder in self.reminders],
            "draft_replies": [draft.export() for draft in self.draft_replies],
            "source_bundle_id": self.source_bundle_id,
            "source_policy_hash": self.source_policy_hash,
        }
```

Validation rules:

- `schema_version` must be `mobile_messages_environment_input_v1`.
- `threads` and `messages` must be non-empty lists.
- `thread_id`, `message_id`, `participant`, `sender`, `body`, and
  `received_at` must be non-empty strings.
- Every message `thread_id` must exist in `threads`.
- Reminder `source_message_id`, when present, must exist in `messages`.
- Draft reply `thread_id` must exist in `threads`.
- Optional `source_bundle_id` must be a non-empty string when present.
- Optional `source_policy_hash` must be a `sha256:` content hash when present.

### Mobile Local Source Payload

The mobile profile-local JSON fixture should use this shape:

```json
{
  "threads": [
    {"thread_id": "thread_maya", "participant": "Maya"},
    {"thread_id": "thread_alex", "participant": "Alex"},
    {"thread_id": "thread_delivery", "participant": "Delivery"}
  ],
  "messages": [
    {
      "message_id": "msg_maya_project_update",
      "thread_id": "thread_maya",
      "sender": "Maya",
      "body": "Can you remind me to send the project update tomorrow at 9 AM?",
      "received_at": "2026-06-12T08:00:00Z"
    }
  ],
  "reminders": [],
  "draft_replies": []
}
```

Rules:

- Payload content may contain synthetic message bodies needed to build the
  fixture, but source events and run-profile metadata must not export bodies.
- The importer should accept omitted `reminders` and `draft_replies` as empty.
- The importer should reject malformed payloads through
  `ControlledSourceFetchError` during profile-local source admission.

### Pipeline Signature

Replace contacts-specific source input plumbing:

```python
contacts_environment_input: ContactsEnvironmentInput | None = None
```

with generic plumbing:

```python
domain_environment_input: object | None = None
```

Rules:

- Contacts builder accepts `ContactsEnvironmentInput`.
- Mobile builder accepts `MobileMessagesEnvironmentInput`.
- Passing a mismatched input type to a domain builder raises `ValueError` with
  a domain-specific message.
- Existing tests that pass `contacts_environment_input` should be migrated to
  the new parameter.

## File Map

- Create `synthesis/domain_sources.py`:
  importer protocol, generic profile-local source request/import records,
  importer resolution, and a helper that calls shared source governance with a
  selected importer.
- Create `synthesis/mobile_sources.py`:
  `MobileMessagesSourceImporter` and mobile JSON payload parsing.
- Modify `synthesis/sources.py`:
  keep governance primitives, add a generic profile-local source builder that
  receives a `DomainSourceImporter`, and keep contacts wrappers as compatibility
  shims only if needed during migration.
- Modify `synthesis/environments.py`:
  expose contacts payload-to-input conversion through a contacts importer
  boundary or a small public helper; do not leave the only parser as a private
  function used by the generic path.
- Modify `synthesis/mobile_environment.py`:
  add `MobileMessagesEnvironmentInput`, validation/export helpers,
  `create_from_input(...)`, and source-provenance-aware metadata.
- Modify `synthesis/contracts.py`:
  add `validate_mobile_messages_environment_input_record`, accept
  `local_mobile_messages_json` in run-profile source metadata and attribution,
  and preserve raw-content/path redaction checks.
- Modify `synthesis/run_profiles.py`:
  accept `local_mobile_messages_json`, reject mismatched source kind/domain
  combinations, and keep path/license/byte validation unchanged.
- Modify `synthesis/domain_pipeline.py`:
  replace contacts-specific environment input with generic domain input and add
  domain importer lookup or registration.
- Modify `synthesis/pipeline.py`:
  replace `contacts_environment_input` with `domain_environment_input`, preserve
  source admission/rejection behavior, and keep default fixture behavior
  unchanged.
- Modify `main.py`:
  route `profile.source` through the generic domain source importer, while
  keeping controlled network source ingestion contacts-only.
- Add `tests/test_domain_sources.py`.
- Extend `tests/test_source_governance.py`, `tests/test_run_profiles.py`,
  `tests/test_mobile_environment.py`, `tests/test_mobile_pipeline.py`,
  `tests/test_foundation_pipeline.py`, `tests/test_cli.py`, and
  `tests/test_contracts.py`.
- Add fixtures:
  - `tests/fixtures/run_profiles/mobile-messages-profile.json`;
  - `tests/fixtures/run_profiles/profile-local-mobile-messages.json`;
  - `tests/fixtures/run_profiles/profile-local-mobile-messages-bad-schema.json`.
- Update [../../DESIGN.md](../../DESIGN.md),
  [../../BACKEND.md](../../BACKEND.md), [../../DATA.md](../../DATA.md),
  [../../ROADMAP.md](../../ROADMAP.md),
  [../../generated/mobile-domain-pipeline-pressure.md](../../generated/mobile-domain-pipeline-pressure.md),
  [../completed/0034-reward-label-export-and-runtime-scoring-consumer.md](../completed/0034-reward-label-export-and-runtime-scoring-consumer.md),
  [../../PLANS.md](../../PLANS.md), and this plan's completion evidence when
  implementation finishes.

## Implementation Tasks

### Task 1: Add Domain Source Importer Tests First

**Files:**

- Create: `tests/test_domain_sources.py`
- Modify later: `synthesis/domain_sources.py`
- Modify later: `synthesis/sources.py`

- [x] Add failing tests for generic profile-local source admission:

```python
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path


class DomainSourceImporterTest(unittest.TestCase):
    def test_contacts_importer_uses_shared_profile_local_governance(self) -> None:
        from synthesis.domain_sources import (
            ProfileLocalDomainSourceRequest,
            build_profile_local_domain_source_input,
            resolve_domain_source_importer,
        )
        from synthesis.environments import ContactsEnvironmentInput

        importer = resolve_domain_source_importer("contacts_fixture", "local_contacts_json")
        source_import = build_profile_local_domain_source_input(
            ProfileLocalDomainSourceRequest(
                domain_id="contacts_fixture",
                kind="local_contacts_json",
                source_id="source_profile_contacts_v1",
                path=Path("tests/fixtures/run_profiles/contacts-profile.json"),
                license_label="cc-by-4.0",
                max_bytes=65536,
            ),
            importer=importer,
        )

        self.assertEqual(source_import.domain_id, "contacts_fixture")
        self.assertEqual(source_import.source_kind, "local_contacts_json")
        self.assertIsInstance(source_import.environment_input, ContactsEnvironmentInput)
        self.assertEqual(source_import.source_summary["source_id"], "source_profile_contacts_v1")
        self.assertRegex(
            str(source_import.source_summary["source_policy_hash"]),
            r"^sha256:[0-9a-f]{64}$",
        )
        exported = json.dumps(source_import.events, sort_keys=True)
        self.assertNotIn("contacts-profile.json", exported)
        self.assertNotIn("alice.zhang@example.test", exported)

    def test_resolver_rejects_mismatched_domain_and_source_kind(self) -> None:
        from synthesis.domain_sources import resolve_domain_source_importer

        with self.assertRaisesRegex(ValueError, "local_mobile_messages_json"):
            resolve_domain_source_importer("contacts_fixture", "local_mobile_messages_json")
        with self.assertRaisesRegex(ValueError, "local_contacts_json"):
            resolve_domain_source_importer("mobile_messages_fixture", "local_contacts_json")

    def test_profile_local_source_rejects_payload_without_leaking_content(self) -> None:
        from synthesis.domain_sources import (
            ProfileLocalDomainSourceRequest,
            build_profile_local_domain_source_input,
            resolve_domain_source_importer,
        )
        from synthesis.sources import ControlledSourceFetchError

        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "mobile.json"
            path.write_text(
                json.dumps({"threads": [], "messages": []}),
                encoding="utf-8",
            )
            importer = resolve_domain_source_importer(
                "mobile_messages_fixture",
                "local_mobile_messages_json",
            )

            with self.assertRaisesRegex(ControlledSourceFetchError, "environment source"):
                build_profile_local_domain_source_input(
                    ProfileLocalDomainSourceRequest(
                        domain_id="mobile_messages_fixture",
                        kind="local_mobile_messages_json",
                        source_id="source_mobile_bad",
                        path=path,
                        license_label="cc-by-4.0",
                        max_bytes=65536,
                    ),
                    importer=importer,
                )


if __name__ == "__main__":
    unittest.main()
```

- [x] Run:

```bash
uv run python -m unittest tests.test_domain_sources
```

- [x] Confirm the tests fail because `synthesis.domain_sources` does not exist.

### Task 2: Add Mobile Environment Input Contract Tests

**Files:**

- Modify: `tests/test_mobile_environment.py`
- Modify later: `synthesis/mobile_environment.py`
- Modify later: `synthesis/contracts.py`

- [x] Add tests proving mobile input validation and construction:

```python
def test_mobile_environment_input_export_is_contract_valid(self) -> None:
    from synthesis.contracts import validate_mobile_messages_environment_input_record
    from synthesis.mobile_environment import (
        MessageRecord,
        MessageThreadRecord,
        MobileMessagesEnvironmentInput,
    )

    environment_input = MobileMessagesEnvironmentInput(
        threads=(MessageThreadRecord("thread_maya", "Maya"),),
        messages=(
            MessageRecord(
                message_id="msg_maya_project_update",
                thread_id="thread_maya",
                sender="Maya",
                body="Can you remind me to send the project update tomorrow at 9 AM?",
                received_at="2026-06-12T08:00:00Z",
            ),
        ),
        source_bundle_id="bundle_source_mobile_messages_v1",
        source_policy_hash="sha256:" + "1" * 64,
    )

    validate_mobile_messages_environment_input_record(environment_input.export())


def test_mobile_environment_can_create_from_source_input(self) -> None:
    from synthesis.mobile_environment import (
        MessageRecord,
        MessageThreadRecord,
        MobileMessagesEnvironment,
        MobileMessagesEnvironmentInput,
    )

    environment_input = MobileMessagesEnvironmentInput(
        threads=(MessageThreadRecord("thread_maya", "Maya"),),
        messages=(
            MessageRecord(
                message_id="msg_maya_project_update",
                thread_id="thread_maya",
                sender="Maya",
                body="Can you remind me to send the project update tomorrow at 9 AM?",
                received_at="2026-06-12T08:00:00Z",
            ),
        ),
        source_bundle_id="bundle_source_mobile_messages_v1",
        source_policy_hash="sha256:" + "1" * 64,
    )

    with tempfile.TemporaryDirectory() as tmpdir:
        environment = MobileMessagesEnvironment.create_from_input(
            Path(tmpdir),
            environment_input,
            source_provenance={"source_policy_hash": "sha256:" + "1" * 64},
        )
        match = environment.search_messages(query="project update", participant="Maya")

    self.assertEqual(match["message_id"], "msg_maya_project_update")
    self.assertEqual(
        environment.metadata().source_provenance["source_policy_hash"],
        "sha256:" + "1" * 64,
    )
```

- [x] Add invalid-contract tests for missing threads, missing messages,
  unknown message thread ids, unknown reminder source ids, unknown draft thread
  ids, and invalid `source_policy_hash`.

- [x] Run:

```bash
uv run python -m unittest tests.test_mobile_environment tests.test_contracts
```

- [x] Confirm the new tests fail because the mobile input record and validator
  do not exist.

### Task 3: Implement Mobile Environment Input and Contract Validation

**Files:**

- Modify: `synthesis/mobile_environment.py`
- Modify: `synthesis/contracts.py`

- [x] Add `MobileMessagesEnvironmentInput` to `synthesis.mobile_environment`
  using the contract shape in this plan.

- [x] Extract the current mobile fixture table creation into a private helper
  such as `_create_schema(connection)` so both `create_fixture()` and
  `create_from_input()` use the same table definitions.

- [x] Implement `MobileMessagesEnvironment.create_from_input(...)`:

```python
@classmethod
def create_from_input(
    cls,
    output_dir: Path,
    environment_input: MobileMessagesEnvironmentInput,
    *,
    source_provenance: dict[str, object] | None = None,
) -> "MobileMessagesEnvironment":
    validate_mobile_messages_environment_input_record(environment_input.export())
    output_dir.mkdir(parents=True, exist_ok=True)
    database_path = output_dir / "mobile_messages.sqlite3"
    if database_path.exists():
        database_path.unlink()
    environment = cls(database_path, source_provenance=source_provenance)
    with closing(environment.connect()) as connection:
        with connection:
            _create_schema(connection)
            _insert_mobile_input(connection, environment_input)
    return environment
```

- [x] Preserve `create_fixture()` behavior by constructing the same fixture
  rows it writes today.

- [x] Update `metadata()` and `runtime_metadata()` only as needed to include
  sanitized `source_provenance` equivalent to contacts.

- [x] Add `validate_mobile_messages_environment_input_record(record)` in
  `synthesis.contracts`.

- [x] Run:

```bash
uv run python -m unittest tests.test_mobile_environment tests.test_contracts
```

- [x] Confirm the mobile input and contract tests pass.

### Task 4: Add Domain Source Protocol and Contacts Compatibility Importer

**Files:**

- Create: `synthesis/domain_sources.py`
- Modify: `synthesis/sources.py`
- Modify: `synthesis/environments.py`
- Test: `tests/test_domain_sources.py`
- Test: `tests/test_source_governance.py`

- [x] Create `synthesis.domain_sources` with:
  - `ProfileLocalDomainSourceRequest`;
  - `DomainSourceImport`;
  - `DomainSourceImporter`;
  - `resolve_domain_source_importer(domain_id, source_kind)`;
  - `build_profile_local_domain_source_input(request, importer)`.

- [x] Move shared profile-local file governance into a generic helper. The
  helper must:
  - open only the already-resolved profile-local path;
  - read at most `max_bytes + 1`;
  - reject missing files and oversize payloads with sanitized events;
  - create the same local `SourceBundle` shape used today;
  - call `validate_source_bundle`;
  - call `importer.build_environment_input(...)`;
  - return `DomainSourceImport`.

- [x] Expose a contacts importer without changing contacts behavior:

```python
class ContactsSourceImporter:
    domain_id = "contacts_fixture"
    source_kind = "local_contacts_json"

    def build_environment_input(
        self,
        content: bytes,
        *,
        source_bundle_id: str,
        source_policy_hash: str,
    ) -> ContactsEnvironmentInput:
        return contacts_environment_input_from_payload(
            content,
            source_bundle_id=source_bundle_id,
            source_policy_hash=source_policy_hash,
        )
```

- [x] If `contacts_environment_input_from_payload` remains in
  `synthesis.sources`, make it public and narrow. Prefer moving it to a focused
  contacts-owned helper if the edit stays small.

- [x] Keep `build_profile_local_contacts_source_input(...)` as a compatibility
  shim that delegates to the generic helper and returns the existing
  `ProfileLocalContactsSourceInput` shape. This preserves current tests while
  the pipeline migrates.

- [x] Run:

```bash
uv run python -m unittest tests.test_domain_sources tests.test_source_governance
```

- [x] Confirm contacts source-governance tests still pass.

### Task 5: Add Mobile Source Importer and Fixtures

**Files:**

- Create: `synthesis/mobile_sources.py`
- Create: `tests/fixtures/run_profiles/mobile-messages-profile.json`
- Create: `tests/fixtures/run_profiles/profile-local-mobile-messages.json`
- Create: `tests/fixtures/run_profiles/profile-local-mobile-messages-bad-schema.json`
- Modify: `tests/test_domain_sources.py`

- [x] Add mobile JSON fixture payload:

```json
{
  "threads": [
    {"thread_id": "thread_maya", "participant": "Maya"},
    {"thread_id": "thread_alex", "participant": "Alex"},
    {"thread_id": "thread_delivery", "participant": "Delivery"}
  ],
  "messages": [
    {
      "message_id": "msg_maya_project_update",
      "thread_id": "thread_maya",
      "sender": "Maya",
      "body": "Can you remind me to send the project update tomorrow at 9 AM?",
      "received_at": "2026-06-12T08:00:00Z"
    },
    {
      "message_id": "msg_alex_late_reply",
      "thread_id": "thread_alex",
      "sender": "Alex",
      "body": "Please reply that I will be five minutes late.",
      "received_at": "2026-06-12T08:05:00Z"
    },
    {
      "message_id": "msg_delivery_pickup_code",
      "thread_id": "thread_delivery",
      "sender": "Delivery",
      "body": "Your pickup code is 4821. Ask the desk if the sender is missing.",
      "received_at": "2026-06-12T08:10:00Z"
    }
  ],
  "reminders": [],
  "draft_replies": []
}
```

- [x] Add profile fixture:

```json
{
  "schema_version": "run_profile_v2",
  "profile_id": "profile_local_mobile_messages",
  "dataset_version": "dataset_profile_local_mobile_messages",
  "profile_purpose": "diagnostic_probe",
  "seed": {
    "seed_id": "seed_mobile_messages_v1",
    "domain": "mobile_messages_fixture",
    "description": "Synthetic phone messages, reminders, and draft replies.",
    "task_taxonomy": [
      "mobile_message_lookup",
      "mobile_message_to_reminder",
      "mobile_draft_reply",
      "mobile_branch_fallback"
    ]
  },
  "generation": {"mode": "mobile_fixture"},
  "features": {},
  "source": {
    "kind": "local_mobile_messages_json",
    "source_id": "source_profile_mobile_messages_v1",
    "path": "mobile-messages-profile.json",
    "license_label": "cc-by-4.0",
    "max_bytes": 65536
  }
}
```

- [x] Implement `MobileMessagesSourceImporter` in `synthesis.mobile_sources`.
  It should parse JSON bytes, construct `MobileMessagesEnvironmentInput`, call
  `validate_mobile_messages_environment_input_record`, and raise a sanitized
  importer error for invalid payloads.

- [x] Register mobile importer in `resolve_domain_source_importer(...)`.

- [x] Add tests asserting:
  - mobile importer returns `MobileMessagesEnvironmentInput`;
  - source summary uses `local_mobile_messages_json`;
  - source events omit message bodies and profile paths;
  - bad schema payload raises `ControlledSourceFetchError`.

- [x] Run:

```bash
uv run python -m unittest tests.test_domain_sources tests.test_mobile_environment
```

- [x] Confirm all importer tests pass.

### Task 6: Teach Run Profiles About Domain Source Kinds

**Files:**

- Modify: `synthesis/run_profiles.py`
- Modify: `tests/test_run_profiles.py`

- [x] Extend `SOURCE_KINDS` to include `local_mobile_messages_json`.

- [x] Add domain/source-kind compatibility validation in `_load_source(...)` or
  immediately after loading seed and source:

```python
def _validate_source_domain_compatibility(seed: DomainSeed, source: RunProfileSource | None) -> None:
    if source is None:
        return
    normalized_domain = "contacts_fixture" if seed.domain in {"contacts", "contacts_fixture"} else seed.domain
    allowed = {
        "contacts_fixture": {"local_contacts_json"},
        "mobile_messages_fixture": {"local_mobile_messages_json"},
    }
    if source.kind not in allowed.get(normalized_domain, set()):
        raise RunProfileValidationError(
            f"source.kind {source.kind!r} is not supported for seed.domain {seed.domain!r}"
        )
```

- [x] Add tests:
  - `profile-local-mobile-messages.json` loads as `run_profile_v2`;
  - sanitized metadata excludes `mobile-messages-profile.json` and message
    body text;
  - contacts domain rejects `local_mobile_messages_json`;
  - mobile domain rejects `local_contacts_json`.

- [x] Run:

```bash
uv run python -m unittest tests.test_run_profiles
```

- [x] Confirm run-profile tests pass.

### Task 7: Refactor Domain Pipeline to Accept Generic Domain Inputs

**Files:**

- Modify: `synthesis/domain_pipeline.py`
- Modify: `tests/test_mobile_pipeline.py`
- Modify: `tests/test_foundation_pipeline.py`

- [x] Replace `contacts_environment_input` in
  `build_domain_pipeline_bundle(...)` with:

```python
domain_environment_input: object | None = None
```

- [x] In the contacts branch:
  - accept `None` or `ContactsEnvironmentInput`;
  - reject any other input type with `ValueError("contacts_fixture source input must be ContactsEnvironmentInput")`.

- [x] In the mobile branch:
  - accept `None` or `MobileMessagesEnvironmentInput`;
  - reject any other input type with `ValueError("mobile_messages_fixture source input must be MobileMessagesEnvironmentInput")`;
  - call `MobileMessagesEnvironment.create_from_input(...)` when input exists.

- [x] Keep `enable_mcp_adapter` rejected for mobile.

- [x] Add tests:
  - contacts bundle still builds from contacts input;
  - mobile bundle builds from mobile input and uses source provenance;
  - mismatched contacts/mobile input types are rejected;
  - default fixture bundle behavior remains unchanged.

- [x] Run:

```bash
uv run python -m unittest tests.test_mobile_pipeline tests.test_foundation_pipeline
```

- [x] Confirm domain bundle and pipeline tests pass.

### Task 8: Refactor Pipeline Source Admission Plumbing

**Files:**

- Modify: `synthesis/pipeline.py`
- Modify: `tests/test_source_governance.py`
- Modify: `tests/test_foundation_pipeline.py`
- Modify: `tests/test_mobile_pipeline.py`

- [x] Replace `run_foundation_pipeline(..., contacts_environment_input=...)`
  with `domain_environment_input=...`.

- [x] Preserve environment source admission behavior:
  - when `domain_environment_input` is present, add
    `environment_source_admission: accepted` to source provenance;
  - if domain bundle construction rejects the input, write a
    `source_policy_rejected` rejection with
    `environment_source_admission: rejected`;
  - emit `environment_source_admitted` or `environment_source_rejected` events
    when source audit is enabled.

- [x] Migrate existing tests from `contacts_environment_input` to
  `domain_environment_input`.

- [x] Add a mobile pipeline source test:

```python
def test_mobile_pipeline_runs_from_domain_source_import(self) -> None:
    from synthesis.domain_sources import (
        ProfileLocalDomainSourceRequest,
        build_profile_local_domain_source_input,
        resolve_domain_source_importer,
    )
    from synthesis.pipeline import run_foundation_pipeline

    importer = resolve_domain_source_importer(
        "mobile_messages_fixture",
        "local_mobile_messages_json",
    )
    source_import = build_profile_local_domain_source_input(
        ProfileLocalDomainSourceRequest(
            domain_id="mobile_messages_fixture",
            kind="local_mobile_messages_json",
            source_id="source_profile_mobile_messages_v1",
            path=Path("tests/fixtures/run_profiles/mobile-messages-profile.json"),
            license_label="cc-by-4.0",
            max_bytes=65536,
        ),
        importer=importer,
    )
    with tempfile.TemporaryDirectory() as tmpdir:
        result = run_foundation_pipeline(
            Path(tmpdir),
            dataset_version="dataset_mobile_source_profile",
            seed_override=mobile_seed(),
            source_bundle=source_import.source_bundle,
            domain_environment_input=source_import.environment_input,
            source_events=source_import.events,
            enable_source_audit=True,
            run_profile_metadata={
                "schema_version": "run_profile_v2",
                "profile_id": "profile_local_mobile_messages",
                "generation_mode": "mobile_fixture",
                "profile_purpose": "diagnostic_probe",
                "target_candidate_count": None,
                "config_hash": "sha256:" + "2" * 64,
                "enabled_features": [],
                "source": source_import.source_summary,
            },
        )

    self.assertEqual(result.accepted_count, 4)
    self.assertIsNotNone(result.source_events_path)
```

- [x] Run:

```bash
uv run python -m unittest tests.test_source_governance tests.test_foundation_pipeline tests.test_mobile_pipeline
```

- [x] Confirm source admission behavior is preserved.

### Task 9: Wire CLI Profile Sources Through the Generic Importer

**Files:**

- Modify: `main.py`
- Modify: `tests/test_cli.py`

- [x] Replace direct use of
  `build_profile_local_contacts_source_input(...)` with:

```python
from synthesis.domain_sources import (
    ProfileLocalDomainSourceRequest,
    build_profile_local_domain_source_input,
    resolve_domain_source_importer,
)
```

- [x] When `profile.source` exists:
  - resolve importer from `profile.seed.domain` and `profile.source.kind`;
  - build `ProfileLocalDomainSourceRequest` from profile source fields;
  - set `source_bundle`, `domain_environment_input`, `source_events`, and
    `profile_source_summary` from the generic import result.

- [x] Keep `--enable-network-source` contacts-only. If a run profile selects a
  mobile domain and the user also enables network source, the existing
  profile/network conflict should remain enforced by CLI validation.

- [x] Add CLI test:
  - run `--run-profile tests/fixtures/run_profiles/profile-local-mobile-messages.json`;
  - assert accepted count is 4;
  - assert manifest `run_profile.source.kind` is `local_mobile_messages_json`;
  - assert source events exist;
  - assert output does not include profile path, message bodies, or raw payload.

- [x] Add CLI test with `--write-episode-quality-report`,
  `--write-episode-replay-report`, and `--write-reward-label-report` separately
  for the mobile source profile, or one combined regression if test runtime is
  a concern. Assert each report sees `mobile_messages_fixture`.

- [x] Run:

```bash
uv run python -m unittest tests.test_cli
```

- [x] Confirm CLI profile source behavior works for contacts and mobile.

### Task 10: Update Artifact Contracts and Redaction Tests

**Files:**

- Modify: `synthesis/contracts.py`
- Modify: `tests/test_contracts.py`
- Modify: `tests/test_quality_reporting.py` if source-kind slices need updates.

- [x] Update run-profile source metadata and attribution validators to accept
  `local_mobile_messages_json`.

- [x] Ensure validators still reject:
  - `path`;
  - `raw_payload`;
  - `messages`;
  - `body`;
  - arbitrary host paths;
  - secret-like values.

- [x] Add tests using a valid `local_mobile_messages_json` source summary and
  invalid variants with path/raw payload/message body fields.

- [x] Run:

```bash
uv run python -m unittest tests.test_contracts tests.test_quality_reporting
```

- [x] Confirm artifact contract tests pass.

### Task 11: Update Canonical Docs

**Files:**

- Modify: `docs/DESIGN.md`
- Modify: `docs/BACKEND.md`
- Modify: `docs/DATA.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/generated/mobile-domain-pipeline-pressure.md`
- Modify: `docs/PLANS.md`
- Modify: `docs/exec-plans/active/README.md`

- [x] Update [../../DESIGN.md](../../DESIGN.md):
  - source governance is framework-owned;
  - domain source importers are domain-owned;
  - source importers create typed environment input, not source events or
    manifests.

- [x] Update [../../BACKEND.md](../../BACKEND.md):
  - add `synthesis.domain_sources` and `synthesis.mobile_sources`;
  - replace contacts-only profile source flow with generic domain source import
    flow;
  - keep controlled network source contacts-only.

- [x] Update [../../DATA.md](../../DATA.md):
  - document `local_mobile_messages_json`;
  - document `mobile_messages_environment_input_v1`;
  - state redaction requirements for mobile message bodies in metadata,
    source events, and reports.

- [x] Update [../../ROADMAP.md](../../ROADMAP.md):
  - add plan 0035 under Stage 4 as active or implemented depending on timing;
  - keep async orchestration, semantic duplicate detection, external MCP, RL,
    and runtime extraction deferred.

- [x] Update
  [../../generated/mobile-domain-pipeline-pressure.md](../../generated/mobile-domain-pipeline-pressure.md):
  - move mobile source-governed input from unresolved to resolved narrowly when
    implementation completes;
  - keep Agentic RL rollout, external MCP, semantic duplicate detection, async,
    and runtime extraction unresolved.

- [x] Update [../../PLANS.md](../../PLANS.md) and
  [README.md](README.md) for lifecycle state when this plan is completed.

- [x] Run:

```bash
uv run python scripts/validate_docs.py
```

- [x] Confirm documentation validation passes.

### Task 12: Full Regression and Completion Notes

**Files:**

- Modify: `docs/exec-plans/active/0035-domain-source-admission-interface.md`
- Moved to: `docs/exec-plans/completed/0035-domain-source-admission-interface.md`
- Modify: `docs/exec-plans/completed/README.md`
- Modify: `docs/exec-plans/active/README.md`
- Modify: `docs/PLANS.md`

- [x] Run focused regression:

```bash
uv run python -m unittest tests.test_domain_sources tests.test_source_governance tests.test_run_profiles tests.test_mobile_environment tests.test_mobile_pipeline tests.test_foundation_pipeline tests.test_cli tests.test_contracts
```

- [x] Run full regression:

```bash
uv run python -m unittest
```

- [x] Run docs validation:

```bash
uv run python scripts/validate_docs.py
```

- [x] Confirm:
  - default CLI output remains contacts-only and unchanged;
  - contacts profile-local source behavior is preserved;
  - mobile profile-local source uses the generic importer path;
  - manifest/source events/sample lineage/rejection details do not expose
    profile paths, raw payloads, message bodies, contact emails from source
    metadata, provider payloads, credentials, or host paths;
  - episode quality, replay, and reward-label reports still work for mobile
    source-backed runs;
  - plan 0014 remains deferred;
  - plan 0025 remains deferred.

- [x] Move the plan to `docs/exec-plans/completed/`, mark completion date, and
  sync `docs/PLANS.md`, `docs/exec-plans/active/README.md`, and
  `docs/exec-plans/completed/README.md`.

## Validation

During implementation, run the focused commands listed in each task. Final
validation must include:

```bash
uv run python scripts/validate_docs.py
uv run python -m unittest
```

Completion evidence recorded on 2026-06-14:

- `uv run python -m unittest tests.test_domain_sources tests.test_source_governance tests.test_run_profiles tests.test_mobile_environment tests.test_mobile_pipeline tests.test_foundation_pipeline tests.test_cli tests.test_contracts`
  passed with 184 tests.
- `uv run python scripts/validate_docs.py` passed.
- `uv run python -m unittest` passed with 359 tests.

## Completion Criteria

- `run_profile_v2` supports profile-local source declarations for contacts and
  mobile through one domain source admission path.
- The central pipeline no longer accepts a contacts-specific environment input
  parameter.
- Contacts source-backed runs preserve existing behavior and artifact schemas.
- Mobile source-backed runs can produce accepted samples, source events,
  sanitized run-profile metadata, episode-quality reports, executable replay
  reports, and reward-label reports.
- Source governance remains framework-owned while payload parsing and typed
  environment input construction are domain-owned.
- No source paths, raw payload rows, message bodies, contacts emails from source
  metadata, credentials, provider payloads, environment variables, or host paths
  leak into metadata or reports.
- Async orchestration, semantic duplicate detection, external MCP servers,
  Agentic RL rollout collection, and AWM runtime package extraction remain
  deferred.

## Risks

- **Over-abstracting domain import too early:** Keep the protocol limited to
  profile-local JSON source payloads and typed environment input construction.
  Do not introduce a plugin loader, service registry, external package format,
  or arbitrary file ingestion.
- **Moving source governance into domain modules:** Domains should parse
  admitted content only. Shared path, license, hash, event, and source-bundle
  behavior must stay in the source governance layer.
- **Leaking payload content through metadata:** Mobile message bodies and
  contacts emails are needed to build environments, but source events,
  run-profile metadata, and reports must contain only source ids and hashes.
- **Breaking contacts compatibility while generalizing:** Keep contacts
  compatibility shims until all tests use the generic path; then remove only
  truly unused contacts-specific plumbing.
- **Confusing local importer support with network ingestion:** Controlled
  network ingestion remains contacts-only in this plan. General network
  domain importers require a later plan with separate host, content-type, and
  replay/reproducibility analysis.
