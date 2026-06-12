# Plan 0029: Mobile Agent Second-Domain Pipeline Probe

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

## Status

Planned on 2026-06-12. Completed on 2026-06-12.

## Goal

Introduce a narrow second domain environment that is closer to mobile Agent
workflows, then use it to validate and improve the synthesis pipeline boundary
without turning the work into release infrastructure, async orchestration, or a
full AWM runtime extraction.

## Architecture

Add a deterministic `mobile_messages_fixture` domain representing a local phone
message inbox, reminders, and draft replies. The pipeline should be able to run
either the existing contacts domain or the new mobile domain from run-profile
seed metadata while preserving the default contacts behavior.

The main architectural value is pressure-testing the current contacts-specific
assumptions in environment construction, tool registry setup, scripted policy
generation, state verification, quality slicing, and artifact assembly. Any
generic boundary introduced in this plan must be the smallest internal boundary
needed for two domains to run through the same synchronous candidate-processing
path.

## Tech Stack

- Python standard library: `dataclasses`, `pathlib`, `sqlite3`, `unittest`, and
  JSON fixtures.
- Existing modules: `synthesis.pipeline`, `synthesis.candidate_processing`,
  `synthesis.execution`, `synthesis.verification`, `synthesis.tasks`,
  `synthesis.run_profiles`, `synthesis.datasets`, `synthesis.quality`, and
  `main.py`.
- New focused modules: `synthesis.domain_pipeline`,
  `synthesis.mobile_environment`, `synthesis.mobile_tools`, and
  `synthesis.mobile_tasks`.
- Verification through `uv run python scripts/validate_docs.py` and
  `uv run python -m unittest`.

## Basis

- [../../DESIGN.md](../../DESIGN.md) defines the framework as executable,
  verifiable, versioned Agent data synthesis across bounded contexts, not as a
  contacts-only data generator.
- [../completed/0016-candidate-execution-boundary-and-orchestration-readiness.md](../completed/0016-candidate-execution-boundary-and-orchestration-readiness.md)
  extracted per-candidate processing but kept the batch-level foundation
  pipeline contacts-centered.
- [../completed/0021-candidate-isolation-and-deterministic-merge.md](../completed/0021-candidate-isolation-and-deterministic-merge.md)
  established candidate-local environment, registry, and adapter isolation, but
  only for contacts.
- [../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md](../deferred/0025-awm-runtime-boundary-and-shared-environment-kernel.md)
  says a second domain environment is one valid pressure signal for the future
  runtime boundary. This plan supplies that evidence without extracting a
  separate runtime package.
- [../../PRODUCT_SENSE.md](../../PRODUCT_SENSE.md) makes controllable Agent
  training trajectories the product focus. A phone-message domain is closer to
  mobile Agent behavior than more release-report work.

## Why This Plan Now

The recent release-admission and release-evidence plans are sufficient for the
current local MVP artifact path. Continuing to add release comparison or release
presentation would not answer the more important architectural question: can
the synthesis framework generalize beyond contacts?

The next useful step is a second deterministic domain that is small enough to
implement safely but different enough to break hidden contacts assumptions. A
mobile messages/reminders domain fits that need:

- it is close to mobile Agent scenarios;
- it includes read-only lookup, state mutation, and draft-output behavior;
- it supports deterministic verification without real phone permissions;
- it can expose whether task, policy, verifier, and environment contracts are
  truly domain-aware.

## Scope

- Add a new `mobile_messages_fixture` environment with synthetic phone message
  threads, reminders, and draft replies stored in SQLite.
- Add domain tools:
  - `search_phone_messages`;
  - `create_phone_reminder`;
  - `draft_message_reply`.
- Add deterministic mobile candidates covering:
  - message lookup;
  - message-to-reminder state change;
  - draft reply creation;
  - branch fallback from a missing direct message to a broader thread search.
- Add a run-profile fixture that selects the mobile domain through seed domain
  and generation mode metadata.
- Add the minimal internal pipeline-domain boundary needed to select the
  environment builder, tool registry builder, candidate generator, policy
  generator, and verifier behavior for contacts or mobile.
- Preserve the default `uv run python main.py` contacts path and existing
  artifact contracts.
- Record implementation evidence in docs about which contacts-specific
  assumptions were removed and which remain.

