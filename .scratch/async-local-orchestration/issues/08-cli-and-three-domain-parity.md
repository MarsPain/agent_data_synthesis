# 08 — Expose the Operator CLI and Prove Three-Domain Parity

**What to build:** Expose the completed local orchestration behavior through an
explicit CLI workflow and prove that deterministic async execution preserves
the existing synchronous contracts across contacts, mobile messages, and
workspace tasks while leaving the default command unchanged.

**Blocked by:** [06 — Cancel and Resume a Live Synthesis Job](06-cooperative-cancellation-and-resume.md) and [07 — Publish Sanitized Per-Role Usage Evidence](07-sanitized-role-usage.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Async Local Orchestration](../../../docs/product-specs/async-local-orchestration.md)

## Acceptance criteria

- [ ] The CLI exposes explicit async enablement, job identity, resume, and
  maximum-concurrency options; async enablement without a concurrency value
  uses one worker.
- [ ] The ordinary command remains synchronous and produces unchanged core
  behavior when no async option is supplied.
- [ ] Invalid option combinations, missing resume state, configuration drift,
  unsafe output ownership, and exhausted authorization fail before provider
  work begins.
- [ ] Process interrupt and termination signals request cooperative cancellation
  and leave a valid cancelled or interrupted job rather than corrupting state.
- [ ] Deterministic contacts, mobile-messages, and workspace-tasks fixtures each
  produce equivalent sync and async samples, rejections, ordering, quality,
  evaluation, and applicable coverage evidence.
- [ ] Existing source governance, sandbox admission, mutation admission, role
  guardrails, provider-host policy, held-out evaluation, profile decisions, and
  release gates behave identically in async mode.
- [ ] Operator documentation describes creation, status, cancellation,
  resumption, ambiguity, authorization, concurrency, artifacts, and the
  unchanged synchronous default.
- [ ] Focused CLI and three-domain tests, retained-material scans,
  documentation validation, type checks, and the full unit suite pass without
  paid provider calls.

## Scope guard

Do not add a service, dashboard, remote control endpoint, automatic async
activation, new domain behavior, real-provider validation, or dataset release
promotion.
