# Roadmap

This roadmap communicates product and architecture direction. It does not own
task status, dependency edges, assignment, or technical-debt state; those live
in the [configured issue tracker](agents/issue-tracker.md).

## Established Foundation

The repository has a synchronous, local-first pipeline across contacts, mobile
messages, and workspace tasks. It includes governed sources, executable tools,
candidate isolation, verification and quality gates, runtime episodes, replay,
reward labels, held-out evaluation, release admission, reproducibility packs,
representative-run evidence, and downstream benchmark exchange.

Historical delivery evidence is preserved in the
[completed execution-plan archive](exec-plans/completed/README.md). Current and
target-system details live in [DESIGN.md](DESIGN.md) and the
[deep design index](README.md#deep-design).

## Directional Priorities

1. Improve generation and verification quality using evidence from real
   representative campaigns, beginning with
   [semantic mutation admission](product-specs/semantic-mutation-admission.md)
   and without weakening fail-closed contracts or grounding gates.
2. Add coverage-driven representative synthesis so operators can select a
   small named profile while domain packs declare reachable task space and the
   framework schedules structural coverage deficits. Desired behavior is in the
   [coverage-driven synthesis spec](product-specs/coverage-driven-representative-synthesis.md).
3. Strengthen semantic duplicate measurement after coverage-driven generation
   establishes meaningful structural families and reviewed comparison evidence.
   Desired behavior is in the
   [semantic duplicate detection spec](product-specs/semantic-duplicate-detection.md).
4. Add resumable local orchestration only when run duration, interruption cost,
   or usage attribution makes it worthwhile. Desired behavior is in the
   [async local orchestration spec](product-specs/async-local-orchestration.md).
5. Consider external MCP servers, stronger generated-code isolation, distributed
   workers, or separate runtime packaging only after their trust, scale, and
   ownership boundaries are justified by observed needs.

## Interpretation Rules

- A roadmap item is direction, not a scheduled commitment.
- A representative run is evidence, not proof of release readiness or downstream
  model improvement.
- Product behavior changes belong in a spec; durable system design belongs in a
  design doc; qualifying accepted trade-offs may receive an ADR.
- Consult [.scratch/](../.scratch/README.md) for current issue disposition.
