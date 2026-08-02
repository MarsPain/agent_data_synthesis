# Data

## Canonical Entities

- **Seed:** source material, domain description, task taxonomy, or prior accepted sample used to start generation.
- **Run Profile:** versioned local-run configuration that names a profile id,
  dataset version, seed metadata, generation mode, target candidate count when
  applicable, profile purpose, supported feature flags, and, for
  `run_profile_v2`, an optional governed local JSON source declaration for
  supported domains. Any supported version may opt into the compatible
  `coverage_profile` reference described below; its absence preserves the
  existing profile meaning. Profile purpose is one of `diagnostic_probe`,
  `release_candidate`, or `benchmark`.
- **Coverage Profile Reference:** optional run-profile object with exact
  `profile_id`, `version`, and positive `target_accepted_sample_count` fields
  plus optional `overrides.balance_weights`. Overrides may reference only cells
  selected by the named profile and must remain within its declared positive
  weight bound. The explicit accepted-sample target is never inferred from
  `generation.target_candidate_count`. For a coverage-enabled profile, the
  candidate target must instead equal the attempt ceiling derived from the
  selected coverage profile; profiles without coverage retain their existing
  meaning.
- **Coverage Plan:** sanitized `coverage_plan_v1` preview artifact compiled
  before generation from one domain-owned catalog, named coverage profile,
  enabled features, accepted-sample target, admitted aggregate capacity, and
  bounded overrides. The plan records the target distribution and attempt
  ceiling separately.
- **Coverage Assignment:** locally issued `coverage_assignment_v1` requirement
  for exactly one planned cell and one bounded grounding unit. Its stable hash
  binds plan identity, assignment ordinal, cell dimensions, and grounding hash.
  Providers receive the assignment contract but cannot return locally owned
  assignment or coverage evidence.
- **Coverage Evidence:** automatically written `coverage_evidence_v1` for a
  coverage-enabled run. It hash-binds the catalog, coverage profile, compiled
  plan, scheduler semantics, sanitized run profile, issued assignments,
  accepted samples, and rejections. It reconciles planned, attempted,
  generated, accepted, rejected, and remaining counts per cell; records bounded
  rejection and deficit reasons; and publishes sanitized structural-family,
  grounding-reuse, difficulty, exact-duplicate, and fulfillment summaries.
  Partial diagnostic output remains valid with `fulfillment.status:
  incomplete`.
- **Structural Family:** one deterministic equivalence class emitted by
  `representative_structural_taxonomy_v1` from executed task type, ordered
  required-tool sequence, selector-field shape, state behavior, cross-step
  bindings, and recovery signature. Instruction text, provider identity,
  coverage assignment, and coverage-cell identity are excluded.
- **Structural Taxonomy Comparison:** sanitized
  `structural_taxonomy_comparison_v1` evidence that binds one taxonomy identity
  and hash to classified, unclassifiable, distinct-family, largest-family, and
  concentration counts for two sample sets. It is the like-for-like
  cross-scale structural comparison; it does not replace execution,
  verification, safety, release, or downstream evidence.
- **Source Record:** provenance contract for fixture, synthetic, transformed, or
  external/local-file material, including source id, sanitized origin reference,
  content hash, license label, retrieval timestamp when applicable, and
  retention/export eligibility.
- **License Policy Decision:** explicit allow, reject, or review-required
  decision for a source record.
- **Network Policy:** default-deny external-source access policy with explicit
  enablement, host allowlist, request budget, and source-event requirement.
- **Sandbox Policy:** external-source handling policy that records filesystem
  isolation, generated-code exclusion, and secret-redaction expectations.
- **Source Event:** sanitized audit record for accepted or rejected source
  material, fetch attempts, fetch outcomes, and environment-source admission. It
  stores hashes, aliases, outcomes, and rejection causes, never raw payloads or
  credentials.
- **Fetched Source Request:** opt-in HTTPS request contract with URL, exact host
  allowlist, request budget, timeout, maximum bytes, expected content type,
  license label, and source-audit requirement.
- **Fetched Source Result:** sanitized fetch result with source id, origin alias,
  retrieval timestamp, content hash, content type, byte count, and policy
  outcome.
- **Contacts Environment Input:** typed contacts rows and optional follow-up rows
  derived from an admitted source bundle, plus source bundle id, source policy
  hash, and validation errors. The deterministic default fixture retains six
  rows, while the opt-in representative v2 fixture carries fifteen
  independently selectable rows under the `example.test` domain.
- **Mobile Messages Environment:** deterministic synthetic phone-like fixture
  with message threads, messages, reminders, and draft replies. It uses
  `environment.id: mobile_messages_fixture` and supports checkpoint/restore and
  candidate-local rebuilds without real mobile OS access. Its expanded
  representative fixture provides sixteen bounded grounding selections,
  including one deterministic multi-result selection.
- **Workspace Tasks Environment:** deterministic synthetic workspace fixture
  with projects, task records, lightweight documents, and comments. It uses
  `environment.id: workspace_tasks_fixture`, stores local SQLite state, supports
  checkpoint/restore and candidate-local rebuilds, may be built from a governed
  profile-local workspace JSON input, and does not read browser profiles,
  credentials, network resources, or real workspace data. Its representative
  grounding surface provides sixteen bounded project, task, document, and
  comment selections.
- **Seed Transformation:** bounded expansion record that maps a source seed to a
  target taxonomy node, capability target, and intended difficulty movement.
- **Environment:** executable stateful world with reset/checkpoint behavior.
- **Runtime Metadata:** internal lifecycle record for an environment runtime. It
  records runtime id/version, environment id/version, reset recipe class, state
  backend, checkpoint strategy, and optional sanitized source/sandbox/adapter
  summaries. It deliberately excludes dataset version, profile decisions,
  release status, provider prompts, raw payloads, credentials, environment
  variables, and host paths.
- **Runtime Capability Descriptor:** `awm_runtime` registry record for runtime
  identity, domain id, replay/reward eligibility, checkpoint/rebuild support,
  local-adapter support, state-changing tools, task taxonomy, optional replay
  rebuild seed, and sanitized descriptor metadata. Contacts, mobile message,
  and workspace task fixtures declare opt-in local-adapter support through
  repository-owned descriptors in `synthesis.runtime_registry`; the descriptor
  primitive itself remains package-neutral. It is not dataset release,
  profile promotion, provider prompt, credential, raw source, or host-path
  metadata. Runtime capability lookups use the sanitized status vocabulary
  `supported`, `unsupported`, `insufficient_evidence`, and `malformed`; consumer
  reports map those statuses onto their existing report checks.
- **Runtime Action Request:** internal `runtime_action_request_v1` envelope for
  executing one tool action against a runtime session. It contains runtime id,
  tool name, sanitized arguments, deterministic argument hash, and optional
  action id. It excludes raw source payloads, prompts, credentials, environment
  variables, profile paths, and host paths.
- **Runtime Action Result:** internal `runtime_action_result_v1` envelope for
  the outcome of one runtime action. It records runtime id, tool name, status,
  sanitized observation, observation hash, state-change hash, error class, side
  effect summary, and optional action id.
- **Runtime Session:** `awm_runtime` in-process runtime-facing object that wraps
  a domain environment and tool registry with list-tools, execute-action,
  checkpoint/restore, and rebuild semantics. It is internal infrastructure, not
  an external MCP server.
- **Tool:** typed callable action exposed to the Agent.
- **Mobile Tool:** domain-owned callable in the mobile fixture. Current tools
  are `search_phone_messages`, `create_phone_reminder`, and
  `draft_message_reply`; draft tools create local draft state only and do not
  send real messages.
- **Workspace Tool:** domain-owned callable in the workspace fixture. Current
  tools are `search_workspace_items`, `create_workspace_task`, and
  `add_workspace_comment`. Search is read-only; task and comment creation are
  state-mutating and expose sanitized state-change summaries.
- **Task:** user-facing goal plus structured constraints and difficulty metadata.
- **Task Contract:** internal execution/verification view derived from
  `CandidateTask`. It separates task intent, execution policy hints, expected
  final-answer evidence, and expected environment-state checks. It is validated
  before execution and is not exported in default public artifacts.
- **Task Suggestion:** intent-level task proposal with required capabilities,
  target tools, constraints, verification expectation, suggestion outcome, and
  role lineage.
- **Edited Task:** task-editor output that either contains a valid
  `CandidateTask` mapping ready for normal validation or a classified edit
  rejection.
- **Solution Policy:** selected or generated ordered tool-use plan for satisfying
  a task.
- **Branch Plan:** bounded behavior-tree-like plan with ordered branch attempts,
  fallback relationships, terminal outcomes, and per-branch tool steps.
- **Branch Outcome:** audit record for one branch attempt, including selected
  status, failure cause, retry/refinement eligibility, depth, and branch-local
  trajectory events.
- **Trajectory:** ordered interaction events including tool calls, observations,
  state changes, and final responses.
- **Episode Log:** `awm_runtime` evidence view derived from a trajectory. It records
  ordered transitions, deterministic hashes over sanitized JSON payloads,
  runtime identity, policy identity, verifier identity, and accepted/rejected or
  failed outcome. It is kept internal by default and is written to
  `episodes.jsonl` only when episode-quality, episode-replay, or reward-label
  reporting is explicitly requested.
- **Episode Quality Report:** opt-in data-quality consumer report over
  `episode_log_v1`. It validates and scores episode transition completeness,
  descriptor-derived state-change support, runtime identity, and
  accepted-outcome consistency without reading or writing raw prompts, raw
  payloads, tool arguments,
  observations, final-response text, credentials, or host paths.
