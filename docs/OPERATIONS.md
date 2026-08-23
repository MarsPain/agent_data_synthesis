# Local Synthesis Operations

`main.py` remains synchronous unless the operator explicitly enables local
orchestration. The ordinary command is unchanged:

```bash
uv run python main.py --output-dir artifacts/foundation
```

## Create a job

Async execution requires a validated run profile and a stable job identifier.
The job state is owned by the selected output directory.

```bash
uv run python main.py \
  --run-profile tests/fixtures/run_profiles/profile-local-workspace-tasks.json \
  --enable-async-runner \
  --job-id workspace-local-01 \
  --output-dir artifacts/workspace-local-01
```

`--enable-async-runner` also accepts the opt-in aliases `--enable-async` and
`--async`. If `--max-concurrency` is omitted, the durable job records one
worker. A positive bound can be selected explicitly:

```bash
uv run python main.py \
  --run-profile tests/fixtures/run_profiles/profile-local-contacts.json \
  --enable-async-runner \
  --job-id contacts-local-02 \
  --max-concurrency 2 \
  --output-dir artifacts/contacts-local-02
```

The bound is part of job identity and cannot change during resume. CLI feature
switches that affect a profile's execution must be declared in the profile so
the durable configuration remains hash-bound. Profile-local sources continue
through source admission and domain-owned importers.

Profiles that enable task expansion or refinement remain synchronous-only until
their additional work is represented in the durable job ledger; async mode
rejects them before execution rather than silently dropping that work.

## Inspect status and artifacts

The completion line reports the job status and durable paths. The local state
is under:

```text
<output-dir>/orchestration/<job-id>/
  job.json             lifecycle, configuration identity, and counts
  work_items.jsonl     candidate or coverage-slot dispositions
  events.jsonl         append-only integrity-chained journal
  provider_usage.json  sanitized role, attempt, token, and price evidence
```

Core dataset artifacts stay at the output root: `samples.jsonl`,
`rejections.jsonl`, `manifest.json`, `quality_report.json`, and any explicitly
requested evaluation, episode, coverage, or release reports. Orchestration
files are separate and are not attached to a dataset manifest or release pack.

## Cancel and resume

Press `Ctrl-C` or send `SIGTERM` to an active async process. Both signals set a
cooperative cancellation signal. The runner stops picking up new work, drains
bounded in-flight work where possible, records interrupted dispositions, and
finishes with a valid `cancelled` job snapshot. Repeated cancellation is
idempotent. A cancelled dataset manifest is diagnostic and marked incomplete;
it cannot pass fulfillment or release gates.

Resume with the same output directory and job identity:

```bash
uv run python main.py \
  --run-profile tests/fixtures/run_profiles/profile-local-workspace-tasks.json \
  --enable-async-runner \
  --job-id workspace-local-01 \
  --resume \
  --output-dir artifacts/workspace-local-01
```

Resume validates the profile/configuration hash, output ownership, journal,
provider identity, authorization, and concurrency before provider work begins.
Missing state, drift, unsafe ownership, malformed history, or an exhausted
logical-call budget fails closed. Completed jobs are inspectable but are not
reprocessed.

## Provider authorization and ambiguity

Async LLM profiles require an explicit cumulative logical-call budget. Provider
and model aliases are sanitized identity values, while credentials remain in
the normal environment configuration:

```bash
uv run python main.py \
  --run-profile tests/fixtures/contacts-coverage-tracer.json \
  --use-llm \
  --enable-async-runner \
  --job-id contacts-provider-01 \
  --logical-call-budget 6 \
  --provider-alias approved-provider \
  --model-alias approved-model \
  --output-dir artifacts/contacts-provider-01
```

Issued attempts consume the cumulative budget, including attempts whose
responses are lost and later classified as `ProviderResponseLost` or
ambiguous. The journal and usage summary retain sanitized role lineage,
adapter retry counts, allowlisted token fields, and provider-reported price
metadata when present. Missing price metadata is reported as unavailable; it
is never inferred from tokens. Raw prompts, provider payloads, credentials,
authorization headers, private source rows, and host paths are not durable
orchestration material.

Contacts, mobile messages, and workspace tasks use the same runner boundary.
Deterministic fixture runs should produce the same core samples, rejections,
ordering, quality, evaluation, and applicable coverage evidence as the
synchronous command. Async mode does not automatically activate from a profile
decision and does not add a service, remote control endpoint, provider
authority, or release promotion.

## Live Workspace Release Candidate acceptance

The Workspace tracer's real leg is a separate, explicitly authorized command.
It is not a default pipeline mode and a prior authorization does not authorize
a new provider-spending attempt:

```bash
uv run python scripts/run_workspace_live_acceptance.py \
  --authorize-live-provider \
  --authorization-id <fresh-authorization-id> \
  --candidate-budget 24 \
  --attempt-budget 24 \
  --generator-model <generator-model> \
  --mutation-judge-model <independent-judge-model> \
  --max-generator-retries <0-3> \
  --output-dir artifacts/workspace-live-acceptance-<date>
```

The command requires the fixed coverage-enabled Workspace Release Candidate
profile, a generator and a distinct mutation-admission judge identity, and the
normal provider environment variables. Before any generation call, it sends one
fixed, non-source-backed request through the production semantic-judge contract.
The preflight uses the profile retry limit and is included in a physical judge
call ceiling derived from the approved coverage attempt ceiling. A preflight
failure stops before generation spend.

The current DeepSeek V4-Pro judge profile explicitly sets
`thinking_mode: disabled` and a 90-second bounded deadline. The judge-only
client emits the documented top-level `"thinking": {"type": "disabled"}`
request field; the setting contributes to the sanitized judge configuration
identity. It is not an environment variable and does not affect the task
generator. See the
[DeepSeek thinking and timeout research](references/deepseek-thinking-timeout-research.md)
before changing the bound timeout or retry policy again.

The explicitly authorized generator retry limit is 0 through 3. It remains
separate from the logical attempt budget: the frozen evidence binds the derived
physical generator-call ceiling (`attempt budget × (retry limit + 1)`) and the
observed physical-call count.

An unsuccessful authorized attempt writes
`live_attempt_failure.json`. It records the authorization and run binding,
bounded generation and judge usage, bounded judge failure-class totals, a
bounded rejection-cause summary, and whether a qualification was reached. It
never records provider responses,
prompts, credentials, source payloads, or a tracer proof. The CLI prints that
record's path when available. Only an independently verified Release Candidate
may freeze `trace/provider.json` and construct the `real_live` tracer proof;
neither outcome is publication approval or a training recommendation.
