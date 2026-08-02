# 07 — Publish Sanitized Per-Role Usage Evidence

**What to build:** Give the synthesis operator a versioned orchestration usage
summary that attributes known and ambiguous provider attempts, retries, tokens,
and provider-reported prices to sanitized roles across an original job and all
resumes without altering deterministic dataset artifacts.

**Blocked by:** [03 — Resume Provider Work Within Cumulative Authorization](03-provider-resumption-and-budget.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Async Local Orchestration](../../../docs/product-specs/async-local-orchestration.md)

## Acceptance criteria

- [ ] Usage evidence aggregates call counts, adapter retries, known attempts,
  ambiguous attempts, and allowlisted token fields by role and sanitized
  provider/model alias.
- [ ] Aggregation covers the original job and every validated resume without
  double-counting checkpointed terminal work.
- [ ] Provider-reported price metadata is preserved when present; unavailable
  price information is stated explicitly and is never estimated from tokens.
- [ ] Zero-token failures, exhausted budgets, ambiguous attempts, and roles
  without calls remain representable without malformed totals.
- [ ] Usage artifacts are orchestration-owned and do not change byte-stable core
  artifacts, profile decisions, coverage evidence, or release decisions.
- [ ] Retained-material scans find no credentials, authorization headers, raw
  prompts, raw provider payloads, unrestricted source rows, environment
  variables, host paths, or provider error bodies.
- [ ] Unknown roles, malformed usage, unsupported schemas, inconsistent totals,
  and identity drift fail closed.
- [ ] Focused multi-role, retry, ambiguity, resume, price-presence,
  price-absence, validation, redaction, and regression tests pass with fake
  providers only.

## Scope guard

Do not create billing, forecasting, quota-purchasing, provider-account, or
automatic cost-optimization behavior, and do not infer dollar prices.