- **Episode Replay Report:** opt-in execution-consistency consumer report over
  `episode_log_v1`. It uses the runtime registry to determine replay support,
  state-changing tools, and rebuild seeds, rebuilds fresh supported fixture
  runtimes, re-executes action transitions through
  `RuntimeSession.execute_action(...)`, compares replayed
  observation/state-change hashes, and writes sanitized
  summaries without raw prompts, payloads, tool arguments, observations,
  final-response text, credentials, or host paths.
- **Reward Label:** opt-in deterministic label record over `episode_log_v1`.
  It combines episode outcome, contract validity, execution evidence,
  descriptor-derived state-change support, and replay consistency into a bounded
  scalar reward and preference-group metadata. It is evidence for future
  reward/RL workflows, not a trained reward model, release gate, or downstream
  quality claim.
- **Reward Label Report:** opt-in summary over reward labels. It records label
  coverage, usable/excluded/insufficient-evidence counts, sanitized per-label
  summaries, and a local decision status without exposing raw trajectory,
  prompt, source, credential, or host-path content.
- **Diagnostic Rollout:** repo-local scripted-policy execution through
  `awm_runtime.RuntimeSession`. It emits sanitized `episode_log_v1` records for
  diagnostics, replay, and reward-label compatibility. It is not RL training,
  online policy optimization, release admission, or profile promotion.
- **Verifier:** independent checks that decide whether a trajectory satisfies the task.
- **Refinement Attempt:** bounded critic diagnosis plus one revised candidate or
  solution policy used to rerun a failed candidate.
- **Role Definition:** registry entry that names a generation or verification
  role, owner module, output type, enabled state, retry policy, and lineage
  fields.
- **Capability Gap:** structured diagnosis for a task or solution policy that
  requires a missing, incompatible, or unavailable tool capability.
- **Tool Proposal:** structured `tool_generation` output that describes a
  requested tool contract, side-effect class, environment dependency, verifier
  implication, safety notes, and lineage without executable code.
- **Tool Admission:** local curated decision that either admits a known tool
  implementation into the active registry or rejects the proposal with a reason.
- **Adapter Manifest:** `synthesis.mcp`-owned local MCP-compatible description
  of an environment/tool bundle, including adapter identity, protocol label,
  environment metadata, source-policy hash, supported operations, tool schemas,
  side effects, reset/checkpoint support, and verifier implications.
- **Adapter Call Envelope:** tool-call request and result records routed through
  the local adapter boundary. Result envelopes record observation payloads,
  side-effect summaries, execution status, and classified adapter errors.
- **Adapter Lineage:** sample or rejection metadata showing which adapter,
  protocol label, operation, tool, call id, and execution outcome participated in
  an opt-in adapter run.
- **Sample:** accepted training record assembled from the above entities.
- **Dataset Version:** manifest that groups samples, schemas, generator configs, and quality reports.
- **Coverage Manifest Binding:** coverage-only
  `coverage_manifest_binding_v1` metadata that records the semantic evidence
  identity and exact byte hashes for `coverage_evidence.json`,
  `samples.jsonl`, and `rejections.jsonl`. Profile and representative
  consumers verify this sanitized chain before accepting fulfillment; they do
  not parse sample or rejection content.
- **Mutation Admission Report:** deterministic aggregate counts over retained
  admission evidence, grouped by domain, task type, action, provenance,
  verdict, reason, provider outcome, and model-independence status.
- **Mutation Calibration Review Packet:** standalone
  `mutation_calibration_review_packet_v1` containing normalized judge inputs,
  frozen action-policy snapshots, evidence references, criticality, sampling
  strata, tuning/held-out assignments, contract versions, and hashes for 200
  balanced cases. Its status is `pending_human_review`; it is not reviewed
  evidence.
- **Mutation Calibration Split Freeze:** standalone
  `mutation_calibration_split_freeze_v1` binding the packet hash, every
  normalized-input hash, every split assignment, and the 60 held-out case ids
  before prompt or policy tuning.
- **Reviewed Mutation Calibration Corpus:** standalone
  `reviewed_mutation_calibration_corpus_v1` produced only after a complete set
  of valid `human_mutation_calibration_label_v1` records is imported. It binds
  the packet, freeze, ordered human labels, reviewer provenance, and final
  corpus hash.

## Quality Metrics

Track metrics at sample, batch, and dataset levels:

- Executable rate: fraction of candidates that run without infrastructure or schema errors.
- Success rate: fraction of executable candidates that satisfy verifiers.
- Instruction clarity: ambiguity and missing-slot assessment.
- Response relevance: final response matches the task and output contract.
- Logical consistency: task, actions, observations, and answer do not contradict.
- Distribution coverage: coverage across domains, tools, difficulties, and personas.
- Long-tail capture: explicit count of edge cases, failures, retries, and recovery paths.
- Curriculum effectiveness: alignment between task difficulty progression and model learning or verifier pass-rate curves.
- Transfer gain: downstream improvement on held-out Agent tasks after training or evaluating with a dataset version.
- Cost: model calls, tokens, wall time, CPU/GPU time, and aggregate
  release-review minutes when an explicit resolution report exists. Recorded
  minutes are workflow-cost evidence, not reviewer-effectiveness or model-gain
  evidence.

Metrics must be sliceable by domain, task type, difficulty level, tool
combination, generator role, verifier type, role name, role output type,
capability-gap type, proposed tool, proposed tool side-effect class, proposal
outcome, branch depth, selected branch, branch outcome, fallback count, and
seed-transformation type, taxonomy node, suggestion outcome, editor action, edit
rejection cause, source kind, license policy outcome, external-source
eligibility, source rejection cause, environment-source admission outcome,
adapter id, adapter protocol, adapter execution outcome, adapter rejection cause,
run-profile id, generation mode, run-profile schema version, and dataset
version. Dataset reports should preserve trends over time so regressions are
visible instead of hidden inside aggregate averages.

## Dataset Output Contract

The default training export writes accepted samples, rejected candidates, a manifest,
and a quality report:

- `samples.jsonl`: accepted training records.
- `rejections.jsonl`: rejected candidate records with classified causes and retry
  eligibility in `details.retry_eligible`.
- `manifest.json`: dataset counts, artifact names, lineage/version summaries, and
  aggregate quality rates.
- `quality_report.json`: dataset-level counts, rates, rejection-cause counts, and
  deterministic metric slices. Coverage-enabled runs add only the sanitized
  `coverage_quality_summary_v1`; non-coverage reports retain their previous
  shape.
- `coverage_evidence.json`: automatic hash-bound evidence for coverage-enabled
  execution. It is absent for non-coverage runs.
- `coverage_plan.json`: the compiled plan for coverage-enabled execution.
- `parent_comparison.json`: when both compared quality reports carry coverage,
  adds evidence identities and deltas for structural-family count and
  concentration, grounding reuse, and difficulty, plus both fulfillment
  statuses. Non-coverage comparisons retain their previous shape.
- `tool_proposals.jsonl`: optional proposal-event records with the original
  capability gap, structured proposal, and local admission decision.
- `source_events.jsonl`: optional source-audit records written when source
  auditing is enabled.
- `sandbox_audits.jsonl`: optional generated-code sandbox audit records written
  only when the deterministic sandbox fixture is explicitly enabled.
- `evaluation_report.json`: optional held-out benchmark report written only
  when explicitly requested.
- `profile_decision_report.json`: optional benchmark decision report written
  only when explicitly requested for a profile run.
- `dataset_release_report.json`: optional dataset release admission report
  written only when explicitly requested after evaluation and profile decision
  reports are available.
- `mutation_admission_report.json`: automatically written for
  `run_profile_v4` admission runs. It contains bounded aggregate counts only;
  samples and rejections retain the per-candidate evidence contract.
- `release_quality_audit.json`: optional release quality evidence report
  written only when explicitly requested after a dataset release report is
  available.
- `review_queue.jsonl`: optional candidate-time queue of reviewable rejected
  candidates using `human_review_record_v1`.
- `release_review_queue.jsonl`: separate optional release-audit queue using
  `release_review_item_v1`, written only for opt-in `watch` evidence.
- `review_decisions.jsonl`: explicit local reviewer-owned
  `review_decision_v1` input. The pipeline does not create or attach it.
- `review_resolution_report.json`: optional aggregate-only
  `review_resolution_report_v1` written by the offline resolution consumer.
- `mutation_calibration_review_packet.json` and
  `mutation_calibration_split_freeze.json`: standalone deterministic
  calibration export artifacts. They are not default pipeline outputs or
  manifest artifacts.
- `representative_mutation_activation_gate.json`: standalone final framework
  activation/no-go evidence. It binds the reviewed activation report, fresh
  representative enforce campaign, mutation-safe manifest checks, protected
  historical-campaign digest, model lineage, costs, failures, and limitations.
  It always records dataset release readiness separately.
- `human_labels.jsonl`: reviewer-owned calibration input. The exporter never
  creates it and the importer never treats generated or judge-produced records
  as human ground truth.
- `reviewed_mutation_calibration_corpus.json`: standalone validated import
  output. It is written only after all frozen cases have exactly one valid
  direct-human label.
- `dataset_release_pack.json`: optional hash-locked release pack written only
  when explicitly requested after a dataset release report passes.
- `dataset_release_card.md`: optional human-readable release card written only
  when explicitly requested after a dataset release report is available.
