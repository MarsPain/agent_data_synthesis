# Compile Bounded Public Intent Before Mutation and Keep Review Shadowed

## Status

Accepted on 2026-09-06. Supersedes
[ADR 0001: Require Independent Semantic Mutation Admission Before Execution](0001-independent-semantic-mutation-admission.md).

## Decision

A Domain compiles a task only when its requested action, target, arguments,
conditions, and success criteria are supported by the public instruction and
observable tool evidence. Compilation rejects unsupported free-form meaning,
negation, unresolved targets, uncheckable conditions, and private exact
requirements that the requester did not state.

Before a state-changing tool executes, the Domain deterministically verifies
the action and requester-controlled arguments against the compiled public
intent. A task slot, model proposal, expected state, or private oracle does not
authorize a mutation. Where a public request legitimately permits several
outcomes, the Domain uses a reviewed allowed-result set or predicate rather
than inventing a hidden exact result.

The initial core admits demonstrations only after deterministic execution,
authorization, and assessment. Every admission record states that its mode is
deterministic and that it is unreviewed; admission never claims human approval.
Rejections remain in the negative collection.

Post-execution quality judgment is shadow-only when it is introduced. A shadow
verdict may report on a public task and observable Episode but cannot change
collection placement. Optional semantic enforcement is a separate, explicitly
gated capability: it requires frozen, held-out human evidence for the exact
judge, Domains, and task distribution, and an ineligible request fails before
provider work instead of silently falling back to shadow mode.

## Consequences

The first core seam contains no provider judge and makes no calibration or
human-approval claim. It nevertheless establishes the deterministic
authorization prerequisite that later Agent rollout, shadow review, and
optional enforcement work must preserve.

Domains may retain expected source facts privately for assessment, but public
Episode artifacts exclude oracle fields, secrets, unrestricted provider
material, local absolute source paths, and hidden reasoning. A later review
implementation may expose bounded verdicts and evidence references; it cannot
use an unbounded rationale as admission evidence.
