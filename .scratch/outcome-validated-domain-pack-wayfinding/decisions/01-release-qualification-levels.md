# Define Release Qualification Levels and Allowed Claims

- **Status:** closed
- **Assignee:** Codex
- **Label:** `wayfinder:grilling`
- **Parent map:** [Outcome-Validated Domain Pack](../README.md)
- **Blocked by:** None

## Question

What are the canonical release qualification levels, what evidence moves an
artifact set into each level, which claims does each level permit, and which
states or transitions must fail closed?

## Resolution comment

The canonical qualifications are **Release Candidate**, **Publishable**, and
**Training Recommended**, in that order. They are cumulative claim envelopes
over one exact artifact identity, not aliases for individual pipeline statuses.
`Unqualified` is the fail-closed absence of a qualification, not a fourth
level.

Releaseability and downstream utility remain separate evidence boundaries:
Training Recommended adds a scoped utility claim to a Publishable release; it
does not make release admission stronger, and downstream evidence can never
repair missing publishability evidence.

### Qualification contract

| Level | Minimum evidence boundary | Allowed claim | Claims not allowed |
| --- | --- | --- | --- |
| **Release Candidate** | One exact artifact set is bound to its applicable dataset, Domain Pack, capability, contract, and profile identities; the run is complete and intended for release evaluation; contract, execution, verification, grounding, quality, provenance, source-governance, mutation-safety, coverage, held-out evaluation, profile-promotion, release-completeness, and dataset-release gates that apply to that run have machine-verifiable passing evidence. A valid release-quality audit must expose any remaining review risks. | “This exact artifact set passed the declared machine release gates and is eligible for human publication review.” It may be packaged and reviewed. | Publication approval, unrestricted safety or fitness, downstream gain, causal benefit, or a recommendation to train. A `release_candidate` profile purpose by itself establishes no qualification. |
| **Publishable** | Release Candidate evidence remains valid; the exact hash-bound release pack verifies independently; governance and declared distribution constraints are complete; audit risks are either absent or explicitly dispositioned; and an authorized human approval or bounded risk-acceptance record binds the immutable release identity and evidence. Review completion alone is not approval. | “This exact release pack is approved for distribution or use within the declared licence, audience, purpose, and risk constraints.” It may be exchanged with an external benchmark or training system under those constraints. | Training effectiveness, model improvement, causality, generalization, universal fitness, or approval of a changed/repacked artifact. |
| **Training Recommended** | Publishable evidence remains valid; a predeclared, leakage-controlled downstream protocol compares a baseline that does not consume the release with a treatment that consumes exactly the approved release; training, model, benchmark, seed/sample, and artifact identities are bound; the sample-count tolerance and minimum meaningful gain pass; any optional protocol-declared model-level guardrail passes; and the normalized result verifies against the release-pack hash. | “This exact release is recommended for the named training treatment, model/training-system identity, benchmark suite, and protocol because the predeclared criteria were met.” | General causal claims, universal or cross-model benefit, best-dataset claims, recommendation for other artifact versions or recipes, or automatic dataset/model promotion. The current point-estimate status `improved` is supporting evidence only and is not sufficient by itself. |

The exact canonical identity fields are owned by
[Define Canonical Domain Capability Identity](02-canonical-domain-capability-identity.md);
the exact publishability evidence and authority record by
[Define Publishability Evidence and Decision Authority](05-publishability-evidence-and-authority.md);
the experimental thresholds and validity contract by
[Define Training Recommended Evidence](06-training-recommended-evidence.md);
and the mapping from current Workspace artifacts by
[Align Workspace Release-Candidate Semantics](07-workspace-release-candidate-semantics.md).

### State and transition rules

1. The only forward path is `Unqualified -> Release Candidate -> Publishable ->
   Training Recommended`; transitions cannot skip a level or borrow evidence
   from another release identity.
2. Missing, unreadable, malformed, unknown-version, stale, revoked, or
   identity/hash/domain/capability/contract-mismatched evidence yields
   `insufficient_evidence` for the attempted qualification and denies the
   transition.
3. An applicable hard gate that is `failed`, `blocked`, `ineligible`,
   incomplete, cancelled, unsupported, uncertain, or otherwise non-passing
   denies the transition. Human approval and accepted risk cannot waive source
   governance, mutation safety, artifact integrity, identity binding, or other
   hard machine-admission gates.
4. Audit `watch`, pending review, confirmed issues, or follow-up needs cannot be
   treated as approval. A bounded accepted-risk disposition counts only when
   the later authority contract permits it and binds its scope and release
   identity explicitly.
5. `no_detected_improvement`, experimental invalidity, leakage, missing
   pre-registration, or failure of an optional protocol-declared non-regression
   gate denies Training Recommended without changing an otherwise valid
   Publishable qualification.
6. A failed higher-level attempt does not erase a still-valid lower level.
   Conversely, revocation or invalidation of lower-level evidence invalidates
   every dependent higher level. History remains append-only while the current
   effective qualification falls to the highest level still fully provable.
7. Any byte-changing artifact mutation or identity-changing repack is a new
   qualification subject; prior approval and downstream evidence do not carry
   over implicitly.
8. Qualification never mutates release admission, review evidence, tracker
   state, training state, or model-promotion state automatically.

This choice rejects both a binary released/not-released flag, which collapses
authority and utility, and three independent badges, which permit contradictory
claims. The cumulative model keeps the user-facing claim order simple while
preserving independent evidence at each boundary.
