# Agent Working Map

This repository is an early-stage Agent data synthesis framework. Root files are maps; canonical detail lives in `docs/`.

## Start Here

- Human onboarding: [README.md](README.md)
- Architecture map: [ARCHITECTURE.md](ARCHITECTURE.md)
- Docs index: [docs/README.md](docs/README.md)
- Core design: [docs/DESIGN.md](docs/DESIGN.md)
- Deep framework design: [docs/design-docs/agent-data-synthesis-framework.md](docs/design-docs/agent-data-synthesis-framework.md)
- Architecture explainers: [docs/design-docs/architecture-explainers.md](docs/design-docs/architecture-explainers.md)
- PDF source analysis: [docs/references/agent-data-synthesis-pdf-analysis.md](docs/references/agent-data-synthesis-pdf-analysis.md)
- Plan index: [docs/PLANS.md](docs/PLANS.md)

## Working Rules

- Do not put long specifications in this file.
- Treat `docs/` as the source of truth for architecture, data contracts, security rules, and implementation plans.
- Keep runtime pipeline outputs under `artifacts/`.
- Keep generated documentation assets, schemas, diagrams, reports, or source analyses under `docs/generated/` or `docs/references/`.
- Preserve links when moving documents.
- Update tests or validation when changing documentation structure.

## Commands

```bash
uv run python main.py
uv run python scripts/validate_docs.py
uv run python -m unittest
```

## Current Implementation Shape

- `main.py` runs the local foundation pipeline and writes runtime outputs to `artifacts/foundation/` by default.
- The implementation follows the bounded contexts in [ARCHITECTURE.md](ARCHITECTURE.md).
- Latest completed work is documented in [docs/exec-plans/completed/0003-quality-reporting-and-curriculum-foundation.md](docs/exec-plans/completed/0003-quality-reporting-and-curriculum-foundation.md).
