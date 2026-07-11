# Plan 0041: Release Review Resolution and Evidence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `subagent-driven-development` or `executing-plans` to implement this plan
> task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Turn release-quality audit warnings into a deterministic, redacted,
human-review workflow that records reviewer outcomes and aggregates review
evidence without changing sample admission or dataset release decisions.

**Architecture:** Keep candidate-time `review_queue.jsonl` unchanged for
reviewable rejected candidates. Add a separate release-review consumer that
reads an existing `release_quality_audit.json`, emits a redacted
`release_review_queue.jsonl` only for audit `watch` signals, validates an
explicit local `review_decisions.jsonl` input, and writes a
`review_resolution_report.json` summary. The flow is opt-in, append-only at the
artifact boundary, and cannot accept/reject samples, mutate quality reports, or
alter `dataset_release_report_v1`.

**Tech Stack:** Python standard library (`dataclasses`, `hashlib`, `json`,
`pathlib`), existing artifact/manifest helpers, `unittest`, JSONL fixtures, and
the repository documentation validator.

---

## Status

Completed. Created on 2026-07-10 and completed on 2026-07-11.

## Implementation Outcome

The implementation adds a separate deterministic redacted release-review queue,
contract-validates explicit local reviewer decisions, and writes aggregate-only
resolution evidence without changing sample admission or dataset release
decisions. Offline resolution may append only the same-dataset resolution report
reference after pack creation; pack bytes remain unchanged, and verification
accepts the append only when removing that unique reference exactly reconstructs
the canonical manifest hash and byte count locked in the pack.

## Why This Plan

Plan 0040 completed release-candidate evidence paths for contacts, mobile
messages, and workspace tasks. Each deterministic release candidate currently
passes release admission with the minimum five accepted samples, while its
release-quality audit returns `watch` because the release is smaller than the
eight-sample review threshold. The audit deliberately exposes concentration and
duplicate-family signals but does not create a reviewer work item or preserve a
human conclusion.

The pipeline already routes reviewable rejected candidates into
`review_queue.jsonl` when explicitly enabled. That record is a candidate-time
rejection artifact and is not suitable for release-level audit risks: an audit
may flag accepted samples or a release-wide concentration condition. This plan
fills that gap without treating an audit warning as an automatic release block.

This directly supports the data-quality-team workflow and the product metrics
for failure diagnosis and human review minutes. It also creates the evidence
needed to decide later whether the documented semantic-duplicate or async
orchestration triggers reflect real production pressure rather than fixture
assumptions.

## Scope

- Define and validate a redacted `release_review_item_v1` JSONL contract.
- Define and validate a reviewer-authored `review_decision_v1` JSONL contract.
- Build deterministic review items from a valid release-quality audit with
  `decision.status == "watch"`.
- Write `release_review_queue.jsonl` only when at least one release review item
  exists.
- Read an explicit decisions file and write `review_resolution_report_v1` with
  pending, resolved, confirmed-issue, accepted-risk, and follow-up counts plus
  aggregate review minutes.
- Add opt-in CLI commands/flags that require the existing release-quality audit
  path and attach written review artifacts to the manifest.
- Keep the existing candidate rejection `review_queue.jsonl` contract and
  routing behavior unchanged.
- Cover contacts, mobile messages, and workspace tasks through unit and CLI
  smoke tests.
- Document the review boundary, redaction rules, commands, and non-claims.

## Out of Scope

- A browser UI, authentication, reviewer assignment service, notifications, or
  network-backed workflow system.
- Altering `samples.jsonl`, `rejections.jsonl`, candidate acceptance, exact
  duplicate admission, quality metrics, profile promotion, evaluation, or
  dataset release admission from a reviewer decision.
- Semantic duplicate detection, embedding providers, vector stores, clustering,
  or near-duplicate admission gates from `TD-0002`.
- Async orchestration, durable queues, cancellation, resumption, distributed
  workers, or per-role cost accounting from plan 0014.
- A fourth domain, external MCP servers, browser automation, real-user data,
  reward-model training, policy optimization, or Agentic RL.

## Existing Boundaries to Preserve

