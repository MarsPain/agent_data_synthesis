# Agent-first Operations

All commands use the single active `agent_synthesis` core through `main.py`.
Use Python 3.13 or newer. Outputs belong under `artifacts/`.

## Offline run

Create a validated configuration JSON. The minimal required fields are
`run_id`, `domain_id` (`contacts`, `mobile_messages`, or `workspace_tasks`),
`model_id`, and `slot_limit`. Set `accepted_target` when a particular count is
required. The configuration also supports bounded generation batches,
concurrency, steps, per-role physical requests, retries, timeouts, and optional
shadow review. `agent_synthesis.configuration.RunConfiguration` owns the exact
schema.

```bash
uv run python main.py run \
  --configuration <configuration.json> \
  --output-directory artifacts/<run> \
  --fixture-responses <responses.jsonl>
```

`responses.jsonl` contains one strict JSON model decision per physical call,
in dispatch order. This path is for scripted offline fixtures. `--source` may
select a local Domain source file; without it, the built-in fixture is used.
A fresh run directory is required. Inspect `run_report.json`,
`provider_usage.json`, `demonstrations.jsonl`, `negatives.jsonl`, and
`manifest.json` after completion.

## Live provider run

A live attempt requires a fresh authorization for its exact model, source,
request ceilings, and purpose. The command checks authorization before any
provider dispatch:

```bash
AGENT_DATA_LLM_BASE_URL=<base-url> AGENT_DATA_API_KEY=<secret> \
AGENT_DATA_LLM_MODEL=<remote-model> \
uv run python main.py run \
  --configuration <configuration.json> \
  --output-directory artifacts/<run> \
  --authorize-live-provider --authorization-id <nonsecret-id>
```

The CLI does not infer live authorization from environment variables alone.
A resume that may call the provider needs its own fresh authorization ID.
Do not use a prior acceptance-campaign authorization for a new run.

## Resume and replay

Resume repeats the same configuration and model adapter selection while using
the persisted frozen state and request ledger. It does not repeat terminal
Episodes. A scripted resume supplies only decisions still needed.

```bash
uv run python main.py resume \
  --configuration <configuration.json> \
  --output-directory artifacts/<run> \
  --fixture-responses <remaining-responses.jsonl>
uv run python main.py replay --output-directory artifacts/<run>
```

Replay calls no provider and writes `replay_report.json`. It reports whether
saved observations and assessments align with reconstructed execution.

## Blind review

Freeze a blind queue from a completed run before labeling:

```bash
uv run python main.py create-review-queue \
  --output-directory artifacts/<run> \
  --cohort-id <unique-cohort-id> \
  --purpose held-out-evaluation
```

Use the resulting `blind_review_queue.jsonl`. A human reviewer
submits direct labels with the required five dimensions, Episode/cohort IDs,
and direct-human provenance. Import those labels without a model or provider:

```bash
uv run python main.py import-review-labels \
  --output-directory artifacts/<run> \
  --labels <human-labels.jsonl>
```

AI diagnostics are separate artifacts and are not valid inputs to this command.
The prior three-Domain campaign procedure and decision files are retained under
`artifacts/agent-first-acceptance-20260924/`; its formal dataset result remains
incomplete under the operator-directed cutover exception.
