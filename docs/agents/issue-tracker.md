# Issue Tracker Configuration

## Configuration

- **Type:** Local Markdown
- **Store:** [`.scratch/`](../../.scratch/)
- **Legacy issue naming:** `ISSUE-NNNN-short-title.md`
- **Feature grouping:** `<feature>/README.md`
- **Feature ticket naming:** `<feature>/issues/NN-short-title.md`
- **Wayfinder grouping:** `<feature>-wayfinding/README.md`
- **Wayfinder decision naming:** `<feature>-wayfinding/decisions/NN-short-title.md`
- **Index:** [`.scratch/README.md`](../../.scratch/README.md)

The local Markdown tracker is the repository's only source of truth for work
status, dependencies, assignment, discussion, activation triggers, and technical
debt. Product specs own desired behavior and acceptance; design docs own
current or target-system design; ADRs, if introduced later, own qualifying
accepted decisions.

Every implementation issue must link to one parent spec. Completed execution
plans remain historical evidence under `docs/exec-plans/`; their old status and
checklists are archival and must not be used to determine current work state.

## Feature Ticket Contract

Use a feature directory when one specification requires multiple implementation
tickets. Its `README.md` is the aggregation point for feature status, the
canonical spec, the governing ADR when one exists, ticket order, and dependency
shape. It does not duplicate product requirements.

Each file under `issues/` must contain:

- a two-digit ordered title;
- `What to build`, `Blocked by`, `Status`, `Assignee`, and `Parent spec` fields;
- the exact initial status `ready-for-agent`;
- one link to the canonical parent product spec;
- externally observable acceptance criteria; and
- a scope guard when adjacent work could expand the ticket materially.

The root tracker index links feature directories, while the feature index links
each ticket. Ticket dependencies link the blocking ticket rather than copying
its requirements. Blocking ticket links must remain inside the same feature and
point to lower-numbered tickets so the numbered order is a valid dependency
order. Specifications are completed through the specification workflow, feature
tickets are produced from that specification, and only ticket files are handed
to implementation agents.

After publication, status may advance through `in-progress`, `blocked`, and
`completed`. The feature and root indexes must reflect material state changes.

## Wayfinding Operations

Wayfinder maps use the existing local Markdown store but are decision work,
not implementation features. A map lives at
`.scratch/<feature>-wayfinding/README.md`, and its child decision tickets live
under `.scratch/<feature>-wayfinding/decisions/`. The `-wayfinding` suffix and
`decisions/` child directory are mandatory so that the unsuffixed
`.scratch/<feature>/issues/` path remains unambiguously reserved for
implementation tickets produced from a specification. The canonical issue
identity is the repository-relative Markdown path.

The map file carries `Status`, `Label: wayfinder:map`, and `Assignee` fields,
then the required `Destination`, `Notes`, `Decisions so far`, `Not yet
specified`, and `Out of scope` sections. Open child decisions are discovered
from the files under `decisions/`; they are not duplicated in the map body.

Each child decision ticket contains:

- `Status`, initially `open`;
- `Assignee`, initially `Unassigned`;
- one `wayfinder:<type>` label;
- a `Parent map` link;
- `Blocked by`, using links to child decisions in the same map or `None`; and
- one `Question` section.

Claim a decision before working it by replacing `Assignee: Unassigned` with the
driver's stable local name. The frontier is the set of open, unassigned child
decisions whose `Blocked by` entries are all closed. Because the local tracker has
no native dependency object, `Blocked by` is the authoritative fallback
relationship. A resolution appends a `Resolution comment`, changes the child
status to `closed`, and adds one linked gist to the map's `Decisions so far`.
Newly visible decisions are created before their blocking links are added.
