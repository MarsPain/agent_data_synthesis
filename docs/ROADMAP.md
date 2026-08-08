# Roadmap

This roadmap communicates product and architecture direction. It does not own
task status, dependency edges, assignment, or technical-debt state; those live
in the [configured issue tracker](agents/issue-tracker.md).

## Established Foundation

The repository has a local-first pipeline with a synchronous default and
opt-in durable async execution across contacts, mobile messages, and workspace
tasks. It includes governed sources, executable tools, candidate isolation,
verification and quality gates, bounded concurrency, cooperative cancellation,
runtime episodes, replay, reward labels, held-out evaluation, release
admission, reproducibility packs, representative-run evidence, and downstream
benchmark exchange.

Historical delivery evidence is preserved in the
[completed execution-plan archive](exec-plans/completed/README.md). Current and
target-system details live in [DESIGN.md](DESIGN.md) and the
[deep design index](README.md#deep-design).

## Directional Priorities

1. Improve generation and verification quality using evidence from real
   representative campaigns, beginning with
   [semantic mutation admission](product-specs/semantic-mutation-admission.md)
   and without weakening fail-closed contracts or grounding gates.
2. Use coverage-driven representative evidence to improve domain catalogs and
   generation quality without weakening accepted-only reconciliation or
   bounded-backfill contracts. The framework boundary is defined in the
   [coverage-driven synthesis spec](product-specs/coverage-driven-representative-synthesis.md).
3. Strengthen semantic duplicate measurement after coverage-driven generation
   establishes meaningful structural families and reviewed comparison evidence.
   Desired behavior is in the
   [semantic duplicate detection spec](product-specs/semantic-duplicate-detection.md).
4. Consider external MCP servers, stronger generated-code isolation, distributed
   workers, or separate runtime packaging only after their trust, scale, and
   ownership boundaries are justified by observed needs.

## Interpretation Rules

- A roadmap item is direction, not a scheduled commitment.
- A representative run is evidence, not proof of release readiness or downstream
  model improvement.
- Product behavior changes belong in a spec; durable system design belongs in a
  design doc; qualifying accepted trade-offs may receive an ADR.
- Consult [.scratch/](../.scratch/README.md) for current issue disposition.
