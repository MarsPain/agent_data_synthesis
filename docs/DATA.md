# Data

## Canonical Entities

- **Seed:** source material, domain description, task taxonomy, or prior accepted sample used to start generation.
- **Environment:** executable stateful world with reset/checkpoint behavior.
- **Tool:** typed callable action exposed to the Agent.
- **Task:** user-facing goal plus structured constraints and difficulty metadata.
- **Trajectory:** ordered interaction events including tool calls and observations.
- **Verifier:** independent checks that decide whether a trajectory satisfies the task.
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

Metrics must be sliceable by domain, task type, difficulty level, tool combination, generator role, verifier type, and dataset version. Dataset reports should preserve trends over time so regressions are visible instead of hidden inside aggregate averages.

## Dataset Output Contract

The default training export should be JSONL plus a manifest:

```json
{
  "sample_id": "sample_...",
  "dataset_version": "dataset_...",
  "environment": {"id": "...", "version": "..."},
  "tools": [{"name": "...", "schema": {}, "version": "..."}],
  "task": {"instruction": "...", "constraints": {}, "difficulty": {}},
  "trajectory": [{"type": "action", "tool": "...", "arguments": {}, "observation": {}}],
  "final_response": "...",
  "verification": {"passed": true, "checks": []},
  "quality": {"scores": {}, "tags": []},
  "lineage": {"seed_ids": [], "generator": {}, "verifier": {}}
}
```

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

- Remote provider base URL host or provider alias.
- `AGENT_DATA_LLM_MODEL` value.
- Prompt, template, and runtime config hashes.
- Request role, retry count, error class, token counts, and cost metadata when available.

Do not store `AGENT_DATA_API_KEY` or raw provider credentials in manifests, samples, trajectory logs, or rejected-candidate diagnostics.
