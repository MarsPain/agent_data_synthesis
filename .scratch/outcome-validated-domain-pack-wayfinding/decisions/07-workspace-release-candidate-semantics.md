# Align Workspace Release-Candidate Semantics

- **Status:** closed
- **Assignee:** Codex
- **Label:** `wayfinder:grilling`
- **Parent map:** [Outcome-Validated Domain Pack](../README.md)
- **Blocked by:** [Define Release Qualification Levels and Allowed Claims](01-release-qualification-levels.md), [Define Canonical Domain Capability Identity](02-canonical-domain-capability-identity.md), [Design the Domain Pack Interface and Seam](03-domain-pack-interface-seam.md), [Define Domain Pack Versioning and Compatibility](04-domain-pack-versioning-and-compatibility.md)

## Question

How should Workspace coverage assignments, generated task types, recovery
structures, canonical capabilities, held-out evaluation, and release
completeness align so that a coverage-driven LLM release candidate can qualify
without renaming evidence after the run or weakening existing thresholds?

## Resolution comment

A Workspace coverage-driven LLM run may qualify as a Release Candidate only
when one exact Domain plan binds canonical capability references before
generation and those same references survive unchanged through assignment,
task-contract admission, execution, verification, coverage evidence, held-out
evaluation, release completeness, and the qualification decision. A matching
task-type, tool, branch, or report label is never a substitute for that chain.

### Canonical Workspace capabilities

The `workspace_tasks` Domain Pack declares these independently testable
capability identities:

| Capability identity | Semantic outcome |
| --- | --- |
| `workspace_tasks/item_search` | Find and return the intended workspace item under declared selectors and grounding constraints. |
| `workspace_tasks/task_creation` | Create the requested task in the resolved project with requester-controlled fields preserved and final state verified. |
| `workspace_tasks/comment_addition` | Add the requested comment to the resolved task with requester-controlled content preserved and final state verified. |
| `workspace_tasks/item_search_recovery` | Recover from a declared failed or invalid item-search attempt and return the intended grounded item through an admissible fallback. |
| `workspace_tasks/missing_item_safe_failure` | Fail safely and with the expected bounded cause when the requested item does not exist. |

Each identity is accompanied by the capability contract version selected by
the exact Domain Pack version. `item_search_recovery` and
`missing_item_safe_failure` are distinct capabilities because Release Candidate
evidence makes separate claims about their outcomes. A generic runtime feature
such as branching or checkpoint restore is not a Workspace capability.

### Task types and recovery structures

The canonical task types for new Workspace generation are:

- `workspace_item_search`;
- `workspace_task_creation`;
- `workspace_comment_update`.

Task types remain intent archetypes, not capability ids. The Domain Pack
declares their capability requirements explicitly: item search requires
`item_search`; task creation requires `item_search` and `task_creation`; comment
update requires `item_search` and `comment_addition`. A task may additionally
require `item_search_recovery` when its pre-execution coverage assignment
contains a qualifying recovery structure.

Recovery is expressed by the assignment's recovery dimension and exact branch
plan, not by a fourth `workspace_branch_fallback` task type. An attempted branch
does not prove recovery: the declared initial failure, admissible transition,
fallback execution, intended grounded result, and independent verification must
all be present in the accepted sample. Missing-item safe failure is a held-out
evaluation scenario, not a generated task type and not a training sample that
must be accepted.

### Evidence flow and ownership

1. The Domain plan selects exact Workspace capability references, canonical
   task types, required capability floors, coverage catalog/profile, held-out
   suite, mutation contracts, runtime requirements, and release thresholds.
2. The local coverage compiler places the exact references and task type on
   each assignment before provider generation. A provider may propose task
   content but cannot mint, rename, remove, or self-attest capability evidence.
3. Pre-execution membership validation checks that the returned task contract,
   tools, state behavior, grounding, recovery structure, and declared
   capabilities satisfy the assignment. Unknown or mismatched references are
   rejected before execution rather than repaired later.
