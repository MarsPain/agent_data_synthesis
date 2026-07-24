# 09 — Produce and Import a Reviewed Calibration Corpus

**What to build:** Give an evaluator a reproducible workflow for exporting a
balanced mutation-admission review packet, freezing a held-out split before
judge tuning, and importing human-reviewed ground truth with reviewer
provenance and contamination checks. This ticket establishes trustworthy
evaluation inputs but does not run or score the remote judge.

**Blocked by:** [04 — Shadow-admit Contact Follow-ups](04-shadow-contact-followups.md), [05 — Shadow-admit Mobile Mutations](05-shadow-mobile-mutations.md), [06 — Shadow-admit Workspace Task Creation](06-shadow-workspace-task-creation.md)

**Status:** blocked

**Assignee:** Unassigned

**Parent spec:** [Semantic Mutation Admission](../../../docs/product-specs/semantic-mutation-admission.md)

## Acceptance criteria

- [ ] The review packet contains at least 200 cases across every current mutation action and all three domains.
- [ ] At least 100 cases are unsupported or adversarial, and at least 60 are assigned to an immutable held-out split before prompt or policy tuning.
- [ ] Coverage includes negation, conditional authorization, missing requester content, parameter smuggling, false provenance, semantic paraphrase, legitimate defaults, deterministic derivations, and prompt injection.
- [ ] Exported cases bind normalized inputs, action policy, evidence references, criticality, and split assignment by version and hash.
- [ ] Human-reviewed labels use a versioned import contract with reviewer provenance and explicit supported, unsupported, or uncertain ground truth.
- [ ] Generated or judge-produced labels cannot be represented as human-reviewed ground truth.
- [ ] Import validation rejects duplicate cases, changed held-out assignments, invalid labels, missing provenance, and post-freeze input changes.
- [ ] Fixture tests demonstrate deterministic export, valid import, and every contamination or integrity failure without remote calls.

## Scope guard

Do not invoke the semantic judge, calculate activation metrics, or claim that
the proposed packet is reviewed until valid human labels are imported.
