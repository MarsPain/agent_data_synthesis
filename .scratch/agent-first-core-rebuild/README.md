# Agent-First Core Rebuild

- **Status:** Ticketed
- **Label:** `ready-for-agent`
- **Canonical spec:** [Agent-First Core Rebuild](../../docs/product-specs/agent-first-core-rebuild.md)
- **Current phase:** Ticket 10's Agent-first implementation cutover is complete
  under the operator's explicit prerequisite exception. Ticket 09's AI
  diagnostic review found 106 pass, 13 fail, and 1 uncertain; independent
  direct-human labels remain absent and formal dataset acceptance is still
  incomplete. Optional judge activation remains independent of core cutover.

The original spec required engineering and independent human dataset acceptance
before replacing the legacy core. Engineering passed; the operator directed
the implementation cutover under an explicit exception to the incomplete
human gate. Judge enforcement remains a separate optional delivery path.
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
7. [Add shadow quality review and blind-label import](issues/07-add-shadow-quality-review.md) — completed
8. [Gate optional semantic enforcement on held-out evaluation](issues/08-gate-semantic-enforcement-on-calibration.md) — completed; optional and outside the cutover dependency path
9. [Run independent three-domain dataset acceptance](issues/09-run-three-domain-agent-acceptance.md) — in progress; live cohort frozen, direct-human review pending
10. [Cut over and remove the legacy core](issues/10-cut-over-and-remove-legacy-core.md) — implementation completed under an explicit prerequisite exception; formal dataset acceptance remains incomplete

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
