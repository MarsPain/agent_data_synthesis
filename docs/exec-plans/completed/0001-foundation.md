# Plan 0001: Local Executable Foundation

## Status

Completed on 2026-05-16.

## Goal

Build the first local-runner version of the Agent data synthesis framework with deterministic environments, typed tools, remote LLM-backed task generation, executable verification, and versioned JSONL exports.

## Scope

- Rename project metadata from the template name to the framework name.
- Create package boundaries matching [../../BACKEND.md](../../BACKEND.md). Initial modules now exist under `synthesis/`.
- Implement seed/domain config loading. Initial deterministic seed fixture exists.
- Implement remote LLM provider configuration from `AGENT_DATA_LLM_BASE_URL`, `AGENT_DATA_API_KEY`, and `AGENT_DATA_LLM_MODEL`. The pipeline now includes an OpenAI-compatible `/chat/completions` client for LLM-backed candidate generation and records provider host, model, token metadata, and config hash without writing secrets.
- Implement SQLite environment fixture generation. Initial contact fixture exists.
- Implement tool registry with typed schemas. Initial read-only contact lookup tool exists.
- Implement candidate task records and difficulty metadata. Initial accepted and rejected task fixtures exist.
- Implement trajectory event capture. Initial action, observation, and final-response events are captured.
- Implement independent verifier execution. Initial exact-answer verifier exists.
- Implement accepted sample assembly and manifest export. Initial JSONL, rejection, and manifest export exists.

## Implementation Progress

- `uv run python main.py` runs the first local foundation slice and writes runtime artifacts to `artifacts/foundation/`.
- The default first slice is deterministic so local validation can run without credentials.
- `uv run python main.py --use-llm` exercises the remote LLM-backed candidate generation path when `AGENT_DATA_LLM_BASE_URL`, `AGENT_DATA_API_KEY`, and `AGENT_DATA_LLM_MODEL` are configured.
- Judge-based verification and generated-code sandboxing remain out of scope for this first foundation slice.

## Completion Notes

- Completion commit: `0262162 feat: add foundation synthesis pipeline`.
- Default local run result: `accepted=1 rejected=1`.
- The LLM-backed smoke path was exercised during implementation and produced accepted samples after prompt grounding and candidate normalization.
- Follow-up contract work continued in [0002-data-contracts-and-quality-gates.md](0002-data-contracts-and-quality-gates.md), not by extending this completed foundation slice.

## Acceptance Criteria

- A local command can generate at least one verified sample from a small fixture domain.
- LLM-backed generation uses a remote OpenAI-compatible API and does not require local LLM cluster deployment.
- The accepted sample includes environment, tools, task, trajectory, verifier, quality, and lineage fields.
- Failed candidates are classified by cause.
- `uv run python scripts/validate_docs.py` passes.
- `uv run python -m unittest` passes.

## Validation

- `uv run python main.py --output-dir artifacts/foundation --dataset-version dataset_foundation_v1`
- `uv run python scripts/validate_docs.py`
- `uv run python -m unittest`

## Risks

- Generated code execution can become unsafe without sandboxing.
- Verifier quality can lag generator quality and accept shallow samples.
- Data contracts may churn if implemented before schemas are written down.

## Notes

Keep the first implementation small. Do not introduce distributed orchestration, MCP servers, model routing, or local LLM serving until local runner contracts are proven.
