# Define the Workspace Tracer Proof

- **Status:** closed
- **Assignee:** Codex
- **Label:** `wayfinder:grilling`
- **Parent map:** [Outcome-Validated Domain Pack](../README.md)
- **Blocked by:** [Define Release Qualification Levels and Allowed Claims](01-release-qualification-levels.md), [Design the Domain Pack Interface and Seam](03-domain-pack-interface-seam.md), [Define Domain Pack Versioning and Compatibility](04-domain-pack-versioning-and-compatibility.md), [Define Publishability Evidence and Decision Authority](05-publishability-evidence-and-authority.md), [Define Training Recommended Evidence](06-training-recommended-evidence.md), [Align Workspace Release-Candidate Semantics](07-workspace-release-candidate-semantics.md), [Define Contacts and Mobile Compatibility Fixtures](08-contacts-mobile-compatibility-fixtures.md), [Specify the Workspace Training Recommendation Protocol](09-workspace-training-recommendation-protocol.md)

## Question

What exact observable evidence must the Workspace tracer produce to prove the
Domain Pack contract, release qualification model, verified release pack, and
hash-bound downstream benchmark path are coherent enough to hand off as one
implementable specification?

## Resolution comment

Use one end-to-end Workspace tracer as an executable rehearsal of the exact
contracts, hashes, qualification transitions, and fail-closed behavior. The
tracer must obtain a real machine Release Candidate from a real coverage-driven
LLM run and real local Workspace execution. It then uses permanently
non-qualifying fixtures to exercise Publishable and Training Recommended
software paths without pretending that a human approved publication or an
external model was trained.

### Proof boundary and final truth

The tracer proves that the implementation can generate, carry, validate, and
reject the evidence required by the specification. It does not prove general
dataset quality, real publication approval, or downstream model utility.

Its final report must distinguish effective qualification from conformance:

```text
effective_qualification = release_candidate
publishable = false
training_recommended = false
publishable_conformance = passed
training_recommended_conformance = passed
```

No fixture status may flow into `effective_qualification`. If the implementation
cannot represent the two columns separately, the proof fails rather than
flattening them into one `passed` field.

### Real Workspace Release Candidate leg

The positive leg begins with one exact `workspace_tasks` Domain Pack reference,
capability-contract set, admitted synthetic Workspace source, runtime contract,
and coverage-enabled `release_candidate` profile using real LLM generation and
mutation-admission enforce mode.

The observable chain must show:

1. `DomainPack.plan` deterministically binds the five canonical Workspace
   capabilities, canonical task types, coverage catalog/profile and mandatory
   cells, held-out suite, mutation policy, runtime contract, release thresholds,
   and exact pack/component hashes before provider activity.
2. `DomainPack.open` accepts only that plan and the declared Workspace runtime.
   `DomainRun.generate`, `fork`, `attempt`, and `replay` execute behind the pack
   boundary while the shared framework retains source admission, scheduling,
   stable artifact writing, and final qualification.
3. Coverage assignments carry exact capability references before each real LLM
   request. Sanitized provider evidence binds provider/model/config identity,
   assignment id, request hash, response hash, parser/contract version, and
   attempt outcome without storing credentials or unrestricted prompts.
4. Returned tasks pass production parsing and pre-execution membership checks.
   The provider cannot add, remove, rename, or self-attest a capability, tool,
   mutation authorization, coverage cell, or recovery structure.
5. Accepted tasks execute against isolated local Workspace state and retain
   plan id, pack reference/hash, runtime identity, capability references,
   assignment id, task contract, episode, verifier result, mutation evidence,
   and final-state evidence.
6. Coverage evidence proves ordinary item search, task creation, comment
   addition, and at least one validated item-search recovery. Held-out evidence
   separately proves all five canonical capabilities, including missing-item
   safe failure.
7. Existing machine floors remain intact: at least five accepted samples,
   rejection rate no greater than `0.2`, required read-only/task-creation/
   comment-addition tool combinations, required task and capability coverage,
   applicable source/provenance gates, mutation safety, complete run state, and
   every other Release Candidate hard gate.
8. `DomainPack.assess` produces typed domain evidence for the exact plan and
   artifact set. The shared qualification engine—not the pack—establishes
   Release Candidate.

The live LLM call is part of implementation acceptance, not this planning map.
After the accepted run, sanitized real provider responses are frozen as replay
fixtures. Production parsers, membership checks, execution, and verifiers must
produce the same bounded decisions from replay without another provider call.
Hand-authored invalid responses cover rejection paths that a stochastic live
run cannot be expected to generate.

### Required content-addressed artifacts

The exact filenames may follow the repository's established names, but one root
`workspace_tracer_proof_v1` report must hash-bind and classify at least:

- the Domain Pack descriptor/composition, Domain plan, admitted source and
  runtime bindings;
- run profile, coverage plan, assignment/provider-attempt evidence, accepted
  samples, rejections, episodes or equivalent execution evidence, and replay
  results;
- quality report, coverage evidence, mutation-admission report, held-out
  evaluation report, profile-decision report, dataset-release report, and
  release-quality audit;
- manifest, standalone-verifiable dataset release pack, independent pack
  verification result, Domain assessment, and effective qualification report;
