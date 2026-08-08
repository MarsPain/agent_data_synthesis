# Outcome-Validated Domain Pack Deep Design

## Purpose and Ownership

This document defines the target mechanics for the
[Outcome-Validated Domain Pack product specification](../product-specs/outcome-validated-domain-pack.md).
It owns the deep interface, identity and version bindings, evidence flow,
compatibility projections, qualification state mechanics, failure boundaries,
and Workspace tracer topology. Product acceptance remains in the product spec;
durable rationale remains in [ADR 0002](../adr/0002-domain-pack-semantic-authority-and-deep-interface.md)
and [ADR 0003](../adr/0003-separate-evidence-verification-from-external-authority.md);
live work state remains in the
[local feature tracker](../../.scratch/outcome-validated-domain-pack/README.md).

The resolved [Wayfinder map](../../.scratch/outcome-validated-domain-pack-wayfinding/README.md)
is historical decision provenance. This design is authoritative for the target
system.

## Current-to-Target Boundary

The current domain boundary is a bundle that exposes an environment, tool
registry, verifier, candidate generator, policy generator, registry builder,
generation specification, candidate preparer, mutation policies, mutation
judge, and optional adapter. Shared callers can therefore observe and coordinate
the very fan-out that domain ownership is meant to hide. Current domain ids also
mix logical semantics with fixture runtime names, and downstream artifacts rely
on task, tool, coverage, or report labels that are not canonical capability
references.

The target replaces that shallow aggregate at public consumer seams with two
objects:

```text
DomainPack.plan(intent, admitted_source) -> DomainPlan | PlanFailure
DomainPack.open(plan, runtime_scope) -> DomainRun | OpenFailure
DomainPack.assess(plan, exact_evidence) -> DomainAssessment

DomainRun.generate(request, provider_adapter?) -> GenerationResult
DomainRun.fork(candidate_scope) -> CandidateRun
CandidateRun.attempt(candidate, options) -> AttemptResult
DomainRun.replay(episode) -> ReplayResult
```

The existing environment, registry, verifier, preparer, mutation, and runtime
components may remain internally different across domains. They are composed
behind `DomainPack` and `DomainRun`, not standardized as additional public
interfaces.

## Authority Boundaries

### Domain Pack authority

A Domain Pack is the sole authority for:

- logical Domain Pack identity and composition;
- Domain capability identities and contract versions;
- task-type-to-capability projections;
- generation and provider-response membership semantics;
- coverage catalogs, profiles, assignments, and capability projections;
- held-out task and capability projections;
- mutation action realizations and policy selection;
- runtime contract requirements;
- domain release-completeness requirements;
- compatibility mappings and domain-level compatibility interpretation; and
- typed interpretation of exact domain evidence.

### Shared framework authority

The shared framework retains:

- run-profile intake and synthesis intent;
- source governance and admission;
- credentials and provider selection;
- scheduling, concurrency, cancellation, stable merge, and durable orchestration;
- output-directory ownership and atomic artifact writing;
- generic schema and content-address verification;
- cumulative Release qualification;
- authority-policy and attestation verification;
- tracker, publication, training, and model-promotion side effects, all of which
  remain absent from qualification evaluation.

### External authority

Authenticated risk owners and publication approvers own human distribution
authority. An external experiment owner owns downstream protocol choices,
training, evaluation access, and supplied execution evidence. The framework
verifies bounded evidence; it does not impersonate either authority.

## Identity Model

### Domain Pack reference

An exact Domain Pack reference contains:

```text
domain_pack_id
pack_version
pack_hash
```

`domain_pack_id` is the stable logical semantic authority. The initial ids are
`contacts`, `mobile_messages`, and `workspace_tasks`. `pack_version` is an
immutable monotonic composition label; it does not imply semantic-version
arithmetic. `pack_hash` is the SHA-256 digest of the canonical descriptor bytes.
A registry entry whose bytes do not match the declared version and hash is
invalid.

The canonical descriptor selects exact references for:

- capability contracts;
- task taxonomy and projection map;
- generation contract;
- coverage catalog and supported profiles;
- held-out suite and thresholds;
- mutation policy;
- runtime contract;
- release-completeness contract;
- compatibility mapping set; and
- every schema whose validation semantics affect the pack.

