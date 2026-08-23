# Contacts Domain Pack Lifecycle and Second-Domain Validation

Status: specified; ready for implementation

## Problem Statement

The framework has already established `contacts` as a logical Domain Pack with
canonical capability references, a hash-bound descriptor, and compatibility
mappings for legacy Contacts artifacts.  However, Contacts still executes
through the legacy domain-bundle route.  It does not yet open a run-scoped
Domain run that owns its generation, candidate isolation, attempt, replay, and
assessment behavior.

Workspace is the only domain that has crossed that deep lifecycle and has been
validated by an explicitly authorized real-provider Release Candidate run with
a provider-free replay proof.  That is a valuable vertical proof, but it does
not establish that the common Domain Pack interface is genuinely reusable:
Workspace-specific assumptions could still be hidden in the interface,
pipeline routing, acceptance evidence, or replay behavior.

Contacts is the smallest appropriate second domain.  It has a distinct
environment, source importer, task vocabulary, and state-changing follow-up
action, while its existing canonical capabilities and historical compatibility
corpus give the work a bounded oracle.  The framework needs a current,
canonical Contacts path without rewriting or promoting historical Contacts
evidence.  It also needs a controlled way to decide whether the resulting
second-domain evidence warrants a later Mobile Messages lifecycle effort.

## Solution

Operationalize the existing Contacts Domain Pack through the same public deep
lifecycle used by Workspace: deterministic planning from an admitted source,
opening a run-scoped Domain run, run-owned generation and candidate isolation,
attempt and replay operations, and typed domain assessment.  The shared
framework remains responsible for source governance, provider selection,
orchestration, artifact writing, cumulative qualification, and external human
authority.

Create a Contacts Release Candidate acceptance path that consumes exact
Contacts Domain Pack and capability references, coverage assignments,
enforced mutation admission for follow-up recording, isolated local execution,
held-out capability evidence, release-pack verification, and a typed Contacts
assessment.  Its highest observable seam is a provider-free Contacts
acceptance proof that reconstructs the complete current evidence chain from
frozen artifacts.  A real-provider execution is a separately authorized,
bounded operation that may populate this seam only after all applicable
preconditions are satisfied.

The resulting qualification, if any, is scoped only to one exact Contacts
artifact set.  `Release Candidate` means eligibility for human publication
review; it does not establish Publishable, Training Recommended, global
semantic-mutation activation, or a claim about Mobile Messages.

## User Stories