- `synthesis.candidate_processing` and `synthesis.pipeline` own candidate-time
  review routing. Their `human_review_record_v1` records are for reviewable
  rejected candidates only.
- `synthesis.release_quality` owns sanitized release-audit calculation and the
  human-readable release card. Its `watch` status remains evidence, not a
  release blocker.
- `synthesis.datasets` owns manifest artifact attachment. New artifact keys must
  be attached only after their files were successfully written and validated.
- `synthesis.dataset_release` remains the sole owner of dataset-release
  admission. Review outcomes must not become a hidden release gate.
- Review artifacts must not contain task instructions, trajectory arguments,
  observations, final responses, source payloads, source paths, prompts,
  provider payloads, credentials, headers, local profile paths, or host paths.

## Data Contracts

### Release Review Queue

`release_review_queue.jsonl` contains zero or more `release_review_item_v1`
records. Each item has this shape:

```json
{
  "schema_version": "release_review_item_v1",
  "review_item_id": "review_item:sha256:...",
  "dataset_version": "dataset_mobile_messages_release_candidate",
  "source": {
    "artifact": "release_quality_audit.json",
    "audit_status": "watch"
  },
  "risk": {
    "kind": "small_release_size",
    "level": "watch",
    "reason": "accepted 5 is below small_release_watch_accepted_samples 8",
    "sample_ids": []
  },
  "created_at": "1970-01-01T00:00:00Z"
}
```

`review_item_id` is deterministic: SHA-256 over canonical JSON of
`dataset_version`, source artifact, risk kind, risk level, reason, and sorted
sample ids. It lets a decision reference an item without copying sensitive
sample data. Supported risk kinds are `small_release_size`,
`exact_duplicate_rate`, `task_type_concentration`,
`tool_combination_concentration`, and `duplicate_family`. `sample_ids` may be
present only when already emitted by the existing audit's duplicate-family
record; all other risks use an empty list.

The queue builder must create one item for every audit decision reason named by
`decision.triggered_by`; for `duplicate_family_risk`, it creates one item per
audit `duplicate_family_risks` entry. It creates no queue for audit statuses
`clear`, `blocked`, or `insufficient_evidence`, because those are respectively
not review work, an already-blocked semantic-duplicate condition, or malformed
evidence requiring remediation rather than human content judgment.

### Reviewer Decision Input

`review_decisions.jsonl` is a local, explicit input owned by the reviewer. Each
line uses `review_decision_v1`:

```json
{
  "schema_version": "review_decision_v1",
  "review_item_id": "review_item:sha256:...",
  "outcome": "confirmed_issue",
  "reason_code": "insufficient_diversity",
  "review_minutes": 4,
  "reviewer_alias": "quality_reviewer_1",
  "decided_at": "1970-01-01T00:00:00Z"
}
```

Allowed outcomes are `accepted_risk`, `confirmed_issue`, and
`needs_follow_up`. Allowed reason codes are `sufficient_context`,
`insufficient_diversity`, `near_duplicate_suspected`,
`source_or_verifier_concern`, and `requires_more_data`. `review_minutes` is a
non-negative integer capped at 480. `reviewer_alias` is a non-empty
ASCII-safe opaque identifier; it cannot be a name, email address, path, token,
or free-text note. A decisions file may contain at most one decision for each
review item; unknown item ids, duplicate decisions, malformed records, and
empty files are `insufficient_evidence` rather than exceptions that modify
artifacts.

### Review Resolution Report

`review_resolution_report.json` uses `review_resolution_report_v1`:

```json
{
  "schema_version": "review_resolution_report_v1",
  "dataset_version": "dataset_mobile_messages_release_candidate",
  "inputs": {
    "release_review_queue_path": "release_review_queue.jsonl",
    "review_decisions_path": "review_decisions.jsonl"
  },
  "counts": {
    "queued": 1,
    "resolved": 1,
    "pending": 0,
    "accepted_risk": 0,
    "confirmed_issue": 1,
    "needs_follow_up": 0,
    "review_minutes": 4
  },
  "decision": {
    "status": "reviewed",
    "reasons": ["all queued review items have decisions"],
    "triggered_by": ["review_decisions"]
  }
}
```

