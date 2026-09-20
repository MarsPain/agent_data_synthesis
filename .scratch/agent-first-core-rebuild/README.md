# Agent-First Core Rebuild

- **Status:** Ticketed
- **Label:** `ready-for-agent`
- **Canonical spec:** [Agent-First Core Rebuild](../../docs/product-specs/agent-first-core-rebuild.md)
- **Current phase:** Ticket 06 is completed: the Agent-first core now has
  bounded concurrent run/cancel/resume, durable private accounting, frozen
  snapshots, stable exports, and test-Domain scale evidence. Ticket 07 remains
  ready for implementation.

This feature replaces the legacy core after engineering and independent human
dataset acceptance. Judge enforcement is a separate optional delivery path.
The canonical spec owns behavior and acceptance; this tracker owns delivery
state, dependency edges, assignments, and implementation discussion.

## Test Seams

- The synthesis engine is the principal end-to-end seam.
- Domain adapters share one compliance suite and reviewed structural examples.
- Production and fake model adapters share one provider-neutral JSON seam.
- A production task/verifier change and test-only fourth Domain demonstrate
  change locality through these existing seams.

## Tickets

1. [Prove the Agent-first core seam with a test Domain](issues/01-prove-agent-first-core-seam.md) — completed
2. [Run provider-neutral multi-turn Agent Episodes](issues/02-run-provider-neutral-agent-episodes.md) — blocked by 01
3. [Add Contacts and establish early Agent feasibility](issues/03-add-contacts-domain-adapter.md) — completed; diagnostic live evidence establishes the required behavior examples
4. [Add Mobile Messages and validate the second-Domain seam](issues/04-add-mobile-messages-domain-adapter.md) — completed; twelve-family adapter and locality exercise verified
5. [Add the Workspace Tasks Domain adapter](issues/05-add-workspace-tasks-domain-adapter.md) — completed; nine-family source-derived adapter and frozen replay verified
6. [Resume and scale local synthesis runs](issues/06-resume-and-scale-local-runs.md) — completed
7. [Add shadow quality review and blind-label import](issues/07-add-shadow-quality-review.md) — ready for implementation
8. [Gate optional semantic enforcement on held-out evaluation](issues/08-gate-semantic-enforcement-on-calibration.md) — blocked by 05 and 07; outside the cutover dependency path
9. [Run independent three-domain dataset acceptance](issues/09-run-three-domain-agent-acceptance.md) — blocked by 05, 06, and 07
10. [Cut over and remove the legacy core](issues/10-cut-over-and-remove-legacy-core.md) — blocked by 09

## Dependency Shape

```text
01 -> 02
02 -> 03, 06
03 -> 04, 07
04 -> 05
05, 07 -> 08          (optional enforcement)
05, 06, 07 -> 09 -> 10 (core cutover)
```

Ticket 03 establishes a real Contacts slice before the second production Domain
challenges and stabilizes the interface in Ticket 04. Ticket 05 then proves that
the interface holds for Workspace. Ticket 06 can proceed independently after
02; Ticket 07 follows the first real Domain.

Ticket 07 owns basic human-label import so Ticket 09 never depends on optional
enforcement. Ticket 08 can be delivered and evaluated independently. Its code
acceptance uses deterministic fixtures; any real activation evidence or
remaining implementation stays tracked there even if Ticket 10 completes first.
An unavailable or unqualified judge is not an unfinished core-cutover gate.

Ticket 03's separately authorized feasibility pilot has yielded its required
live behavior evidence; Ticket 09 remains a separate, explicitly authorized
acceptance campaign. No ticket itself authorizes provider calls or automatic
reruns.

## Delivery Evidence

Keep implementation discussion in the owning ticket: early feasibility in 03,
interface revisions and the production change-locality diff in 04, recovery and
engine-capacity measurements in 06, optional activation in 08, and independent
dataset acceptance in 09. Runtime outputs belong under `artifacts/`; generated
documentation reports belong under `docs/generated/`. Link evidence rather
than creating a new execution-plan lifecycle.
