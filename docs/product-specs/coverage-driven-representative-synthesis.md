# Coverage-Driven Representative Synthesis

## Problem Statement

A synthesis operator can currently select a domain and request a candidate
count, but the system does not know which kinds of training experience are
still missing from the resulting dataset. Remote generation can therefore
produce many executable and individually valid candidate tasks while repeatedly
using the same task type, tool sequence, grounding pattern, and difficulty
shape. Natural-language variation makes the records look different without
materially increasing capability or curriculum coverage.

This failure is visible in representative three-domain campaigns. Contacts,
mobile messages, and workspace tasks can achieve high executable and
verification rates while concentrating accepted samples into a small number of
structural families. Exact duplicate rejection removes literal repeats but
cannot tell the generator what useful task to create next. Semantic duplicate
detection could measure or reject additional repetition, but it would still
only shrink an underspecified dataset.

The synthesis operator should not have to manually configure a large
cross-product of task types, tools, difficulty levels, grounding cases,
mutation modes, ambiguity cases, and recovery paths for every run. The
operator should declare the synthesis purpose, domain, target size, and a named
coverage profile. The framework should compile those inputs with a versioned
domain-owned coverage catalog, schedule the most valuable reachable coverage
gaps, and report what the accepted samples actually fulfilled.

## Solution

Provide opt-in, coverage-driven representative synthesis.

Each domain pack declares a versioned coverage catalog containing the
meaningful structural dimensions, reachable coverage cells, compatibility
constraints, grounding capacity, and domain-owned difficulty semantics for
that environment and tool set. A named, versioned coverage profile expresses
the synthesis purpose, such as a small smoke probe or a representative
campaign, without requiring the operator to configure each cell.

Before generation, the framework compiles the run profile, coverage profile,
domain catalog, selected feature flags, and candidate budget into a
deterministic coverage plan. The plan contains bounded coverage assignments,
not task instructions. Each assignment says which reachable cell the next
candidate must satisfy and which declared grounding scope it may use. The
provider generates a task contract within that assignment; it cannot declare
that the task fulfilled the assignment. Local validation derives and attaches
the assignment evidence.

During a coverage-driven run, the scheduler prioritizes mandatory coverage
floors, then the largest remaining deficits, using deterministic tie-breaking.
Only accepted samples satisfy coverage. Rejected candidates, invalid provider
outputs, duplicate candidates, and failed executions remain visible but do not
consume a coverage requirement. A profile-owned attempt budget allows bounded
backfill of unfilled assignments without hidden or unbounded provider spend.
If the plan is unsatisfiable or remains incomplete when the attempt budget is
exhausted, the run reports the exact bounded deficit instead of silently
relaxing the profile.

The output includes sanitized planned-versus-accepted coverage evidence,
concentration and grounding-reuse signals, assignment lineage, and a
machine-readable fulfillment decision. A diagnostic run may remain useful
when coverage is incomplete. A run may claim coverage-driven representative
status only when its mandatory coverage plan is fulfilled and all existing
representative, safety, provenance, execution, and verification requirements
also pass.

Existing run profiles and non-coverage generation retain their current
behavior. Coverage-driven synthesis is selected through a small, versioned
profile reference with optional bounded overrides. Domain catalogs and
coverage profiles carry the detailed configuration so ordinary operators do
not manually orchestrate the coverage matrix.

## User Stories

1. As a synthesis operator, I want to select a named coverage profile, so that I
   can request representative data without configuring dozens of coverage
   dimensions.
2. As a synthesis operator, I want domain, target candidate count, purpose, and
   coverage profile to be sufficient for a normal run, so that smart scheduling
   reduces rather than increases operational complexity.
3. As a synthesis operator, I want optional overrides to be bounded and
   validated, so that I can emphasize one legitimate need without creating an
   incoherent coverage plan.
4. As a synthesis operator, I want to see the plan before paid generation
   begins, so that I can understand the intended distribution and provider
   budget.
