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
- **Domain pack:** The versioned domain-owned semantic authority and common deep
  interface for planning, generation, isolated execution, replay, and assessment.
  It hides how domain-specific environments, tools, policies, and verifiers are
  composed without forcing domains to share an internal implementation; its
  logical identity is independent of the runtime that executes it.
- **Domain Pack version:** An immutable, hash-bound composition of one Domain
  Pack's capability references and domain-owned semantic contracts. It changes
  whenever planning, execution, assessment, or evidence meaning can change.
- **Compatibility mapping:** A deterministic, source-version- and
  projection-scoped interpretation of a legacy reference as a canonical
  reference. It preserves source identity and cannot create missing evidence.
- **Compatibility assessment:** A typed judgment that distinguishes whether an
  artifact is readable, runnable, semantically equivalent, and admissible for a
  current evidence claim. Avoid an unqualified `compatible` result.
- **Compatibility corpus:** A bounded, hash-manifested set of frozen legacy
  inputs and independently reviewed expected projections used to test all axes
  of a compatibility assessment. Passing current writers cannot redefine it.
- **Historical-only evidence:** Legacy evidence that remains readable and
  verifiable under its original contracts but lacks the exact references needed
  to contribute to a current Release qualification.
- **Domain plan:** A deterministic, hash-bound statement compiled by one Domain
  Pack for an admitted synthesis intent. It binds exact capability, coverage,
  evaluation, mutation, runtime, and release-evidence requirements before
  execution begins.
- **Domain run:** An isolated execution scope opened from one exact Domain plan.
  It mediates candidate generation, attempts, and replay without transferring
  scheduling, artifact handling, or qualification authority from the shared
  framework.
- **Domain assessment:** A Domain Pack's typed interpretation of exact
  evaluation or release evidence. It can establish a domain requirement or
  evidence insufficiency, but is not itself a Release qualification.
- **Domain capability:** A stable, independently testable semantic outcome or
  safety behavior owned by one Domain Pack. Its identity combines the Domain
  Pack identity with a pack-local key and remains separate from its contract
  version, task types, tools, coverage cells, and evidence slices.
- **Domain capability reference:** An exact Domain capability identity plus the
  contract version against which an artifact or decision was produced.
- **Runtime:** A versioned execution carrier for a Domain Pack's environment and
  tools. Multiple runtimes may implement the same Domain Pack, so runtime and
  Domain Pack identities are not interchangeable.
- **Runtime feature:** A runtime support fact such as rebuild, replay, reward
  labels, or local-adapter support. It is not a Domain capability.
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
- **Local orchestration job:** An opt-in local lifecycle for running one
  validated deterministic candidate set with durable progress, a persisted
  concurrency bound, and resumable terminal outcomes. The default bound is
  one; it is not a provider queue or a dataset release.
- **Work item:** The durable execution intent for one candidate sequence
  position in a local orchestration job. A work item records pending,
  running, or completed state and an accepted or rejected terminal outcome.
- **Orchestration event journal:** The append-only, integrity-chained event
  history that rebuilds a local orchestration job and its work-item state.
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
- **Release qualification:** The highest evidence-backed claim that may be made
  about one exact artifact set. Qualifications are cumulative, but releaseability
  and downstream utility remain distinct evidence boundaries.
- **Release Candidate:** The first release qualification: an exact artifact set
  has passed the declared machine release gates and may enter human publication
  review, but is not approved for publication or recommended for training.
- **Publishable:** The second release qualification: an exact, independently
  verifiable release pack has explicit human approval or bounded risk acceptance
  for distribution under declared constraints.
- **Publishability evidence bundle:** The hash-bound machine and human evidence
  used to decide whether one exact Release Candidate may be distributed within
  a declared audience, purpose, access, retention, and redistribution scope.
- **Review resolution:** Evidence that each review finding received a valid
  disposition. Completion of review is neither risk acceptance nor publication
  approval.
- **Authority policy:** A versioned trust policy that grants authenticated
  principals bounded review, risk-acceptance, or publication-approval authority
  and declares any required separation of duties.
- **Risk acceptance:** A time-bounded, authenticated decision by an authorized
  risk owner to tolerate specified residual, non-hard-gate risks within an exact
  distribution scope.
