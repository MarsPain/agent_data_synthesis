# Define Canonical Domain Capability Identity

- **Status:** closed
- **Assignee:** Codex
- **Label:** `wayfinder:grilling`
- **Parent map:** [Outcome-Validated Domain Pack](../README.md)
- **Blocked by:** None

## Question

What is the stable identity of a domain capability, and how does it relate to
task types, tool sequences, coverage cells, structural families, held-out
evaluation capabilities, mutation policies, and release completeness without
collapsing those distinct concepts into aliases?

## Resolution comment

A **Domain capability** is a stable, independently testable semantic outcome or
safety behavior that one Domain Pack can generate evidence for and make claims
about. It is not a task template, tool, action, trajectory shape, coverage
bucket, or report slice.

### Canonical identity

The stable semantic identity is the pair:

```text
(domain_pack_id, capability_key)
```

For human-readable references it may be rendered as
`<domain_pack_id>/<capability_key>`, for example
`workspace_tasks/item_search`. The concrete serialized shape belongs to
[Design the Domain Pack Interface and Seam](03-domain-pack-interface-seam.md).

- `domain_pack_id` identifies the logical semantic pack, independent of its
  execution carrier. The canonical logical ids are `contacts`,
  `mobile_messages`, and `workspace_tasks`; current `*_fixture` values are
  runtime or compatibility identities, not future Domain Pack identities.
- `capability_key` is stable and unique within its Domain Pack. It describes an
  independently claimable outcome or safety behavior rather than its current
  implementation.
- A **Domain capability reference** adds the exact capability contract version
  to that identity. Evidence and release decisions bind the reference, while
  the unversioned identity preserves continuity across compatible contract
  evolution.
- A Domain Pack version selects one closed, internally consistent set of
  capability references and projection mappings. The rules for compatible
  evolution, replacement, and legacy interpretation belong to
  [Define Domain Pack Versioning and Compatibility](04-domain-pack-versioning-and-compatibility.md).

This identity is semantic rather than encoded by the current name. A changed
display name does not create a new capability, while materially changed meaning
must not reuse an old identity. Legacy aliases may be accepted only through an
explicit compatibility mapping; they are never emitted as canonical evidence.

### Relationship to adjacent concepts

| Concept | Relationship to a Domain capability | Invariant |
| --- | --- | --- |
| **Task type** | A domain-owned task/intent archetype explicitly declares one or more required capability references. The relationship is many-to-many. | A task type is not a capability id, even when their labels happen to match. |
| **Tool sequence** | One executable realization that may satisfy capabilities required by a task. Different sequences may realize the same capability, and one sequence may jointly exercise several. | Tool names, action names, order, and side effects cannot mint or rename a capability. |
| **Coverage cell** | A planning unit that explicitly declares which capability references its accepted samples are intended to exercise, alongside task type, tools, grounding, difficulty, ambiguity, state, and recovery dimensions. | Multiple cells may cover one capability; cell fulfillment is not automatically capability qualification. |
| **Structural family** | A post-execution equivalence class over trajectory topology used as diversity evidence. Accepted samples in one family may carry capability references from their validated task contracts. | Family identity is derived evidence and never defines, aliases, or independently proves a capability. |
| **Held-out evaluation** | Each held-out task explicitly targets capability references; reports aggregate outcomes by those references and bind the suite version separately. | Evaluation suites consume the Domain Pack catalog and cannot create free-form capability identities. |
| **Mutation policy** | A versioned safety contract attaches an action realization to every state-changing capability it can exercise. Task types using that capability resolve the same policy through the Domain Pack. | Capability identity does not authorize mutation, and `action_type`, tool name, policy id, and capability id remain distinct. |
| **Release completeness** | A release profile declares required capability references and evidence floors. Accepted, correctly bound and verified samples contribute to those requirements; task-type, tool-sequence, coverage, and structural slices may remain additional diversity or diagnostic gates. | No task or tool label may stand in for missing canonical capability evidence. |
| **Runtime feature** | Rebuild, checkpoint/restore, replay, reward-label, and adapter support describe an execution carrier. | Runtime feature names and Domain capability ids occupy separate namespaces and claim boundaries. |

### Evidence and resolution rules

1. The Domain Pack is the only authority that declares capability identities,
   contract versions, and mappings from task, generation, coverage, evaluation,
   mutation, and release projections.
2. Every evidence-producing projection records explicit capability references.
   Consumers must not infer a reference from equal strings, prefixes, task
   types, tools, coverage cells, structural features, or report keys.
3. An accepted sample demonstrates its declared capabilities only after its
   task contract membership, required realization, execution, grounding,
   mutation admission where applicable, and independent verification pass. A
   generated task, fulfilled cell, observed tool call, or family membership
   alone is insufficient.
4. Unknown, missing, duplicate, cross-pack, unsupported-version, or
   projection-inconsistent capability references fail closed before evidence
   contributes to evaluation, release completeness, or release qualification.
5. Recovery and controlled-failure behavior become separate capabilities only
   when the Domain Pack declares them as independently testable and claimable;
   otherwise they remain coverage or evaluation scenarios for another
   capability. The exact Workspace catalog is decided by
   [Align Workspace Release-Candidate Semantics](07-workspace-release-candidate-semantics.md).
6. A runtime binds its own `runtime_id` and version alongside the Domain Pack
   reference. Changing from a fixture runtime to another compatible runtime
   does not rename the pack or its capabilities, but does require new runtime
   evidence and compatibility validation.

### Current names are migration evidence

The repository currently uses different labels for related projections. For
example, Workspace lookup/search appears as fixture task type
`workspace_item_lookup`, generation and coverage task type
`workspace_item_search`, required capability `workspace_search`, and held-out
tag `workspace_item_lookup`; mutation behavior separately uses task types,
action types, and tool names. Release completeness currently keys task-type and
tool-combination thresholds rather than canonical capabilities.

These names remain facts about existing artifacts, but none is promoted to the
canonical identity by accident. The later Workspace alignment and compatibility
decisions must map them explicitly or reject them.
