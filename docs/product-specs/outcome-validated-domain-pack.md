# Outcome-Validated Domain Pack

Status: ticketed; ready for implementation

## Problem Statement

The framework has domain-owned environment, generation, coverage, mutation,
evaluation, and release behavior, but those semantics are exposed through
several adjacent registries, labels, task types, tool names, and report slices.
There is no single versioned authority that says what a domain can claim, how
that claim is planned and executed, or which exact evidence establishes it.
As a result, equal-looking strings can be mistaken for equivalent capability
identities, runtime identity can be confused with domain identity, and legacy
artifacts can appear stronger than the evidence they actually contain.

The existing dataset-release path also stops short of a complete user-facing
qualification model. A passing machine release decision, an independently
verified release pack, completed human review, publication approval, and a
positive downstream benchmark observation are distinct facts, but they are not
yet represented as cumulative qualifications with explicit allowed claims.
Without that distinction, an operator could overstate machine admission as
publication authority or overstate one improved point estimate as evidence that
a release should be used for training.

The framework needs an executable proof that these contracts agree across the
whole path. That proof must use a real coverage-driven Workspace LLM run and
real isolated Workspace execution to establish a Release Candidate, while
exercising Publishable and Training Recommended software paths without
pretending that test fixtures are human approval or external training. It must
also preserve the existing Contacts and Mobile evidence as bounded compatibility
inputs rather than silently promoting it or expanding this effort into three
new domain implementations.

## Solution

Make a versioned Domain Pack the single semantic authority and common deep
interface for each supported domain. A Domain Pack declares stable capability
identities, selects the exact semantic contracts used by planning, generation,
coverage, evaluation, mutation safety, runtime conformance, compatibility, and
release completeness, and produces typed domain assessments. The shared
framework continues to own source admission, provider selection, scheduling,
stable artifact writing, recovery, cumulative release qualification, and human
authority.

Use a two-level lifecycle. A pure planning operation compiles one admitted
synthesis intent into a deterministic, hash-bound Domain plan before provider
or runtime activity. Opening that plan yields a run-scoped Domain run that
hides environment, tool-registry, candidate-preparation, verifier, mutation,
attempt, isolation, and replay mechanics. Assessment interprets exact evidence
for the domain but does not grant a Release qualification.

Define canonical Domain capabilities separately from task types, tool
sequences, coverage cells, structural families, held-out tags, mutation
policies, and runtime features. New artifacts carry exact Domain Pack and
capability references from planning through qualification. Legacy artifacts are
handled through versioned, projection-scoped compatibility mappings and receive
separate readability, runnability, semantic-equivalence, and
evidence-admissibility judgments. Compatibility can preserve historical use and
verification but cannot manufacture missing current evidence.

Introduce three cumulative qualifications over one immutable artifact subject:
Release Candidate, Publishable, and Training Recommended. Each transition fails
closed on missing, stale, malformed, revoked, mismatched, or non-passing
evidence. Release Candidate means the exact artifact set passed all applicable
machine gates and may enter human publication review. Publishable additionally
requires independently verifiable governance evidence and authenticated human
approval for an exact distribution scope. Training Recommended additionally
requires a pre-registered, leakage-controlled external matched experiment whose
reproducible paired-bootstrap lower bound exceeds the declared meaningful-gain
threshold for one exact model, recipe, seed, benchmark, and protocol.

Prove the design with one Workspace tracer. Its real leg uses coverage-driven
LLM generation, enforced mutation admission, isolated local Workspace
execution, all five Workspace capabilities, and a standalone-verifiable release
pack to establish a real Release Candidate. Permanently non-qualifying fixtures
exercise Publishable and Training Recommended conformance. One content-addressed
proof root distinguishes effective qualification from conformance, replays
sanitized provider responses offline, verifies the Contacts/Mobile compatibility
corpus, and runs the complete fail-closed mutation matrix.

## User Stories

1. As a synthesis operator, I want to select one exact Domain Pack, so that all
   domain semantics used by the run come from one reviewable authority.
