# Async Local Orchestration

- **Status:** Ticketed
- **Canonical spec:** [Async Local Orchestration](../../docs/product-specs/async-local-orchestration.md)
- **Parent issue:** [ISSUE-0001](../ISSUE-0001-async-local-orchestration.md)
- **Current phase:** Resumable deterministic serial tracer bullet

This directory is the feature-level aggregation point for async local
orchestration delivery state. Desired behavior and accepted implementation and
testing decisions live in the canonical spec. Current ticket status,
dependencies, and assignment live only in the ticket files below.

## Tickets

1. [Run and resume a deterministic serial job](issues/01-resumable-deterministic-serial-job.md) — ready for agent
2. [Reject unsafe job resumption](issues/02-reject-unsafe-job-resumption.md) — awaits ticket 01
3. [Resume provider work within cumulative authorization](issues/03-provider-resumption-and-budget.md) — awaits ticket 02
4. [Resume coverage assignments and bounded backfill](issues/04-coverage-resumption-and-backfill.md) — awaits ticket 03
5. [Run bounded work concurrently with stable merge](issues/05-bounded-concurrency-stable-merge.md) — awaits ticket 04
6. [Cancel and resume a live synthesis job](issues/06-cooperative-cancellation-and-resume.md) — awaits ticket 05
7. [Publish sanitized per-role usage evidence](issues/07-sanitized-role-usage.md) — awaits ticket 03
8. [Expose the operator CLI and prove three-domain parity](issues/08-cli-and-three-domain-parity.md) — awaits tickets 06 and 07

## Dependency Shape

```text
01 -> 02 -> 03 -> 04 -> 05 -> 06 --+
                `-> 07 --------------+-> 08
```

Tickets 04 through 06 form the execution branch after provider-safe resumption.
Ticket 07 can proceed independently once provider-attempt evidence exists.
Ticket 08 integrates both branches into the operator-facing workflow.

## Frontier

Ticket 01 is the only current frontier ticket. It establishes a complete,
resumable serial path before provider work, coverage recovery, concurrency, or
cancellation is introduced.