## Out of Scope

- Full AWM runtime extraction or a separate `awm_runtime` package.
- Async orchestration, durable queues, cancellation, resumption, or per-role
  cost tracking from plan 0014.
- Semantic duplicate detection, embeddings, clustering, or admission gates from
  `TD-0002`.
- Real mobile OS integration, SMS access, notification access, calendar access,
  device automation, browser automation, or external MCP servers.
- New release-admission, release-pack, release-card, or release-comparison
  behavior.
- Remote LLM prompt expansion for the mobile domain beyond existing role
  boundaries. The first mobile probe is deterministic.
- Broad task/policy/verifier model redesign. This plan may document pressure
  toward that redesign, but it should not complete it.

## Domain Contract

### Environment

The mobile fixture should use `environment_id: mobile_messages_fixture` and a
version such as `env_mobile_messages_v1`.

SQLite tables:

- `message_threads(thread_id TEXT PRIMARY KEY, participant TEXT NOT NULL)`;
- `messages(message_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, sender TEXT
  NOT NULL, body TEXT NOT NULL, received_at TEXT NOT NULL)`;
- `reminders(reminder_id TEXT PRIMARY KEY, title TEXT NOT NULL, due_at TEXT,
  source_message_id TEXT, created_at TEXT NOT NULL)`;
- `draft_replies(draft_id TEXT PRIMARY KEY, thread_id TEXT NOT NULL, body TEXT
  NOT NULL, created_at TEXT NOT NULL)`.

Fixture data should be synthetic and non-sensitive. Suggested records:

- Maya asks: "Can you remind me to send the project update tomorrow at 9 AM?"
- Alex asks: "Please reply that I will be five minutes late."
- A delivery thread mentions a pickup code and a missing direct sender case for
  branch fallback.

The environment must support checkpoint/restore and rebuild behavior equivalent
to contacts so candidate isolation still works.

### Tools

`search_phone_messages`:

```json
{
  "type": "object",
  "properties": {
    "query": {"type": "string"},
    "participant": {"type": "string"}
  },
  "required": ["query"],
  "additionalProperties": false
}
```

Returns sanitized message ids, participants, and snippets. It must not expose
host paths or external data.

`create_phone_reminder`:

```json
{
  "type": "object",
  "properties": {
    "title": {"type": "string"},
    "due_at": {"type": "string"},
    "source_message_id": {"type": "string"}
  },
  "required": ["title"],
  "additionalProperties": false
}
```

Creates or upserts a reminder record and returns a `state_change` summary.

`draft_message_reply`:

```json
{
  "type": "object",
  "properties": {
    "thread_id": {"type": "string"},
    "body": {"type": "string"}
  },
  "required": ["thread_id", "body"],
  "additionalProperties": false
}
```

Creates or upserts a draft reply and returns a `state_change` summary. It must
not claim to send a real message.

### Candidate Tasks

Use the existing `CandidateTask` record for the first probe, but set
domain-specific constraints explicitly:

```json
{
  "domain": "mobile_messages_fixture",
  "task_type": "mobile_message_to_reminder",
  "required_tools": ["search_phone_messages", "create_phone_reminder"]
}
```

Expected state keys:

- `mobile_reminder`: expected reminder title, optional due time, and optional
  source message id;
- `mobile_draft_reply`: expected thread id and body.

This intentionally exposes the limitation that `CandidateTask` still mixes task
intent, execution hints, expected answer, and expected state. If the
implementation becomes awkward, document the observed pressure for a later
task/policy/verifier decoupling plan rather than expanding this plan.

## File Map

- Create `synthesis/mobile_environment.py` for mobile environment records,
  SQLite fixture construction, checkpoint/restore, rebuild, message search,
  reminder creation, draft reply creation, and state inspection helpers.
- Create `synthesis/mobile_tools.py` for mobile tool registry construction and
  tool schemas.
- Create `synthesis/mobile_tasks.py` for deterministic mobile candidates and
  scripted mobile solution policies.
- Create `synthesis/domain_pipeline.py` for the minimal domain bundle used by
  the synchronous pipeline.
- Modify `synthesis/pipeline.py` to select a domain bundle from the active seed
  and to remove hard dependencies on contacts when running mobile profiles.