2. As a synthesis operator, I want a Domain plan before provider activity, so
   that invalid capability, coverage, runtime, mutation, or release bindings
   fail before cost or side effects.
3. As a synthesis operator, I want identical admitted inputs to produce the same
   Domain plan and hash, so that runs and evidence can be reproduced.
4. As a synthesis operator, I want provider and credential selection to remain
   framework concerns, so that a Domain Pack does not take over operational
   authority.
5. As a synthesis operator, I want source admission to remain outside the Domain
   Pack, so that planning cannot bypass provenance, license, sandbox, or network
   policy.
6. As a synthesis operator, I want the default local workflow to remain usable,
   so that adoption of the new interface does not require distributed workers
   or external services.
7. As a synthesis operator, I want bounded reason codes for planning, opening,
   execution, assessment, and qualification failures, so that failures can be
   diagnosed without parsing sensitive free-form content.
8. As a synthesis operator, I want a profile purpose named `release_candidate`
   to remain only an intent until every required gate passes, so that
   configuration is not mistaken for evidence.
9. As a domain author, I want one stable logical Domain Pack identity independent
   of its runtime, so that changing execution carriers does not rename domain
   semantics.
10. As a domain author, I want stable pack-local capability keys, so that
    semantically continuous claims remain recognizable across compatible
    contract evolution.
11. As a domain author, I want materially different claims to receive different
    capability keys, so that changed meaning cannot reuse old evidence.
12. As a domain author, I want capability contract versions separate from
    capability identity, so that stricter proof requirements are explicit.
13. As a domain author, I want one immutable composition version to select the
    exact task, coverage, evaluation, mutation, runtime, release, and
    compatibility contracts, so that a pack cannot drift after evidence is
    written.
14. As a domain author, I want any behavior-affecting generator, verifier, or
    policy change to produce a new pack version, so that observable changes do
    not hide behind a reused version label.
15. As a domain author, I want task types to declare capability requirements
    explicitly, so that label similarity never becomes an implicit mapping.
16. As a domain author, I want recovery and safe-failure behavior represented as
    independent capabilities only when they are independently testable and
    claimable, so that capability catalogs remain meaningful.
17. As a domain author, I want mutation policy to remain distinct from capability
    identity, so that a capability name never authorizes a state change.
18. As a domain author, I want runtime features separate from Domain
    capabilities, so that rebuild, replay, or branching support is not reported
    as a semantic domain outcome.
19. As a framework maintainer, I want one deep Domain Pack interface, so that the
    shared pipeline no longer depends on the internal fan-out of environment,
    registry, verifier, preparer, and mutation components.
20. As a framework maintainer, I want run-scoped candidate isolation behind the
    Domain run, so that every attempt receives a clean environment without
    exposing raw runtime sessions to callers.
21. As a framework maintainer, I want generation, attempt, and replay to use the
    same Domain run semantics, so that offline regression does not exercise a
    different contract from live execution.
22. As a framework maintainer, I want Domain assessment to return typed evidence
    or insufficiency, so that a pack can interpret its evidence without granting
    its own Release qualification.
23. As a framework maintainer, I want the shared framework to retain scheduling,
    stable merge, artifact writing, resumption, and final qualification, so that
    Domain Packs do not become shallow copies of the whole pipeline.
24. As a framework maintainer, I want exact pack, runtime, component, and
    capability references at every public boundary, so that consumers do not
    consult mutable defaults.
25. As a framework maintainer, I want canonical writers to emit no legacy aliases
    in semantic fields, so that migration converges on one vocabulary.
26. As a framework maintainer, I want compatibility mappings scoped by source
    schema, version, field kind, and legacy value, so that equal strings in
    different namespaces cannot collide.
27. As a framework maintainer, I want compatibility to report readability,
    runnability, semantic equivalence, and evidence admissibility separately, so
    that one vague `compatible` flag cannot overstate support.
28. As a framework maintainer, I want migrated artifacts to preserve source
    bytes, hashes, original references, mapping identity, and derivation
    lineage, so that migration is auditable.