Any change capable of changing a plan, Domain run result, assessment, or current
evidence admissibility requires a new descriptor and pack version. A component
bug fix that changes observable output also changes the component version and
pack version. A proven behavior-preserving refactor does not.

### Domain capability reference

The stable capability identity is:

```text
(domain_pack_id, capability_key)
```

An exact evidence reference adds `capability_contract_version`. A materially
different claim receives a new key; changed proof rules for a continuous claim
receive a new contract version. Display-name changes do neither.

The initial catalogs are:

| Domain Pack | Capability keys |
| --- | --- |
| `workspace_tasks` | `item_search`, `task_creation`, `comment_addition`, `item_search_recovery`, `missing_item_safe_failure` |
| `contacts` | `contact_lookup`, `followup_recording`, `contact_lookup_recovery`, `missing_contact_safe_failure` |
| `mobile_messages` | `message_search`, `reminder_creation`, `draft_reply`, `message_search_recovery`, `missing_message_safe_failure` |

Capability references are never inferred from task types, tool names, action
types, coverage cells, structural families, held-out tags, report keys, or
runtime features. Each projection declares them explicitly.

### Runtime reference

A runtime reference contains its own runtime id, version, contract version, and
implementation hash. Fixture-named ids such as `workspace_tasks_fixture` remain
valid runtime identities. They never become logical Domain Pack ids merely by
suffix removal.

## Domain Plan

Planning is pure. It receives an already validated synthesis intent and
sanitized facts from an admitted source. It performs no provider call, runtime
construction, file mutation, or external lookup.

A Domain plan contains at least:

- schema version, plan id, and canonical plan hash;
- exact Domain Pack reference and descriptor hash;
- admitted source identity, policy result, and source content hash;
- exact runtime contract requirement;
- canonical task types and their capability requirements;
- capability references and required evidence floors;
- coverage catalog/profile, compiled coverage plan, and assignment policy;
- generation, parser, grounding, expected-state, and membership contracts;
- held-out suite, tasks, capability projections, and thresholds;
- mutation policy and required admission mode;
- release-completeness thresholds and applicable machine gates;
- compatibility mapping reference when an input used legacy projections; and
- canonical hashes for every selected component.

`plan_id` is derived from canonical plan content rather than a path, timestamp,
or registry order. The exported record is safe to compare and hash and contains
no credentials, raw unrestricted prompts, or source payload beyond the existing
sanitized policy boundary.

Planning returns a bounded failure when a reference is missing, duplicated,
unknown, cross-pack, incompatible, internally inconsistent, or unverifiable.
Stated but unreachable coverage, an unsupported runtime contract, an ambiguous
legacy mapping, or a release profile whose mutation mode cannot qualify also
fails here when statically knowable.

## Domain Run

`open` verifies the complete plan hash, Domain Pack reference, runtime contract,
admitted-source binding, and runtime scope before creating domain state. The
operation rejects mutable registry defaults or a runtime that merely shares a
display name.

A Domain run is scoped to one plan and runtime. It provides:

- `generate`, which turns one framework-owned request and optional provider
  adapter into a candidate result under the plan's domain contracts;
- `fork`, which creates candidate-scoped isolated execution state without
  exposing the underlying runtime session;
- `attempt`, on the candidate run returned by `fork`, which prepares, admits,
  executes, verifies, and records one candidate attempt; and
- `replay`, which verifies and replays an episode against the same pack and
  runtime contracts.

Generation receives a locally created coverage assignment. Provider output may
propose task instruction, declared policy, and expected outcome only within the
assignment schema. The provider cannot set pack, plan, assignment, cell,
capability, lineage, fulfillment, qualification, or authority fields.

Before an attempt, membership validation proves that task type, declared tools,
state behavior, grounding, expected state, recovery structure, and exact
capability references satisfy the assignment and Domain plan. Invalid output is
a classified rejection and is not reassigned to another cell.

