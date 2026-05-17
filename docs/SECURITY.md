# Security

## Trust Boundaries

Agent data synthesis executes generated code, tools, and environment logic. Treat every generated artifact as untrusted until it passes sandbox and validation checks.

## Initial Rules

- Run generated solution and verifier code in a restricted process or container before accepting it.
- Do not expose host secrets, SSH keys, cloud credentials, browser profiles, or personal files to generated tools.
- Treat `AGENT_DATA_API_KEY` as a secret and pass it only to the remote LLM provider adapter.
- Prefer offline fixtures for early development. External network access must be explicit and logged.
- Record all tool side effects in trajectory logs.
- Make destructive tool actions reversible through environment reset or checkpoint restore.

## Source Governance Gates

External source material is rejected before environment construction unless a
validated source bundle includes all of the following:

- Source records with content hashes, license labels, retrieval timestamps for
  external material, and retention/export eligibility.
- Explicit license policy decisions. Unknown, incompatible, review-required, or
  missing decisions do not admit external material.
- A network policy with external access enabled, an allowlisted host, sufficient
  request budget, and source-event auditing required.
- A sandbox policy that keeps generated executable code disabled, requires
  artifact-subdirectory filesystem isolation, and enables secret redaction.

The deterministic source-governance fixture simulates external material without
performing real network access. `source_events.jsonl` records source id, source
kind, policy outcome, origin alias, hashes, license outcome, and rejection
causes only. It must not contain raw provider payloads, authorization headers,
API keys, source text, private user data, or other raw secrets.

The controlled network-backed path is disabled by default and only admits one
explicit HTTPS source URL when the caller also supplies a license label and exact
allowed host. The fetch boundary rejects unsafe schemes, non-allowlisted hosts,
redirects, exhausted request budgets, oversized payloads, unsupported content
types, and non-200 HTTP responses before environment construction. The first
adapter only accepts JSON contacts data for the local SQLite contacts
environment. Fetch audit events record `fetch_attempt`, `fetch_accepted`, or
`fetch_rejected`; environment-source audit events record
`environment_source_admitted` or `environment_source_rejected`. These events use
origin aliases and hashes only.

## LLM Provider Secrets

The synthesis pipeline may call a remote OpenAI-compatible LLM API configured by `AGENT_DATA_LLM_BASE_URL`, `AGENT_DATA_API_KEY`, and `AGENT_DATA_LLM_MODEL`. The project should not deploy local LLM clusters or expose provider credentials to generated code, tools, environments, fixtures, manifests, trajectory exports, or rejected-candidate diagnostics.

Logs may include provider alias, base URL host, model id, prompt or config hash, token counts, cost metadata, retry count, and error class. Logs must not include API keys, authorization headers, or raw secrets.

## Generated Code Controls

- The current `tool_generation` role is proposal-only. It may describe a tool
  contract but must not provide Python code, shell commands, package names,
  executable handlers, or migrations.
- Only curated local implementations can be admitted into the active tool
  registry. Admission requires schema, side-effect, and environment compatibility
  checks.
- Static scan generated code for forbidden imports, filesystem paths, subprocess usage, network calls, and environment variable access.
- Execute generated code with timeouts, memory limits, and deterministic seeds where possible.
- Separate verifier execution from solution execution.
- Preserve failure logs for audit and root-cause classification.

## Data Handling

- Keep source provenance with every sample.
- Mark synthetic, transformed, and externally sourced records separately.
- Avoid storing raw secrets, private user data, or licensed source text in training exports.
- Use redaction or fixture generation for any sensitive real-world inputs.
