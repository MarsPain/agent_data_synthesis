# Plan 0001: Local Executable Foundation

## Status

Active.

## Goal

Build the first local-runner version of the Agent data synthesis framework with deterministic environments, typed tools, remote LLM-backed task generation, executable verification, and versioned JSONL exports.

## Scope

- Rename project metadata from the template name to the framework name.
- Create package boundaries matching [../../BACKEND.md](../../BACKEND.md).
- Implement seed/domain config loading.
- Implement remote LLM provider configuration from `LLM_BASE_URL`, `API_KEY`, and `LLM_MODEL`.
- Implement SQLite environment fixture generation.
- Implement tool registry with typed schemas.
- Implement candidate task records and difficulty metadata.
- Implement trajectory event capture.
- Implement independent verifier execution.
- Implement accepted sample assembly and manifest export.

## Acceptance Criteria

- A local command can generate at least one verified sample from a small fixture domain.
- LLM-backed generation uses a remote OpenAI-compatible API and does not require local LLM cluster deployment.
- The accepted sample includes environment, tools, task, trajectory, verifier, quality, and lineage fields.
- Failed candidates are classified by cause.
- `uv run python scripts/validate_docs.py` passes.
- `uv run python -m unittest` passes.

## Risks

- Generated code execution can become unsafe without sandboxing.
- Verifier quality can lag generator quality and accept shallow samples.
- Data contracts may churn if implemented before schemas are written down.

## Notes

Keep the first implementation small. Do not introduce distributed orchestration, MCP servers, model routing, or local LLM serving until local runner contracts are proven.