Each candidate fork starts from the correct isolated environment state.
State-changing candidates cross enforced semantic mutation admission before the
first tool call. Attempt results bind the candidate, plan, Domain Pack, runtime,
assignment, capability references, task contract, episode, verifier result,
mutation evidence, and final-state evidence. Only an accepted result can
contribute to coverage or capability floors.

Replay verifies episode identity and evidence bindings before reconstructing
the execution. A changed pack, runtime, capability contract, source state,
episode byte, or verifier contract yields a bounded mismatch rather than a
best-effort replay.

## Domain Assessment

Assessment consumes one exact Domain plan plus content-addressed evidence. It
validates domain-owned requirements and returns either established domain
evidence or a bounded insufficiency/failure. It does not return Publishable or
Training Recommended and cannot grant Release Candidate by itself.

The Workspace assessment checks:

- canonical reference continuity from plan and assignment through accepted
  samples, coverage, held-out evaluation, and release completeness;
- accepted evidence for item search, task creation, comment addition, and at
  least one independently verified item-search recovery;
- held-out evidence for all five Workspace capabilities, including safe failure;
- enforced mutation admission for state-changing samples;
- minimum five accepted samples and rejection rate no greater than 0.2;
- required read-only, task-creation, and comment-addition tool combinations;
- all applicable source, provenance, execution, grounding, quality,
  completeness, and release gates; and
- exact Domain Pack, runtime, component, profile, catalog, suite, policy, and
  artifact identities.

The assessment records the exact missing or mismatched fact. It never repairs a
deficit by translating a task type, tool trace, branch flag, coverage status, or
held-out tag after the run.

## Workspace Semantic Projections

New generated task types and capability requirements are:

| Task type | Required capabilities |
| --- | --- |
| `workspace_item_search` | `item_search` |
| `workspace_task_creation` | `item_search`, `task_creation` |
| `workspace_comment_update` | `item_search`, `comment_addition` |

An assignment may additionally require `item_search_recovery`. The accepted
trajectory must contain the declared initial failure, admissible transition,
fallback execution, intended grounded result, and independent verification.
Branch-plan presence is not evidence.

`missing_item_safe_failure` is a held-out scenario. It passes only when the item
is absent, the attempt ends with the expected bounded cause, and no unintended
state change occurs. It is neither a generated task type nor an accepted-sample
floor.

The held-out suite consumes capability references from the same pack descriptor
as generation and coverage. It cannot invent tags. Capability outcome counts
remain distinct from task-type, cell, tool-combination, structural, and
grounding slices.

## Compatibility Architecture

### Compatibility assessment

One assessment contains four independent axes:

| Axis | Meaning |
| --- | --- |
| Readability | The declared original reader parses and validates the artifact under its original schema and preserves its bytes and relationships. |
| Runnability | A versioned adapter compiles the input into a valid current Domain plan without guessing or dropping a requirement. |
| Semantic equivalence | The selected projection is lossless for the relevant domain meaning. |
| Evidence admissibility | The source already contains all exact facts required by the requested current claim. |

Each axis has a bounded status and reason. A consumer requests the axes it
needs; unknown on any required axis fails closed. Readability can pass while
all stronger axes fail.

### Mapping key and migration lineage

A compatibility mapping is keyed by:

```text
source_schema_version
projection_kind
legacy_value
target_reference
mapping_version
mapping_hash
```

The projection kind prevents a runtime field named `contacts_fixture`, a
semantic-domain field with the same value, a task label, and a tool label from
sharing an accidental alias rule.

A migrated record retains:

- original relative path, bytes hash, byte count, schema, and reference;
- selected mapping version and hash;
- exact target reference and derivation reason;
- original profile and artifact hashes; and
- new canonical artifact identity and hash.

Original files are never rewritten. Canonical semantic fields emit only exact
Domain Pack and capability references. Namespaced lineage may retain legacy
values. Runtime fields may retain exact legacy-named runtime ids.

### Compatibility corpus

The initial compatibility corpus freezes:

- the 26 selected checked-in Contacts and Mobile profiles at a declared cutoff;
- one reviewed synthetic valid version-3 bridge profile per domain;
- one complete historical version-1 artifact chain per domain;
- one complete mutation-aware version-2 artifact chain per domain;
- every referenced sample, rejection, coverage, evaluation, release, audit, and
  review dependency needed to verify those chains; and
