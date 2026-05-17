# Data

## Canonical Entities

- **Seed:** source material, domain description, task taxonomy, or prior accepted sample used to start generation.
- **Source Record:** provenance contract for fixture, synthetic, transformed, or
  external material, including source id, origin reference, content hash, license
  label, retrieval timestamp when applicable, and retention/export eligibility.
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
  hash, and validation errors.
- **Seed Transformation:** bounded expansion record that maps a source seed to a
  target taxonomy node, capability target, and intended difficulty movement.
- **Environment:** executable stateful world with reset/checkpoint behavior.
- **Tool:** typed callable action exposed to the Agent.
- **Task:** user-facing goal plus structured constraints and difficulty metadata.
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
- **Sample:** accepted training record assembled from the above entities.
- **Dataset Version:** manifest that groups samples, schemas, generator configs, and quality reports.

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
- Cost: model calls, tokens, wall time, CPU/GPU time, and human review minutes.

Metrics must be sliceable by domain, task type, difficulty level, tool
combination, generator role, verifier type, role name, role output type,
capability-gap type, proposed tool, proposed tool side-effect class, proposal
outcome, branch depth, selected branch, branch outcome, fallback count, and
seed-transformation type, taxonomy node, suggestion outcome, editor action, edit
rejection cause, source kind, license policy outcome, external-source
eligibility, source rejection cause, environment-source admission outcome, and
dataset version. Dataset reports should preserve trends over time so regressions
are visible instead of hidden inside aggregate averages.

## Dataset Output Contract

The default training export writes accepted samples, rejected candidates, a manifest,
and a quality report:

- `samples.jsonl`: accepted training records.
- `rejections.jsonl`: rejected candidate records with classified causes and retry
  eligibility in `details.retry_eligible`.
- `manifest.json`: dataset counts, artifact names, lineage/version summaries, and
  aggregate quality rates.
- `quality_report.json`: dataset-level counts, rates, rejection-cause counts, and
  deterministic metric slices.
- `tool_proposals.jsonl`: optional proposal-event records with the original
  capability gap, structured proposal, and local admission decision.
- `source_events.jsonl`: optional source-audit records written when source
  auditing is enabled.

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
  "lineage": {"seed_ids": [], "generator": {}, "source_provenance": {}, "solution_policy": {}, "refinement": {}, "verifier": {}}
}
```

`manifest.json` must include artifact references for `samples`, `rejections`, and
`quality_report`. When tool proposal, parent comparison, or review routing is
enabled, it also references `tool_proposals`, `parent_comparison`, and
`review_queue`. When source auditing is enabled, it references
`source_events`; manifests also include `source_policy_hashes` when samples or
source-gated rejections carry source provenance.

`lineage.source_provenance` records the source bundle id, source policy hash,
source ids, source kinds, license labels, license outcomes, retention/export
eligibility, `external_source_eligible`, and, for network-backed contacts
inputs, `environment_source_admission`. Environment metadata carries the same
source provenance so environment versions can be traced back to the policy hash
that admitted their source bundle. Network-backed environment reset recipes also
record source bundle id, source policy hash, contact count, and follow-up count;
they do not record raw source URLs or payload text. Rejected external source
material and rejected environment-source inputs use `source_policy_rejected` and
store sanitized source governance details under `details.source_governance`.

Trajectory events currently supported by the contract are:

- `action`: tool name and JSON arguments submitted by the solution policy.
- `observation`: structured tool result returned by the registry.
- `state_change`: sanitized state mutation summary for mutating tools.
- `final_response`: final assistant response assembled from the executed policy.

`lineage.solution_policy` is present when a scripted or remote policy generator
is used separately from task generation. It follows the same sanitized role
metadata shape as `lineage.generator`.

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
  and environment-source admission outcome.

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
`llm_response_schema_error`. Generation-stage rejection details include sanitized
`error_class`, `retry_count`, and `retry_eligible` values, and must not include raw
provider payloads, prompts, headers, or credentials.

### Parent Comparison Contract

When a local parent manifest or quality report path is supplied, the pipeline writes
`parent_comparison.json` with `schema_version: parent_comparison_v1`. The comparison
records accepted-count delta, rejected-count delta, success-rate delta,
executable-rate delta, new and removed slice keys, and rejection-cause deltas.

### Human Review Queue Contract

When review routing is enabled for reviewable failures, the pipeline writes
`review_queue.jsonl`. Each record uses `schema_version: human_review_record_v1` and
contains `candidate_id`, `cause`, `task`, `uncertainty_reason`, `source_artifact`,
and `created_at`. The default foundation run keeps review routing disabled.

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