- `episodes.jsonl`: optional internal episode evidence export written only when
  `--write-episode-quality-report`, `--write-episode-replay-report`, or
  `--write-reward-label-report` is explicitly requested. It contains validated
  `episode_log_v1` records aligned to admitted samples and non-duplicate
  rejected execution attempts.
- `episode_quality_report.json`: optional deterministic quality report over
  `episodes.jsonl`, written only when explicitly requested. It is not a dataset
  release, profile-promotion, reward-model, or downstream model-quality proof.
- `episode_replay_report.json`: optional deterministic executable replay report
  over `episodes.jsonl`, written only when explicitly requested. It is package
  boundary evidence for runtime extraction decisions, not a dataset release,
  profile-promotion, reward-model, or downstream model-quality proof.
- `reward_labels.jsonl`: optional deterministic scalar and preference-ready
  label export over `episodes.jsonl`, written only when
  `--write-reward-label-report` is explicitly requested. It is not reward-model
  training, RL rollout collection, release admission, profile promotion, or
  downstream model-quality proof.
- `reward_label_report.json`: optional label coverage and decision summary over
  `reward_labels.jsonl`, written only when explicitly requested.
- `orchestration/<job-id>/job.json`, `work_items.jsonl`, and `events.jsonl`:
  opt-in local serial-orchestration state using the versioned
  `orchestration_job_v1`, `orchestration_work_item_v1`, and
  `orchestration_event_v1` contracts. These records contain durable job
  progress and normalized provisional outcomes from the existing pipeline
  boundary; sensitive provider envelopes, credentials, secret-like values,
  and host paths are rejected before journaling. Job records also bind a
  normalized configuration identity, declared authorization limits, and a
  hash-only output owner. The sibling local lock is exclusive and is not
  treated as dataset state; stale-lock recovery is explicit and validates the
  durable journal before takeover. They remain separate from core dataset
  artifacts and are never attached to a dataset manifest or release pack.

### Mutation Calibration Import Contract

The exporter assigns 40 cases to each current state-changing action. Each case
hash-binds its normalized input, action policy, referenced evidence, criticality,
scenario tag, and split. The packet contains 120
`unsupported_or_adversarial` sampling strata and 80 supported-candidate strata;
these are construction strata, not human ground truth. Exactly 60 cases are
assigned to `held_out`. The separate freeze repeats held-out ids and
normalized-input hashes so any later input or assignment change fails import.
Current `legitimate_defaults` and `deterministic_derivations` cases bind
supplemental evidence to versioned system-managed field declarations (for
example `created_at` defaults and deterministic record identifiers); they do
not invent requester-content defaults that the v1 mutation policies forbid.

Each line of the reviewer-owned `human_labels.jsonl` must have exactly this
versioned shape:

```json
{
  "schema_version": "human_mutation_calibration_label_v1",
  "corpus_version": "mutation_calibration_corpus_v1",
  "case_id": "mutation_calibration_case:contact_followup_record:literal_support:alpha",
  "case_hash": "sha256:<64 lowercase hex characters>",
  "ground_truth": "supported",
  "reviewer_provenance": {
    "reviewer_id": "reviewer.alias",
    "reviewed_at": "2026-07-25T09:30:00Z",
    "review_method": "human_direct_review",
    "human_review_attestation": "I directly reviewed this case and did not use generated or judge-produced labels as human ground truth."
  }
}
```

`ground_truth` is exactly `supported`, `unsupported`, or `uncertain`. The
reviewer id is a bounded alias and `reviewed_at` is UTC. The review method and
attestation are fixed contract literals: provider-, generator-, or
judge-produced methods cannot be encoded as human review. Import requires one
label for every frozen case and rejects extras, duplicates, changed case hashes,
invalid labels, missing provenance, split drift, input drift, or a mismatched
packet/freeze. Only a successful complete import writes a corpus whose
`review_status` is `human_reviewed`.

Internal task contracts are deliberately absent from default exports. Public
accepted-sample and rejection schemas still expose the existing task,
trajectory, verifier, quality, and lineage fields; `CandidateTask.export()`
remains the compatibility shape for candidate records. Contract validation may
reject unsafe or unsupported internal task/policy/verifier combinations before
execution, but it does not add `task_contract`, raw expected state, or policy
hint payloads to `samples.jsonl`, `rejections.jsonl`, episode quality reports,
or episode replay reports.

```json
{
  "sample_id": "sample_...",
  "dataset_version": "dataset_...",
  "environment": {"id": "...", "version": "...", "source_provenance": {}},
  "tools": [{"name": "...", "schema": {}, "version": "..."}],
  "task": {"instruction": "...", "constraints": {}, "difficulty": {}},
  "trajectory": [{"type": "action", "tool": "...", "arguments": {}}],
  "final_response": "...",
  "verification": {"passed": true, "checks": []},
  "quality": {"scores": {}, "tags": []},
  "lineage": {"seed_ids": [], "generator": {}, "source_provenance": {}, "solution_policy": {}, "adapter": [], "refinement": {}, "verifier": {}}
}
```

`manifest.json` must include artifact references for `samples`, `rejections`, and
`quality_report`. When tool proposal, parent comparison, or review routing is
enabled, it also references `tool_proposals`, `parent_comparison`, and
`review_queue`. Coverage-enabled execution references `coverage_plan`; local
preview-only coverage commands do not write a dataset manifest. When source
auditing is enabled, it references
`source_events`; manifests also include `source_policy_hashes` when samples or
source-gated rejections carry source provenance. When the generated-code sandbox
fixture is enabled, the manifest references `sandbox_audits`. When held-out
evaluation is explicitly requested, the manifest references `evaluation_report`.
When profile decision reporting is explicitly requested, the manifest references
`profile_decision_report`; if both reports are requested, the profile decision
report records the evaluation input name and held-out evidence summary.
When dataset release reporting is explicitly requested, the manifest references
`dataset_release_report`. This report is absent by default and does not change
candidate processing, evaluation, or profile-promotion behavior.
When dataset release pack writing is explicitly requested, the manifest
references `dataset_release_pack` before the pack computes the final manifest
hash. The pack is absent by default and can be written only after
`dataset_release_report.json` passes dataset release admission.
When release quality audit or dataset release card writing is explicitly
requested, the manifest references `release_quality_audit` and
`dataset_release_card` respectively. Both artifacts are absent by default and
do not change candidate admission, profile promotion, or dataset release
admission.
When release-review queue writing is explicitly requested and the audit status
is `watch`, the manifest references `release_review_queue`. The offline
resolution consumer may later reference `review_resolution_report`. It never
attaches the local reviewer-owned `review_decisions.jsonl`. Both generated
review artifacts are absent by default and cannot change candidate admission,
quality/evaluation/profile reports, dataset release admission, semantic
duplicate decisions, or async-orchestration decisions.
When episode-quality reporting is explicitly requested, the manifest references
`episodes` and `episode_quality_report`. These references are absent by default
and do not change `samples.jsonl`, `rejections.jsonl`, release admission, or
profile promotion.
When episode-replay reporting is explicitly requested, the manifest references
`episodes` and `episode_replay_report`. These references are absent by default
and do not change `samples.jsonl`, `rejections.jsonl`, release admission,
profile promotion, or reward/RL workflows.
When reward-label reporting is explicitly requested, the manifest references
`episodes`, `reward_labels`, and `reward_label_report`. These references are
absent by default. Episode-quality and episode-replay evidence may be computed
in memory for scoring, but their artifacts are referenced only when their own
flags are explicitly requested. Reward labels do not change `samples.jsonl`,
`rejections.jsonl`, release admission, profile promotion, or reward/RL
workflows.

When a run is configured by a `run_profile_v1` file, `manifest.json` includes an
optional `run_profile` object. This object is sanitized metadata only:
`schema_version`, `profile_id`, `generation_mode`, `profile_purpose`,
`target_candidate_count`, `config_hash`, and `enabled_features`.
`deterministic_scale_probe` and `mobile_fixture` profiles default to
`diagnostic_probe`; `foundation_fixture` and `llm` profiles default to
`release_candidate` when the field is omitted. The purpose participates in the
profile config hash because it changes release eligibility. The metadata must
not copy raw profile files,
source payloads, authorization headers, provider prompts, API keys, or other
secret-like fields. Non-profile runs omit `run_profile`.

`run_profile_v2` preserves the same manifest metadata and may add
`run_profile.source` after source admission. That summary contains only `kind`,
`source_id`, `content_hash`, `license_label`, and `source_policy_hash`.
Supported profile-local source kinds are `local_contacts_json` for the contacts
domain, `local_mobile_messages_json` for `mobile_messages_fixture`, and
`local_workspace_tasks_json` for `workspace_tasks_fixture`. The profile-local
source path is used only at runtime to read the declared JSON file relative to
the profile directory; manifests, quality reports, source events, and rejection
metadata must not persist raw local paths, raw contacts payloads, raw mobile
message payloads, mobile message bodies, raw workspace document bodies, or raw
task/comment content.

