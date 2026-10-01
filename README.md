# Agent Data Synthesis

[简体中文](README.zh.md)

Agent Data Synthesis generates executable Agent Episodes from three local Domains:
Contacts, Mobile Messages, and Workspace Tasks. The Agent-first engine owns
bounded model calls, isolated task execution, deterministic admission, private
SQLite state, replay, and sanitized dataset collections. Shadow quality review
is the default; deterministic admission does not imply human approval.

## Quick start

Python 3.13 or newer and `uv` are required.

```bash
uv sync
uv run python main.py --help
uv run python scripts/validate_docs.py
uv run python -m unittest
```

`main.py` provides `run`, `resume`, `replay`, `create-review-queue`, and
`import-review-labels` commands.
A run requires a validated JSON [configuration](docs/OPERATIONS.md) and either
scripted fixture responses or a separately authorized remote provider. No
provider is called by default. Outputs go to the chosen directory under
`artifacts/`: `demonstrations.jsonl`, `negatives.jsonl`, `manifest.json`,
`quality_report.json`, `provider_usage.json`, and `run_report.json`.

The old `synthesis/` and `awm_runtime/` implementations and their commands were
removed at cutover. Earlier artifacts and profiles are historical; regenerate
with the current interface instead of reading them through compatibility code.

## Acceptance status

The frozen three-Domain live cohort has 40 Agent Episodes per Domain. An AI
review found 106 pass, 13 fail, and 1 uncertain. It is diagnostic and does not
satisfy direct-human dataset acceptance. The operator directed cutover work to
proceed under an explicit exception. See [current work](.scratch/README.md)
for the exact decision and remaining work. No unreviewed Episode is labeled
human-approved.

## Documentation

- [Architecture](ARCHITECTURE.md) maps packages and boundaries.
- [Glossary](CONTEXT.md) defines the current Domain language.
- [Documentation index](docs/README.md) points to canonical detail and history.
- [Operations](docs/OPERATIONS.md) gives run and recovery commands.
- [Agent map](AGENTS.md) gives repository working rules.
