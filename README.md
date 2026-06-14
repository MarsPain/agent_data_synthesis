# Agent Data Synthesis

Agent Data Synthesis is an early-stage Python project for building an automated framework that generates, validates, and versions agent training data. The design target is not simple instruction-response expansion. The framework should synthesize executable agent trajectories across environments, tools, tasks, observations, and verification results.

## Current State

- The repository currently contains the initial design documentation and a small local foundation runner.
- `main.py` builds a SQLite contact fixture, registers a typed lookup tool, executes candidate tasks, verifies trajectories independently, and writes JSONL plus a manifest.
- The architecture is documented before implementation so later code can follow stable domain boundaries.
- The current implementation is intentionally small; treat `docs/` as the source of truth for design and development guidance.
- The synchronous pipeline now delegates candidate-level gate execution to a typed candidate-processing boundary while keeping artifact assembly ordered and local.
- Profile runs can optionally write a sanitized `profile_decision_report.json`
  with explicit async orchestration, semantic duplicate detection, and MVP
  quality-floor decisions.
- Runs can optionally write a sanitized `evaluation_report.json` from a
  deterministic held-out contacts suite; profile decision reports include that
  evidence when both report flags are supplied.
- Runs can optionally write sanitized `episodes.jsonl`,
  `episode_quality_report.json`, and `episode_replay_report.json` artifacts for
  runtime episode evidence scoring and executable replay consistency checks.
- Candidate execution now derives internal task-intent, policy-hint,
  expected-outcome, and expected-state contracts before policy execution and
  verification while preserving the public sample and rejection schemas.
- The planned synthesis pipeline is LLM-driven through a remote OpenAI-compatible API. It does not include local LLM cluster deployment.

## Documentation Map

- [ARCHITECTURE.md](ARCHITECTURE.md): top-level system map.
- [AGENTS.md](AGENTS.md): agent working guide and repository navigation.
- [docs/README.md](docs/README.md): canonical documentation index.
- [docs/DESIGN.md](docs/DESIGN.md): core architecture contracts.
- [docs/design-docs/agent-data-synthesis-framework.md](docs/design-docs/agent-data-synthesis-framework.md): deep design for the Agent data synthesis framework.
- [docs/references/agent-data-synthesis-pdf-analysis.md](docs/references/agent-data-synthesis-pdf-analysis.md): structured analysis of `Agent-数据合成.pdf`.
- [docs/PLANS.md](docs/PLANS.md): implementation plan index.

## Development Commands

```bash
uv run python main.py
uv run python main.py --output-dir artifacts/foundation --dataset-version dataset_foundation_v1
uv run python main.py --enable-refinement --output-dir artifacts/foundation-refined
uv run python main.py --enable-branching --output-dir artifacts/foundation-branching
uv run python main.py --enable-task-expansion --output-dir artifacts/foundation-task-expansion
uv run python main.py --enable-source-governance-fixture --output-dir artifacts/foundation-source-governance
uv run python main.py --write-episode-replay-report --output-dir artifacts/foundation-episode-replay
uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-scale-probe-25.json --write-evaluation-report --write-profile-decision-report --output-dir artifacts/foundation-scale-probe
uv run python main.py --use-llm --output-dir artifacts/foundation-llm
uv run python scripts/evaluation_report.py --manifest artifacts/foundation/manifest.json --quality-report artifacts/foundation/quality_report.json
uv run python scripts/validate_docs.py
uv run python -m unittest
```

## LLM Configuration

LLM-backed generation and judge steps should read these environment variables:

- `AGENT_DATA_LLM_BASE_URL`: OpenAI-compatible remote API base URL.
- `AGENT_DATA_API_KEY`: API key for the configured remote LLM provider.
- `AGENT_DATA_LLM_MODEL`: model id used by the synthesis pipeline.

The default local runner uses deterministic fixture candidates so it can run without provider credentials. Pass `--enable-refinement` to enable the deterministic one-shot critic/refinement fixture loop. Pass `--enable-branching` to include the deterministic multi-path branching fixture. Pass `--enable-task-expansion` to include deterministic seed transformation and task suggester/editor expansion. Pass `--enable-source-governance-fixture` to exercise deterministic no-network external-source governance and write `source_events.jsonl`. Pass `--use-llm` to generate candidates through the configured remote OpenAI-compatible `/chat/completions` API.

## Repository Rules

- Keep root files concise and use them as navigation entrypoints.
- Keep deep design, data, backend, security, and product decisions under `docs/`.
- Update docs and implementation in the same change whenever architecture, workflows, schemas, or entrypoints change.