5. As a synthesis operator, I want an impossible plan to fail before a provider
   call when the impossibility is statically knowable, so that I do not pay for
   a campaign that cannot meet its stated goal.
6. As a synthesis operator, I want the attempt ceiling to be explicit and
   derived from the selected profile, so that rejected candidates cannot cause
   hidden or unbounded spend.
7. As a synthesis operator, I want a run to stop at its declared attempt
   ceiling, so that coverage backfill remains operationally predictable.
8. As a synthesis operator, I want incomplete coverage to produce bounded
   deficit reasons, so that I know whether to change the environment, catalog,
   profile, provider, or budget.
9. As a synthesis operator, I want existing non-coverage profiles to keep their
   current behavior, so that adopting smart scheduling is deliberate and
   backward compatible.
10. As a synthesis operator, I want diagnostic runs to retain partial valid
    samples even when their coverage plan is incomplete, so that small probes
    still produce useful evidence without claiming representativeness.
11. As a domain pack maintainer, I want to declare the structural dimensions
    that matter in my domain, so that generic scheduling does not infer domain
    semantics from natural-language prompts or tool schemas alone.
12. As a domain pack maintainer, I want to declare reachable cells rather than
    an unconstrained Cartesian product, so that impossible combinations do not
    enter the plan.
13. As a domain pack maintainer, I want to declare compatibility constraints
    among task type, tool sequence, grounding pattern, state behavior,
    difficulty, ambiguity, and recovery behavior, so that every assignment is
    executable in principle.
14. As a domain pack maintainer, I want coverage catalogs to be versioned, so
    that changing domain semantics produces auditable new evidence rather than
    silently changing an old dataset meaning.
15. As a domain pack maintainer, I want domain-owned deterministic difficulty
    semantics, so that a provider cannot label a structurally simple task as
    difficult without evidence.
16. As a domain pack maintainer, I want to declare grounding capacity and reuse
    limits, so that a thirty-sample campaign does not repeatedly select the same
    object merely because it is easy to reference.
17. As a domain pack maintainer, I want catalog validation to identify empty,
    duplicate, unreachable, contradictory, or unbounded cells, so that invalid
    coverage policy fails locally.
18. As a domain pack maintainer, I want feature-dependent cells to declare their
    required feature flags, so that branching or recovery assignments are not
    scheduled when the run has disabled those capabilities.
19. As a domain pack maintainer, I want source-backed environments to compile
    coverage only from admitted, bounded domain facts, so that coverage planning
    does not bypass source governance.
20. As a framework maintainer, I want one shared coverage-plan compiler, so
    that contacts, mobile messages, and workspace tasks use the same scheduling
    and evidence rules.
21. As a framework maintainer, I want domain semantics represented as validated
    data, so that the shared scheduler does not acquire domain-name branches.
22. As a framework maintainer, I want a deterministic plan for fixed inputs, so
    that plan hashes, reruns, comparisons, and release evidence remain
    reproducible.
23. As a framework maintainer, I want mandatory floors scheduled before
    balancing discretionary cells, so that high-value long-tail requirements
    are not crowded out by common easy tasks.
24. As a framework maintainer, I want deterministic deficit and tie-breaking
    rules, so that provider output order does not unpredictably change the
    intended distribution.
25. As a framework maintainer, I want the scheduler to account for accepted
    coverage and in-flight assignments separately, so that concurrent or
    batched work does not oversubscribe the same cell.
26. As a framework maintainer, I want only accepted samples to fulfill
    assignments, so that generation attempts, invalid outputs, and failed
    executions cannot inflate coverage.
27. As a framework maintainer, I want bounded backfill to target the remaining
    accepted-sample deficit, so that a rejection in one cell does not cause
    unrelated easy cells to be overproduced.
28. As a framework maintainer, I want provider output constrained by one
    assignment while assignment identity is attached locally, so that
    untrusted model output cannot self-certify coverage.