`run_profile_v3` is the representative remote-generation contract. Its manifest
adds `generation_contract`: spec version, `synthetic_fixture` policy,
target/generated counts, fulfillment, computed eligibility, fixed reason codes,
and a grounding-context hash computed over the full spec grounding context, not
a per-batch window. Provider calls remain capped at five candidates;
contacts uses five while mobile and workspace use two. Every call receives a
deterministic one-based batch index and candidate-ID prefix. Each batch focuses
a single task type by rotation, renders each grounding list as a sliding
window of the domain-declared `grounding_window_size`, and carries a bounded
exclusion list of up to twenty recent prior instructions. The complete
machine-readable output contract is derived from the selected domain
specification. Each task type declares the observation source and fields that
may support its final answer plus the exact required-capability list; provider
records must copy those capabilities exactly. Mutating task types also own one registered
state-mutating tool and exact expected-state items. A mutating task type may
instead declare `final_answer_source: state_tool_observation` with a
`final_answer_derivation` template; the provider record must then carry the
fixed sentinel `$derived_from_expected_state$` as its final-answer value, and
the real answer is derived deterministically from the validated expected-state
arguments, with `{field}` inserting the raw value and `{field|stable_id}` the
slugified value from the shared stable-ID primitive. Observation-sourced final
answers must be substrings of declared-field observation values collected
across the full grounding context, and declared expected-state reference fields
must exactly equal some grounding observation value. Domain grounding pairs
curated primary arguments with the observation those arguments reproduce. These
prompt-only values are never exported. Prompts, grounding rows, tool arguments,
candidate IDs from prior batches, exclusion-list instruction text, provider
payloads, source payloads, credentials, and host paths are never persisted;
persisted candidate lineage carries only the integer
`excluded_instruction_count` for the exclusion list.
Evaluation, profile-decision, release, and release-pack artifacts preserve the
same validated mapping so campaign evidence can reject metadata drift.

Coverage-enabled profile preview does not write a dataset manifest. Each
domain's v1 catalog declares its original reachable cells, v2 expands
representative grounding capacity, and v3 adds executable structural-recovery
cells plus observation-backed grounding identity validation without changing
earlier identities. The domain-owned declarations use one dimension vocabulary
and include task/tool/state compatibility tuples, stable grounding-unit
identities and eligibility, declared grounding-context sizes, feature
requirements, optional deterministic branch plans, and exact difficulty
semantics. The catalogs cover read-only selection, state-changing cross-step
bindings, deterministic multi-result selection, constrained mutation
arguments, and feature-gated recovery where the domain runtime can execute and
independently verify the outcome. Each domain provides named smoke and
representative profiles with mandatory floors, balance weights, grounding
reuse, an attempt ratio, and an override bound. The shared compiler and
reachability validator
reject unknown contract or profile versions, unknown dimensions, duplicate or
unreachable cells, contradictory compatibility or difficulty declarations,
missing mandatory features, invalid overrides, insufficient admitted or usable
cell capacity, overlap-induced grounding reuse violations, and impossible
floors. Recovery reachability is executable: read-only branch probes must
observe the declared failure and a successful fallback whose final-answer
fields equal the selected grounding observation.
Known catalog/profile identities come from the domain planning definition's
version registry rather than a provider value or identifier naming pattern.

`coverage_plan.json` uses canonical UTF-8 JSON with a trailing newline. It
contains only stable identifiers, contract versions and hashes, enabled feature
names, aggregate capacity counts and hash, per-cell target counts, mandatory
floors, effective balance weights, feature requirements, grounding-reuse
policy, attempt policy, the accepted-sample target, and the distinct bounded
attempt ceiling plus candidate target. `plan_hash` binds the complete plan payload; `plan_id` is
derived from that hash. Raw grounding rows, source payloads, prompts, provider
records, credentials, and host paths are excluded. Fixed inputs produce the
same bytes. `--preview-coverage-plan` prints those bytes and
`--write-coverage-plan` writes them under `--output-dir`; both exit before
candidate generation or execution. Normal coverage-enabled LLM execution also
persists the plan, issues the deterministic initial assignment wave, reconciles
accepted-only cell coverage, and uses remaining plan capacity for bounded
deficit backfill. It retains `coverage_assignment_lineage_v1` on accepted
samples and relevant rejections. That lineage contains only assignment, plan,
cell, catalog, profile, scheduler, and grounding-scope identifiers, versions,
and hashes. Provider prompts, responses, credentials, unrestricted grounding
rows, and raw source payloads remain excluded. The programmatic pipeline result
exposes a sanitized `coverage_reconciliation_v1` snapshot with planned,
in-flight, accepted, rejected, remaining, attempt, wave, completion, and
bounded-deficit fields. Publishing hash-bound run-level coverage evidence and
fulfillment authority remains outside this contract.

Profile-configured runs also attach a narrow per-record attribution record under
`lineage.run_profile` for accepted samples and `details.run_profile` for
rejected candidates. This record uses `schema_version:
run_profile_attribution_v1` and contains only `profile_schema_version`,
`profile_id`, `generation_mode`, optional `profile_purpose`, `config_hash`, and
the optional sanitized source summary fields already admitted for manifest
metadata. It intentionally omits manifest-only fields such as
`target_candidate_count` and `enabled_features`, plus raw profile paths, source
paths, payload rows, prompts, headers, API keys, and arbitrary profile JSON
keys. Non-profile runs omit this per-record attribution entirely.

`runtime_metadata_v1` is the runtime-owned lifecycle contract:

```json
{
  "schema_version": "runtime_metadata_v1",
  "runtime_id": "contacts_fixture",
  "runtime_version": "env_contacts_v2",
  "environment_id": "contacts_fixture",
  "environment_version": "env_contacts_v2",
  "reset_recipe": "sqlite_fixture:contacts",
  "state_backend": "sqlite",
  "checkpoint_strategy": "sqlite_backup",
  "source_provenance": {},
  "sandbox_policy": {},
  "adapter": {}
}
```

`runtime_metadata_v1` must stay separate from dataset manifests, run-profile
metadata, profile decisions, release reports, release packs, and release cards.
Validators reject release/profile fields, raw source payloads, provider prompts
or payloads, headers, API keys, environment variables, database paths, and
absolute host paths.

`episode_log_v1` is internal episode evidence derived from accepted or selected
rejected execution trajectories:

```json
{
  "schema_version": "episode_log_v1",
  "episode_id": "episode_sample_candidate_contacts_alice",
  "candidate_id": "candidate_contacts_alice",
  "runtime": {
    "schema_version": "runtime_metadata_v1",
    "runtime_id": "contacts_fixture",
    "runtime_version": "env_contacts_v2"
  },
  "policy": {
    "policy_id": "policy_candidate_contacts_alice",
    "role": "scripted_solution_policy"
  },
  "verifier": {
    "id": "exact_answer_verifier",
    "version": "verifier_exact_answer_state_v2"
  },
  "transitions": [],
  "outcome": {"status": "accepted", "failure_cause": null}
}
```

Allowed episode transition types are `action`, `observation`, `state_change`,
`final_response`, and `error`. Transition hashes are `sha256:` values computed
over sorted sanitized JSON. Allowed outcomes are `accepted`, `rejected`, and
`failed`. Episode redaction removes local/source paths, profile fields, provider
prompts, provider payloads, headers, API keys, environment variables, and
secret-like values. Episode logs are never persisted to `samples.jsonl` or
`rejections.jsonl`; the opt-in `episodes.jsonl` export is an internal evidence
artifact used by `episode_quality_report.json` and
`episode_replay_report.json`.

### Episode Quality Report Contract

`episode_quality_report.json` uses `schema_version:
episode_quality_report_v1` and is generated only when explicitly requested. It
reads validated `episode_log_v1` records from `episodes.jsonl`, uses runtime
descriptors for known-runtime and state-changing-tool diagnostics, and records:

- artifact input names for `manifest.json` and `episodes.jsonl`;
- observed episode counts by outcome and runtime;
- unique tool names;
- fixed checks for `contract_valid`, `has_action`, `has_observation`,
  `accepted_has_final_response`, `accepted_has_no_error`,
  `state_change_supported`, and `runtime_known`;
- per-episode summaries containing ids, runtime id, outcome status, transition
  counts, tool names, and failed check names only;
- a decision status of `passed`, `watch`, `failed`, or
  `insufficient_evidence`.

Required failures in contract validity, action/observation presence,
accepted-final-response count, or accepted-error absence produce `failed`.
Failures in descriptor-derived state-change support or known-runtime diagnostics
produce `watch`. Unknown runtime descriptors are unsupported runtime evidence,
not malformed episode evidence; malformed episode records fail `contract_valid`.
No episodes produce `insufficient_evidence`.

Report validators reject absolute or nested input paths, unsupported check
names, unsupported summary keys, raw secrets, provider/prompt payload material,
and host-path-like artifact references. Episode summaries must not contain raw
instructions, tool arguments, observations, final-response content, source
payloads, provider payloads, prompts, credentials, or local paths.

### Episode Replay Report Contract

`episode_replay_report.json` uses `schema_version:
episode_replay_report_v1` and is generated only when explicitly requested. It
reads validated `episode_log_v1` records from `episodes.jsonl`, resolves replay
support and rebuild seeds through runtime descriptors, rebuilds fresh supported
fixture runtimes, executes action transitions through
`RuntimeSession.execute_action(...)`, and records:

- artifact input names for `manifest.json` and `episodes.jsonl`;
- observed episode counts by runtime and unique tool names;
- fixed checks for `contract_valid`, `runtime_supported`, `runtime_rebuilt`,
  `actions_replayed`, `accepted_has_final_response`,
  `observation_hash_match`, `state_change_hash_match`, and
  `runtime_metadata_stable`;
- per-episode summaries containing ids, runtime id, outcome status, action and
  replay counts, observation/state-change match counts, final-response count,
  tool names, and failed check names only;
- runtime-boundary evidence containing allowlisted runtime methods
  (`rebuild`, `runtime_metadata`, `execute_action`) and no direct tool-registry
  execution methods;
