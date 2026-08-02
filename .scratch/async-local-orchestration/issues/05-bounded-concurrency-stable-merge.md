# 05 — Run Bounded Work Concurrently With Stable Merge

**What to build:** Allow independent durable work items to execute with an
operator-selected positive concurrency bound while preserving candidate-local
isolation, cumulative provider limits, stable sequence merge, duplicate
admission, coverage reconciliation, and deterministic core artifacts.

**Blocked by:** [04 — Resume Coverage Assignments and Bounded Backfill](04-coverage-resumption-and-backfill.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Async Local Orchestration](../../../docs/product-specs/async-local-orchestration.md)

## Acceptance criteria

- [ ] Async execution defaults to concurrency one and rejects zero, negative,
  non-integer, or implementation-unsafe concurrency values before work begins.
- [ ] A configured bound limits simultaneous work pickup and remote-attempt
  reservation without permitting the cumulative authorization to overshoot.
- [ ] Concurrent work preserves candidate-local environment rebuild,
  checkpoint, tool-registry, adapter, mutation, execution, and verification
  isolation.
- [ ] A deterministic test forces provisional outcomes to finish in reverse
  order and proves that merge still follows stable sequence index.
- [ ] Exact-duplicate admission chooses the same winner as serial execution,
  and review, proposal, episode, rejection, and coverage ordering remain stable.
- [ ] Serial and concurrent fake-provider coverage jobs produce equivalent core
  artifacts for identical inputs; only orchestration timing and usage ordering
  may differ.
- [ ] Interrupted concurrent work resumes without duplicating completed items
  or exceeding the original concurrency and budget bounds.
- [ ] Focused bound, isolation, reverse-completion, duplicate, coverage,
  interruption, and equivalence tests pass without paid calls.

## Scope guard

Do not add multi-process or distributed workers, speculative duplicate work,
automatic concurrency tuning, or an external queue or semaphore service.