- publishability conformance bundle/decision and Training Recommendation
  protocol/evidence/result fixtures, each marked non-qualifying;
- the Contacts/Mobile compatibility-corpus result as an auxiliary prerequisite,
  not as extra Workspace tracer runs; and
- the positive and negative proof-case results described below.

Every reference stores schema/version, relative path, SHA-256 digest, and byte
count. The root report binds the expected Domain Pack, release id, release-pack
hash, evidence class, effective qualification, conformance statuses, and exact
proof-case set. Re-running the offline verifier over unchanged bytes must
produce the same report; no stage may rely on a mutable path, display name,
current registry default, or post-run label inference.

### Publishable conformance leg

Starting from the real verified Release Candidate pack, a fixture-only
publishability bundle exercises publication-governance, review disposition,
risk-acceptance when applicable, approval scope, authority-policy, expiry/
revocation, and cumulative state-transition contracts.

Fixture authority is explicitly test-only and can produce only
`publishable_conformance = passed`. The effective qualification remains Release
Candidate even when every fixture field and test attestation verifies. A wrong
release hash, broader requested scope, missing hard governance result, pending
finding, expired approval, or revoked authority must deny conformance.

### Training Recommended conformance leg

The publishability fixture output feeds a
`evidence_class: conformance_fixture` Workspace training protocol. It binds the
same release-pack hash and supplies content-addressed baseline/treatment
manifests, evaluation manifest, paired binary task results, and external leakage
report under `workspace_training_protocol_v1`.

The implementation must recompute the ten-percent record-count tolerance,
`task_success_rate`, deterministic 10,000-replicate paired bootstrap interval,
and strict `relative_lower_bound > 0.01` result exactly as specified in
[Specify the Workspace Training Recommendation Protocol](09-workspace-training-recommendation-protocol.md).
The numerical positive path produces only
`training_recommended_conformance = passed`; fixture evidence can never make
`training_recommended = true`.

### Mandatory fail-closed proof matrix

The proof is incomplete unless isolated mutations of the positive chain produce
the expected bounded failure without rewriting earlier artifacts:

| Case | Mutation | Required observation |
| --- | --- | --- |
| Plan identity | Change pack, capability-contract, coverage, or runtime hash | planning/opening or assessment rejects the mismatch before it can qualify |
| Provider contract | Return an unknown tool, changed capability ref, missing assignment, or undeclared recovery | rejected before execution with no coverage credit |
| Mutation safety | Omit requester authorization or argument provenance for a state change | mutation admission rejects; no durable change and no accepted sample |
| Execution evidence | Alter final state, verifier result, episode, or replay binding | accepted-sample/assessment evidence becomes invalid |
| Coverage/evaluation | Remove a required capability, recovery result, held-out result, task type, or tool combination | Release Candidate becomes `insufficient_evidence` |
| Run completeness | Cancel, omit an artifact, or leave an applicable gate non-passing | Release Candidate denied without borrowing fixture evidence |
| Artifact integrity | Change one referenced byte, hash, byte count, dataset version, or release id | standalone release-pack verification fails |
| Publishability | Bind fixture approval to another pack, omit governance, exceed scope, expire, or revoke it | publishable conformance denied; effective RC remains |
| Fixture isolation | Relabel fixture authority or experiment evidence as real | qualification engine rejects the evidence-class transition |
| Training arms | Exceed the 10% count tolerance or change a registered model/config/common input | training experiment invalid |
| Evaluation/leakage | Mismatch task ids or split/scoring hashes, selectively omit results, report evaluation use in training, or leave unresolved overlap | training experiment invalid |
| Meaningful gain | Make the reproducible relative 95% lower bound less than or equal to 1% | `no_detected_meaningful_gain`; effective RC remains |
| Cumulative dependency | Invalidate or revoke a lower-level dependency | every dependent effective qualification disappears while history remains |

Each negative case starts from independently copied positive bytes, changes one
declared fact, records the expected reason code, and proves that unrelated
earlier evidence remains byte-identical. A generic exception, parser crash,
silent default, post-hoc repair, or merely different free-form message does not
satisfy the proof.

### Acceptance report

`workspace_tracer_proof_v1.status` is `passed` only when:

- the live LLM Workspace leg establishes a real, independently verifiable
  Release Candidate for one exact artifact identity;
- replay of sanitized provider responses reproduces the declared admission and
  execution decisions;
- publishability and training conformance paths pass while both remain
  non-qualifying;
- every mandatory negative case returns its exact bounded status/reason and no
  unexpected mutation occurs;
- Contacts/Mobile compatibility assertions pass without treating either as a
  second tracer; and
- a clean offline verification starting only from the proof root and referenced
  files reconstructs all hashes, identities, dependencies, effective state, and
  conformance distinctions.

Failure of any proof component yields `failed` or `insufficient_evidence`; the
report never skips a case and never reports partial success as the destination.
This is the observable handoff criterion for an implementable specification.

The human confirmed on 2026-08-08 that the Workspace tracer is an executable
end-to-end rehearsal, that its positive Release Candidate leg uses a real LLM
and real per-sample/local-domain verification, that sanitized real responses are
retained only for deterministic regression, and that fixture-based Publishable
and Training Recommended paths prove software conformance without granting
those real qualifications.