29. As a framework maintainer, I want coverage scheduling to reuse the existing
    domain generation, candidate processing, mutation admission, execution,
    verification, duplicate, and dataset assembly boundaries, so that
    scheduling does not create a second pipeline.
30. As a framework maintainer, I want exact duplicate admission to remain in
    force, so that coverage-driven generation does not weaken the deterministic
    quality baseline.
31. As a framework maintainer, I want mutation authorization to remain
    independent from coverage value, so that an underfilled mutation cell never
    justifies executing an unauthorized state change.
32. As a framework maintainer, I want assignment and plan metadata sanitized,
    so that lineage can be retained without prompts, credentials, private source
    payloads, or unrestricted grounding content.
33. As a data quality reviewer, I want planned, attempted, generated, accepted,
    rejected, and unfilled counts per cell, so that I can distinguish model
    failure from execution failure and insufficient domain capacity.
34. As a data quality reviewer, I want structural-family concentration reported
    independently from exact duplicates, so that paraphrased repetition does
    not look like new curriculum coverage.
35. As a data quality reviewer, I want grounding reuse and difficulty
    distributions reported, so that entity diversity and curriculum diversity
    are observable rather than assumed.
36. As a data quality reviewer, I want each accepted sample linked to one
    locally validated assignment, so that I can trace why it exists in the
    dataset.
37. As a data quality reviewer, I want cell-level rejection causes to use a
    bounded vocabulary, so that coverage failures can be aggregated without
    retaining unsafe provider text.
38. As an evaluator, I want representative status to require mandatory
    coverage fulfillment, so that a high executable rate over a narrow task
    family cannot establish representativeness.
39. As an evaluator, I want coverage evidence hash-bound to the catalog,
    profile, plan, run profile, and admitted samples, so that post-run policy or
    sample changes invalidate the claim.
40. As an evaluator, I want two dataset versions compared by structural
    coverage and concentration as well as acceptance rate, so that a larger
    dataset is not automatically treated as better.
41. As an evaluator, I want held-out or downstream evaluation to remain
    separate from the coverage scheduler, so that the scheduler cannot optimize
    directly against protected evaluation outcomes.
42. As a researcher, I want coverage cells to correspond to distinguishable
    Agent capabilities and failure modes, so that added samples have a plausible
    training purpose rather than only lexical novelty.
43. As a researcher, I want to know when increasing the candidate target no
    longer increases fulfilled structural coverage, so that I can expand the
    domain instead of paying for more paraphrases.
44. As a researcher, I want semantic duplicate analysis to remain an optional
    later evaluation layer, so that detection can be calibrated without making
    it responsible for creating task diversity.

## Implementation Decisions

- Introduce the canonical concepts of coverage dimension, coverage cell,
  coverage catalog, coverage profile, coverage plan, coverage assignment,
  coverage scheduler, and coverage fulfillment.
- Keep detailed task-space knowledge in each domain pack. The shared framework
  owns contract validation, plan compilation, scheduling, reconciliation,
  evidence assembly, and generic failure semantics.
- Represent a domain catalog as a versioned set of explicitly reachable cells
  or constrained cell families. Do not blindly materialize the Cartesian
  product of every declared dimension.
- Every coverage cell has a stable domain-scoped identifier and declares the
  structural values needed to validate membership. Initial structural
  dimensions include task type, ordered required-tool sequence, read-only or
  state-changing behavior, grounding-selection pattern, constraint profile,
  difficulty class, ambiguity or expected-failure mode, and branch or recovery
  pattern when applicable.
- A domain may extend the initial dimension set through a new catalog version.
  Unknown dimensions fail closed rather than being ignored.
- Cells may declare required run features and capacity constraints. A cell is
  ineligible when its required capability, feature, tool, grounding data, or
  environment state is unavailable.
- Difficulty is derived from domain-owned structural declarations and validated
  locally. Provider-reported difficulty is not authoritative coverage evidence.
