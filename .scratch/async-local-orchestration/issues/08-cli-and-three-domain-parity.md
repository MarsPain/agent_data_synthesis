# 08 — Expose the Operator CLI and Prove Three-Domain Parity

**What to build:** Expose the completed local orchestration behavior through an
explicit CLI workflow and prove that deterministic async execution preserves
the existing synchronous contracts across contacts, mobile messages, and
workspace tasks while leaving the default command unchanged.

**Blocked by:** [06 — Cancel and Resume a Live Synthesis Job](06-cooperative-cancellation-and-resume.md) and [07 — Publish Sanitized Per-Role Usage Evidence](07-sanitized-role-usage.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Async Local Orchestration](../../../docs/product-specs/async-local-orchestration.md)

## Acceptance criteria

- [x] The CLI exposes explicit async enablement, job identity, resume, and
  maximum-concurrency options; async enablement without a concurrency value
  uses one worker.
- [x] The ordinary command remains synchronous and produces unchanged core
  behavior when no async option is supplied.
- [x] Invalid option combinations, missing resume state, configuration drift,
  unsafe output ownership, and exhausted authorization fail before provider
  work begins.
- [x] Process interrupt and termination signals request cooperative cancellation
  and leave a valid cancelled or interrupted job rather than corrupting state.
- [x] Deterministic contacts, mobile-messages, and workspace-tasks fixtures each
  produce equivalent sync and async samples, rejections, ordering, quality,
  evaluation, and applicable coverage evidence.
- [x] Existing source governance, sandbox admission, mutation admission, role
  guardrails, provider-host policy, held-out evaluation, profile decisions, and
  release gates behave identically in async mode.
- [x] Operator documentation describes creation, status, cancellation,
  resumption, ambiguity, authorization, concurrency, artifacts, and the
  unchanged synchronous default.
- [x] Focused CLI and three-domain tests, retained-material scans,
  documentation validation, type checks, and the full unit suite pass without
  paid provider calls.

## Implementation

Added explicit `--enable-async-runner`/`--enable-async`/`--async` CLI opt-in
with durable job identity, resume, stale-lock recovery, bounded concurrency,
and LLM authorization options. The CLI preserves the existing synchronous
path, installs cooperative SIGINT/SIGTERM handlers, reports cancellation and
durable job paths, binds dataset-version/source behavior into validated
resumption, and routes remote mutation-judge calls through the same durable
logical-call budget and sanitized usage evidence. Deterministic contacts,
mobile-messages, and workspace-tasks subprocess tests compare core artifacts
and retained material between sync and async runs. Operator workflows are
documented in `docs/OPERATIONS.md`; docs validation, isolated mypy, focused
tests, and the full unit suite pass with fake providers only.

## Scope guard

Do not add a service, dashboard, remote control endpoint, automatic async
activation, new domain behavior, real-provider validation, or dataset release
promotion.