- independently reviewed canonical expected projections and four-axis outcomes.

The top-level corpus manifest binds every byte. Legacy inputs and expected
outputs are not generated by the current reader, adapter, or writer under test.
All four golden chains reproduce only their original decisions and are
`historical_only` / `insufficient_evidence` for current qualifications because
they lack exact current pack and capability references.

## Qualification State Machine

The effective state is derived, never manually promoted:

```text
Unqualified -> Release Candidate -> Publishable -> Training Recommended
```

The evidence for each level is cumulative and bound to one exact artifact
subject. Evaluation proceeds from the bottom each time. A higher-level failure
does not invalidate a still-valid lower level, but invalidating a lower
dependency removes every dependent current state. History is append-only.

Common failure rules are:

- missing, unreadable, malformed, unknown-version, stale, expired, revoked, or
  identity/hash/contract-mismatched evidence becomes `insufficient_evidence`;
- an applicable failed, blocked, ineligible, incomplete, cancelled,
  unsupported, uncertain, or otherwise non-passing hard gate denies the
  transition;
- evidence from another release subject or evidence class is never borrowed;
- a changed artifact byte, pack, limitation, finding set, or scope creates a new
  subject; and
- evaluators are pure: they do not publish, train, mutate review records,
  promote models, or change tracker state.

### Release Candidate

Release Candidate requires a complete run intended for release evaluation,
exact pack/runtime/capability/component/profile bindings, independently
verified accepted samples, and passing applicable contract, execution,
verification, grounding, quality, provenance, source, mutation, coverage,
held-out, profile-promotion, release-completeness, dataset-release, and artifact
integrity gates. A valid release-quality audit must expose remaining review
risks.

The permitted claim is that the exact artifact set passed declared machine
release gates and is eligible for human publication review. It is not
publication approval or evidence of training benefit.

### Publishable

The publishability evidence bundle content-binds:

- the still-valid Release Candidate decision and exact verified release pack;
- publication-governance results for license, export, retention, privacy,
  consent, sensitive material, secrets, access, redistribution, limitations,
  and proposed scope;
- the release-quality audit, exact review queue, and review resolution;
- risk-acceptance attestations when needed;
- the publication-approval attestation;
- the authority policy and trust root; and
- current expiry and revocation evidence.

Integrity, source and publication governance, sensitive-material controls,
mutation safety, and authority validity are hard gates. Risk acceptance cannot
waive them. `clear` audit means no configured finding needs disposition; it is
not approval. A `watch` audit proceeds only when every finding is cleared as
inapplicable with evidence or covered by a valid risk record. Blocked,
insufficient, pending, confirmed-issue, or follow-up-needed evidence denies the
transition.

Risk acceptance and publication approval are separate canonical attestations.
Verification covers signature or equivalent attestation, principal/key, role,
authority-policy reference, decision time, validity, revocation, exact release
and bundle hashes, scope, and limitations. Risk records additionally bind exact
findings, severity, bounded reason, compensating controls, scope, and mandatory
expiry. External/public distribution with residual risk requires distinct risk
and publication principals; bounded internal use may combine roles only when
policy explicitly permits it.

The requested use must be equal to or a machine-verifiable subset of the
approved distribution scope. The pure decision returns `passed`, `denied`, or
`insufficient_evidence`.

### Training Recommended

Training Recommended requires a still-valid Publishable release and one exact
pre-registered external experiment. The external owner supplies ordinary
content-addressed files for the registered protocol, baseline manifest,
treatment manifest, evaluation manifest, paired results, and leakage report.
The framework does not load the model or tokenizer, train, evaluate, access
sealed samples, or run overlap detection.

The registered Workspace protocol binds:

- release id, release-pack hash, Domain Pack reference, and Publishable evidence;
- benchmark suite/version, sealed split/hash, ordered task-id manifest, and
  scoring-code hash;
- initial model, tokenizer declaration, training system/code/environment,
  hyperparameters, seed, schedule, stopping, and exclusions;
- common training inputs, control corpus, deterministic selection/replacement
  rule, and content-bound arm manifests;