29. As a framework maintainer, I want migration to create new artifacts instead
    of rewriting historical inputs, so that old claims remain reproducible.
30. As a maintainer of existing workflows, I want the bounded legacy reader floor
    for profiles, manifests, reports, and release packs to remain explicit, so
    that support is preserved intentionally rather than accidentally.
31. As a maintainer of existing workflows, I want supported legacy profiles to
    compile into canonical plans without guessing, so that old entry points can
    migrate safely.
32. As a maintainer of existing workflows, I want unsupported, ambiguous,
    cross-pack, and unknown-version legacy references to fail closed, so that an
    adapter cannot repair evidence by invention.
33. As a dataset curator, I want every accepted sample to carry the exact
    capability references assigned before generation, so that a provider cannot
    self-certify what its sample proves.
34. As a dataset curator, I want assignment membership validated before
    execution, so that mismatched task, tool, grounding, state, and recovery
    structures receive no coverage credit.
35. As a dataset curator, I want only admitted, executed, independently verified
    samples to contribute to capability floors, so that generation and cell
    fulfillment alone cannot establish evidence.
36. As a dataset curator, I want capability coverage reported separately from
    task type, tool combination, structural family, and coverage cell, so that
    useful diagnostic slices do not become aliases.
37. As a Workspace domain user, I want item search, task creation, comment
    addition, item-search recovery, and missing-item safe failure represented as
    five canonical capabilities, so that each claim has explicit evidence.
38. As a Workspace domain user, I want item-search recovery to prove the initial
    failure, admissible fallback, grounded result, and independent verification,
    so that branch-plan presence alone cannot count as recovery.
39. As a Workspace domain user, I want missing-item requests to fail with the
    expected bounded cause and no unintended mutation, so that safety behavior
    is independently verifiable.
40. As a release manager, I want Release Candidate to require every applicable
    contract, execution, verification, grounding, quality, provenance, source,
    mutation, coverage, held-out, completeness, and release gate, so that one
    passing status cannot substitute for the full machine boundary.
41. As a release manager, I want the existing Workspace floors preserved, so
    that the new capability model cannot weaken minimum sample count, maximum
    rejection rate, or required tool-combination coverage.
42. As a release manager, I want a standalone-verifiable exact release pack, so
    that qualification can be checked without rerunning generation.
43. As a release manager, I want qualification to follow only Unqualified,
    Release Candidate, Publishable, and Training Recommended in order, so that
    evidence cannot skip levels.
44. As a release manager, I want a failed higher-level attempt to preserve a
    still-valid lower qualification, so that downstream failure does not erase
    machine or publication evidence.
45. As a release manager, I want invalidation or revocation of lower evidence to
    remove every dependent effective qualification, so that stale claims cannot
    survive a broken prerequisite.
46. As a release manager, I want any byte-changing repack to become a new
    qualification subject, so that approval and experimental evidence cannot
    drift across artifact identities.
47. As a publication approver, I want a publishability evidence bundle to bind
    the exact release, governance, audit, review, risk, authority, scope, and
    revocation evidence, so that approval is independently verifiable.
48. As a publication approver, I want review completion, audit clearance, risk
    acceptance, and publication approval to remain separate facts, so that a
    completed queue cannot authorize distribution.
49. As a publication approver, I want hard machine governance gates to be
    non-waivable, so that human approval cannot override integrity, source,
    mutation, privacy, or authority failures.
50. As a publication approver, I want approval bound to a machine-verifiable
    distribution scope, so that broader audience, purpose, access, retention,
    or redistribution requires new authority.
51. As a risk owner, I want accepted risk to bind exact findings, severity,
    compensating controls, scope, and expiry, so that residual risk cannot be
    accepted indefinitely or generically.
52. As a governance owner, I want external or public distribution with residual
    risk to use different risk and publication principals, so that separation
    of duties is enforced where it matters.
53. As an external experiment owner, I want to choose and pre-register the model,
    training system, benchmark, control corpus, and protocol outside this
    framework, so that the repository does not become a trainer or benchmark
    service.
