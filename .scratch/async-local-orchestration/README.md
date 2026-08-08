# Async Local Orchestration

- **Status:** Completed
- **Canonical spec:** [Async Local Orchestration](../../docs/product-specs/async-local-orchestration.md)
- **Parent issue:** [ISSUE-0001](../ISSUE-0001-async-local-orchestration.md)
- **Current phase:** Completed provider-safe resumable bounded local orchestration

This directory is the feature-level aggregation point for async local
orchestration delivery state. Desired behavior and accepted implementation and
testing decisions live in the canonical spec. Current ticket status,
dependencies, and assignment live only in the ticket files below.

## Tickets

1. [Run and resume a deterministic serial job](issues/01-resumable-deterministic-serial-job.md) — completed
2. [Reject unsafe job resumption](issues/02-reject-unsafe-job-resumption.md) — completed
3. [Resume provider work within cumulative authorization](issues/03-provider-resumption-and-budget.md) — completed
4. [Resume coverage assignments and bounded backfill](issues/04-coverage-resumption-and-backfill.md) — completed
5. [Run bounded work concurrently with stable merge](issues/05-bounded-concurrency-stable-merge.md) — completed
6. [Cancel and resume a live synthesis job](issues/06-cooperative-cancellation-and-resume.md) — completed
7. [Publish sanitized per-role usage evidence](issues/07-sanitized-role-usage.md) — completed
8. [Expose the operator CLI and prove three-domain parity](issues/08-cli-and-three-domain-parity.md) — completed

## Dependency Shape

```text
01 -> 02 -> 03 -> 04 -> 05 -> 06 --+
                `-> 07 --------------+-> 08
```

Tickets 04 through 06 form the execution branch after provider-safe resumption.
Ticket 07 can proceed independently once provider-attempt evidence exists.
Ticket 08 integrates both branches into the operator-facing workflow.

## Completion Summary

Tickets 01 through 08 establish a complete, hardened local path with bounded
concurrency, cooperative cancellation, sanitized usage evidence, an explicit
operator CLI, and deterministic parity across the three supported domains.