- binary `task_success_rate` as the sole qualification metric; and
- `paired_percentile_bootstrap_v1`, 10,000 resamples, explicit seed, two-sided
  95% interval, and strict relative lower-bound threshold greater than 0.01.

Inserted release records and removed control records must both be positive and
satisfy:

```text
abs(inserted - removed) / removed <= 0.10
```

Token, step, elapsed-time, and compute observations are optional and non-gating.

For `N` paired binary task rows, the bootstrap draw index is:

```text
unsigned_int(SHA256(UTF8(seed + ":" + replicate + ":" + draw))) mod N
```

Replicate and draw are zero-based decimal integers. Each replicate computes the
treatment-minus-baseline absolute success-rate difference. Sorting 10,000
replicates, the 95% nearest-rank interval uses one-based ranks 250 and 9,750
(zero-based indices 249 and 9,749). The observed baseline rate must be greater
than zero, and:

```text
relative_lower_bound = absolute_delta_lower_bound / observed_baseline_rate
```

Only `relative_lower_bound > 0.01` passes. Equality does not. Leakage evidence
must bind the registered evaluation and scoring hashes, state that the protocol
was frozen before training, deny evaluation use for training, and report zero
unresolved overlap.

Real evidence uses `external_experiment`. A positive valid result is
`training_recommended`; a valid result below threshold is
`no_detected_meaningful_gain`; protocol, membership, leakage, matching, or
post-registration violations are `invalid_experiment`; missing or unverifiable
evidence is `insufficient_evidence`.

`conformance_fixture` is permanently non-qualifying and can return only a
protocol-conformance result. External submitter provenance is trusted at the
import boundary; this first protocol does not require signatures for training
evidence.

## Workspace Tracer Topology

The tracer is one directed proof graph rooted at `workspace_tracer_proof_v1`.
Every edge records schema/version, relative path, SHA-256 digest, and byte count.
The verifier follows only declared edges and never consults a mutable registry
default or infers identity from filenames.

### Real Release Candidate leg

The positive real leg is:

```text
admitted Workspace source
  -> exact Domain plan
  -> coverage assignments
  -> real LLM generation attempts
  -> membership and mutation admission
  -> isolated Workspace attempts and episodes
  -> accepted/rejected artifacts and replay
  -> quality, coverage, held-out, mutation, and release reports
  -> Domain assessment
  -> independently verified release pack
  -> Release Candidate qualification
```

Provider evidence retains provider/model/config identity, assignment id,
request and response hashes, parser/contract version, and bounded outcome. It
does not retain credentials or unrestricted prompts. After live acceptance,
sanitized responses become frozen replay inputs. Replay uses production
parsing, membership, execution, and verification.

### Conformance legs

The verified real Release Candidate pack feeds a fixture-only publishability
bundle. Test authority can exercise governance, review, risk, approval, scope,
expiry, and revocation mechanics but can set only
`publishable_conformance = passed`; it cannot set effective Publishable.

That result feeds a `conformance_fixture` Workspace training protocol with known
paired results. It exercises record matching, metric calculation, bootstrap,
and leakage rules but can set only
`training_recommended_conformance = passed`; it cannot set effective Training
Recommended.

The required root summary is:

```text
effective_qualification = release_candidate
publishable = false
training_recommended = false
publishable_conformance = passed
training_recommended_conformance = passed
```

### Compatibility prerequisite

The root includes the complete Contacts/Mobile compatibility-corpus result as
an auxiliary prerequisite. Contacts and Mobile do not run additional tracer
pipelines.

### Fail-Closed Proof Cases

Each case copies the positive inputs, mutates one declared fact, and verifies
the exact bounded result while earlier unrelated bytes remain unchanged:

| Case | Mutation | Required result |
| --- | --- | --- |
| Plan identity | Pack, capability, coverage, component, or runtime hash | Planning, opening, or assessment rejects before qualification. |
| Provider contract | Unknown tool, changed capability, missing assignment, undeclared recovery | Rejected before execution and receives no credit. |
| Mutation safety | Missing requester authorization or argument provenance | Admission rejects with no durable state change. |
| Execution evidence | Changed state, verifier, episode, or replay binding | Accepted/domain evidence becomes invalid. |
| Coverage/evaluation | Missing required capability, recovery, held-out result, task type, or tool combination | Release Candidate is insufficient. |
| Run completeness | Cancellation, missing artifact, or non-passing gate | Release Candidate denied; fixture evidence cannot repair it. |
| Artifact integrity | Changed byte, digest, size, release id, or dataset version | Standalone pack/proof verification fails. |
| Publishability | Wrong pack, missing governance, wider scope, expiry, or revocation | Conformance denied; effective Release Candidate remains. |
| Fixture isolation | Fixture authority or experiment relabeled as real | Evidence-class transition rejected. |
| Training arms | Count tolerance exceeded or registered training identity changed | Experiment invalid. |
| Evaluation/leakage | Membership/hash mismatch, selective omission, training use, or unresolved overlap | Experiment invalid. |
| Meaningful gain | Relative lower bound at or below 0.01 | No meaningful gain; effective Release Candidate remains. |
| Cumulative dependency | Lower-level dependency invalidated or revoked | Dependent effective qualifications disappear; history remains. |

A parser crash, generic exception, silent default, post-hoc repair, skipped case,
or free-form-only difference fails the proof.

## Artifact and Schema Strategy

New contracts are strict, versioned, size/depth bounded, secret-safe, and
validated before semantic use. At minimum the implementation introduces
records for:

- Domain Pack descriptor and exact reference;
- Domain capability reference;
- Domain plan and planning result;
- Domain assessment;
- compatibility mapping, corpus manifest, and four-axis assessment;
- cumulative qualification report;
- publication-governance report;
- risk-acceptance and publication-approval attestations;
- authority policy and revocation evidence;
- publishability evidence bundle and decision;
- Workspace training protocol, external evidence manifest, and result;
- Workspace tracer proof root and proof-case result.

Schema versions describe serialized validation. Pack versions describe selected
domain semantics. Capability contract versions describe proof meaning. Runtime
versions describe execution carriers. These versions are recorded together and
never substituted for one another.

Canonical JSON hashing uses the repository's stable JSON rules. Artifact paths
are locators only. Every proof-bearing reference also contains expected bytes,
SHA-256, schema, and semantic identity.

## Failure and Safety Invariants

- No untrusted provider field can create or change local identity, assignment,
  capability, fulfillment, qualification, or authority evidence.
- No compatibility mapping creates facts absent from the source.
- No human approval waives a hard machine gate.
- No downstream experiment repairs Release Candidate or Publishable evidence.
- No fixture class can become real evidence by changing a label.
- No higher qualification survives invalid lower evidence.
- No failed higher qualification erases valid lower evidence.
- No evaluation decision performs the external action it discusses.
- No canonical writer emits a semantic legacy alias.
- No replay or offline verification uses mutable current defaults.
- No real provider proof stores credentials, unrestricted prompts, or
  unrestricted private source content.

## Migration Sequence

1. Add strict identity, descriptor, plan, assessment, compatibility, and
   qualification contracts without changing existing default execution.
2. Introduce the deep lifecycle and move Workspace fixture execution behind it,
   preserving observable behavior while removing shared reliance on the shallow
   bundle internals.
3. Freeze and verify the Contacts/Mobile compatibility corpus, then add scoped
   readers and adapters that emit canonical plans and lineage.
4. Carry canonical Workspace capability references through coverage-driven LLM
   assignments, task admission, attempts, episodes, coverage, held-out
   evaluation, assessment, release completeness, and release packs.
5. Establish the real Workspace Release Candidate decision through the shared
   cumulative qualification evaluator.
6. Add publishability evidence and authority verification without external
   publication side effects.
7. Add the verifier-only Workspace training protocol and deterministic
   bootstrap result.
8. Assemble the offline tracer root, conformance fixtures, compatibility
   prerequisite, and complete negative matrix.
9. Run the authorized live provider acceptance, freeze sanitized responses, and
   verify clean offline reproduction.

Existing non-Domain-Pack entry points may remain temporarily through explicit
adapters, but new proof-bearing writers are canonical-only. Removal of a legacy
reader or adapter requires an explicit support-policy change and migration path.