- Define named, versioned coverage profiles. A normal operator selects one
  profile instead of supplying cell-by-cell quotas. The initial product surface
  supports at least a bounded smoke profile and a representative profile.
- A coverage profile declares mandatory floors, balancing weights, permitted
  concentration, grounding-reuse policy, attempt-budget policy, and fulfillment
  semantics. Profiles may specialize by domain without moving domain semantics
  into the shared scheduler.
- Run profiles opt into coverage-driven synthesis through one coverage-profile
  reference. They may provide a small allowlisted overrides object. Overrides
  may increase or decrease declared emphasis within domain and profile bounds,
  but cannot introduce unknown cells, disable safety or verification, change
  mutation authorization, or silently expand provider spend.
- Preserve the meaning of existing run-profile versions and profiles. The new
  surface is introduced through a new version or an explicitly compatible
  optional field whose absence preserves existing behavior.
- Compile a deterministic coverage plan before remote generation. Compilation
  validates catalog and profile versions, domain identity, selected features,
  target candidate count, source-admission state, statically available
  grounding capacity, override bounds, and attempt budget.
- Expose a no-provider plan-preview operation through the normal programmatic
  and command-line run surfaces. Preview emits the same sanitized plan and
  hashes that execution would consume, or the same bounded compilation error,
  without generating or executing a candidate.
- The plan records the target accepted-sample distribution and a bounded
  attempt ceiling separately. It does not reinterpret the existing candidate
  target silently or permit unbounded replacement generation.
- Statically unsatisfiable mandatory floors fail before the first provider
  call. Dynamic underfill caused by provider, execution, verification,
  mutation-admission, or duplicate rejection is reported after bounded
  reconciliation.
- The scheduler selects mandatory underfilled cells first, then selects the
  largest normalized deficit among discretionary cells, then applies a stable
  tie-break. The exact policy and version are retained in plan metadata.
- Track planned, in-flight, accepted, rejected, and remaining counts
  separately. In-flight work prevents accidental duplicate scheduling but does
  not satisfy coverage.
- Generate one locally created assignment for each provider task contract. The
  assignment constrains allowed task type, tools, grounding scope, expected
  state shape, difficulty semantics, and other cell-owned requirements.
- Provider requests receive only the selected assignment contract and the
  minimum domain-approved grounding context necessary to fulfill it. Existing
  remote-disclosure and source-governance rules continue to apply.
- Provider responses cannot set plan ids, assignment ids, cell ids, fulfillment
  outcomes, lineage, or coverage scores. The framework derives and attaches
  them after strict parsing and local membership validation.
- A candidate that fails its assignment contract is a classified generation
  rejection. It does not silently move to a different cell even when it would
  be valid there.
- Route assigned candidates through the existing candidate-processing path.
  Contract validation, semantic mutation admission, environment isolation,
  execution, verification, exact duplicate admission, refinement, review
  routing, and dataset assembly remain authoritative.
- Only an accepted sample with locally validated assignment membership fulfills
  one planned unit. One sample cannot satisfy multiple cells merely because it
  shares attributes with them.
- Reconcile coverage after each bounded batch or processing wave. When attempt
  capacity remains, backfill the highest-priority accepted-sample deficit
  rather than generating an unrelated replacement.
- Feature-dependent assignments may use existing branching, task expansion, or
  refinement only when the run profile enables the relevant behavior and the
  domain catalog declares it. The scheduler never enables features on behalf of
  the operator.
- Separate structural coverage from lexical novelty. Instruction wording may be
  recorded in existing duplicate signatures, but raw instruction text is not a
  coverage dimension and paraphrasing alone does not create a new cell.
- Keep the exact duplicate gate unchanged. Semantic duplicate detection remains
  a separate optional policy and may later consume coverage-family evidence.
- Emit a versioned coverage evidence artifact containing sanitized catalog,
  profile, plan, scheduler, run-profile, and accepted-sample hashes; aggregate
  cell counts; bounded deficit and rejection reasons; concentration; grounding
  reuse; difficulty distribution; and fulfillment status.
