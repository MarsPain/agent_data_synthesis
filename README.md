# Agent Data Synthesis

[简体中文](README.zh.md)

Agent Data Synthesis is a local-first Python framework for generating,
executing, validating, and packaging agent-training data. It accepts records
only when executable environment state, tool calls, observations, verification,
lineage, and quality evidence support them; it is not a flat
instruction-response expander.

## Current Status

The repository is an early-stage but working framework. Its default workflow is
offline and deterministic; it currently supports Contacts, synthetic mobile
messages, and Workspace tasks through one shared domain-pipeline boundary.

- A synchronous local foundation run is the default. Validated run profiles can
  opt into durable local orchestration with bounded concurrency, resumption,
  cancellation, and sanitized usage evidence.
- Governed sources, isolated candidate execution, contract and state
  verification, replay, reward labels, held-out evaluation, coverage evidence,
  release-admission reports, hash-bound evidence packs, and the current
  Contacts release-evidence/qualification adapter are implemented as explicit
  opt-ins.
- A separately authorized, real-provider Workspace acceptance has completed and
  its sanitized evidence can be replayed offline. It establishes one
  **Release Candidate** only—not publication approval, a training
  recommendation, or downstream model improvement.
- Local LLM serving, distributed workers, external MCP servers, and publishing
  a separate `awm_runtime` package remain deferred.

For live work status, dependencies, and technical debt, use the
[local issue tracker](.scratch/README.md); it is the repository's sole source
of truth for those items.

## Requirements

- Python 3.13 or newer
- [uv](https://docs.astral.sh/uv/)

## Quick Start

```bash
uv sync
uv run python main.py
uv run python scripts/validate_docs.py
uv run python -m unittest
```

The default run writes to `artifacts/foundation/`:

```text
samples.jsonl
rejections.jsonl
manifest.json
quality_report.json
```

## Choose a Workflow

### Run a local domain profile

Use a checked-in profile to exercise the Workspace path and write executable
replay and reward-label evidence:

```bash
uv run python main.py \
  --run-profile tests/fixtures/run_profiles/profile-local-workspace-tasks.json \
  --write-episode-replay-report \
  --write-reward-label-report \
  --output-dir artifacts/profile-local-workspace
```

### Inspect coverage without a provider call

Coverage-plan previews are local and provider-free:

```bash
uv run python main.py \
  --run-profile tests/fixtures/run_profiles/contacts-coverage-smoke.json \
  --preview-coverage-plan
```

### Use async or provider-backed workflows

- For durable local jobs, resumption, cancellation, and provider-call budgets,
  follow [Local Synthesis Operations](docs/OPERATIONS.md).
- `--use-llm` calls a remote OpenAI-compatible API. Configure credentials in
  the environment; the framework keeps secrets, raw provider payloads, prompts,
  and private source rows out of durable public artifacts. See
  [Security](docs/SECURITY.md).
- For release reports, packs, quality audits, and artifact schemas, start with
  [Data](docs/DATA.md) and use `uv run python main.py --help` as the current
  CLI contract.
- Live Workspace acceptance is a separate, paid/provider-backed command that
  requires a fresh explicit authorization for every attempt. It is not a normal
  test or default pipeline mode; follow its
  [operator procedure](docs/OPERATIONS.md#live-workspace-release-candidate-acceptance).

All non-default artifact families are opt-ins. Evidence and qualification
artifacts do not themselves publish a dataset, authorize training, or prove a
downstream gain.

## Find the Right Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) — top-level domains and package map.
- [CONTEXT.md](CONTEXT.md) — canonical domain glossary.
- [docs/README.md](docs/README.md) — index of core docs, deep design, specs,
  ADRs, references, generated analysis, and historical records.
- [docs/DESIGN.md](docs/DESIGN.md) — system contracts and bounded contexts.
- [docs/OPERATIONS.md](docs/OPERATIONS.md) — async and explicitly authorized
  live-provider operations.
- [docs/DATA.md](docs/DATA.md) — schemas, artifact families, lineage, and
  quality rules.
- [docs/SECURITY.md](docs/SECURITY.md) — source, sandbox, provider, and secret
  handling boundaries.
- [AGENTS.md](AGENTS.md) — concise working map and operating constraints for
  coding agents.

## Repository Conventions

- Root files are maps; canonical design, specification, and operational detail
  lives under `docs/`.
- `CONTEXT.md` owns terminology, while `.scratch/` owns current work state.
- Runtime outputs belong in `artifacts/`.
- Update implementation and its affected documentation together.