- a decision status of `passed`, `watch`, `failed`, or
  `insufficient_evidence`.

Required failures in contract validity, runtime support, runtime rebuild,
action execution, or accepted-final-response count produce `failed`. Optional
diagnostic mismatches in observation hashes, state-change hashes, or runtime
metadata produce `watch`. Unsupported replay capability remains distinct from
malformed episode evidence. No episodes produce `insufficient_evidence`.

Report validators reject absolute or nested input paths, unsupported check
names, unsupported summary keys, unsupported runtime/registry method names, raw
secrets, provider/prompt payload material, and host-path-like artifact
references. Replay summaries must not contain raw instructions, tool arguments,
observations, final-response content, source payloads, provider payloads,
prompts, credentials, or local paths.

### Reward Label Contract

`reward_labels.jsonl` uses one validated `reward_label_v1` object per line. Each
record is aligned to an episode and contains only stable ids, runtime id,
outcome status, `label_status`, bounded `scalar_reward`, fixed component
scores, sanitized `label_source`, deterministic `preference_group` metadata,
and sanitized reason codes. Fixed component names are `outcome`, `contract`,
`execution`, `state_support`, and `replay_consistency`.

The initial deterministic scalar is
`0.35*outcome + 0.20*contract + 0.20*execution + 0.15*state_support +
0.10*replay_consistency`. Accepted episodes with passing quality and replay
evidence score `1.0`. Accepted episodes without replay evidence can remain
usable but record `replay_evidence_absent` and use lower replay consistency.
Invalid episode contracts are excluded with sanitized reasons.
Runtime reward-label capability and state-changing-tool support come from
runtime descriptors, so adding a new descriptor-backed runtime does not require
editing reward-label consumer allowlists.

`reward_label_report.json` uses `schema_version: reward_label_report_v1`. It
records relative or null input artifact names, observed episode/label counts,
runtime counts, average scalar reward, fixed checks, sanitized label summaries,
and a decision status of `passed`, `watch`, `failed`, or
`insufficient_evidence`. Allowed checks are `labels_present`,
`label_contract_valid`, `episode_contract_valid`, `quality_evidence_aligned`,
`replay_evidence_aligned`, `usable_label_coverage`, and
`sanitized_summaries`.

Reward-label validators reject absolute paths, unsupported runtime ids,
unsupported component names, unsupported preference-group fields, raw task
instructions, expected answers, expected state, tool arguments, observations,
final responses, source/provider payloads, prompts, credentials, environment
variables, and host paths.

Runtime action validators reject unsupported schema versions, malformed status
values, bad content hashes, raw secret material, unsupported fields, and missing
required runtime/tool/status/hash fields. Action requests and results are
internal records; persisted dataset samples still use the public trajectory
shape unless an explicit diagnostic report writes episode evidence.

`mobile_messages_environment_input_v1` is the typed mobile source environment
input. It contains non-empty `threads` and `messages`, optional `reminders` and
`draft_replies`, and optional `source_bundle_id`/`source_policy_hash`. Message
threads and source ids must be internally consistent before the environment is
created. This contract is domain-owned; shared source governance does not
understand mobile table semantics.

`workspace_tasks_environment_input_v1` is the typed workspace source
environment input. It contains non-empty `projects` and `tasks`, optional
`documents` and `comments`, and optional `source_bundle_id`/
`source_policy_hash`. Tasks and documents must reference declared projects;
comments must reference declared tasks. This contract is domain-owned; shared
source governance does not understand workspace table semantics.

`lineage.source_provenance` records the source bundle id, source policy hash,
source ids, source kinds, license labels, license outcomes, retention/export
eligibility, `external_source_eligible`, and, for source-backed environment
inputs, `environment_source_admission`. Environment metadata carries the same
source provenance so environment versions can be traced back to the policy hash
that admitted their source bundle. Network-backed and profile-local environment
reset recipes also record source bundle id and source policy hash; they do not
record raw source URLs, raw local paths, or payload text.
Rejected external/local-file source material and rejected
environment-source inputs use `source_policy_rejected` and store sanitized source
governance details under `details.source_governance`.

Trajectory events currently supported by the contract are:

- `action`: tool name and JSON arguments submitted by the solution policy.
- `observation`: structured tool result returned by the registry.
- `state_change`: sanitized state mutation summary for mutating tools.
- `final_response`: final assistant response assembled from the executed policy.

`lineage.solution_policy` is present when a scripted or remote policy generator
is used separately from task generation. It follows the same sanitized role
metadata shape as `lineage.generator`.

Expected-state verification currently recognizes `contact_followup`,
`mobile_reminder`, and `mobile_draft_reply`. Mobile reminder checks compare
title, optional due time, and optional source message id against the active
mobile environment. Mobile draft checks compare thread id and body against the
active mobile environment.

`lineage.refinement` is present only for accepted samples produced by a repaired
rerun. It records the original candidate id, attempt number, source failure
cause, critic diagnosis, repair decision, and sanitized role metadata. Refined
rejections store the same attempt metadata under `details.refinement` while
preserving the original source failure details.

`lineage.branching` is present only for accepted samples produced from a branch
plan. It uses `schema_version: branch_lineage_v1` and records the plan id,
selected branch id, selected branch depth, fallback count, and `branch_outcomes`.
Each branch outcome uses `schema_version: branch_outcome_v1` and records
`branch_id`, `attempted`, `selected`, `outcome`, `failure_cause`,
`retry_eligible`, `refinement_eligible`, `message`, `depth`, and a branch-local
trajectory. The top-level sample `trajectory` remains the selected successful
path. Failed branching candidates preserve branch outcomes under
`details.branch_outcomes`.

`lineage.adapter` is present only for samples produced with the opt-in local
MCP-compatible adapter path. Each record uses `schema_version:
adapter_lineage_v1` and records adapter id, protocol label, adapter version,
operation, tool name, call id, execution status, and optional rejection cause.
Adapter execution preserves the normal trajectory event contract; it does not
add adapter-specific events to the top-level trajectory. Adapter-contract
failures are rejected with `adapter_contract_rejected` and store sanitized
details under `details.adapter_rejection`, including the adapter lineage record
and the classified result envelope.

`lineage.seed_transformation`, `lineage.task_suggester`, and
`lineage.task_editor` are present only for accepted samples produced through the
task-expansion loop. The seed-transformation record uses
`schema_version: seed_transformation_v1` and records the transformation id,
source seed id, transformation type, target taxonomy node, capability target,
difficulty movement, and sanitized lineage. `task_suggester` and `task_editor`
use the same sanitized role-lineage shape as other remote-capable roles. Edited
task candidates still carry normal task-generation and solution-policy lineage;
suggester and editor metadata do not overwrite those fields.

### Quality Report Contract

`quality_report.json` uses `schema_version: quality_report_v1` and records:

- `dataset_version`.
- `counts.total`, `counts.accepted`, `counts.rejected`, `counts.executable`,
  `counts.refined_attempted`, `counts.refined_accepted`, and
  `counts.refined_rejected`.
- `rates.success_rate` and `rates.executable_rate`.
- `rejection_causes`, keyed by classified cause.
- `role_outcomes`, keyed by role name, with attempted, accepted, rejected,
  aggregate retry count, output types, token totals, and cost totals when lineage
  provides them.
- `tool_proposal_outcomes`, keyed by admission outcome.
- `branch_outcomes`, keyed by accepted or rejected branch-attempt outcome.
- `branch_failure_causes`, keyed by classified branch failure cause.
- `suggestion_outcomes`, keyed by rejected suggestion outcome.
- `editor_actions`, keyed by task editor action.
- `edit_rejection_causes`, keyed by suggestion or editor rejection cause.
- `slices`, keyed by deterministic dimensions currently available in foundation
  records: dataset version, domain, task type, difficulty level, curriculum level,
  tool combination, generator role, verifier type, rejection cause, refinement
  status, role name, role output type, capability-gap type, proposed tool,
  proposed tool side-effect class, tool-proposal outcome, branch depth, selected
  branch, branch outcome, fallback count, seed-transformation type, taxonomy
  node, suggestion outcome, editor action, edit rejection cause, source kind,
  license policy outcome, external-source eligibility, source rejection cause,
  environment-source admission outcome, adapter id, adapter protocol, adapter
  execution outcome, adapter rejection cause, sandbox artifact kind, sandbox scan
  status, sandbox admission outcome, sandbox rejection cause, sandbox execution
  status, run-profile id, generation mode, and run-profile schema version.
  Profile slices are populated only from per-record run-profile attribution;
  no-profile records do not create synthetic `unknown` profile slices.

### Evaluation Report Contract

`evaluation_report.json` uses `schema_version: evaluation_report_v1` and is
generated only when explicitly requested. The report resolves a deterministic
held-out suite from the manifest run-profile domain. Contacts profiles use
`contacts_heldout_v1`; mobile messages profiles use
`mobile_messages_heldout_v1`; workspace profiles use
`workspace_tasks_heldout_v1`. These suites are separate from generated
candidates and scale-probe duplicate patterns, and they execute fixed held-out
tasks through the domain pipeline environment, tool registry, scripted policy
execution, and verifier contracts.

The report records sanitized dataset/profile identity, artifact input names,
suite id/version/domain/task count, top-level evaluation domain, per-task
pass/fail results, capability slices, aggregate counts, pass rate, optional
parent evaluation comparison, and a threshold decision. Thresholds include
`mvp_min_heldout_pass_rate`,
`max_regression_count`, and optional `min_capability_pass_rates`. Capability
thresholds ratchet individual benchmark slices independently of the aggregate
pass rate; if a required slice is missing, the decision is
`insufficient_evidence`.