54. As an external experiment owner, I want one matched baseline/treatment pair
    with record counts matched within ten percent, so that the evidence remains
    feasible while preserving an approximate-size comparison.
55. As an external experiment owner, I want token and compute observations to be
    optional and non-gating, so that the framework need not load a tokenizer or
    attest external compute.
56. As an evaluator, I want the sealed task set, scoring code, paired outcomes,
    and leakage declarations content-bound before training, so that
    result-guided protocol changes are inadmissible.
57. As an evaluator, I want the framework to recompute task success and the
    deterministic 10,000-replicate paired bootstrap, so that an external
    aggregate score is not trusted blindly.
58. As an evaluator, I want Training Recommended to require a strict relative
    95% lower bound greater than one percent, so that a positive point estimate
    or equality at the threshold is insufficient.
59. As an evaluator, I want invalid experiments, insufficient evidence, and no
    detected meaningful gain reported separately, so that failure causes remain
    actionable.
60. As an evaluator, I want a Training Recommended claim scoped to the exact
    release, model, recipe, seed, benchmark, split, and protocol, so that one
    experiment is not generalized beyond its evidence.
61. As a security reviewer, I want provider lineage sanitized, so that proof
    artifacts retain identities and hashes without credentials, unrestricted
    prompts, or private source payloads.
62. As a security reviewer, I want malformed, oversized, unknown-version,
    mismatched, expired, or revoked evidence to fail closed, so that parser and
    authority edge cases cannot create a qualification.
63. As a compatibility reviewer, I want Contacts and Mobile frozen as a
    hash-manifested corpus with independently reviewed expected projections, so
    that changing current writers cannot redefine legacy truth.
64. As a compatibility reviewer, I want every Contacts and Mobile corpus row to
    have expected results on all four compatibility axes, so that partial
    support is explicit.
65. As a compatibility reviewer, I want historical chains to reproduce only
    their original claims and remain historical-only for current qualification,
    so that compatibility does not retroactively mint stronger evidence.
66. As a test engineer, I want one content-addressed Workspace tracer proof root,
    so that the complete contract can be verified from a single observable
    boundary.
67. As a test engineer, I want one real LLM Workspace leg to establish the real
    Release Candidate, so that the proof does not rely entirely on synthetic
    success fixtures.
68. As a test engineer, I want sanitized real responses frozen for replay, so
    that production parsing, admission, execution, and verification can be
    regression-tested without repeated provider calls.
69. As a test engineer, I want Publishable and Training Recommended fixtures
    permanently marked non-qualifying, so that conformance success cannot alter
    effective qualification.
70. As a test engineer, I want every mandatory negative proof case to mutate one
    fact in independently copied evidence, so that failures are attributable
    and earlier artifacts remain byte-identical.
71. As a test engineer, I want the proof report to distinguish effective
    qualification from conformance status, so that one flattened `passed` field
    cannot misrepresent the result.
72. As a test engineer, I want clean offline verification to reconstruct every
    identity, hash, dependency, qualification, and conformance result, so that
    no decision depends on mutable paths or registry defaults.

## Implementation Decisions

- Adopt the logical Domain Pack identities `contacts`, `mobile_messages`, and
  `workspace_tasks`. Runtime identities remain separate and are recorded beside
  the pack reference.
- Define an exact Domain Pack reference as logical identity, immutable
  composition version, and canonical content hash. Reusing a version with
  different content is invalid.
- Define a Domain capability identity as a logical Domain Pack plus a stable
  pack-local capability key. Evidence binds an exact capability contract
  version in addition to that identity.
- Treat task types, tools, action types, coverage cells, structural families,
  evaluation slices, mutation policies, and runtime features as separate
  concepts. Relationships to capabilities are explicit many-to-many
  projections selected by the Domain Pack.
- Require a new Domain Pack version whenever planning, opening, generation,
  execution, replay, assessment, evidence meaning, compatibility mapping, or
  release completeness can change. Behavior-preserving refactors and
  display-only metadata changes do not require a new version.
