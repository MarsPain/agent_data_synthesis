# Mobile Domain Pipeline Pressure

Generated during plan 0029 on 2026-06-12. Updated by plans 0030 and 0031 on
2026-06-13.

## What Changed

The synchronous foundation pipeline now supports a second deterministic domain,
`mobile_messages_fixture`, alongside `contacts_fixture`. The mobile domain owns
its SQLite fixture state, tool registry, deterministic task candidates, and
scripted solution policies for synthetic phone messages, reminders, and draft
replies.

The pipeline owns the shared candidate-processing flow: source policy checks,
domain bundle selection, candidate-local environment rebuilds, execution,
verification, deterministic merge admission, artifact writing, manifest
assembly, and quality reporting.

## Contacts-Specific Assumptions Removed

- Pipeline setup no longer directly constructs `ContactEnvironment` and
  `build_contact_tool_registry`; it asks `synthesis.domain_pipeline` for a
  domain bundle.
- Candidate-local isolation no longer rebuilds only contacts environments; it
  rebuilds the selected domain bundle for each candidate.
- Scripted solution policy routing is no longer a single contacts path; the
  domain bundle supplies either contacts or mobile policy generation.
- Verifier state dispatch now handles `contact_followup`, `mobile_reminder`,
  and `mobile_draft_reply` expected-state keys.
- Foundation smoke gates are domain-aware: contacts checks
  `lookup_contact_email`, while mobile checks `search_phone_messages`.

## Assumptions Intentionally Left Unresolved

- `CandidateTask` still mixes task intent, execution hints, expected answer, and
  expected state. The mobile probe made this visible but did not split those
  responsibilities.
- MCP adapter support remains contacts-only. Mobile profiles that request the
  adapter are rejected instead of silently falling back.
- Source-governed environment input remains contacts-only. Mobile local source
  ingestion is outside this plan.
- The domain bundle is an internal synchronous boundary, not a separate AWM
  runtime package.

## Plan 0030 Runtime Boundary Update

Plan 0030 resolved the narrow lifecycle pressure exposed by the second domain:

- `ContactEnvironment` and `MobileMessagesEnvironment` now satisfy a shared
  internal runtime protocol with `metadata()`, `runtime_metadata()`,
  checkpoint/restore, rebuild, and SQLite database path semantics.
- `synthesis.domain_pipeline` depends on the shared runtime protocol instead of
  a local contacts/mobile placeholder protocol.
- Runtime-owned `runtime_metadata_v1` records identify runtime id/version,
  environment id/version, reset recipe class, state backend, and checkpoint
  strategy without dataset-release, profile-decision, provider, credential, or
  host-path fields.
- Existing contacts and mobile trajectories can be converted into sanitized
  `episode_log_v1` evidence for diagnostic quality readers without changing
  `samples.jsonl`, `rejections.jsonl`, or manifest output.

The larger 0025 extraction pressure remains unresolved:

- The runtime boundary is still repo-local and synchronous, not a separate
  `awm_runtime` package.
- Episode evidence is an in-memory diagnostic contract consumer, not a replay
  engine, reward/data-quality trainer, Agentic RL collector, or release
  artifact.
- MCP adapter support remains contacts-only, and mobile source-governed input
  remains outside scope.
- `CandidateTask` still mixes task intent, policy hints, expected answer, and
  expected state; 0030 documents that pressure but does not migrate the schema.

## Plan 0031 Episode-Quality Consumer Update

Plan 0031 partially resolves the in-memory-only episode pressure by adding a
repo-local, opt-in consumer:

- `--write-episode-quality-report` writes validated `episodes.jsonl` records for
  admitted samples and non-duplicate rejected execution attempts.
- `episode_quality_report_v1` scores contract validity, action/observation
  presence, accepted final-response and error consistency, state-change support,
  and known runtime ids across contacts and mobile episodes.
- The report summaries contain ids, runtime/outcome fields, transition counts,
  tool names, and failed check names only; they omit raw arguments,
  observations, final responses, prompts, provider payloads, source payloads,
  credentials, and host paths.
- Manifest references for `episodes` and `episode_quality_report` are attached
  only when the report is explicitly requested.

This does not resolve executable replay, reward-label export, Agentic RL rollout
collection, external MCP environment servers, mobile source-governed input, or
the `CandidateTask` intent/policy/expected-state split.

## Evidence

- `tests.test_mobile_environment` covers mobile SQLite fixture construction,
  search, reminder/draft mutation, checkpoint/restore, and sanitized metadata.
- `tests.test_mobile_tools` covers the mobile registry, schemas, argument
  validation, state-change summaries, and registry checkpoint/restore.
- `tests.test_mobile_pipeline` covers deterministic mobile candidates, scripted
  policies, domain bundle selection, mobile state verification, sample contract
  validation, and quality slices.
- `tests.test_runtime_contract` covers shared runtime metadata, safety
  validation, and checkpoint/restore/rebuild protocol behavior across contacts
  and mobile environments.
- `tests.test_episode_logs` covers episode transition mapping, deterministic
  hashing, redaction, contract validation, and the diagnostic episode quality
  summary reader.
- `tests.test_episode_quality` covers opt-in episode JSONL round trips,
  deterministic episode-quality decisions, report validation, and sanitized
  summaries for contacts and mobile episodes.
- `tests.test_cli` covers the mobile run profile and confirms default CLI output
  remains contacts-only; it also covers opt-in episode-quality report writing.