Held-out task records store task id, capability tags, status, sanitized failure
cause, and optional expected-outcome audit fields. `expected_outcome: passed`
means execution and verification must pass. `expected_outcome:
controlled_failure` means the task passes only when the observed sanitized
failure cause matches the expected controlled failure. `observed_failure_cause`
records that sanitized cause even when the controlled-failure task is counted as
passed. Evaluation reports must not include raw local profile paths, raw source
payloads, contact emails beyond existing synthetic fixture values, prompts,
provider payloads, headers, API keys, or arbitrary profile JSON.

### Profile Decision Report Contract

`profile_decision_report.json` uses `schema_version:
profile_decision_report_v1` and is generated only when explicitly requested. The
report reads existing `manifest.json`, `quality_report.json`, optional
`parent_comparison.json`, and optional `evaluation_report.json` artifacts, then
records dataset/profile identity,
artifact input names, observed candidate counts, success and executable rates,
exact duplicate counts/rates, infrastructure and source-policy rejection
counts/rates, optional runtime seconds, optional held-out evaluation status,
profile slice count, the thresholds used, and deterministic decisions for
`async_orchestration`,
`semantic_duplicate_detection`, `mvp_quality_floor`, and `profile_promotion`.

Decision statuses are machine-readable. Async orchestration is `activate` only
when candidate count or runtime meets the configured threshold; otherwise it is
`defer`. Semantic duplicate detection is `activate` only when both volume and
exact-duplicate-rate thresholds are met. Low volume keeps it deferred even when
the exact duplicate rate is high, but the decision records an `exact_duplicate_rate`
watch trigger and rationale so the pressure remains visible without activating
[ISSUE-0002](../.scratch/ISSUE-0002-semantic-duplicate-detection.md).

The MVP quality floor is `passed` when success and executable rates meet
minimums, infrastructure/source-policy rejection rates stay within caps, and any
supplied held-out evaluation has passed. It is `failed` when observed rates miss
those thresholds or a supplied held-out evaluation fails, and
`insufficient_evidence` when required quality rates or supplied evaluation
evidence are absent or malformed. `profile_promotion` is the higher-level local
MVP promotion decision: it can be `passed`, `failed`, `blocked`, or
`insufficient_evidence`. Promotion requires the MVP floor and held-out
evaluation to pass, remains blocked when async orchestration or semantic
duplicate detection activates, and reports insufficient evidence when required
quality or evaluation evidence is missing, malformed, or from a domain that
does not match the manifest run-profile domain.
The report stores sanitized profile metadata only and must not include raw
profile files, source paths, payload rows, contact emails, prompts, headers, API
keys, or arbitrary profile JSON.

### Dataset Release Report Contract

`dataset_release_report.json` uses `schema_version:
dataset_release_report_v1` and is generated only when explicitly requested with
`--write-dataset-release-report`. It reads existing `manifest.json`,
`quality_report.json`, `evaluation_report.json`, and
`profile_decision_report.json` artifacts and writes a deterministic release
admission decision. It does not rerun candidates, change the quality report, or
promote profiles.

The report records sanitized dataset/profile identity, artifact input names,
accepted/rejected counts, success and executable rates, source-policy rejection
rate, held-out status, profile-promotion status, async-orchestration status,
semantic-duplicate status, release completeness evidence, release artifact
references, and
`decisions.dataset_release`. Allowed release statuses are `passed`, `failed`,
`blocked`, `ineligible`, and `insufficient_evidence`.

`dataset_release` is narrower and later than `profile_promotion`.
`mvp_quality_floor` decides whether the artifact metrics meet the local quality
floor. `profile_promotion` decides whether a run profile is ready as a local MVP
configuration using held-out evidence and scale deferrals. `dataset_release`
decides whether the concrete artifact set can be treated as a releaseable local
MVP dataset version. Release admission passes only for `profile_purpose:
release_candidate`, passed profile promotion, passed held-out evaluation,
deferred async orchestration, deferred semantic duplicate detection, zero
source-policy rejection rate, evaluation evidence whose domain matches the
manifest run-profile domain, and manifest references to `samples`,
`rejections`, `quality_report`, `evaluation_report`, and
`profile_decision_report`. It also requires release completeness evidence to
pass. Diagnostic probes and benchmark profiles are non-releaseable by default.

Release completeness is a deterministic evidence layer inside
`dataset_release_report_v1`. It is computed from sanitized manifest counts and
quality-report slices; it must not read raw samples, raw source payloads, local
profile paths, prompts, provider payloads, headers, API keys, or arbitrary
profile JSON. Current release completeness thresholds are domain-aware. All
supported local release-candidate domains require at least `5` accepted samples
and at most `0.2` rejection rate. Contacts require `lookup_contact_email`,
`contact_followup`, and `contact_branch_fallback` task-type coverage. Mobile
requires `mobile_message_lookup`, `mobile_message_to_reminder`,
`mobile_draft_reply`, and `mobile_branch_fallback`. Workspace requires
`workspace_item_lookup`, `workspace_task_creation`, `workspace_comment_update`,
and `workspace_branch_fallback`. Required tool-combination coverage is
domain-specific; dataset release reports store the exact threshold list used in
`release_completeness.thresholds`.

Required task-type and tool-combination threshold lists remain non-empty.
Observed coverage lists may be empty when no candidate is accepted; each present
entry must still be a non-empty string. Empty observation is truthful missing
evidence, triggers both applicable coverage checks, and can never produce a
`passed` completeness decision. Benchmark profiles remain `ineligible` even
when the rest of their reporting chain validates.

The report records:

- `release_completeness.thresholds.min_accepted_samples`: minimum accepted
  samples required before a release-candidate artifact set has enough local
  sample evidence.
- `release_completeness.thresholds.max_rejection_rate`: maximum allowed
  `rejected / (accepted + rejected)` rate for release admission.
- `release_completeness.thresholds.required_task_types`: accepted task-type
  slice keys that must be present in `quality_report.slices.task_type`.
- `release_completeness.thresholds.required_tool_combinations`: accepted
  tool-combination slice keys that must be present in
  `quality_report.slices.tool_combination`. Dataset release reporting
  normalizes the quality-report separator ` > ` to `+` in its own observed
  release-completeness field.
- `release_completeness.observed`: accepted/rejected counts, rejection rate,
  observed accepted task types, and observed accepted tool combinations.
- `release_completeness.decision`: machine-readable completeness status,
  reasons, and trigger keys.

When profile purpose, profile promotion, held-out evaluation, source policy,
async orchestration, and semantic duplicate gates would otherwise allow release
but `release_completeness.decision.status` is not `passed`,
`decisions.dataset_release.status` must be `insufficient_evidence` and include
`release_completeness` in `triggered_by`. A dataset release can pass only when
both the earlier release gates and release completeness pass.

### Release Quality Audit and Card Contract

`release_quality_audit.json` uses `schema_version:
release_quality_audit_v1` and is generated only when explicitly requested with
`--write-release-quality-audit`. It requires
`--write-dataset-release-report`, reads existing sanitized release artifacts,
and does not rerun candidate generation or change default dataset release
admission.

The audit records sanitized dataset/profile identity, input artifact names,
accepted/rejected counts, exact duplicate count/rate, accepted task-type and
tool-combination counts, largest accepted task-type and tool-combination
shares, release completeness status, semantic duplicate decision status, the
thresholds used, duplicate-family risk groups, and a machine-readable decision.

Current audit thresholds are:

- `small_release_watch_accepted_samples`: `8`.
- `max_largest_task_type_share`: `0.75`.
- `max_largest_tool_combination_share`: `0.8`.
- `max_exact_duplicate_rate`: `0.0`.
- `max_duplicate_family_size`: `2`.

Audit decision statuses are:

- `clear`: all required inputs are present and no configured watch threshold is
  triggered.
- `watch`: release admission can remain valid, but reviewers should inspect
  small-release, exact-duplicate, concentration, or duplicate-family signals.
- `insufficient_evidence`: required audit inputs are absent, unreadable, or
  malformed.
- `blocked`: profile decisions say `semantic_duplicate_detection.status` is
  `activate`, so semantic duplicate detection must be implemented before
  release use.

Duplicate-family risk groups are deterministic review signals. Family keys are
SHA-256 hashes derived from structured accepted-sample fields: task type,
ordered tool names, verifier type, and difficulty level. Risk groups may
include family hashes, risk kind, risk level, accepted sample ids, sample
counts, and sanitized reason strings. They must not include raw task
instructions, raw trajectory arguments, contact emails, local profile paths,
source paths, raw source payloads, prompts, provider payloads, headers, API
keys, credentials, or arbitrary profile JSON.

`dataset_release_card.md` is generated only when explicitly requested with
`--write-dataset-release-card`. It is a human-readable summary, not a machine
contract. It includes stable headings for identity, release decision, artifact
integrity, quality evidence, coverage and diversity, known limitations, and
non-claims. Machine consumers should read `release_quality_audit.json`,
`dataset_release_report.json`, and `dataset_release_pack.json`.

The card must state that release admission, audit status, and pack verification
evidence does not prove downstream model quality, transfer gain, or training
utility. Like the audit, it must not persist raw sample contents, raw task
instructions, local profile paths, source paths, source payloads, prompts,
provider payloads, headers, API keys, credentials, or arbitrary profile JSON.

### Release Review Queue, Decision, and Resolution Contracts