- Retain assignment lineage on accepted samples and relevant rejections using
  stable identifiers and hashes. Do not retain raw prompts, raw provider
  responses, credentials, headers, host paths, unrestricted grounding rows, or
  private source payloads.
- Extend quality and representative evidence with coverage summaries without
  treating the number of generated candidates as coverage. Existing
  executable, verification, source, mutation, and release evidence remains
  separately visible.
- A diagnostic profile may complete with `incomplete` coverage and usable
  accepted samples. A coverage-driven representative claim requires all
  mandatory cells and profile thresholds to be fulfilled, in addition to every
  existing representative eligibility requirement.
- Coverage profile or catalog changes create new versions and hashes. Old
  evidence remains interpretable under its original versions.
- Start with contacts as the end-to-end tracer domain, then add mobile messages
  and workspace tasks through the same interfaces. Each initial catalog must
  expose meaningful structural variation supported by its environment rather
  than filling thirty slots with wording variants.
- Expand deterministic fixtures when the current environment cannot support the
  declared representative profile. Fixture expansion must add executable,
  independently verifiable state cases such as distinct grounding selections,
  multi-result or zero-result conditions, ambiguity, cross-step bindings, and
  recovery opportunities; it must not add arbitrary rows solely to inflate
  lexical variety.
- Treat structural-family growth under one versioned common taxonomy as the
  cross-scale diversity authority. More accepted samples or locally distinct
  coverage cells do not establish structural growth when they classify into
  families already fulfilled at the smaller target.
- Treat meaningful state-changing sequences as a high-leverage but optional
  source of structural diversity. Such a sequence counts only when its tool
  topology or bindings are structurally distinct, mutation authorization and
  argument provenance pass the configured admission policy, and an independent
  verifier confirms the resulting state. Redundant mutations and unnecessary
  tool calls do not create valid coverage.
- Do not create a new ADR for the initial implementation. The decision is a
  reversible extension of the existing domain-owned generation specification
  and shared generation kernel. Revisit the ADR threshold only if later work
  adopts a costly external representation provider or makes coverage policy a
  cross-system release authority.

## Testing Decisions

- Prefer one high, externally observable seam: a coverage-enabled run profile
  passes through the existing pipeline with a deterministic fake provider and
  produces accepted samples, rejections, assignment lineage, and coverage
  evidence. Tests assert behavior and artifacts, not scheduler helper calls or
  prompt text.
- Use one secondary pure seam for deterministic plan compilation. Given a
  domain catalog, coverage profile, selected features, target size, and bounded
  overrides, compilation must produce the same plan and hashes or the same
  bounded validation error.
- Reuse existing run-profile, domain generation, candidate-processing, quality
  report, profile-decision, release-evidence, and CLI test styles as prior art.
  Extend their public fixtures instead of creating a parallel test harness.
- Contract tests cover unknown versions and dimensions, duplicate cells,
  contradictory constraints, unavailable features, insufficient grounding
  capacity, invalid override keys or values, impossible mandatory floors, and
  attempt-budget inconsistencies.
- Scheduler behavior tests prove mandatory-first selection, deficit balancing,
  stable tie-breaking, in-flight accounting, accepted-only fulfillment, bounded
  backfill, and deterministic exhaustion.
- Provider-boundary tests prove that one assignment constrains each generated
  contract, that extra coverage or lineage fields are rejected, and that the
  provider cannot self-certify cell membership.
- Pipeline tests prove that schema rejection, semantic mutation rejection,
  execution failure, verification failure, exact duplicate rejection, and
  refinement outcomes do not fulfill coverage and retain bounded cell-level
  evidence.
- Safety tests prove that coverage pressure cannot bypass source admission,
  remote-disclosure policy, mutation authorization, tool schemas, environment
  isolation, verification, or exact duplicate admission.
