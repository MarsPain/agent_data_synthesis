# Data

## Canonical Entities

- **Seed:** source material, domain description, task taxonomy, or prior accepted sample used to start generation.
- **Environment:** executable stateful world with reset/checkpoint behavior.
- **Tool:** typed callable action exposed to the Agent.
- **Task:** user-facing goal plus structured constraints and difficulty metadata.
- **Solution Policy:** selected or generated ordered tool-use plan for satisfying
  a task.
- **Trajectory:** ordered interaction events including tool calls, observations,
  state changes, and final responses.
- **Verifier:** independent checks that decide whether a trajectory satisfies the task.
- **Refinement Attempt:** bounded critic diagnosis plus one revised candidate or
  solution policy used to rerun a failed candidate.
- **Role Definition:** registry entry that names a generation or verification
  role, owner module, output type, enabled state, retry policy, and lineage
  fields.
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
combination, generator role, verifier type, role name, role output type, and
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

```json
{
  "sample_id": "sample_...",
  "dataset_version": "dataset_...",
  "environment": {"id": "...", "version": "..."},
  "tools": [{"name": "...", "schema": {}, "version": "..."}],
  "task": {"instruction": "...", "constraints": {}, "difficulty": {}},
  "trajectory": [{"type": "action", "tool": "...", "arguments": {}}],
  "final_response": "...",
  "verification": {"passed": true, "checks": []},
  "quality": {"scores": {}, "tags": []},
  "lineage": {"seed_ids": [], "generator": {}, "solution_policy": {}, "refinement": {}, "verifier": {}}
}
```

`manifest.json` must include artifact references for `samples`, `rejections`, and
`quality_report`. When parent comparison or review routing is enabled, it also
references `parent_comparison` and `review_queue`.

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
- `slices`, keyed by deterministic dimensions currently available in foundation
  records: dataset version, domain, task type, difficulty level, curriculum level,
  tool combination, generator role, verifier type, rejection cause, refinement
  status, role name, and role output type.

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
stable local lineage from runtime configuration, but remote samples should use the
candidate-level and policy-level provider lineage rather than reconstructing it
later.

The default role registry currently enables `task_generation`, `solution_policy`,
and `critic_refinement`. It also defines disabled guardrails for
`environment_generation`, `tool_generation`, `verifier_generation`,
`judge_verification`, `task_suggester`, and `task_editor`; these roles must fail
before any provider call until a later plan explicitly enables and validates
their output contracts.

Do not store `AGENT_DATA_API_KEY` or raw provider credentials in manifests, samples, trajectory logs, or rejected-candidate diagnostics.
