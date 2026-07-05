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

## Local MCP-Compatible Adapter Controls

The MCP-compatible adapter path is disabled by default and enabled only with
`--enable-mcp-adapter` or `enable_mcp_adapter=True`. The adapter surface is an
in-process runtime-backed shim over already-curated local runtime sessions and
tool registries for contacts and mobile fixtures. It does not discover or
connect to arbitrary MCP servers, start browser automation, read credentials,
broker secrets, access remote filesystems, or execute generated handlers.

Adapter manifests must include environment identity, source-policy hash,
supported operations, tool schemas, side-effect classes, reset/checkpoint
capability, and verifier implications before execution. Tool-call request
envelopes are sanitized before being mapped into `runtime_action_request_v1`;
tool-call results preserve MCP-compatible adapter lineage while retaining
runtime action evidence internally. Contract failures are rejected as
`adapter_contract_rejected` with sanitized details; they are not treated as
executable verifier failures.

## Runtime Package Boundary Controls

The in-repository `awm_runtime` package owns runtime metadata safety checks,
action request/result sanitization, runtime sessions, and package-neutral
episode hashing/redaction primitives. It must not import domain packs, source
governance, dataset assembly, profile decisions, release reports, CLI wiring,
provider configuration, or local host paths. Contacts/mobile/workspace
descriptor construction stays in `synthesis.runtime_registry`; the retired
`synthesis.runtime` and `synthesis.episodes` compatibility modules must not be
reintroduced.

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
- `synthesis.sandbox` owns the first generated-code admission boundary for
  Python artifacts emitted by future tool-handler, environment-builder, or
  verifier roles. These roles remain disabled or proposal-only by default.
- Generated executable artifacts are scanned before admission. The static
  scanner rejects syntax errors, forbidden imports or access patterns (`os`,
  `sys`, `subprocess`, `socket`, `urllib`, `http`, `ftplib`, `pathlib`,
  `shutil`, `importlib`, dynamic import, `eval`, `exec`, `open`, `compile`,
  `globals`, `locals`, and environment access), shell/package command markers,
  filesystem escapes, credential paths, API-key-like strings, and authorization
  header material.
- Admission requires an explicit sandbox policy with generated code allowed,
  artifact-subdirectory filesystem isolation, and redaction enabled. Rejected
  artifacts use `unsafe_generated_code`.
- The restricted local helper runs only admitted Python snippets in a temporary
  artifact directory with sanitized environment variables, deterministic stdin,
  timeout, hash-only stdout/stderr exports, and best-effort standard-library
  process limits where available.
- Sandbox audit artifacts contain hashes, violation categories, policy metadata,
  role lineage, admission outcomes, and execution status only. They must not
  contain raw generated code, provider prompts, API keys, authorization headers,
  environment variables, or host paths.
- This helper is not a hardened container or VM. It is a local engineering
  guardrail that keeps unsafe generated code non-executable until a future plan
  introduces stronger isolation.

## Data Handling

- Keep source provenance with every sample.
- Mark synthetic, transformed, and externally sourced records separately.
- Avoid storing raw secrets, private user data, or licensed source text in training exports.
- Use redaction or fixture generation for any sensitive real-world inputs.