- Feature interaction tests prove that branching, recovery, task expansion,
  and refinement cells are scheduled only when both the run profile and domain
  catalog allow them.
- Domain conformance tests exercise contacts, mobile messages, and workspace
  tasks through the same plan and assignment contracts. Each domain proves more
  than lexical variation by producing accepted samples in distinct structural
  cells.
- Versioned taxonomy tests classify each newly declared structural cell through
  executed sample evidence, pin its expected family features, require zero
  unclassifiable samples, and prove that the larger representative target adds
  at least one family not fulfilled by the smaller target. Cell-count growth
  alone fails this gate.
- Stateful structural-cell tests prove that the synthetic requester authorized
  the mutation, requester-controlled arguments have valid provenance, earlier
  observations bind the intended later arguments, and the verifier observes
  the declared final state. A longer trajectory without those facts is not a
  diversity success.
- Evidence tests validate exact keys, hashes, aggregate counts, cell
  concentration, grounding reuse, difficulty distribution, bounded reasons,
  redaction, and planned-versus-accepted reconciliation.
- Backward-compatibility tests prove existing profiles and default commands
  produce unchanged deterministic artifacts when no coverage profile is
  selected.
- A small fake-provider representative pilot is the required system test before
  any paid campaign. It must expose a meaningful number of distinct structural
  cells and must not satisfy the profile by paraphrasing one cell.
- A serial paid pilot uses approximately ten to twelve candidates per domain
  before a three-domain thirty-candidate campaign. The paid pilot is operational
  evidence, not a unit-test prerequisite.
- The full campaign compares structural-cell coverage, largest family share,
  grounding reuse, difficulty distribution, rejection causes, provider usage,
  executable rate, and verification rate against the prior representative
  baseline.
- The implementation hypothesis is rejected if structural coverage does not
  continue to increase as the target grows, if the scheduler repeatedly
  exhausts the same grounding cases, or if new cells pass generation but cannot
  execute and verify reliably.
- The chosen coverage dimensions must be reconsidered if structural coverage
  improves but held-out or downstream Agent evaluation shows no meaningful
  difference from a size-matched baseline.

## Out of Scope

- Implementing embedding-based or model-based semantic duplicate admission.
- Treating the current mixed provisional mutation-calibration labels as a
  release-grade human-reviewed corpus.
- Changing semantic mutation authorization, argument provenance, judge
  activation thresholds, or enforcement semantics.
- Replacing exact duplicate admission.
- Allowing coverage pressure to weaken grounding, execution, verification,
  source-governance, sandbox, or release gates.
- Requiring operators to provide a cell-by-cell matrix for normal runs.
- Optimizing arbitrary continuous multi-objective functions supplied in a run
  profile.
- Automatically learning coverage dimensions from provider output.
- Generating new tools, environments, verifiers, or executable code solely to
  satisfy an underfilled cell.
- Adding a fourth production domain.
- Distributed scheduling, external brokers, durable async queues, or worker
  services.
- Using protected held-out or downstream benchmark outcomes as online scheduler
  rewards.
- Claiming that structural coverage alone proves downstream training value.

## Further Notes

The motivating representative campaign showed that exact instruction
uniqueness can coexist with a narrow task space. Across contacts, mobile
messages, and workspace tasks, accepted samples were concentrated in only a
few task types and ordered tool sequences, while branching, task expansion,
refinement, and recovery coverage were absent. This evidence activates the
need for coverage-driven generation before the deferred
[Semantic Duplicate Detection](semantic-duplicate-detection.md) feature.

This specification extends the domain-owned semantics established by the
[Domain-Aware Representative Generation](../design-docs/domain-aware-representative-generation.md)
design. It does not replace that design's shared provider boundary, grounding
rules, strict task-contract parsing, or representative eligibility model.

The central product principle is:

> The synthesis operator declares intent and budget, the domain pack declares
> the reachable task space, and the coverage scheduler decides what useful
> candidate should be generated next.
