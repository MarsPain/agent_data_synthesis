# Agent Data Synthesis

Agent Data Synthesis is a local-first Python framework for generating,
executing, validating, and packaging agent training data. It is not an
instruction-response expander: accepted records are grounded in executable
environment state, tool calls, observations, verifier results, lineage, and
quality evidence.

The repository is still early-stage, but it now has a working synchronous
pipeline with three deterministic domains, source governance, profile-based runs,
runtime episode evidence, replay checks, reward-label export, and release
admission artifacts. Canonical design detail lives in [docs/](docs/).

## What Works Now

- `main.py` runs the local synchronous foundation pipeline and writes outputs
  under `artifacts/foundation/` by default.
- Contacts, synthetic mobile-message, and workspace-task domains run through a
  shared domain pipeline boundary.
- Stable runtime and episode primitives are available through the in-repository
  `awm_runtime` package. Runtime-facing code imports `awm_runtime` directly, or
  `synthesis.runtime_registry` for the repository-owned default
  contacts/mobile/workspace descriptor registry.
- `run_profile_v1` and `run_profile_v2` fixtures configure deterministic local
  runs, scale probes, release candidates, and profile-local governed sources.
- Profile-local JSON sources are admitted through shared source governance, then
  parsed by domain-owned importers for contacts, mobile messages, or workspace
  tasks.
- Candidate processing validates task contracts, executes policies, verifies
  final answers and expected state, classifies rejections, and merges outcomes
  deterministically.
- Opt-in reports can add held-out evaluation, profile decisions, dataset release
  admission, release packs, release quality audits, release-review evidence,
  episode quality, executable replay, and deterministic reward labels.
- Remote LLM generation is supported through an OpenAI-compatible API, but local
  LLM serving, distributed workers, external MCP servers, Agentic RL rollout
  collection, and separate `awm_runtime` publishing are intentionally deferred.

## Quick Start

```bash
uv run python main.py
uv run python -m unittest
uv run python scripts/validate_docs.py
```

Default output is written to `artifacts/foundation/` and includes
`samples.jsonl`, `rejections.jsonl`, `manifest.json`, and
`quality_report.json`.

## Common Runs

```bash
# Contacts foundation variants
uv run python main.py --enable-branching --output-dir artifacts/foundation-branching
uv run python main.py --enable-task-expansion --output-dir artifacts/foundation-task-expansion
uv run python main.py --enable-source-governance-fixture --output-dir artifacts/foundation-source-governance

# Profile-driven contacts, mobile, and workspace runs
uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-scale-probe-25.json --write-evaluation-report --write-profile-decision-report --output-dir artifacts/foundation-scale-probe
uv run python main.py --run-profile tests/fixtures/run_profiles/profile-local-contacts.json --output-dir artifacts/profile-local-contacts
uv run python main.py --run-profile tests/fixtures/run_profiles/profile-local-mobile-messages.json --write-episode-replay-report --write-reward-label-report --output-dir artifacts/profile-local-mobile
uv run python main.py --run-profile tests/fixtures/run_profiles/profile-local-workspace-tasks.json --write-episode-replay-report --write-reward-label-report --output-dir artifacts/profile-local-workspace

# Controlled no-network test of the HTTPS source path
uv run python main.py --enable-network-source --source-url https://allowed.example.test/contacts.json --source-license-label cc-by-4.0 --allowed-source-host allowed.example.test --mock-source-fixture tests/fixtures/contacts.json --output-dir artifacts/foundation-network-source

# Release-candidate evidence packs
uv run python main.py --run-profile tests/fixtures/run_profiles/foundation-release-candidate.json --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --write-dataset-release-pack --write-release-quality-audit --write-dataset-release-card --output-dir artifacts/foundation-release-candidate
uv run python main.py --run-profile tests/fixtures/run_profiles/mobile-messages-release-candidate.json --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --write-dataset-release-pack --write-release-quality-audit --write-release-review-queue --write-dataset-release-card --output-dir artifacts/mobile-release-candidate
uv run python main.py --run-profile tests/fixtures/run_profiles/workspace-tasks-release-candidate.json --write-evaluation-report --write-profile-decision-report --write-dataset-release-report --write-dataset-release-pack --write-release-quality-audit --write-dataset-release-card --output-dir artifacts/workspace-release-candidate
uv run python scripts/verify_dataset_release.py --output-dir artifacts/foundation-release-candidate
uv run python scripts/verify_dataset_release.py --output-dir artifacts/mobile-release-candidate
uv run python scripts/verify_dataset_release.py --output-dir artifacts/workspace-release-candidate

# After a reviewer creates the local, reviewer-owned decisions file
uv run python scripts/write_review_resolution.py --output-dir artifacts/mobile-release-candidate --decisions-path artifacts/mobile-release-candidate/review_decisions.jsonl

# Offline representative-scale and downstream evidence exchange
uv run python scripts/write_representative_scale_evidence.py --campaign artifacts/evidence-campaign/campaign.json --output artifacts/evidence-campaign/representative_scale_evidence.json
uv run python scripts/write_downstream_benchmark_bundle.py --release-pack artifacts/contacts-release/dataset_release_pack.json --benchmark-suite-id external_agent_tasks_v1 --benchmark-suite-version external_agent_tasks_v1 --output artifacts/downstream/downstream_benchmark_bundle.json
uv run python scripts/import_downstream_benchmark_result.py --bundle artifacts/downstream/downstream_benchmark_bundle.json --observation artifacts/downstream/external_observation.json --output artifacts/downstream/downstream_benchmark_result.json
```