- Use a pure `plan` operation to compile admitted intent and governed source
  facts into one deterministic Domain plan. The plan binds all semantic,
  runtime, coverage, evaluation, mutation, compatibility, and release
  requirements before provider or runtime activity.
- Use an `open` operation to accept a valid plan and an admitted runtime scope
  and return one Domain run. The Domain run owns generation, candidate-scoped
  isolation, attempt, and replay behavior while hiding internal component
  composition.
- Use an `assess` operation to return typed domain evidence or bounded
  insufficiency for an exact plan and artifact set. Final release qualification
  remains framework-owned.
- Do not expose a generic dictionary projection bus or a raw runtime-session
  escape hatch in the initial public interface. Add typed operations only when
  a proven use case cannot use the lifecycle.
- Keep source governance, credentials, provider selection, orchestration,
  concurrency, cancellation, stable merge, artifact writing, qualification,
  and human authority in the shared framework.
- Require canonical capability references on plans, coverage assignments,
  generated task contracts, accepted samples, episodes, verification evidence,
  coverage evidence, held-out tasks and reports, domain assessments, release
  completeness, release packs, and qualification decisions.
- Reject missing, unknown, duplicate, cross-pack, unsupported-version, or
  projection-inconsistent capability references before they can contribute to
  evidence. Never infer a capability from equal strings or post-run labels.
- Define the Workspace capability set as item search, task creation, comment
  addition, item-search recovery, and missing-item safe failure. New Workspace
  generation uses item search, task creation, and comment update task types;
  recovery remains an assignment structure and missing-item safety remains a
  held-out scenario.
- Require the Workspace Release Candidate path to use coverage-driven LLM
  generation, enforced independent mutation admission for state changes,
  isolated local execution, and exact capability references fixed before each
  provider request.
- Preserve current Workspace quantitative and structural release floors:
  minimum five accepted samples, maximum rejection rate of 0.2, required
  read-only/task-creation/comment-addition tool combinations, all required task
  and capability coverage, at least one validated recovery sample, and held-out
  evidence for all five capabilities.
- Model compatibility with four independent statuses: readability,
  runnability, semantic equivalence, and evidence admissibility. Unknown status
  on any required axis fails closed.
- Scope compatibility mappings by source schema/version, projection kind,
  legacy value, and target reference. Mappings are versioned and hash-bound;
  aliases are accepted only at ingestion.
- Preserve original bytes and references during migration. Canonical output is
  a new artifact carrying migration lineage and exact canonical references.
- Freeze all selected checked-in Contacts and Mobile profiles plus reviewed
  synthetic version-bridge fixtures and four self-contained golden artifact
  chains into one hash-manifested compatibility corpus. Expected canonical
  projections are independent fixtures, not regenerated by the code under
  test.
- Keep all legacy golden chains historical-only for current qualifications
  unless every required current fact was already explicit and losslessly
  equivalent. The initial corpus does not meet that condition and must report
  insufficient evidence for current qualification.
- Implement one cumulative qualification evaluator with the only forward path
  Unqualified to Release Candidate to Publishable to Training Recommended.
  Missing or invalid evidence denies the attempted transition; a failed higher
  level preserves the highest still-valid lower level.
- Bind every qualification to one exact immutable artifact subject. Byte
  changes, identity changes, changed limitations, changed findings, or expanded
  scope create a new subject.
- Define Release Candidate as the passing conjunction of all applicable machine
  gates plus a valid release-quality audit. The permitted claim is eligibility
  for human publication review, not publication or training utility.
- Define a publishability evidence bundle that content-binds the verified
  release pack, machine qualification, governance report, audit, review queue
  and resolutions, risk records, publication approval, authority policy, scope,
  validity, and revocation evidence.
- Treat artifact integrity, identity binding, source and publication governance,
  sensitive-material controls, mutation safety, and authority validity as
  non-waivable hard gates.
