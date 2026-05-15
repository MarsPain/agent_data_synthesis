# Security

## Trust Boundaries

Agent data synthesis executes generated code, tools, and environment logic. Treat every generated artifact as untrusted until it passes sandbox and validation checks.

## Initial Rules

- Run generated solution and verifier code in a restricted process or container before accepting it.
- Do not expose host secrets, SSH keys, cloud credentials, browser profiles, or personal files to generated tools.
- Treat `API_KEY` as a secret and pass it only to the remote LLM provider adapter.
- Prefer offline fixtures for early development. External network access must be explicit and logged.
- Record all tool side effects in trajectory logs.
- Make destructive tool actions reversible through environment reset or checkpoint restore.

## LLM Provider Secrets

The synthesis pipeline may call a remote OpenAI-compatible LLM API configured by `LLM_BASE_URL`, `API_KEY`, and `LLM_MODEL`. The project should not deploy local LLM clusters or expose provider credentials to generated code, tools, environments, fixtures, manifests, trajectory exports, or rejected-candidate diagnostics.

Logs may include provider alias, base URL host, model id, prompt or config hash, token counts, cost metadata, retry count, and error class. Logs must not include API keys, authorization headers, or raw secrets.

## Generated Code Controls

- Static scan generated code for forbidden imports, filesystem paths, subprocess usage, network calls, and environment variable access.
- Execute generated code with timeouts, memory limits, and deterministic seeds where possible.
- Separate verifier execution from solution execution.
- Preserve failure logs for audit and root-cause classification.

## Data Handling

- Keep source provenance with every sample.
- Mark synthetic, transformed, and externally sourced records separately.
- Avoid storing raw secrets, private user data, or licensed source text in training exports.
- Use redaction or fixture generation for any sensitive real-world inputs.
