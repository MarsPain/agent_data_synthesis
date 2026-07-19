# Issue Tracker Configuration

## Configuration

- **Type:** Local Markdown
- **Store:** [`.scratch/`](../../.scratch/)
- **Issue naming:** `ISSUE-NNNN-short-title.md`
- **Index:** [`.scratch/README.md`](../../.scratch/README.md)

The local Markdown tracker is the repository's only source of truth for work
status, dependencies, assignment, discussion, activation triggers, and technical
debt. Product specs own desired behavior and acceptance; design docs own
current or target-system design; ADRs, if introduced later, own qualifying
accepted decisions.

Every implementation issue must link to one parent spec. Completed execution
plans remain historical evidence under `docs/exec-plans/`; their old status and
checklists are archival and must not be used to determine current work state.
