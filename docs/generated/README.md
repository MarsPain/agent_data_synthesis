# Generated Artifacts

Use this directory for generated documentation assets, schemas, diagrams, quality reports, and benchmark summaries that should be reviewed but not treated as hand-written source documents.

Runtime pipeline outputs such as generated samples, rejection logs, manifests, and SQLite fixture state belong under [`../../artifacts/`](../../artifacts/), not under `docs/`.

## Foundation Runner

`uv run python main.py` writes the first local foundation artifacts to `artifacts/foundation/` by default.

Those runtime files are generated outputs. Re-run the command when validating the local runner rather than editing them by hand.

Use `uv run python main.py --use-llm --output-dir artifacts/foundation-llm` to exercise the remote LLM-backed candidate generation path. This requires `AGENT_DATA_LLM_BASE_URL`, `AGENT_DATA_API_KEY`, and `AGENT_DATA_LLM_MODEL`; generated exports record provider host and model lineage without writing the API key.