1. As a synthesis operator, I want to select the logical `contacts` Domain Pack for a current run, so that Contacts semantics are explicit before a provider or runtime is used.
2. As a synthesis operator, I want a deterministic Contacts Domain plan from an admitted source, so that the planned capabilities, runtime, and evidence requirements are inspectable before cost is incurred.
3. As a synthesis operator, I want an invalid Contacts source, Pack reference, capability reference, or runtime reference to fail before execution, so that invalid configurations cannot produce misleading artifacts.
4. As a synthesis operator, I want Contacts fixture and governed local-source runs to enter the same deep lifecycle, so that source selection does not bypass Pack semantics.
5. As a Contacts domain author, I want contact lookup, follow-up recording, lookup recovery, and missing-contact safe failure represented as exact capabilities, so that task names and tools cannot substitute for semantic identity.
6. As a Contacts domain author, I want ordinary generated task types, recovery structure, and held-out safe-failure scenarios to remain distinct projections, so that capability evidence is not inferred from labels alone.
7. As a Contacts domain author, I want a Domain run to hide the environment, tool registry, candidate preparation, verifier, and mutation-policy composition, so that shared callers depend on one deep interface rather than a component bundle.
8. As a synthesis operator, I want each Contacts candidate attempted in isolated state rebuilt by the Domain run, so that one follow-up recording cannot affect another candidate's evidence.
9. As a synthesis operator, I want read-only Contacts candidates to retain their established behavior, so that adopting the lifecycle does not create unnecessary semantic-judge calls.
10. As a synthesis operator, I want a contact follow-up to execute only after declared mutation admission succeeds in enforce mode, so that a generated expected state cannot authorize a requester-controlled note.
11. As a synthesis operator, I want unsupported, uncertain, malformed, unavailable, or non-independent mutation-judge outcomes to reject a state-changing Contacts candidate before its first tool call, so that provider failure cannot authorize a mutation.
12. As a data curator, I want exact Contacts Pack, plan, runtime, assignment, capability, mutation, episode, verifier, and final-state bindings retained for each accepted sample, so that a future release claim is auditable.
13. As a data curator, I want rejected Contacts candidates to retain bounded rejection evidence without raw prompts, provider payloads, credentials, source content, or judge reasoning, so that failures remain diagnosable without broadening retained material.
14. As a coverage scheduler, I want accepted Contacts samples alone to fulfill Contacts capability assignments, so that a valid-looking provider response or failed attempt receives no coverage credit.
15. As a coverage scheduler, I want recovery credit to require the declared failed lookup, an admissible fallback, and a verified grounded result, so that a recovery label alone cannot establish the capability.
16. As an evaluator, I want missing-contact safe failure evaluated independently from ordinary generation, so that a successful lookup cannot conceal an unsafe missing-object behavior.
17. As an evaluator, I want held-out evaluation to consume the exact capability catalog selected in the Contacts plan, so that evaluation cannot silently assess a different Contacts meaning.
18. As an evaluator, I want a Contacts Domain assessment to return evidence or bounded insufficiency for the exact plan and artifact set, so that assessment is not mistaken for release qualification.
19. As a release manager, I want a Contacts Release Candidate to require all applicable source, contract, grounding, mutation, execution, verification, coverage, held-out, completeness, quality, and release-pack gates, so that a single passing report cannot substitute for the whole machine boundary.
20. As a release manager, I want Contacts release thresholds to be selected by the exact Contacts Pack rather than copied from Workspace, so that the two domains do not acquire accidental semantic aliases.
21. As a release manager, I want a byte-changing or identity-changing Contacts repack to become a new qualification subject, so that a prior decision cannot be carried over implicitly.
22. As a replay operator, I want Contacts replay to reject Pack, plan, source, runtime, capability, candidate, episode, verifier, membership, or evidence drift with bounded reasons, so that a replay result remains meaningful.
23. As a replay operator, I want frozen, sanitized provider responses to reproduce parsing, admission, execution, verification, assessment, and qualification without another provider call, so that regression testing does not require recurring spend.
24. As a security reviewer, I want the Contacts acceptance evidence to retain only allowlisted provider identity, configuration hashes, request/response hashes, usage, retry counts, bounded outcome summaries, and cost status, so that proof evidence remains useful without retaining secrets or unrestricted content.
25. As a synthesis operator, I want the Contacts live-acceptance command to require a fresh explicit authorization, a bounded candidate and attempt budget, and distinct generator and mutation-judge identities, so that paid calls and correlated judgment are never implicit.
26. As a synthesis operator, I want the live path to preflight the configured independent mutation judge before generation spend, so that a predictable judge-contract failure stops safely.
27. As a synthesis operator, I want an unsuccessful authorized Contacts run to write a bounded failure record and never freeze provider responses or publish a proof root, so that failed evidence cannot be mistaken for a Release Candidate.
28. As a test engineer, I want one high-level Contacts acceptance proof to verify the complete current evidence graph, so that the second-domain claim is tested at the observable boundary rather than by helper-call assertions.
29. As a test engineer, I want copied-artifact negative cases to mutate one declared Contacts fact at a time, so that Pack, runtime, source, mutation, capability, execution, and qualification failures are independently attributable.
30. As a framework maintainer, I want the shared pipeline to route a Contacts Domain run without Contacts-specific behavior leaking into provider, scheduler, artifact, or qualification code, so that the second domain tests the depth of the common interface.
31. As a framework maintainer, I want only the minimum common acceptance and replay machinery extracted from the existing Workspace proof, so that proving a second domain does not create a premature generic abstraction.
32. As a framework maintainer, I want the existing Workspace lifecycle and proof to remain behaviorally unchanged, so that a Contacts migration cannot weaken the already established real Release Candidate evidence.
33. As a compatibility reviewer, I want the frozen Contacts legacy corpus to remain readable, runnable, semantically assessed, and historical-only according to its existing four-axis results, so that current canonical evidence does not rewrite historical truth.
34. As a compatibility reviewer, I want a new canonical Contacts artifact to carry migration lineage when it originated from a legacy-compatible input, so that compatibility mapping cannot erase source identity.
35. As a reviewer of semantic-mutation evidence, I want Contacts lifecycle validation to consume but not alter the reviewed calibration corpus, held-out split, activation thresholds, or independent-judge policy, so that this feature cannot self-certify global safety activation.
36. As a product owner, I want the final Contacts proof to record explicit non-claims about Publishable, Training Recommended, Mobile Messages, and downstream utility, so that a successful second-domain result is not overstated.
37. As a product owner, I want a documented evidence-backed decision point after Contacts validation, so that Mobile Messages is expanded only if the second-domain proof reveals no incompatible seam or unresolved safety limitation.
38. As an implementation agent, I want the specification to state the boundary between current canonical Contacts evidence and legacy compatibility evidence, so that implementation work does not silently promote old artifacts into a current qualification.

