# Async Local Orchestration

## Desired Behavior

Provide an opt-in local runner for long synthesis campaigns that can persist
candidate work, resume after interruption, bound concurrency, cancel safely, and
attribute remote-provider usage by role. The existing synchronous command
remains the default.

## Constraints

- Reuse the existing candidate-processing, source-governance, sandbox, role,
  verification, and dataset-writing boundaries.
- Use repository-local durable state; do not require an external broker,
  distributed worker system, service API, or dashboard.
- Preserve deterministic merge order and artifact contracts.
- Never persist credentials, headers, raw prompts, or private source payloads.

## Accepted Implementation and Testing Decisions

- Model one job as durable candidate work items with explicit terminal states.
- Treat interrupted in-progress items as resumable rather than complete.
- Keep concurrency bounded and expose the async path only through an explicit
  CLI or programmatic opt-in.
- Verify deterministic fixture equivalence with the synchronous path, queue
  recovery after interruption, cancellation behavior, invalid transition
  rejection, and metadata redaction.

## Acceptance

- Completed items are not duplicated after resumption.
- Partial artifacts remain internally valid after cancellation or failure.
- Identical deterministic inputs yield the same admitted samples and rejections
  as the synchronous path.
- Per-role usage summaries contain only sanitized identifiers and counts.
- Default `uv run python main.py` behavior is unchanged.

Current scheduling and activation state live only in
[ISSUE-0001](../../.scratch/ISSUE-0001-async-local-orchestration.md). The
[legacy Plan 0014](../exec-plans/deferred/0014-async-local-orchestration-with-durable-queues.md)
is preserved as historical design and delivery detail.