- Modify `synthesis/candidate_processing.py` only where type annotations or
  tool-admission behavior assume `ContactEnvironment`.
- Modify `synthesis/execution.py` to allow domain-specific scripted policies
  without hard-coding every mobile task into the generic contacts policy path.
- Modify `synthesis/verification.py` to support mobile expected-state checks
  while preserving existing contact checks.
- Modify `synthesis/run_profiles.py` to accept the deterministic mobile
  generation mode.
- Modify `synthesis/quality.py` only if domain slices need an explicit accepted
  `domain` dimension beyond existing task-type and tool-combination slices.
- Add `tests/fixtures/run_profiles/mobile-agent-fixture.json`.
- Add `tests/test_mobile_environment.py`, `tests/test_mobile_tools.py`, and
  `tests/test_mobile_pipeline.py`.
- Extend `tests/test_foundation_pipeline.py` and `tests/test_cli.py` for default
  contacts stability and mobile-profile execution.
- Update [../../DATA.md](../../DATA.md), [../../DESIGN.md](../../DESIGN.md),
  [../../ROADMAP.md](../../ROADMAP.md), and [../../PLANS.md](../../PLANS.md).
- Add `docs/generated/mobile-domain-pipeline-pressure.md` and link it from
  `docs/generated/README.md`.

## Implementation Tasks

### Task 1: Add Mobile Environment Contract Tests

- [ ] Add `tests/test_mobile_environment.py`.
- [ ] Test that `MobileMessagesEnvironment.create_fixture(tmpdir)` creates
  message, reminder, and draft tables with deterministic fixture data.
- [ ] Test `search_messages(query="project update", participant="Maya")`
  returns the expected synthetic message id and snippet.
- [ ] Test `create_reminder(...)` records a reminder and
  `has_reminder(...)` returns true for the expected title, due time, and source
  message id.
- [ ] Test `draft_reply(...)` records a draft and `has_draft_reply(...)`
  returns true for the expected thread id and body.
- [ ] Test checkpoint/restore rolls back reminder and draft state after a
  mutation.
- [ ] Test `metadata()` returns `environment_id:
  mobile_messages_fixture`, the environment version, a SQLite reset recipe, and
  no host path beyond the database file name.

### Task 2: Implement Mobile Environment

- [ ] Create `synthesis/mobile_environment.py`.
- [ ] Add immutable records for message threads, messages, reminders, and draft
  replies with `export()` methods.
- [ ] Implement `MobileMessagesEnvironment.create_fixture(...)` with synthetic
  phone data only.
- [ ] Implement search, reminder, draft, state-inspection, checkpoint, restore,
  rebuild, and metadata methods.
- [ ] Run `uv run python -m unittest tests.test_mobile_environment`.

### Task 3: Add Mobile Tool Registry

- [ ] Add `tests/test_mobile_tools.py`.
- [ ] Test that `build_mobile_tool_registry(environment)` exports exactly
  `search_phone_messages`, `create_phone_reminder`, and
  `draft_message_reply`.
- [ ] Test each tool validates required argument types and rejects empty
  strings with `ValueError`.
- [ ] Test mutating tools return `state_change` summaries and that registry
  checkpoint/restore delegates to the mobile environment.
- [ ] Create `synthesis/mobile_tools.py` and implement the three tool
  definitions.
- [ ] Run `uv run python -m unittest tests.test_mobile_tools`.

### Task 4: Add Deterministic Mobile Candidate and Policy Fixtures

- [ ] Add `tests/test_mobile_pipeline.py` tests for
  `generate_mobile_fixture_candidates(seed)`.
- [ ] Assert the deterministic mobile fixture yields at least four candidates:
  lookup, reminder creation, draft reply creation, and branch fallback.
- [ ] Assert each mobile candidate has `constraints.domain ==
  "mobile_messages_fixture"` and an explicit `task_type`.
- [ ] Create `synthesis/mobile_tasks.py`.
- [ ] Implement deterministic candidates using existing `CandidateTask` without
  changing exported sample shape.
- [ ] Implement `scripted_mobile_solution_policy(task)` for mobile lookup,
  reminder, draft reply, and branch fallback tasks.
- [ ] Keep contact-specific `scripted_solution_policy(task)` behavior unchanged.

### Task 5: Introduce the Minimal Domain Pipeline Boundary

