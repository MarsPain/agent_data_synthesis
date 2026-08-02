# 07 — Publish Sanitized Per-Role Usage Evidence

**What to build:** Give the synthesis operator a versioned orchestration usage
summary that attributes known and ambiguous provider attempts, retries, tokens,
and provider-reported prices to sanitized roles across an original job and all
resumes without altering deterministic dataset artifacts.

**Blocked by:** [03 — Resume Provider Work Within Cumulative Authorization](03-provider-resumption-and-budget.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Async Local Orchestration](../../../docs/product-specs/async-local-orchestration.md)

## Acceptance criteria

- [x] Usage evidence aggregates call counts, adapter retries, known attempts,
  ambiguous attempts, and allowlisted token fields by role and sanitized
  provider/model alias.
- [x] Aggregation covers the original job and every validated resume without
  double-counting checkpointed terminal work.
- [x] Provider-reported price metadata is preserved when present; unavailable
  price information is stated explicitly and is never estimated from tokens.
- [x] Zero-token failures, exhausted budgets, ambiguous attempts, and roles
  without calls remain representable without malformed totals.
- [x] Usage artifacts are orchestration-owned and do not change byte-stable core
  artifacts, profile decisions, coverage evidence, or release decisions.
- [x] Retained-material scans find no credentials, authorization headers, raw
  prompts, raw provider payloads, unrestricted source rows, environment
  variables, host paths, or provider error bodies.
- [x] Unknown roles, malformed usage, unsupported schemas, inconsistent totals,
  and identity drift fail closed.
- [x] Focused multi-role, retry, ambiguity, resume, price-presence,
  price-absence, validation, redaction, and regression tests pass with fake
  providers only.

## Implementation

Added versioned `orchestration_provider_usage_v2` evidence derived from durable
provider attempts and sanitized terminal role lineage. The artifact reports
per-role calls, known/ambiguous/failed attempts, adapter retries, allowlisted
tokens, and provider-reported price metadata with explicit unavailable status.
Issued attempts are treated conservatively as ambiguous until recovery settles
them. Strict validation rejects role/schema/identity/total drift, and
predecessor flat usage snapshots are rebuilt from the event journal. Focused
fake-provider tests cover retries, multi-role aggregation, resume accounting,
ambiguity, zero-token failures, prices, redaction, validation, and artifact
regression; the full suite passes.

## Scope guard

Do not create billing, forecasting, quota-purchasing, provider-account, or
automatic cost-optimization behavior, and do not infer dollar prices.