- Require independently verifiable authenticated attestations for risk
  acceptance and publication approval. Risk acceptance has mandatory expiry
  and cannot waive hard gates. External or public publication with residual risk
  requires distinct authenticated principals.
- Make the publishability evaluator deterministic and side-effect free with
  bounded passed, denied, and insufficient-evidence outcomes. It never publishes
  artifacts.
- Make the training-evidence boundary verifier-only. External experiment owners
  select, register, fund, and execute training and evaluation; the framework
  imports content-addressed evidence and verifies internal consistency.
- Bind the first Workspace training protocol to an exact Publishable release,
  externally chosen model and training identities, frozen benchmark and ordered
  task set, scoring code, control and treatment manifests, leakage method, seed,
  schedule, stopping/exclusion rules, and evidence schemas before training.
- Use training-record replacement as the matching unit. Inserted release records
  and removed control records must both be positive and differ by no more than
  ten percent relative to removed records. Token and compute observations are
  non-gating.
- Use paired binary task success as the sole initial Workspace utility metric.
  Recompute a deterministic 10,000-replicate paired percentile-bootstrap
  interval and require a strict relative lower bound greater than 0.01. The
  observed baseline rate must be positive.
- Treat external experiment provenance as trusted at the explicit import
  boundary while verifying all supplied hashes, identities, membership,
  counts, calculations, and leakage declarations. The first protocol requires
  no signatures for experiment evidence.
- Distinguish real external experiment evidence from permanently non-qualifying
  conformance fixtures. Relabeling a fixture as real is an invalid evidence-class
  transition.
- Emit one content-addressed Workspace tracer proof root that binds the Domain
  Pack, plan, source, runtime, generation, assignment, accepted/rejected sample,
  episode/replay, quality, coverage, mutation, held-out, release, assessment,
  qualification, compatibility, conformance, and negative-case artifacts.
- Keep effective qualification and conformance as separate report fields. The
  required tracer result is real Release Candidate, false Publishable, false
  Training Recommended, passed Publishable conformance, and passed Training
  Recommended conformance.
- Freeze sanitized responses from the authorized real provider acceptance run
  for deterministic replay. Hand-authored invalid responses cover stochastic
  failure cases that a live run is not expected to generate.
- Require every negative proof case to start from copied positive bytes, mutate
  one declared fact, return the exact bounded status/reason, and leave unrelated
  evidence unchanged.
- Do not automatically publish a dataset, start training, promote a model,
  mutate review state, or change tracker state from any qualification decision.

## Testing Decisions

- Prefer one highest externally observable seam: an offline verifier starts from
  `workspace_tracer_proof_v1` and reconstructs the complete identity graph,
  hashes, effective qualification, conformance statuses, compatibility result,
  replay decisions, and mandatory negative-case results. Tests assert artifacts
  and bounded decisions rather than helper calls or internal component layout.
- Use one authorized live-LLM Workspace acceptance run to create the real
  Release Candidate leg. The acceptance run is separate from the deterministic
  unit suite; it must use production parsing, membership admission, mutation
  enforcement, isolated execution, verification, release packing, and
  qualification.
- Replay sanitized responses captured from the live run through the same
  production parser and Domain run. Offline replay must reproduce the bounded
  admission, execution, and verification outcomes without another provider
  call.
- Use fixture-only Publishable and Training Recommended positive paths to prove
  software conformance. Tests must assert that these fixtures cannot raise the
  effective qualification above Release Candidate.
- Exercise every mandatory negative case at the proof-root seam: plan identity,
  provider contract, mutation safety, execution evidence, coverage/evaluation,
  run completeness, artifact integrity, publishability scope/authority,
  evidence-class isolation, training-arm consistency, evaluation/leakage,
  meaningful gain, and cumulative dependency invalidation.
- Add focused pure contract tests only where the end-to-end proof cannot
  localize a rule economically: canonical reference validation, deterministic
  plan hashing, compatibility mapping selection, schema bounds, signature and
  revocation verification, scope subset checks, sample-count tolerance, paired
  bootstrap reproduction, and bounded reason codes.