4. Only an admitted, executed, independently verified accepted sample may
   contribute to the assignment and capability evidence floors. Its task type,
   capability references, coverage-assignment id, plan id, Domain Pack
   reference/hash, runtime identity, and applicable mutation evidence remain
   content-bound.
5. Coverage evidence aggregates by planned cell and canonical capability
   reference while retaining task-type, tool-combination, recovery, structural,
   and grounding slices as separate dimensions. Cell fulfillment alone does
   not establish a capability whose verification conditions did not pass.
6. The held-out suite consumes the same Domain Pack capability catalog and
   records exact references on each task and slice. It uses distinct held-out
   instances and grounding; it cannot invent free-form capability tags.

No consumer may infer a capability from a tool name, task type, coverage cell,
branch-plan presence, or equal string. No post-run projection may rename a
sample or evaluation slice to fill a release deficit.

### Workspace Release Candidate completeness

The first coverage-driven Workspace Release Candidate path uses LLM generation
under an exact coverage-enabled `release_candidate` run profile; the existing
deterministic fixture path remains compatibility evidence rather than the tracer
for this destination. Release completeness requires all of the following:

- the exact Domain plan and its Domain Pack, capability-contract, runtime,
  coverage-catalog/profile, mutation-policy, held-out-suite, and threshold
  identities verify;
- every mandatory coverage floor is fulfilled by accepted samples with valid
  assignment membership, including ordinary item search, task creation,
  comment addition, and at least one independently verified item-search
  recovery path;
- accepted generation evidence satisfies the required capability floors for
  `item_search`, `task_creation`, `comment_addition`, and
  `item_search_recovery`;
- the Workspace held-out suite passes the required floor for all five canonical
  capabilities, including `missing_item_safe_failure`;
- mutation admission is enforced for state-changing samples, and every other
  applicable machine Release Candidate gate remains passing;
- the existing quantitative floors are not weakened: at least five accepted
  samples, rejection rate no greater than `0.2`, and the existing required
  read-only, task-creation, and comment-addition tool-combination coverage;
- release completeness additionally preserves required canonical task-type and
  capability-reference coverage rather than replacing the existing structural
  gates with broader status fields.

A profile purpose of `release_candidate`, an LLM generation mode, a fulfilled
coverage plan, or a passed held-out report alone establishes no qualification.
Any missing, unknown-version, cross-pack, mismatched, legacy-only, or
unverifiable reference yields `insufficient_evidence`; an applicable failed
gate denies qualification.

### Legacy projection mappings

Existing Workspace names remain readable only through versioned,
source-projection-scoped compatibility mappings declared before admission:

| Legacy projection | Canonical interpretation |
| --- | --- |
| fixture task type / held-out tag `workspace_item_lookup` | task type `workspace_item_search`; capability `workspace_tasks/item_search` |
| provider field `workspace_search` | capability `workspace_tasks/item_search` |
| fixture task type `workspace_branch_fallback` | task type `workspace_item_search` plus a separately validated `workspace_tasks/item_search_recovery` requirement |
| held-out tag `workspace_branching` | capability `workspace_tasks/item_search_recovery` only when the held-out recovery contract passes |
| held-out tag/task `workspace_missing_item` | capability `workspace_tasks/missing_item_safe_failure` only when the controlled-failure contract passes |
| task/tag `workspace_task_creation` | task type `workspace_task_creation`; capability `workspace_tasks/task_creation` through the declared projection mapping |
| task/tag `workspace_comment_update` | task type `workspace_comment_update`; capability `workspace_tasks/comment_addition` through the declared projection mapping |

These mappings explain historical artifacts; they do not make legacy evidence
admissible for a current qualification unless the exact compatibility
assessment permits it. New artifacts write canonical capability references and
never emit a legacy alias as capability identity.

The human confirmed on 2026-08-07 that recovery and missing-item safe failure
are independently claimable Workspace capabilities rather than task types or
mere item-search scenarios.