- [ ] Add tests in `tests/test_mobile_pipeline.py` proving a domain bundle can
  be built for `contacts_fixture` and `mobile_messages_fixture`.
- [ ] Create `synthesis/domain_pipeline.py` with a small immutable
  `DomainPipelineBundle` containing:
  - `domain_id`;
  - `environment`;
  - `registry`;
  - `verifier`;
  - `candidate_generator`;
  - `policy_generator`;
  - optional `adapter_shim`.
- [ ] Add `build_domain_pipeline_bundle(seed, output_dir, ...)` that returns the
  existing contacts bundle for `contacts_fixture` and the mobile bundle for
  `mobile_messages_fixture`.
- [ ] Keep MCP adapter support contacts-only for this plan. If a mobile profile
  enables MCP adapter, reject it with a clear configuration error rather than
  silently falling back.
- [ ] Keep source-governed contacts input contacts-only for this plan. Mobile
  local source ingestion is a separate future plan.

### Task 6: Run Mobile Through the Existing Candidate Processing Path

- [ ] Generalize `CandidateProcessingContext` annotations so the environment
  only needs `metadata()`, checkpoint-compatible registry behavior, and verifier
  state hooks used by the active verifier.
- [ ] Modify `run_foundation_pipeline(...)` to build a domain bundle from the
  active seed before candidate generation.
- [ ] Route deterministic mobile generation through the bundle when
  `seed.domain == "mobile_messages_fixture"`.
- [ ] Route policy generation through the bundle so contact and mobile scripted
  policies do not need to live in one large `if` chain.
- [ ] Preserve ordered deterministic merge and exact duplicate admission.
- [ ] Run the existing contacts deterministic tests to prove the default path is
  unchanged.

### Task 7: Extend Verification for Mobile State

- [ ] Add verification tests for `expected_state.mobile_reminder` and
  `expected_state.mobile_draft_reply`.
- [ ] Modify `synthesis/verification.py` so the exact-answer verifier keeps the
  current final-response check and delegates state checks by expected-state key.
- [ ] Preserve `contact_followup` state verification semantics exactly.
- [ ] Add mobile state checks that call `has_reminder(...)` and
  `has_draft_reply(...)` when the active environment provides those methods.
- [ ] Return `solution_logic_error` in failed mobile state checks, matching
  contact state-check behavior.

### Task 8: Add Run Profile and CLI Coverage

- [ ] Modify `synthesis/run_profiles.py` to accept generation mode
  `mobile_fixture`.
- [ ] Add `tests/fixtures/run_profiles/mobile-agent-fixture.json` with:
  - `profile_id: mobile_agent_fixture`;
  - `dataset_version: dataset_mobile_agent_fixture`;
  - `profile_purpose: diagnostic_probe`;
  - `seed.domain: mobile_messages_fixture`;
  - `generation.mode: mobile_fixture`;
  - no source block.
- [ ] Extend `tests/test_cli.py` with:

```bash
uv run python main.py --run-profile tests/fixtures/run_profiles/mobile-agent-fixture.json --output-dir <tmp>/mobile-agent-fixture
```

- [ ] Assert the command writes `samples.jsonl`, `rejections.jsonl`,
  `manifest.json`, and `quality_report.json`.
- [ ] Assert accepted samples include `environment.id ==
  "mobile_messages_fixture"` and tools from the mobile registry.
- [ ] Assert default `uv run python main.py` still emits contacts samples and
  does not mention mobile tools.

### Task 9: Preserve Reporting and Artifact Contracts

- [ ] Add tests proving mobile accepted samples validate through existing sample
  contract validation.
- [ ] Confirm quality report slices include mobile task types and mobile tool
  combinations without schema changes.
- [ ] If a domain slice is added, update contracts and tests so both contacts
  and mobile reports include it deterministically.
- [ ] Ensure manifest run-profile metadata remains sanitized and does not store
  raw fixture records beyond normal sample trajectories.
- [ ] Do not modify dataset release report, release pack, release quality audit,
  or release card behavior except for compatibility fixes required by existing
  tests.

### Task 10: Document Pipeline Pressure From the Second Domain