- Add Domain Pack contract tests that prove callers see only the deep lifecycle
  and that Workspace-specific knowledge does not leak into shared consumers.
- Add compatibility-corpus tests that use frozen legacy inputs and independently
  reviewed expected projections. The reader, adapter, and writer under test must
  not generate either side of the oracle.
- Add canonical-writer tests proving semantic fields contain exact Domain Pack
  and capability references and no legacy aliases, while exact legacy-named
  runtime ids remain permitted in runtime fields.
- Add Workspace evidence-flow tests proving capability references are fixed in
  the plan and assignment, provider output cannot alter them, rejected or
  unverified work receives no credit, and held-out evaluation consumes the same
  catalog.
- Add qualification tests proving transitions cannot skip levels, higher-level
  failure preserves a lower level, lower-level invalidation removes dependents,
  byte-changing repacks create new subjects, and historical records remain
  append-only.
- Add publishability tests for hard gates, review dispositions, risk expiry,
  signature/attestation verification, authority scope, separation of duties,
  approval expiry, revocation, and subset use requests.
- Add training-protocol tests for frozen identities, manifest membership,
  duplicate/missing/extra/reordered task ids, record-count tolerance, zero
  baseline, deterministic nearest-rank bootstrap bounds, equality at the
  threshold, leakage declarations, post-registration change, and
  evidence-class isolation.
- Reuse the existing run-profile, domain-generation, coverage-assignment,
  Workspace-pipeline, held-out-evaluation, mutation-admission, release-pack,
  release-review, downstream-benchmark, CLI, contract, and documentation
  validation test styles as prior art. Extend the current public seams rather
  than creating a parallel pipeline harness.
- A good test verifies externally observable behavior, stable artifacts,
  identity/hash relationships, side-effect absence, and bounded decisions. It
  must not assert private helper order, internal dataclass layout, exact prompt
  prose, or implementation-specific call counts unless those facts are part of
  a public contract.

## Out of Scope

- Running model training, tokenization, or a real external benchmark inside the
  repository.
- Selecting a default external model, training stack, benchmark, control corpus,
  compute budget, or sealed evaluation data.
- Claiming that fixture evidence establishes real publication approval or
  downstream utility.
- Automatically publishing a dataset, changing external access, promoting a
  model, or starting a training job.
- Adding a fourth domain or making Contacts and Mobile additional end-to-end
  tracer implementations.
- Expanding the Contacts, Mobile, or Workspace coverage catalogs beyond the
  capability alignment required by this specification.
- Implementing semantic duplicate detection solely to support compatibility or
  leakage claims.
- Performing internal duplicate or overlap scans over sealed external benchmark
  data.
- Distributed workers, external MCP execution, a publication portal, model
  serving infrastructure, or key management for external training evidence.
- Replacing the existing local orchestration lifecycle or weakening source
  governance, mutation safety, isolation, quality, provenance, and release
  gates.
- Retrofitting historical artifacts with invented capability references or
  silently promoting historical release statuses into the new qualification
  model.

## Further Notes

- Canonical terminology is in the [Domain glossary](../../CONTEXT.md).
- Target interfaces, schemas, evidence flow, compatibility mechanics, and tracer
  topology are in the [deep design](../design-docs/outcome-validated-domain-pack.md).
- The durable semantic-authority decision is recorded in
  [ADR 0002](../adr/0002-domain-pack-semantic-authority-and-deep-interface.md).
- The external-authority boundary is recorded in
  [ADR 0003](../adr/0003-separate-evidence-verification-from-external-authority.md).
- The resolved Wayfinder map remains decision provenance:
  [Outcome-Validated Domain Pack Wayfinding](../../.scratch/outcome-validated-domain-pack-wayfinding/README.md).
- Current delivery state and ordered implementation work are in the
  [Outcome-Validated Domain Pack feature tracker](../../.scratch/outcome-validated-domain-pack/README.md).
- This document is the only product specification for the feature. The deep
  design owns target-system mechanics; ADRs own durable rationale; tickets own
  work state and dependencies.
