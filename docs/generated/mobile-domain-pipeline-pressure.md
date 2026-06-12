# Mobile Domain Pipeline Pressure

Generated during plan 0029 on 2026-06-12.

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

## Evidence

- `tests.test_mobile_environment` covers mobile SQLite fixture construction,
  search, reminder/draft mutation, checkpoint/restore, and sanitized metadata.
- `tests.test_mobile_tools` covers the mobile registry, schemas, argument
  validation, state-change summaries, and registry checkpoint/restore.
- `tests.test_mobile_pipeline` covers deterministic mobile candidates, scripted
  policies, domain bundle selection, mobile state verification, sample contract
  validation, and quality slices.
- `tests.test_cli` covers the mobile run profile and confirms default CLI output
  remains contacts-only.