Statuses are `reviewed`, `pending_review`, and `insufficient_evidence`.
`reviewed` means every queue item has one valid decision, not that the dataset
is approved or releaseable. `pending_review` means the queue is valid but one
or more items have no decision. `insufficient_evidence` means the queue or
decisions input is absent, unreadable, malformed, references unknown items, or
contains duplicate item decisions. The report contains aggregate counts only;
it does not repeat decision records, aliases, raw samples, or audit content.

## File Map

- Add `synthesis/release_review.py`
  - Own release-review item construction, deterministic ids, decision loading,
    resolution reporting, JSONL writing, and redaction-safe error outcomes.
- Modify `synthesis/contracts.py`
  - Add validators and allowed-value constants for the three review contracts;
    extend manifest artifact-key validation for release review outputs.
- Modify `synthesis/datasets.py`
  - Add narrowly named manifest attachment helpers for
    `release_review_queue` and `review_resolution_report`.
- Modify `main.py`
  - Add opt-in flags, prerequisite validation, queue/report writing, and
    manifest attachment after existing release-audit generation.
- Add `scripts/write_review_resolution.py`
  - Provide a standalone offline consumer so decisions can be resolved without
    rerunning candidate generation or overwriting release artifacts.
- Add `tests/test_release_review.py`
  - Cover queue construction, id stability, redaction, decision validation,
    pending/reviewed/insufficient report status, and three-domain fixtures.
- Modify `tests/test_contracts.py`
  - Add malformed-contract and manifest-artifact-key coverage.
- Modify `tests/test_cli.py`
  - Add release queue and standalone resolution smoke coverage, including flag
    prerequisite failures and no-default-artifact assertions.
- Modify `tests/test_docs_validation.py` only if the docs validator requires a
  new explicit plan/link assertion.
- Modify `README.md`, `docs/BACKEND.md`, `docs/DATA.md`,
  `docs/PRODUCT_SENSE.md`, `docs/ROADMAP.md`, `docs/PLANS.md`,
  `docs/README.md`, and `docs/exec-plans/active/README.md`
  - Document commands, contracts, non-claims, active-plan state, and the
    transition from review routing to a release-review resolution workflow.

## Implementation Tasks

### Task 1: Lock Existing Review and Release Behavior

**Files:**
- Modify: `tests/test_cli.py`
- Modify: `tests/test_release_quality.py`
- Modify: `tests/test_quality_reporting.py`

- [x] Add characterization tests proving the default foundation command writes
  neither `release_review_queue.jsonl` nor `review_resolution_report.json`.
- [x] Add a release-audit fixture assertion that a `watch` audit has not changed
  `dataset_release_report.json` or candidate-time `review_queue.jsonl`.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_cli tests.test_release_quality tests.test_quality_reporting
  ```

  Expected: existing behavior passes before release-review implementation.

### Task 2: Add Release Review Contract Tests

**Files:**
- Modify: `tests/test_contracts.py`
- Add: `tests/test_release_review.py`

- [x] Write failing tests for valid `release_review_item_v1`,
  `review_decision_v1`, and `review_resolution_report_v1` records.
- [x] Add malformed cases for unknown risk kinds, a non-deterministic item id,
  disallowed outcomes/reason codes, a reviewer alias containing `@` or `/`,
  review minutes above 480, unknown decision item ids, and duplicate decisions.
- [x] Add manifest tests accepting `release_review_queue` and
  `review_resolution_report` artifact keys while rejecting absolute or parent
  traversal paths.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_contracts tests.test_release_review
  ```

  Expected: FAIL because the new validators and module do not yet exist.

### Task 3: Implement the Redacted Release Review Queue

**Files:**
- Add: `synthesis/release_review.py`
- Modify: `synthesis/contracts.py`
- Modify: `tests/test_release_review.py`

- [x] Add `build_release_review_items(audit: Mapping[str, Any]) -> list[dict[str, object]]`.
- [x] Canonicalize risk input with `json.dumps(..., ensure_ascii=True,
  sort_keys=True, separators=(",", ":"))`, hash it with SHA-256, and prefix
  the digest with `review_item:sha256:`.
