# Agent Working Map

This repository has one active Agent-first synthesis core in `agent_synthesis/`.
Root files are maps; canonical detail lives under `docs/`.

## Start here

- [README.md](README.md): onboarding and current acceptance disclosure.
- [ARCHITECTURE.md](ARCHITECTURE.md): package and dependency map.
- [CONTEXT.md](CONTEXT.md): canonical Domain glossary.
- [docs/README.md](docs/README.md): documentation index.
- [docs/DESIGN.md](docs/DESIGN.md): core design.
- [docs/OPERATIONS.md](docs/OPERATIONS.md): run, resume, replay, and review.
- [docs/agents/issue-tracker.md](docs/agents/issue-tracker.md): tracker rules.
- [.scratch/README.md](.scratch/README.md): current work and exceptions.
- [docs/PLANS.md](docs/PLANS.md): historical plan archive.

## Working rules

- Keep terminology in `CONTEXT.md` and canonical designs under `docs/`.
- Keep current work state, dependencies, and technical debt in `.scratch/`.
- Keep runtime outputs under `artifacts/` and generated documentation under
  `docs/generated/` or `docs/references/`.
- Preserve links when moving documents; update documentation validation when
  changing structure.
- Never describe deterministic or AI-reviewed Episodes as human-approved.
- Provider use requires a fresh, explicit authorization and bounded run plan.

## Commands

```bash
uv run python main.py --help
uv run python main.py run --configuration <configuration.json> --output-directory artifacts/<run> --fixture-responses <responses.jsonl>
uv run python main.py resume --configuration <configuration.json> --output-directory artifacts/<run> --fixture-responses <responses.jsonl>
uv run python main.py replay --output-directory artifacts/<run>
uv run python main.py create-review-queue --output-directory artifacts/<run> --cohort-id <id> --purpose held-out-evaluation
uv run python main.py import-review-labels --output-directory artifacts/<run> --labels <human-labels.jsonl>
uv run python scripts/validate_docs.py
uv run python -m unittest
```