## Implementation Decisions

- Treat this as an operational adoption of the existing logical `contacts` Domain Pack, not as a new domain or a rewrite of the Contacts environment.  Its logical identity remains distinct from the `contacts_fixture` runtime identity.
- Select the existing `contacts_pack_v1` descriptor only when the Contacts lifecycle validates against its exact component and runtime contracts.  A mismatch fails closed; implementation must not mutate the existing version or relabel old evidence.  Any necessary semantic change requires a separately declared immutable Pack version.
- Use the existing public Domain Pack lifecycle shape: pure planning, opening a run-scoped Domain run, run-owned generation, candidate fork, attempt, replay, and typed assessment.  The Contacts adapter may own Contacts semantics, but it must not expose a raw runtime session or a public bundle of internal components.
- Route current Contacts fixture and governed local-source execution through the Contacts Domain run once it is available.  Preserve externally observable accepted/rejected outcomes, final states, episodes, sanitization, source-governance behavior, and artifact ordering where their contracts are unchanged.
- Keep source governance, provider credentials and selection, scheduling, asynchronous orchestration, cancellation, stable merge, artifact writing, cumulative qualification, and human authority in the shared framework.  The Contacts Pack does not acquire any of those authorities.
- Bind the Contacts plan to the exact declared capability references for contact lookup, follow-up recording, contact lookup recovery, and missing-contact safe failure.  Task types, tools, coverage cells, structural families, mutation actions, and held-out tags remain separate projections.
- Make Contacts planning and opening reject unknown, duplicate, cross-Pack, unsupported-version, or hash-mismatched references before runtime construction.  A source-backed environment must also bind the admitted source identity and source-policy hash.
- Require run-owned candidate isolation for every attempt, including initial, refinement, and capability-expansion attempts.  Contact state may be rebuilt only through the Contacts run, not passed as a caller-owned mutable environment.
- Reuse the existing Contacts generation, grounding, candidate preparation, deterministic verification, and mutation-policy semantics through the Domain run.  Shared code must call the lifecycle contract rather than take a Contacts-specific shortcut.
- Reuse the established Semantic Mutation Admission contract for contact follow-up recording.  Enforce mode requires deterministic validation followed by a `supported` verdict from an independent judge; disabled and shadow modes preserve their defined behavior.  This feature neither changes activation thresholds nor treats a local or same-model judgment as global activation evidence.
- Define a versioned Contacts Release Candidate acceptance profile through the Contacts Pack's exact coverage, held-out, mutation, completeness, and machine-gate contracts.  It must prove every declared Contacts capability through the correct generated or held-out evidence path and must never borrow Workspace floors merely because the report shapes are similar.
- Carry the Contacts Pack reference, exact capability references, plan and runtime bindings, assignment membership, mutation evidence, episodes, verifier results, final state, coverage evidence, assessment, release-pack hash, and qualification subject through canonical current artifacts.  Canonical semantic fields must not carry legacy aliases.
- Build a small shared acceptance/replay seam only where Contacts and Workspace demonstrate identical needs.  Domain-specific acceptance configuration and semantics stay inside the relevant Pack adapter; shared acceptance code must not branch on domain names.
- Make the offline Contacts acceptance proof the authoritative high-level result.  It starts from immutable run and release evidence, reconstructs plan-to-qualification bindings through production contracts, and reports effective qualification separately from fixture conformance and non-claims.
- A real Contacts provider campaign is a separate explicit operator action.  It requires a fresh authorization, a bounded logical and retry-expanded physical-call budget, independent generator and judge identities, a sanitized-evidence policy, and a passed judge preflight before generation.  Unit tests and default commands remain provider-free.
- Freeze sanitized Contacts provider responses only after the run's release evidence, Contacts assessment, release-pack verification, and Release Candidate qualification independently pass.  If any prerequisite fails, retain only the bounded failure record and do not construct a real-live proof.
- Preserve the Workspace live acceptance runner and reconstructed proof as regression evidence.  Refactor only as needed to make common behavior explicit and prove that the Workspace result remains byte- and decision-compatible where its contracts have not changed.
- Preserve the Contacts legacy compatibility corpus unchanged.  Its four-axis compatibility results remain historical evidence; it cannot establish a current Contacts Release Candidate, Publishable, or Training Recommended qualification.
- No new ADR is required for this feature: it applies the accepted Domain Pack semantic-authority decision and the existing separation between framework evidence verification and external authority.

## Testing Decisions