- [x] Build items only for `audit.decision.status == "watch"`; map decision
  triggers to the defined risk kinds and create one `duplicate_family` item per
  audit risk group.
- [x] Reject unrecognized audit trigger values as `insufficient_evidence` when
  building the later report; never silently invent a risk kind.
- [x] Ensure serialized items contain only dataset version, artifact basename,
  audit status, allowed risk data, hashed/id-safe sample references, and the
  fixed deterministic timestamp.
- [x] Add `write_release_review_queue(...) -> Path | None` that validates all
  items, writes JSONL only when items exist, and removes a stale output queue
  when no work exists.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_release_review tests.test_release_quality
  ```

  Expected: PASS, including redaction assertions with injected prompts, source
  paths, and credentials absent from the emitted queue.

### Task 4: Implement Decision Loading and Resolution Reporting

**Files:**
- Modify: `synthesis/release_review.py`
- Modify: `synthesis/contracts.py`
- Modify: `tests/test_release_review.py`

- [x] Add `load_review_decisions(path: Path) -> list[dict[str, object]]` using
  line-by-line JSONL parsing and contract validation.
- [x] Add `build_review_resolution_report(queue_path: Path, decisions_path: Path)
  -> dict[str, object]` that validates item identity, rejects duplicates and
  unknown ids, computes aggregate outcome/minute counts, and writes only
  basenames in `inputs`.
- [x] Make invalid inputs return a validated `insufficient_evidence` report with
  a sanitized exception class/reason code, not raw parser errors or local paths.
- [x] Make a valid incomplete decision file return `pending_review`; make a
  complete valid file return `reviewed`, regardless of whether outcomes contain
  `confirmed_issue` or `needs_follow_up`.
- [x] Add `write_review_resolution_report(...) -> Path` and prove output is
  deterministic for fixed queue and decision fixtures.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_release_review tests.test_contracts
  ```

  Expected: PASS.

### Task 5: Attach Artifacts and Add Offline CLI Surfaces

**Files:**
- Modify: `synthesis/datasets.py`
- Modify: `main.py`
- Add: `scripts/write_review_resolution.py`
- Modify: `tests/test_cli.py`

- [x] Add `attach_release_review_queue_to_manifest(...)` and
  `attach_review_resolution_report_to_manifest(...)`, both delegating to the
  existing relative-artifact attachment helper.
- [x] Add `--write-release-review-queue` to `main.py`; require
  `--write-release-quality-audit`, which already requires
  `--write-dataset-release-report`, held-out evaluation, and profile decisions.
- [x] After `write_release_quality_audit(...)`, write/attach the review queue;
  do not create it for a `clear`, `blocked`, or `insufficient_evidence` audit.
- [x] Add a standalone command:

  ```bash
  uv run python scripts/write_review_resolution.py \
    --output-dir artifacts/mobile-release-candidate \
    --decisions-path artifacts/mobile-release-candidate/review_decisions.jsonl
  ```

  It reads only the local queue and decisions file, writes the resolution
  report, attaches it to the manifest, and never reruns generation, release
  admission, evaluation, or release-pack verification.
