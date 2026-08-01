# Domain Glossary

This glossary defines the repository's canonical domain language. It describes
terms, not package structure, implementation plans, or work status. See
[ARCHITECTURE.md](ARCHITECTURE.md) for the system map and
[docs/DESIGN.md](docs/DESIGN.md) for detailed contracts.

## Core Terms

- **Candidate task:** A proposed agent task together with the intent, policy
  hints, expected outcome, and expected state needed to execute and verify it.
- **Synthetic task requester:** The represented requester whose intent appears
  in a candidate task's task instruction.
- **Synthesis operator:** The person or system that configures and runs data
  synthesis. Operator configuration does not authorize state changes inside a
  candidate task.
- **Task instruction:** The user-facing natural-language request inside a
  candidate task. It expresses the synthetic task requester's intent, not the
  synthesis operator's intent.
- **Domain pack:** A domain-owned bundle of environment construction, tools,
  task semantics, generation policy, verification behavior, and runtime
  metadata. Contacts, mobile messages, and workspace tasks are the current
  deterministic domain packs.
- **Environment:** Executable, isolated state against which tools run. An
  environment is rebuilt per candidate when isolation is required.
- **Tool:** A typed operation over an environment, with a declared input schema
  and deterministic result contract for local fixture paths.
- **Trajectory:** The ordered actions, observations, state transitions, and
  final response produced while attempting a candidate task.
- **Episode:** Sanitized runtime evidence for one task execution, suitable for
  replay, quality scoring, and reward-label derivation.
- **Verifier:** An independent check that compares execution evidence and final
  state with the candidate's declared expected outcome.
- **Accepted sample:** A candidate whose contracts, execution, final answer,
  expected state, and quality gates all pass. Generation alone does not make a
  candidate an accepted sample.
- **Rejection:** A candidate that fails generation, contract, execution,
  verification, grounding, or quality admission, recorded with a bounded reason.

## Mutation Safety Terms

- **State-changing action:** A tool action whose successful execution creates or
  modifies durable environment state, including draft or pending records.
  Read-only lookup and search actions are not state-changing actions.
- **Mutation authorization:** Evidence in the task instruction that the synthetic
  task requester asked for a particular state-changing action. A task type,
  policy hint, or expected state cannot independently authorize an action the
  instruction omits.
- **Requester-controlled mutation argument:** An argument that determines the
  human-meaningful content, target, priority, timing, or scope of a state change.
  Such an argument must not be invented solely to satisfy a generated contract.
- **Mutation argument provenance:** The declared origin of a requester-controlled
  mutation argument: instruction, tool observation, declared default, or
  deterministic derivation. The origin set is closed within one contract
  version and may be extended only through a new versioned contract.
- **Mutation authorization record:** Evidence that pairs each state-changing
  action with mutation authorization and each requester-controlled mutation
  argument with mutation argument provenance for one candidate task.
- **Mutation admission:** The pre-execution decision that a state-changing
  candidate has valid authorization and supported argument provenance. Read-only
  candidates do not require mutation admission.
- **Semantic mutation judge:** An independent semantic verifier that decides
  whether a task instruction supports a declared state-changing action and its
  requester-controlled arguments after deterministic prerequisites pass. It may
  recognize semantic equivalence, but cannot override missing authorization,
  missing provenance, invalid references, or invalid contracts.
- **Semantic mutation verdict:** A structured `supported`, `unsupported`, or
  `uncertain` decision over mutation authorization and argument provenance,
  accompanied by bounded reason codes and evidence references. Model-reported
  confidence and free-form rationale are not admission evidence.

## Run and Release Terms

- **Run profile:** Versioned input that selects a domain, generation mode,
  candidate target, purpose, feature flags, and optional governed source.
- **Coverage dimension:** A domain-owned structural axis used to distinguish
  training experiences, such as task type, tool sequence, state behavior,
  grounding pattern, constraint profile, difficulty, ambiguity, or recovery
  behavior.
- **Structural family:** An equivalence class of executed samples under one
  versioned structural taxonomy. A family may distinguish task type, ordered
  tool sequence, selector-field shape, state behavior, cross-step observation
  bindings, and recovery transitions; instruction wording, provider identity,
  coverage assignment, and coverage-cell identity do not define a family.
- **Structural diversity:** The distribution of accepted samples across
  independently executable and verifiable structural families. A meaningful
  state-changing sequence can be a high-leverage source because it combines
  tool topology, state transition, cross-step binding, and final-state
  verification. State change alone is not sufficient: redundant tool calls,
  extra cell names, grounding substitutions, and instruction paraphrases do
  not establish structural diversity.
- **Coverage cell:** One stable, reachable combination of coverage-dimension
  values that a domain pack can generate, execute, and verify.
- **Coverage catalog:** A versioned domain-pack declaration of reachable
  coverage cells, compatibility constraints, grounding capacity, and
  difficulty semantics.
- **Coverage profile:** A named, versioned synthesis policy that converts an
  operator's purpose and target size into coverage floors, balance, reuse, and
  attempt-budget requirements without requiring cell-by-cell configuration.
- **Coverage plan:** The deterministic, hashable target distribution compiled
  from a run profile, coverage profile, domain catalog, available features,
  and admitted environment capacity before generation.
- **Coverage assignment:** One locally issued requirement for a candidate to
  satisfy a specific coverage cell within a bounded grounding scope. Provider
  output cannot self-assert assignment fulfillment.
- **Coverage scheduler:** The framework component that selects mandatory and
  underfilled coverage assignments, tracks in-flight work, and performs
  bounded deficit backfill.
- **Coverage fulfillment:** The accepted-sample evidence that the mandatory
  cells and distribution requirements in a coverage plan were satisfied.
  Generated, rejected, or merely executable candidates do not fulfill
  coverage.
- **Diagnostic run:** A run intended to test behavior or collect evidence; it is
  not eligible to establish dataset release readiness.
- **Representative run:** A run that satisfies declared scale, provenance, and
  generation-policy requirements for cross-domain evidence. Representative does
  not mean releaseable.
- **Release candidate:** A profile and artifact set evaluated against explicit
  coverage, quality, provenance, and reproducibility gates.
- **Dataset release pack:** A hash-locked collection of admitted dataset
  artifacts that can be verified without rerunning generation.
- **Source admission:** The policy decision that allows a governed source bundle
  to affect an environment after provenance, license, path or network, size, and
  sandbox checks pass.
- **Lineage:** Sanitized metadata connecting a sample or report to its source,
  profile, provider role, environment, tool, and verification evidence without
  exposing secrets or raw private payloads.