- **Publication approval:** An authenticated decision by an authorized approver
  that binds one exact release pack, its publishability evidence, and its
  distribution scope. It establishes Publishable only while every dependency
  remains valid.
- **Training Recommended:** The third release qualification: a Publishable
  release has also met predeclared downstream experimental-validity and utility
  criteria for one named training and evaluation context.
- **Training recommendation protocol:** The immutable, pre-registered contract
  that binds an exact release, matched baseline and treatment, training identity,
  sealed benchmark, meaningful-gain rule, leakage controls, and any optional
  model-level guardrails for one Training Recommended decision.
- **External experiment owner:** The authority outside this framework that
  chooses, pre-registers, funds, and executes a downstream training experiment
  and is accountable for its benchmark access and supplied execution records.
- **External experiment evidence:** An operator-supplied, content-addressed
  bundle containing a pre-registered experiment, matched-arm manifests, and
  item-level evaluation results. The framework verifies its internal
  consistency and statistics while trusting provenance at the import boundary.
- **Training evidence verification:** The framework's bounded evaluation of an
  externally supplied training protocol and result. It does not select models,
  schedule training, hold training credentials, or attest facts it cannot
  independently verify.
- **Protocol conformance fixture:** A permanently non-qualifying, frozen test
  bundle with known inputs and expected decisions used to verify training
  evidence contracts and decision logic. It can exercise a positive decision
  path but can never establish Training Recommended.
- **Workspace tracer:** An end-to-end proof run whose real LLM generation and
  local Workspace evidence may establish Release Candidate while permanently
  non-qualifying fixtures exercise the external approval and training boundaries
  without granting Publishable or Training Recommended. It proves that
  qualification evidence connects and fails closed, not that a release was
  approved or improved a model.
- **Matched training pair:** A baseline and treatment trained from the same
  initial model under the same declared recipe, seed, and schedule, where the
  treatment replaces predeclared control records with one exact release within
  the protocol's sample-count tolerance. It is approximate-size evidence, not
  proof that token volume, compute, or every causal influence is identical.
- **Minimum meaningful gain:** The predeclared primary-effect threshold required
  for downstream utility. For Training Recommended it is more than one-percent
  relative improvement at the lower bound of a paired-bootstrap 95% confidence
  interval, not merely a positive point estimate.
- **Non-regression guardrail:** An optional model-level metric and maximum
  tolerated regression predeclared by an external training protocol. It is not
  a second sample-admission pass over an already Publishable release.
- **Sealed evaluation split:** A content-bound held-out benchmark partition
  whose instances and labels cannot influence release construction, control
  selection, training choices, thresholds, stopping, or protocol revision.
- **Workspace capability set:** The `workspace_tasks` Domain Pack independently
  names `item_search`, `task_creation`, `comment_addition`,
  `item_search_recovery`, and `missing_item_safe_failure`. Task types, tools,
  branch plans, coverage cells, and legacy fixture labels may exercise or map to
  these capabilities but are not their identities.
- **Workspace item-search recovery:** The verified semantic outcome of moving
  from a declared failed or invalid Workspace item-search attempt through an
  admissible fallback to the intended grounded item. Branch-plan presence or a
  runtime branching feature alone does not establish it.
- **Workspace missing-item safe failure:** The verified safety behavior in which
  a request for a nonexistent Workspace item terminates without unintended
  state change and with the expected bounded failure cause.
- **Contacts capability set:** The `contacts` Domain Pack independently names
  `contact_lookup`, `followup_recording`, `contact_lookup_recovery`, and
  `missing_contact_safe_failure`. Fixture task names, tool names, and held-out
  tags are scoped projections rather than capability identities.
- **Mobile Messages capability set:** The `mobile_messages` Domain Pack
  independently names `message_search`, `reminder_creation`, `draft_reply`,
  `message_search_recovery`, and `missing_message_safe_failure`. Fixture task
  names, runtime identity, and held-out tags are not capability identities.
- **Dataset release pack:** A hash-locked collection of admitted dataset
  artifacts that can be verified without rerunning generation.
- **Source admission:** The policy decision that allows a governed source bundle
  to affect an environment after provenance, license, path or network, size, and
  sandbox checks pass.
- **Lineage:** Sanitized metadata connecting a sample or report to its source,
  profile, provider role, environment, tool, and verification evidence without
  exposing secrets or raw private payloads.
