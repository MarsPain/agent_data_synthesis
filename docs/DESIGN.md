# Agent-first Core Design

## Run contract

A validated `RunConfiguration` selects one registered Domain adapter and one
strict-JSON model adapter. It fixes slot, accepted-target, concurrency, step,
role-request, retry, timeout, response-size, and output-token bounds before
work starts. Domain adapters compile untrusted proposals into public tasks and
private cases; the generic engine does not parse Domain sources or oracle data.

Each Agent Episode starts from isolated normalized Domain state. The Agent sees
only the public task, tool schemas, and observable trajectory. A state-changing
tool must be authorized by the public instruction and pass Domain checks.
Deterministic assessment decides whether the Episode enters demonstrations or
negatives. A shadow quality judgment cannot alter that placement.

## Durable execution

The run directory has a process-lifetime writer lock and private SQLite ledger.
The ledger records allocated slots, work ownership, charged physical requests,
private cases, and terminal outcomes. Resume uses the persisted frozen state,
not the current source path; terminal Episodes are not repeated. Request ceilings
remain durable across interruptions and retries. Cooperative cancellation leaves
inspectable partial evidence.

Public output contains sanitized demonstrations, negatives, provider usage,
quality report, run report, and flat manifest. Replay reconstructs Episodes
from frozen input and compares observation and assessment evidence without
calling a provider. Old-format artifacts have no reader in this core.

## Approval boundaries

Deterministic admission, shadow judgment, direct-human review, and optional
semantic enforcement are separate decisions. Unreviewed demonstrations remain
unapproved. Human labels bind a frozen blind cohort and five dimensions.
Enforcement requires an eligible frozen judge policy; the default remains shadow.

The operator directed the cutover implementation to proceed despite incomplete
formal three-Domain dataset acceptance. That exception changes work sequencing,
not the cohort verdicts, approval semantics, or label provenance. Current state
is recorded in the [local tracker](../.scratch/agent-first-core-rebuild/README.md).