- [ ] Add `docs/generated/mobile-domain-pipeline-pressure.md`.
- [ ] Record which contacts-specific assumptions were removed, including:
  environment type annotations, tool-registry construction, scripted policy
  routing, and state-verifier dispatch.
- [ ] Record which assumptions remain intentionally unresolved, especially:
  `CandidateTask` mixing task intent with execution hints and expected answer;
  contacts-only MCP adapter behavior; contacts-only source ingestion.
- [ ] Link the generated note from `docs/generated/README.md`.
- [ ] Update [../../DESIGN.md](../../DESIGN.md) with the second-domain probe
  and the rule that domain packs own domain state/tools while the pipeline owns
  synthesis flow.
- [ ] Update [../../DATA.md](../../DATA.md) with the mobile environment,
  mobile tools, and mobile expected-state keys.
- [ ] Update [../../ROADMAP.md](../../ROADMAP.md) to place the second-domain
  probe before any full AWM runtime extraction.

### Task 11: Validation

- [ ] Run `uv run python scripts/validate_docs.py`.
- [ ] Run `uv run python -m unittest tests.test_mobile_environment`.
- [ ] Run `uv run python -m unittest tests.test_mobile_tools`.
- [ ] Run `uv run python -m unittest tests.test_mobile_pipeline`.
- [ ] Run `uv run python -m unittest tests.test_foundation_pipeline tests.test_cli`.
- [ ] Run `uv run python -m unittest`.
- [ ] Run the mobile profile command:

```bash
uv run python main.py --run-profile tests/fixtures/run_profiles/mobile-agent-fixture.json --output-dir artifacts/mobile-agent-fixture
```

- [ ] Inspect `artifacts/mobile-agent-fixture/manifest.json`,
  `samples.jsonl`, and `quality_report.json` for mobile environment identity,
  mobile tools, accepted reminder/draft state changes, and no real-device data.

## Validation

```bash
uv run python scripts/validate_docs.py
uv run python -m unittest tests.test_mobile_environment
uv run python -m unittest tests.test_mobile_tools
uv run python -m unittest tests.test_mobile_pipeline
uv run python -m unittest tests.test_foundation_pipeline tests.test_cli
uv run python -m unittest
uv run python main.py --run-profile tests/fixtures/run_profiles/mobile-agent-fixture.json --output-dir artifacts/mobile-agent-fixture
```

Expected outcomes:

- Default contacts pipeline behavior is unchanged.
- The mobile profile produces deterministic accepted and rejected artifacts
  through the same synchronous candidate-processing and merge path.
- Mobile samples carry `environment.id: mobile_messages_fixture`.
- Mobile trajectories include search, reminder, draft, and branch-fallback
  behavior where expected.
- Mobile state mutations are independently verified.
- Release-specific artifacts remain opt-in and unaffected.
- Async orchestration, semantic duplicate detection, and full AWM runtime
  extraction remain deferred.

## Acceptance Criteria

- A second deterministic domain environment runs through the same local
  synthesis pipeline as contacts.
- The selected second domain is phone-like: synthetic messages, reminders, and
  draft replies.
- The implementation removes the most obvious contacts-specific assumptions
  from pipeline setup and candidate processing.
- Existing contacts fixtures, CLI defaults, quality reports, and release-related
  optional flags remain compatible.
- Mobile tasks cover read-only lookup, state mutation, draft output, and branch
  fallback.
- Mobile expected-state verification proves reminder and draft mutations instead
  of trusting the solution policy.
- The plan produces written architecture evidence about which boundaries are
  ready for a later 0025-style runtime boundary and which are not.
- Documentation validation and the full unit suite pass.

## Risks

- The plan can accidentally become a broad mobile OS simulator. Keep the
  environment synthetic, local, and deterministic.
- A second domain can produce copy-pasted domain code instead of architectural
  pressure. The implementation must remove at least the setup, policy, and
  verification assumptions needed for both domains to share the pipeline.
- Generalizing too far would prematurely implement plan 0025. Keep the generic
  boundary internal, minimal, and justified by contacts plus mobile only.
- Existing release reports may assume contacts release-candidate coverage. Do
  not make mobile releaseable in this plan; use `diagnostic_probe`.
- Mobile tasks can leak real-device semantics if names imply real sending or
  notification access. Use `draft_message_reply`, not `send_message`, and store
  synthetic fixture data only.