## Optional LLM Configuration

The deterministic fixture path runs without provider credentials. Pass
`--use-llm` to generate candidates through a remote OpenAI-compatible
`/chat/completions` API:

```bash
export AGENT_DATA_LLM_BASE_URL="https://provider.example/v1"
export AGENT_DATA_API_KEY="..."
export AGENT_DATA_LLM_MODEL="model-id"
uv run python main.py --use-llm --output-dir artifacts/foundation-llm
```

Provider calls are routed through role contracts and sanitized lineage. API
keys, headers, raw provider payloads, prompts, source payload rows, profile
paths, and host paths must not be written to public artifacts.

## Artifact Families

- Default dataset artifacts: `samples.jsonl`, `rejections.jsonl`,
  `manifest.json`, `quality_report.json`.
- Source and sandbox audits: `source_events.jsonl`, `sandbox_audits.jsonl`.
- Evaluation and release artifacts: `evaluation_report.json`,
  `profile_decision_report.json`, `dataset_release_report.json`,
  `dataset_release_pack.json`, `release_quality_audit.json`,
  `dataset_release_card.md`, opt-in `release_review_queue.jsonl`, and offline
  `review_resolution_report.json`.
- Standalone evidence artifacts: `representative_scale_evidence.json`,
  `downstream_benchmark_bundle.json`, and `downstream_benchmark_result.json`.
  They consume existing artifacts and are never written by default `main.py`.
- Review artifacts are separate: candidate rejection routing uses
  `review_queue.jsonl`; release-audit watch signals use
  `release_review_queue.jsonl`. The local reviewer-owned
  `review_decisions.jsonl` input is never attached to the manifest.
- Runtime evidence artifacts: `episodes.jsonl`,
  `episode_quality_report.json`, `episode_replay_report.json`,
  `reward_labels.jsonl`, `reward_label_report.json`.

All non-default artifact families are explicit opt-ins. Release-review artifacts
are absent by default, and review outcomes are evidence only: `reviewed` does
not mean approved or releaseable and changes no sample or release decision.
These artifacts are not proof of downstream model improvement.

## Documentation Map

- [AGENTS.md](AGENTS.md): compact working map for coding agents.
- [ARCHITECTURE.md](ARCHITECTURE.md): top-level architecture map.
- [docs/README.md](docs/README.md): canonical documentation index.
- [docs/DESIGN.md](docs/DESIGN.md): bounded contexts and core contracts.
- [docs/BACKEND.md](docs/BACKEND.md): current backend modules and execution flow.
- [docs/DATA.md](docs/DATA.md): schemas, artifacts, lineage, and quality rules.
- [docs/SECURITY.md](docs/SECURITY.md): source, sandbox, adapter, and secret
  handling rules.
- [docs/ROADMAP.md](docs/ROADMAP.md): staged development direction.
- [docs/PLANS.md](docs/PLANS.md): active, deferred, completed, and tech-debt
  implementation plans.
- [docs/design-docs/agent-data-synthesis-framework.md](docs/design-docs/agent-data-synthesis-framework.md):
  deep framework design.
- [docs/references/agent-data-synthesis-pdf-analysis.md](docs/references/agent-data-synthesis-pdf-analysis.md):
  structured analysis of `Agent-数据合成.pdf`.

## Repository Rules

- Keep root files concise and use them as navigation entrypoints.
- Treat `docs/` as the source of truth for architecture, data contracts,
  security rules, and implementation plans.
- Keep runtime pipeline outputs under `artifacts/`.
- Update affected docs and implementation together when workflows, schemas,
  commands, or architecture boundaries change.