Release review is a second workflow, not an extension of candidate rejection
routing. Candidate-time `review_queue.jsonl` contains
`human_review_record_v1` records for reviewable rejected candidates.
Release-level `release_review_queue.jsonl` contains `release_review_item_v1`
records derived only from an existing `release_quality_audit_v1` whose decision
status is `watch`. Audit statuses `clear`, `blocked`, and
`insufficient_evidence` create no release-review queue.

Each `release_review_item_v1` has exactly these fields:

```json
{
  "schema_version": "release_review_item_v1",
  "review_item_id": "review_item:sha256:<64-lowercase-hex>",
  "dataset_version": "dataset_mobile_messages_release_candidate",
  "source": {
    "artifact": "release_quality_audit.json",
    "audit_status": "watch"
  },
  "risk": {
    "kind": "small_release_size",
    "level": "watch",
    "reason": "accepted 5 is below small_release_watch_accepted_samples 8",
    "sample_ids": []
  },
  "created_at": "1970-01-01T00:00:00Z"
}
```

Allowed `risk.kind` values are `small_release_size`, `exact_duplicate_rate`,
`task_type_concentration`, `tool_combination_concentration`, and
`duplicate_family`; `risk.level` and `source.audit_status` are always `watch`,
and `source.artifact` is always `release_quality_audit.json`. Direct-risk
`reason` values are canonical observed-versus-threshold strings from the audit:

- `accepted <integer> is below small_release_watch_accepted_samples <integer>`;
- `exact_duplicate_rate <number> is above max_exact_duplicate_rate <number>`;
- `largest_task_type_share <number> is above max_largest_task_type_share <number>`;
- `largest_tool_combination_share <number> is above max_largest_tool_combination_share <number>`.

A duplicate-family reason is exactly
`<count> accepted samples share the same task type and tool combination`.
`sample_ids` is empty for every direct risk and is a non-empty, unique,
deterministically sorted list only for `duplicate_family` evidence already
present in the sanitized audit. `dataset_version` and sample ids are ASCII-safe
identifiers. `created_at` is the fixed deterministic timestamp shown above.

`review_item_id` is deterministic. Its digest is SHA-256 over ASCII canonical
JSON (`sort_keys=True`, compact separators) containing exactly
`dataset_version`, `source_artifact`, `risk_kind`, `risk_level`, canonical
`reason`, and sorted `sample_ids`; the stored id uses the
`review_item:sha256:` prefix. Unknown triggers, non-canonical reasons, duplicate
ids, or mismatched structured evidence are invalid rather than silently
converted into review work.

`review_decisions.jsonl` is an explicit local input created and owned by the
reviewer. Each line has exactly these `review_decision_v1` fields:

```json
{
  "schema_version": "review_decision_v1",
  "review_item_id": "review_item:sha256:<64-lowercase-hex>",
  "outcome": "confirmed_issue",
  "reason_code": "insufficient_diversity",
  "review_minutes": 4,
  "reviewer_alias": "quality_reviewer_1",
  "decided_at": "1970-01-01T00:00:00Z"
}
```

Allowed `outcome` values are `accepted_risk`, `confirmed_issue`, and
`needs_follow_up`. Allowed `reason_code` values are `sufficient_context`,
`insufficient_diversity`, `near_duplicate_suspected`,
`source_or_verifier_concern`, and `requires_more_data`. `review_minutes` is a
non-negative integer capped at 480 per decision. `reviewer_alias` is a non-empty
ASCII-safe opaque identifier of at most 128 characters matching
`[A-Za-z0-9][A-Za-z0-9_.-]*`; it must not be a personal name, email address,
path, token, or free-text note. `decided_at` is a UTC timestamp in
`YYYY-MM-DDTHH:MM:SSZ` form. A file may contain at most one decision for each
known queue item. Empty, malformed, duplicate, or unknown-item decisions are
insufficient evidence. This input is never attached to `manifest.json`.

`review_resolution_report.json` contains exactly these
`review_resolution_report_v1` fields:

```json
{
  "schema_version": "review_resolution_report_v1",
  "dataset_version": "dataset_mobile_messages_release_candidate",
  "inputs": {
    "release_review_queue_path": "release_review_queue.jsonl",
    "review_decisions_path": "review_decisions.jsonl"
  },
  "counts": {
    "queued": 1,
    "resolved": 1,
    "pending": 0,
    "accepted_risk": 0,
    "confirmed_issue": 1,
    "needs_follow_up": 0,
    "review_minutes": 4
  },
  "decision": {
    "status": "reviewed",
    "reasons": ["all queued review items have decisions"],
    "triggered_by": ["review_decisions"]
  }
}
```

`inputs` stores safe basenames only. All `counts` values are non-negative
integers: `queued == resolved + pending`, `resolved` equals the three outcome
counts, and aggregate `review_minutes` cannot exceed `resolved * 480`.
`decision.reasons` and `decision.triggered_by` are non-empty sanitized
machine-readable strings. Allowed `decision.status` values are:

- `reviewed`: a non-empty queue is fully resolved. This means reviewed only;
  it does not mean approved or releaseable, including when decisions contain
  `confirmed_issue` or `needs_follow_up`.
- `pending_review`: a non-empty valid subset of decisions resolved at least one
  item and at least one item remains pending.
- `insufficient_evidence`: queue or decision evidence is missing, empty,
  unreadable, malformed, duplicated, cross-dataset, or references unknown item
  ids. Resolved outcome counts and review minutes are zero.

The resolution report contains aggregate counts only. It does not repeat
individual decisions or aliases. Neither release-review artifact may contain
raw task instructions, trajectory arguments, observations, final responses,
source paths or payloads, provider payloads, profile contents or paths, host
paths, or credentials. Review creation and resolution do not modify samples,
rejections, quality reports, held-out evaluation, profile decisions, dataset
release, semantic-duplicate or async decisions, or release-pack bytes.

### Dataset Release Pack Contract

Historical release packs use `dataset_release_pack_v1`. Admission-enabled
mutation-safe releases use `dataset_release_pack_v2`; both are generated only
when explicitly requested with
`--write-dataset-release-pack`. It requires
`--write-dataset-release-report`, reads existing sanitized release artifacts,
and does not rerun candidate generation.

The pack records `dataset_version`, deterministic `release_id`, sanitized
profile identity, input artifact names, release evidence, and file records for
`samples`, `rejections`, `manifest`, `quality_report`, `evaluation_report`,
`profile_decision_report`, and `dataset_release_report`. A v2 pack also binds
`mutation_admission_report`. Each file record stores
only the relative artifact name, `sha256:<64 lowercase hex chars>`, and byte
count. `release_id` is deterministic from the dataset version and sorted
artifact hashes.

Verification statuses are:

- `passed`: referenced files exist, hashes and byte counts match, manifest
  release artifact references are present, dataset/profile metadata is
  consistent across the pack and reports, dataset release admission passed, and
  release completeness passed.
- `failed`: the pack is readable, but referenced files drifted or release
  evidence no longer agrees.
- `insufficient_evidence`: the pack or referenced JSON artifacts are absent,
  unreadable, or malformed.

`dataset_manifest_v2` is emitted for `run_profile_v4` runs. It declares
`dataset_sample_v2`, the supported authorization, evidence, domain-policy,
semantic-verdict, and report contract versions, and independent SHA-256/byte
count bindings for `samples.jsonl`, `rejections.jsonl`, and
`mutation_admission_report.json`. Mutation-safe v2 pack construction and
verification re-read those artifacts without provider calls. They require
enforce mode, supported verdicts and successful provider outcomes for accepted
state-changing samples, generator/judge independence, non-diagnostic evidence,
valid internal and artifact hashes, supported contracts, and sanitized retained
material. Missing, shadow, disabled, invalid, diagnostic-only, or tampered
evidence fails. Historical `dataset_manifest_v1` and
`dataset_release_pack_v1` remain readable but cannot claim mutation safety or
grandfather `_30_v5` samples into a new release.

Release-pack verification proves artifact integrity and release-admission
consistency for the local artifact directory. It does not prove downstream model
quality, training gain, or benchmark improvement. The pack must not store raw
sample contents, raw source payloads, local profile paths, provider prompts,
provider payloads, headers, API keys, arbitrary profile JSON, or credentials.

Offline review resolution is the sole controlled post-pack manifest append.
Attaching `review_resolution_report` leaves `dataset_release_pack.json` bytes
unchanged. Verification may pass only when the report is valid and belongs to
the same dataset, and removing that one unique manifest reference reconstructs
the original canonical manifest with exactly the SHA-256 and byte count recorded
in the pack. Any additional manifest drift, missing or duplicate-equivalent
reference, malformed or missing report, dataset mismatch, hash mismatch, or byte
count mismatch fails verification.

Capability-gap records use `schema_version: capability_gap_v1` and preserve
candidate id, policy id, gap type, tool name, rejection cause, message, schema
details, retry eligibility, and source role lineage. Tool proposals use
`schema_version: tool_proposal_v1` and preserve tool name, description, JSON
schema, side effects, required environment, verifier implications, safety notes,
and role lineage. Proposal events use `schema_version: tool_proposal_event_v1`
and bundle the gap, proposal, and admission decision. Accepted reruns preserve
this bundle under `lineage.tool_expansion`; rejected reruns preserve it under
`details.tool_proposal`.

