# Design the Domain Pack Interface and Seam

- **Status:** closed
- **Assignee:** Codex
- **Label:** `wayfinder:prototype`
- **Parent map:** [Outcome-Validated Domain Pack](../README.md)
- **Blocked by:** [Define Canonical Domain Capability Identity](02-canonical-domain-capability-identity.md)

## Question

What is the smallest deep Domain Pack interface that can own domain capability
semantics and supply environment, source, generation, coverage, evaluation,
mutation, runtime, and release behavior without exposing internal seams or
turning the pack into a shallow configuration aggregate?

## Prototype checkpoint

The current recommendation is a two-level lifecycle:

```text
pack.plan(intent, admitted_source) -> DomainPlan
pack.open(plan, runtime_scope) -> DomainRun
pack.assess(plan, exact_evidence) -> DomainAssessment

DomainRun.generate(request, provider_adapter?) -> Candidate
DomainRun.fork(candidate_scope).attempt(candidate, options) -> AttemptResult
DomainRun.replay(episode) -> ReplayResult
```

- `plan` is pure and validates the pack's capability projections, coverage
  semantics, evaluation requirements, runtime binding, mutation policy, and
  release-completeness requirements before side effects begin.
- `open` constructs a run from an already-governed source. Source admission,
  credentials, and provider selection remain framework concerns.
- `DomainRun` hides the environment/registry/verifier/preparer/mutation fan-out
  currently visible to the shared pipeline. `fork` exposes candidate isolation
  without exposing the underlying runtime session.
- `assess` returns typed domain evidence or insufficiency. The shared framework
  still owns final qualification, human authority, scheduling, stable merge,
  artifact writing, and orchestration recovery.
- Runtime identities and capability identities are explicit inputs and outputs;
  neither acts as an alias for the other.

Alternatives considered:

- A minimal `describe` + `run` interface is smaller in method count but absorbs
  orchestration, artifact writing, and recovery into the pack.
- One generic `project(request)` kernel is extensible but risks becoming an
  undiscoverable dictionary bus and weakens type-specific invariants.
- A wider lifecycle with a public raw runtime session preserves flexibility but
  leaks the construction seam that the pack is meant to hide.

## Prototype assets

- Source is preserved off main on the local throwaway branch
  `prototype/domain-pack-interface-seam` at commit `6c9d6e7`.
- Recover the pure model and interactive runner with:

```bash
git show 6c9d6e7:synthesis/prototype_domain_pack_interface.py
git show 6c9d6e7:scripts/run_domain_pack_interface_prototype.py
```

The prototype covers a happy path, planning-only coverage preview, projection
drift, runtime mismatch, candidate mutation rejection, and release-evidence
identity mismatch. The first two invalid bindings fail before side effects;
candidate and evidence failures return structured results without taking over
framework orchestration. The human accepted the interface and the placement of
`attempt` on `DomainRun` on 2026-08-07.

## Resolution comment

Adopt the two-level `DomainPack` / `DomainRun` interface shown above.

- `DomainPack.plan` is the pure, fail-closed compilation boundary. A plan binds
  exact pack, capability, coverage, evaluation, mutation, runtime, and release
  semantics before runtime construction or provider activity.
- `DomainPack.open` accepts only a valid plan and an already-admitted runtime
  scope. It returns an isolated `DomainRun`; it does not admit sources or select
  credentials and providers.
- `DomainRun` owns `generate`, `fork`, `attempt`, and `replay`. In particular,
  `attempt` stays on the run so the shared pipeline does not learn the pack's
  environment, registry, verifier, candidate-preparation, or mutation seams.
- `DomainPack.assess` produces typed domain evidence or an insufficiency result
  for exact inputs. It does not grant a Release qualification.
- The shared framework retains source governance, scheduling and concurrency,
  stable merge, artifact writing, recovery, final qualification, and human
  authority.
- Do not expose a generic projection request or raw runtime-session escape hatch
  in the initial interface. Add a new typed operation only when a proven use case
  cannot be expressed through this lifecycle.

This is a deep seam because callers supply intent, governed inputs, and exact
evidence while the Domain Pack hides the composition of domain-specific
generation, execution, verification, mutation, evaluation, and completeness
policies. Runtime and capability identities remain explicit and non-aliasing at
the boundary.
