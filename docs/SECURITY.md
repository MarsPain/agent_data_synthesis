# Security and Trust Boundaries

Only local fixture or explicitly supplied local source files enter built-in
Domains. They are normalized and frozen before task execution. Source paths and
private rows are not exported in public Episode collections. A candidate task
instruction is the only authority for state changes inside its isolated Domain
state; the synthesis operator's configuration does not add task authority.

Remote model calls require explicit `--authorize-live-provider`, a non-secret
`--authorization-id`, a validated configuration with physical-request limits,
and environment-provided `AGENT_DATA_LLM_BASE_URL`, `AGENT_DATA_API_KEY`, and
`AGENT_DATA_LLM_MODEL` or `--remote-model`. An earlier authorization does not
cover a later run or resume. The API key is not written to public artifacts.
The offline fixture path does not construct a provider client.

The engine bounds response bytes, output tokens, retries, steps, and total and
per-role physical requests. It records sanitized error codes and hashes instead
of raw provider payloads. A writer lock and private ledger protect resumption
and prevent duplicate terminal work. Replay is provider-free.

Deterministic admission does not prove semantic quality. Shadow judgments are
diagnostic, and AI review does not impersonate a human reviewer. Only imported
direct-human pass labels identify human-approved Episodes. Optional enforced
admission requires separate frozen, held-out judge eligibility.
