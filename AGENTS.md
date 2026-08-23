# Agent Working Map

This repository is an early-stage Agent data synthesis framework. Root files are maps; canonical detail lives in `docs/`.

## Start Here

- Human onboarding: [README.md](README.md)
- Architecture map: [ARCHITECTURE.md](ARCHITECTURE.md)
- Domain glossary: [CONTEXT.md](CONTEXT.md)
- Docs index: [docs/README.md](docs/README.md)
- Core design: [docs/DESIGN.md](docs/DESIGN.md)
- Deep framework design: [docs/design-docs/agent-data-synthesis-framework.md](docs/design-docs/agent-data-synthesis-framework.md)
- Architecture explainers: [docs/design-docs/architecture-explainers.md](docs/design-docs/architecture-explainers.md)
- PDF source analysis: [docs/references/agent-data-synthesis-pdf-analysis.md](docs/references/agent-data-synthesis-pdf-analysis.md)
- Operator workflows: [docs/OPERATIONS.md](docs/OPERATIONS.md)
- Issue-tracker configuration: [docs/agents/issue-tracker.md](docs/agents/issue-tracker.md)
- Current work: [.scratch/README.md](.scratch/README.md)
- Historical plan archive: [docs/PLANS.md](docs/PLANS.md)

## Working Rules

- Do not put long specifications in this file.
- Keep terminology in `CONTEXT.md`, canonical designs/specs under `docs/`, and work state, dependencies, assignment, and technical debt only in `.scratch/`.
- Keep runtime pipeline outputs under `artifacts/`.
- Keep generated documentation assets, schemas, diagrams, reports, or source analyses under `docs/generated/` or `docs/references/`.
- Preserve links when moving documents.
- Update tests or validation when changing documentation structure.

## Commands

```bash
uv run python main.py
uv run python main.py --enable-branching --output-dir artifacts/foundation-branching
uv run python main.py --enable-task-expansion --output-dir artifacts/foundation-task-expansion
uv run python main.py --enable-source-governance-fixture --output-dir artifacts/foundation-source-governance
uv run python main.py --enable-network-source --source-url https://allowed.example.test/contacts.json --source-license-label cc-by-4.0 --allowed-source-host allowed.example.test --mock-source-fixture tests/fixtures/contacts.json --output-dir artifacts/foundation-network-source
uv run python main.py --run-profile tests/fixtures/run_profiles/profile-local-workspace-tasks.json --write-episode-replay-report --write-reward-label-report --output-dir artifacts/profile-local-workspace
uv run python main.py --write-episode-replay-report --output-dir artifacts/foundation-episode-replay
uv run python main.py --write-reward-label-report --output-dir artifacts/foundation-reward-labels
uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-scale-probe-25.json --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --output-dir artifacts/foundation-scale-probe
uv run python scripts/write_representative_scale_evidence.py --campaign artifacts/evidence-campaign/campaign.json --output artifacts/evidence-campaign/representative_scale_evidence.json
uv run python scripts/write_downstream_benchmark_bundle.py --release-pack artifacts/contacts-release/dataset_release_pack.json --benchmark-suite-id external_agent_tasks_v1 --benchmark-suite-version external_agent_tasks_v1 --output artifacts/downstream/downstream_benchmark_bundle.json
uv run python scripts/import_downstream_benchmark_result.py --bundle artifacts/downstream/downstream_benchmark_bundle.json --observation artifacts/downstream/external_observation.json --output artifacts/downstream/downstream_benchmark_result.json
uv run python scripts/export_mutation_calibration_packet.py --corpus-version mutation_calibration_corpus_v1 --output-dir artifacts/mutation-calibration
uv run python scripts/import_mutation_calibration_labels.py --packet artifacts/mutation-calibration/mutation_calibration_review_packet.json --split-freeze artifacts/mutation-calibration/mutation_calibration_split_freeze.json --labels artifacts/mutation-calibration/human_labels.jsonl --output artifacts/mutation-calibration/reviewed_mutation_calibration_corpus.json
uv run python scripts/run_workspace_live_acceptance.py --authorize-live-provider --authorization-id <id> --candidate-budget 24 --attempt-budget 24 --generator-model <generator-model> --mutation-judge-model <independent-judge-model>
uv run python scripts/validate_docs.py
uv run python -m unittest
```

## Current Implementation Shape

- `main.py` runs the local foundation pipeline synchronously by default and writes runtime outputs to `artifacts/foundation/`; validated run profiles can opt into durable local orchestration.
- The implementation follows the bounded contexts in [ARCHITECTURE.md](ARCHITECTURE.md).
- Current work state is owned by the [local issue tracker](.scratch/README.md).
- Async local orchestration is complete with resumable jobs, bounded concurrency, cooperative cancellation, sanitized usage evidence, CLI opt-in, and deterministic three-domain parity.
- Live Workspace acceptance is a separate explicitly authorized CLI path; it freezes sanitized provider evidence and builds a `real_live` tracer proof, while the default pipeline remains offline/provider-free.
- The latest completed historical execution plan is [docs/exec-plans/completed/0046-final-answer-grounding-and-generation-diversity.md](docs/exec-plans/completed/0046-final-answer-grounding-and-generation-diversity.md).