- [x] Add CLI tests for missing prerequisites, watch queue creation, clear-audit
  no-op behavior, malformed decisions, pending reports, completed reports, and
  preserved default behavior.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_cli tests.test_release_review tests.test_contracts
  ```

  Expected: PASS.

### Task 6: Prove Three-Domain Evidence and Non-Interference

**Files:**
- Modify: `tests/test_release_review.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_dataset_release.py`

- [x] Run contacts, mobile, and workspace release-candidate fixtures with
  `--write-release-quality-audit --write-release-review-queue`.
- [x] Assert each current small-release `watch` produces a valid queue and that
  queue records contain no raw sample instruction, source path, prompt, or
  credential fixture values.
- [x] Resolve each queue using a valid fixture decision file and assert
  `review_resolution_report_v1.decision.status == "reviewed"`.
- [x] Assert byte-for-byte equality of the pre- and post-resolution
  `dataset_release_report.json` and unchanged admission status. Assert that
  no decision outcome changes samples, rejections, quality reports, profile
  decisions, or release packs.
- [x] Run:

  ```bash
  uv run python -m unittest tests.test_release_review tests.test_cli tests.test_dataset_release
  ```

  Expected: PASS.

### Task 7: Synchronize Documentation and Validate the Repository

**Files:**
- Modify: `README.md`
- Modify: `docs/BACKEND.md`
- Modify: `docs/DATA.md`
- Modify: `docs/PRODUCT_SENSE.md`
- Modify: `docs/ROADMAP.md`
- Modify: `docs/PLANS.md`
- Modify: `docs/README.md`
- Modify: `docs/exec-plans/active/README.md`
- Modify: `AGENTS.md`

- [x] Document the two distinct queues: candidate rejection review routing and
  release-review evidence routing.
- [x] Document all three new schemas, allowed values, artifact names,
  redaction guarantees, CLI commands, and the rule that review outcomes are
  not release-admission decisions.
- [x] Update the product metric wording to distinguish recorded aggregate review
  minutes from any claim of reviewer effectiveness or downstream model gain.
- [x] Update the roadmap to show release-review resolution as the next local
  quality workflow, while retaining semantic duplicate detection and async
  orchestration behind their existing activation triggers.
- [x] Mark every completed checkbox in this plan, move it to
  `docs/exec-plans/completed/`, and update active/completed indexes only after
  all acceptance criteria pass.
- [x] Run:

  ```bash
  uv run python scripts/validate_docs.py
  uv run python -m unittest
  ```

  Expected: documentation validation passes and the complete suite passes.

## Validation Commands

```bash
uv run python scripts/validate_docs.py
uv run python -m unittest
uv run python main.py \
  --run-profile tests/fixtures/run_profiles/mobile-messages-release-candidate.json \
  --write-evaluation-report \
  --write-profile-decision-report \
  --write-dataset-release-report \
  --write-release-quality-audit \
  --write-release-review-queue \
  --output-dir artifacts/mobile-release-review
uv run python scripts/write_review_resolution.py \
  --output-dir artifacts/mobile-release-review \
  --decisions-path artifacts/mobile-release-review/review_decisions.jsonl
```

## Acceptance Criteria

- The default `uv run python main.py` output remains unchanged and writes no
  release-review artifacts.
- Candidate-time `review_queue.jsonl` remains compatible and is not reused as
  a release-review queue.
- A valid `watch` audit produces deterministic, redacted release-review items;
  a `clear`, `blocked`, or `insufficient_evidence` audit produces none.
- Every release-review item and decision is contract-validated, path-safe,
  deterministic where generated, and free of raw sample/source/provider/secret
  content.
- Invalid, duplicate, or unknown review decisions produce a sanitized
  `insufficient_evidence` resolution report without changing existing release
  artifacts.
- Valid incomplete decisions produce `pending_review`; valid complete decisions
  produce `reviewed` and correct aggregate counts/minutes.
- Review outcomes do not change sample admission, quality reports, held-out
  evaluation, profile promotion, dataset release, release-pack verification,
  or semantic/async activation decisions.
- Contacts, mobile, and workspace smoke runs prove queue generation and offline
  resolution.
- Documentation validation and the complete unit suite pass.

## Risks and Mitigations

- **Review artifacts may leak sensitive data.** Construct queue records only
  from sanitized audit values and assert redaction against sentinel secrets in
  tests.
- **A reviewer decision could be mistaken for release approval.** Keep the
  resolution report separate from `dataset_release_report_v1`, use the status
  name `reviewed`, and document that it is evidence only.
- **A decision file can be corrupted or copied between releases.** Validate
  deterministic item ids, reject unknown ids/duplicates, and include dataset
  identity in every item/report.
- **Small fixture audits may create repetitive review work.** Queue generation
  is opt-in and limited to current audit watch signals; it does not add a
  background process, notifications, or automatic retries.
- **This work could be confused with semantic duplicate detection.** Preserve
  the existing TD-0002 trigger; `duplicate_family` review evidence is not an
  embedding-based similarity verdict or an admission gate.
