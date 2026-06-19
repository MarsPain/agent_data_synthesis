# Mobile Domain Pipeline Pressure

Generated during plan 0029 on 2026-06-12. Updated by plans 0030, 0031, and
0032 on 2026-06-13, plans 0033, 0034, and 0035 on 2026-06-14, and plan
0036 on 2026-06-19.

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

## Assumptions Partially Resolved or Intentionally Left Unresolved

- `CandidateTask` remains the public compatibility wrapper, but internal
  `TaskContract` records now split task intent, policy hints, expected final
  answer, and expected state before execution and verification.
- MCP adapter support remains contacts-only. Mobile profiles that request the
  adapter are rejected instead of silently falling back.
- Source-governed profile-local environment input is no longer contacts-only:
  contacts and mobile messages now use one domain importer interface after
  shared source governance admits the local JSON payload.
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
- MCP adapter support remains contacts-only.
- `CandidateTask` still exposed task intent, policy hints, expected answer, and
  expected state through one compatibility record; 0030 documented that
  pressure but did not migrate the internal boundary.

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
collection, external MCP environment servers, or
the internal `CandidateTask` intent/policy/expected-state split that was later
addressed by plan 0033.

## Plan 0032 Executable Replay Update

Plan 0032 resolves the narrow executable replay pressure by adding a repo-local,
opt-in consumer:

- `--write-episode-replay-report` writes validated `episodes.jsonl` records and
  replays them against fresh contacts/mobile fixture runtimes.
- `episode_replay_report_v1` validates the episode contract, checks runtime
  support/rebuild, executes action transitions through `ToolRegistry.execute()`,
  compares observation and state-change hashes, and records final-response
  presence for accepted episodes.
- The report summaries contain ids, runtime/outcome fields, action/replay
  counts, observation/state-change match counts, tool names, and failed check
  names only; they omit raw arguments, observations, final responses, prompts,
  provider payloads, source payloads, credentials, and host paths.
- Runtime-boundary evidence records allowlisted runtime methods
  (`rebuild`, `runtime_metadata`) and registry methods (`execute`) without
  extracting a separate `awm_runtime` package.

This left reward-label export, Agentic RL rollout collection, external MCP
environment servers, and the `CandidateTask`
intent/policy/expected-state split unresolved.

## Plan 0033 Task-Contract Split Update

Plan 0033 partially resolves the `CandidateTask` coupling by adding an internal
contract boundary:

- `synthesis.task_contracts` derives validated `TaskIntent`, `PolicyHint`,
  `ExpectedOutcome`, and `ExpectedStateCheck` records from deterministic and
  generated `CandidateTask` values.
- Contacts and mobile scripted policies can consume contract policy hints while
  compatibility wrappers still accept `CandidateTask`.
- Verification reads final-answer and state expectations through
  contract-aware helpers while preserving verifier ids, versions, and check
  names.
- Public `samples.jsonl`, `rejections.jsonl`, manifest, quality report,
  `episode_log_v1`, `episode_quality_report_v1`, and
  `episode_replay_report_v1` schemas do not gain raw task instructions,
  expected answers, expected state, or policy arguments.

This kept reward-label export, Agentic RL rollout collection, external MCP
environment servers, and mobile source-governed input unresolved. It also kept
full AWM runtime package extraction deferred; plan 0033 is boundary evidence,
not extraction.

## Plan 0034 Reward-Label Export Update

Plan 0034 resolves the narrow reward-label export pressure by adding a
repo-local, opt-in consumer:

- `--write-reward-label-report` writes validated `episodes.jsonl` records,
  deterministic `reward_labels.jsonl`, and `reward_label_report.json`.
- `reward_label_v1` scores outcome, contract validity, execution evidence,
  state-change support, and replay consistency into a bounded scalar reward
  with deterministic preference-group metadata.
- The report summaries contain ids, runtime id, label status, scalar reward,
  and failed check names only; they omit raw task instructions, expected
  answers, expected state, tool arguments, observations, final responses,
  prompts, provider payloads, source payloads, credentials, and host paths.
- Episode-quality and episode-replay evidence can be computed in memory for
  reward-label scoring. Their artifacts are attached to the manifest only when
  their own flags are explicitly requested.

This left Agentic RL rollout collection, external MCP environment servers,
mobile source-governed input, semantic duplicate detection, async orchestration,
and full AWM runtime package extraction unresolved.

## Plan 0035 Domain Source Admission Update

Plan 0035 resolves the narrow mobile source-governed input pressure by adding a
domain source importer boundary:

- `synthesis.sources` keeps shared source governance: profile-relative path
  admission, byte limits, license decisions, source bundles, source-policy
  hashes, and sanitized source events.
- `synthesis.domain_sources` resolves `(domain_id, source.kind)` pairs and
  calls domain importers after source governance admits bytes.
- Contacts keep compatibility through `local_contacts_json`; mobile messages
  add `local_mobile_messages_json` and `MobileMessagesEnvironmentInput`.
- `synthesis.domain_pipeline` and `synthesis.pipeline` accept generic
  `domain_environment_input` instead of a contacts-specific source parameter.
- CLI `run_profile_v2` profile-local source runs now work for both contacts and
  `mobile_messages_fixture`; controlled network ingestion remains contacts-only.

This still leaves Agentic RL rollout collection, external MCP environment
servers, semantic duplicate detection, async orchestration, controlled network
source import for non-contacts domains, and full AWM runtime package extraction
unresolved.

## Plan 0036 Domain-Aware Evaluation Update

Plan 0036 resolves the domain-aware held-out evaluation and release-semantics
pressure:

- `synthesis.evaluation` now resolves held-out suites from manifest
  `run_profile.seed.domain`, preserving `contacts_heldout_v1` and adding
  `mobile_messages_heldout_v1`.
- Mobile held-out evaluation covers message lookup, reminder creation, draft
  reply, branch fallback, and controlled missing-message failure through the
  existing domain pipeline bundle.
- New evaluation reports include suite/report domain identity and domain-aware
  capability thresholds.
- Profile promotion and dataset release admission treat evaluation evidence
  from a different domain as `insufficient_evidence` instead of passed.

This still leaves Agentic RL rollout collection, external MCP environment
servers, semantic duplicate detection, async orchestration, controlled network
source import for non-contacts domains, and full AWM runtime package extraction
unresolved.

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
- `tests.test_episode_replay` covers executable contacts/mobile replay,
  state-change hash matching, insufficient evidence, and sanitized report
  validation.
- `tests.test_reward_labels` covers deterministic contacts/mobile reward labels,
  missing replay evidence, insufficient evidence decisions, and redaction
  contracts.
- `tests.test_task_contracts` covers contacts/mobile contract conversion,
  branch-plan validation reuse, unsafe value rejection, contract-aware scripted
  policies, and contract-aware verification.
- `tests.test_domain_sources` covers generic profile-local domain source
  admission, contacts/mobile importer resolution, mismatch rejection, and
  sanitized source events.
- `tests.test_evaluation` covers contacts/mobile held-out suite resolution,
  mobile evaluation execution, domain report fields, and domain-aware threshold
  decisions.
- `tests.test_profile_decisions` and `tests.test_dataset_release` cover
  domain-mismatch gates for promotion and release admission.
- `tests.test_cli` covers the mobile run profile and confirms default CLI output
  remains contacts-only; it also covers opt-in episode-quality, episode-replay,
  reward-label report writing, profile-local mobile source admission, and
  mobile domain-aware evaluation/profile-decision report writing.