- The primary test seam is a Contacts acceptance proof built from the highest existing observable boundary: a Pack-planned Contacts run through candidate processing, release evidence, independently verifiable release pack, typed domain assessment, cumulative qualification, and provider-free replay.
- Good tests assert stable artifacts, exact identity and hash relationships, visible qualification or bounded failure decisions, side-effect absence, and replay outcomes.  They do not assert private helper ordering, concrete class layout, prompt prose, or internal component construction.
- Add provider-free end-to-end tests with injected transport responses for successful Contacts parsing, rejected contract-valid-but-membership-invalid candidates, enforced follow-up admission, release qualification, frozen response replay, and proof reconstruction.
- Add focused contract tests for Contacts plan determinism; Pack/hash/version validation; capability/projection separation; source and runtime bindings; candidate scope drift; and bounded failure reasons.  These tests complement rather than replace the high-level proof.
- Exercise state isolation by attempting separate Contacts candidates that mutate equivalent initial environments and proving no follow-up record crosses candidate boundaries.
- Exercise the Contacts follow-up admission boundary for valid requester-supported notes and for missing provenance, unsupported notes, false contact bindings, negated requests, unavailable judges, malformed judges, and same-model configuration.  Each non-supported enforce path must prove that no state-changing tool executed.
- Exercise coverage and held-out evidence separately: accepted samples alone fulfill generated capability assignments, recovery requires a verified fallback chain, and missing-contact safe failure proves no unintended mutation.
- Exercise replay and proof negatives by copying positive artifacts and mutating exactly one declared fact for Pack, plan, runtime, source, capability, assignment, mutation, episode, verifier, coverage, assessment, release-pack, and qualification dependencies.  Each case must fail closed with its declared bounded reason while unrelated bytes stay unchanged.
- Exercise sanitization and authorization behavior: missing authorization, exhausted budget, non-independent identities, failed judge preflight, provider failure, malformed provider output, and failed release evidence produce a bounded failure record without frozen response material or a proof root.
- Run existing Workspace lifecycle, live-acceptance, and tracer-proof behavior as regression coverage whenever common acceptance machinery changes.  Existing Contacts legacy compatibility corpus tests remain the oracle for historical artifacts.
- Treat one explicitly authorized real-provider Contacts campaign as an operational acceptance activity, not as a unit-test prerequisite.  Before that activity, the full injected-transport proof and documentation validation must pass; afterward, the frozen result must be replayed and independently verified without provider access.

## Out of Scope

- Implementing the Mobile Messages Domain Pack lifecycle, a Mobile real-provider acceptance campaign, or a third-domain proof.  Mobile becomes a later decision informed by Contacts evidence.
- Adding a fourth domain, expanding Contacts task catalogs merely to increase a metric, or changing the semantic meaning of existing Contacts capabilities without a new Pack version.
- Rewriting, re-adjudicating, deleting, or promoting frozen legacy Contacts artifacts or compatibility-corpus rows into current qualification evidence.
- Changing Semantic Mutation Admission vocabulary, human-review procedure, held-out split, calibration thresholds, activation decision, or independent-judge policy.  Completing its externally gated activation is a separate effort.
- Automatically spending provider funds, storing credentials, retaining raw prompts or responses, publishing a dataset, seeking human publication approval, starting external training, or claiming downstream model improvement.
- Activating semantic duplicate detection, changing its evidence trigger, or adding a duplicate model dependency.
- Replacing local orchestration, adding distributed workers, external MCP execution, or treating acceptance scale as a reason to change concurrency policy.
- Creating a broad generic runtime abstraction beyond the common behavior proven necessary by Contacts and Workspace.

## Further Notes

- This feature follows the completed [Outcome-Validated Domain Pack](outcome-validated-domain-pack.md) effort.  That effort intentionally proved one Workspace tracer and preserved Contacts as compatibility evidence; this specification deliberately opens the next, narrower second-domain step.
- Terminology follows the [Domain Glossary](../../CONTEXT.md), especially the distinctions among Domain Pack, Domain run, compatibility assessment, historical-only evidence, Domain assessment, and Release Candidate.
- The governing architectural choices remain [ADR 0002](../adr/0002-domain-pack-semantic-authority-and-deep-interface.md) and [ADR 0003](../adr/0003-separate-evidence-verification-from-external-authority.md).
- The existing Workspace deep design and real-live acceptance evidence are implementation and test prior art, not a license to copy Workspace semantics into Contacts.
- The local tracker entry for this specification is [Contacts Domain Pack Lifecycle and Second-Domain Validation](../../.scratch/contacts-domain-pack-lifecycle/README.md).  Implementation tickets should be created from this specification after a scoped delivery breakdown; the specification itself is the canonical desired-behavior and acceptance contract.