Branch plans use `schema_version: branch_plan_v1` and preserve plan id, maximum
depth, branch ids, node type, parent id, condition, ordered tool steps,
final-response template, and terminal outcome. The deterministic foundation
runner currently enables the branching fixture only when requested with
`--enable-branching` or `enable_branching=True`, keeping default serial exports
stable.

Adapter manifests use `schema_version: mcp_adapter_manifest_v1`. They are built
from runtime descriptors and `RuntimeSession` tool schemas for opt-in local
adapter runs. Tool-call requests use `schema_version:
mcp_tool_call_request_v1`, and results use `schema_version:
mcp_tool_call_result_v1`. The first supported operation is `tool.call`.
Successful results carry `execution_status: succeeded`; contract, capability, or
schema failures carry `rejected`; runtime failures carry `failed`. Tool-call
arguments are sanitized before they become `runtime_action_request_v1` records,
and successful adapter execution retains corresponding `runtime_action_result_v1`
evidence inside the local adapter layer. Adapter contract rejections are
non-executable for quality-rate purposes and do not inflate verifier success
metrics.

Generated executable records use `schema_version:
generated_executable_artifact_v1` and preserve artifact id, artifact kind
(`tool_handler`, `environment_builder`, or `verifier`), language (`python`),
source hash, declared entrypoint, source role, sanitized role lineage, creation
timestamp, and sandbox-policy hash. They do not export raw source code.

Generated-code scan records use `schema_version:
generated_code_scan_result_v1` and preserve scan status, violation categories
with line numbers, forbidden symbol names, source hash, scanner version, and
redaction summary. Sandbox admission records use `schema_version:
sandbox_admission_result_v1` and preserve artifact id, scan status, policy id,
accepted flag, optional `unsafe_generated_code` rejection cause, sanitized
reason, and audit artifact name. Sandbox execution records use
`schema_version: sandbox_execution_result_v1` and preserve artifact id, status,
timeout flag, exit class, stdout/stderr hashes and byte counts, duration, and
sanitized error class. They do not export raw stdout, stderr, environment
variables, generated code, prompts, headers, API keys, or host paths.

Sandbox audit records use `schema_version: sandbox_audit_v1` and bundle the
artifact, scan, admission, and optional execution records. The deterministic
fixture writes these audits only when requested with `--enable-sandbox-fixture`
or `enable_sandbox_fixture=True`.

Exact duplicate candidates are rejected with `quality_duplicate` when a later
accepted candidate repeats the normalized task instruction and ordered action tool
sequence. Logical consistency failures are rejected with `solution_logic_error`
when a final answer is not supported by observations and verifier expectations.
When refinement is enabled, each repairable failure receives at most one rerun.
The original failure remains inspectable when the rerun is rejected, and refined
successes and failures are reported separately.

Remote LLM generation-stage failures are rejected before candidate execution.
Transient provider, timeout, HTTP 429, and HTTP 5xx failures use
`llm_provider_error`; malformed provider JSON or malformed candidate arrays use
`llm_response_schema_error`. Generation-stage schema rejection details include
sanitized `error_class`, `retry_count`, `retry_eligible`, and exactly one fixed
`schema_reason`: `response_shape_mismatch`, `provider_record_keys_mismatch`,
`invalid_task_type`, `invalid_required_tools`, `invalid_primary_tool`,
`invalid_tool_arguments`, `invalid_difficulty`, `invalid_expected_state`,
`invalid_required_capabilities`, `unsafe_provider_value`,
`duplicate_candidate_id`, `invalid_candidate_id`, `invalid_final_answer`, or
`batch_count_mismatch`.
Expected-state, duplicate-ID, invalid-ID, and final-answer failures may also
include one fixed detail drawn from the reason-specific allowlist.
`invalid_final_answer` admits exactly `final_answer_field_name_literal`,
`final_answer_not_grounded`, `final_answer_sentinel_mismatch`, or
`final_answer_derivation_failed`; `invalid_expected_state` additionally admits
`expected_state_reference_not_grounded`. Required-capability failures
likewise distinguish shape, empty, duplicate, and task-contract mismatch using
fixed details without retaining provider values. Batch index and requested count
are allowed sanitized lineage fields. They must not include raw provider
payloads, field values, prompts, grounding context, response excerpts,
provider-derived exception messages, headers, or credentials.

Default fixture provenance is domain-specific. Contacts, mobile messages, and
workspace tasks use separate source IDs, bundle IDs, origins, and content hashes;
explicit profile or network sources continue to override these defaults. The
same admitted provenance must survive every isolated per-candidate environment
rebuild and appear in both accepted-sample environment metadata and lineage.

### Parent Comparison Contract

When a local parent manifest or quality report path is supplied, the pipeline writes
`parent_comparison.json` with `schema_version: parent_comparison_v1`. The comparison
records accepted-count delta, rejected-count delta, success-rate delta,
executable-rate delta, new and removed slice keys, and rejection-cause deltas.
Run-profile slice dimensions participate in the existing `new_slice_keys` and
`removed_slice_keys` maps without a separate comparison schema.

### Candidate Rejection Human Review Queue Contract

When review routing is enabled for reviewable failures, the pipeline writes
`review_queue.jsonl`. Each record uses `schema_version: human_review_record_v1` and
contains `candidate_id`, `cause`, `task`, `uncertainty_reason`, `source_artifact`,
and `created_at`. This candidate-time queue is only for rejected candidates and
is distinct from release-audit `release_review_queue.jsonl`. The default
foundation run keeps both workflows disabled.

## Versioning Rules

- Changing environment schema creates a new environment version.
- Changing tool signature or side effects creates a new tool version.
- Changing verifier semantics creates a new verifier version.
- Changing accepted sample content creates a new dataset version.
- Manifests must record parent versions so incremental generation can identify affected samples.

## Incremental Regeneration Rules

Dataset manifests must support impact analysis before regeneration:

- Seed changes identify derived tasks, environments, and samples that depend on the changed seed.
- Environment changes identify affected tools, verifiers, reset recipes, and samples.
- Tool changes identify affected task types, trajectories, verifier checks, and compatibility adapters.
- Verifier changes require rechecking prior accepted samples before they can remain in an accepted split.
- Generator or model changes require recording config hashes so new samples can be compared against older samples.

New dataset versions should be compared to their parent version using distribution coverage, quality metrics, cost, and held-out task performance when available. A version is not better merely because it contains more samples.

## LLM Lineage

For every LLM-backed generation, solution, refinement, or judge step, lineage should preserve the provider boundary without leaking secrets:

- Role name, role version, output type, owner module, and retry policy.
- Remote provider base URL host or provider alias.
- `AGENT_DATA_LLM_MODEL` value.
- Prompt, template, and runtime config hashes.
- Request role, retry count, error class, token counts, and cost metadata when available.

LLM-backed task candidates carry the generation lineage returned by the provider
call into accepted samples. LLM-backed solution policies carry separate
`solution_policy` lineage so task generation and execution planning can be
audited independently. The local deterministic fixture path may still build
stable local lineage, but it must not infer remote provider lineage from ambient
LLM environment variables unless the candidate or policy was actually produced by
that provider. Remote samples should use the candidate-level and policy-level
provider lineage rather than reconstructing it later.

The default role registry currently enables `task_generation`, `solution_policy`,
`critic_refinement`, `task_suggester`, `task_editor`, and `tool_generation`.
`task_suggester` may only return structured `task_suggestion` records.
`task_editor` may only return structured `edited_task` records, and edited
candidates must pass normal candidate validation before execution. The
`tool_generation` role may only return structured `tool_proposal` records;
executable tool code remains a local curated implementation concern. The
registry also defines disabled guardrails for `environment_generation`,
`verifier_generation`, and `judge_verification`; these roles must fail before
any provider call until a later plan explicitly enables and validates their
output contracts.

Do not store `AGENT_DATA_API_KEY` or raw provider credentials in manifests, samples, trajectory logs, or rejected-candidate diagnostics.

## Representative Scale And Downstream Evidence

`representative_scale_campaign_v1` is an input-only object containing a label
and exactly one relative artifact directory for each supported domain. The
directory values are resolved relative to the campaign file and are never
persisted. `representative_scale_evidence_v1` stores fixed-order sanitized
domain summaries, artifact basenames and SHA-256 digests, existing
profile-decision signals, aggregate review counts, and one conservative
recommendation. `foundation_fixture`, `deterministic_scale_probe`,
`mobile_fixture`, and `workspace_fixture` are always `diagnostic_only`;
malformed or identity-mismatched evidence is `insufficient_evidence`. Only a
consistent v3 LLM run with fulfilled, cross-artifact-identical generation
contract evidence can be `representative` and support an
activation recommendation.

`downstream_benchmark_bundle_v1` can be built only from a standalone-verified
`dataset_release_pack_v1` or `dataset_release_pack_v2`. It binds the release id,
pack basename, raw-byte
digest and byte count to `external_agent_benchmark_v1`, including declared
metric directions and bounds. External systems return the exact-key
`downstream_benchmark_observation_v1` identity/evaluation/arms object.
`downstream_benchmark_result_v1` preserves valid sanitized observations and
adds deterministic absolute/relative deltas plus `improved`,
`no_detected_improvement`, or `insufficient_evidence`. Invalid observations
retain only bundle identities, empty evaluation identity, null arms/comparison,
and one fixed reason code. Trainer logs, commands, credentials, paths, arbitrary
metadata, and raw external payloads are never copied.

These standalone artifacts are not attached to the manifest. Fixture-scale
results are diagnostic, external training remains outside this repository, and
downstream status never changes sample admission, profile promotion, dataset
release, review resolution, or release-pack bytes.
