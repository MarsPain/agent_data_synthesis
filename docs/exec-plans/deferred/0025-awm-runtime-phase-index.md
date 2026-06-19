# Plan 0025 Phase Index: AWM Runtime Boundary and Shared Environment Kernel

## Status

Planned on 2026-06-09. This is an umbrella phase index and decision record, not
a directly executable implementation plan. The executable work is split into
Phase A-F documents.

Phase A and Phase B completed on 2026-06-19. Phases C-F remain deferred behind
explicit prerequisites.

Do not move Phase F to active unless Phase E produces an explicit
`ready_for_extraction_plan` decision.

## Goal

Evolve the current contacts/mobile environment layer from a multi-domain
synthesis pipeline into a general Agent runtime-backed synthesis framework,
without prematurely splitting runtime code into a separate package.

## Current Evidence

Plans 0030 through 0034 created the pressure needed for a staged 0025:

- Plan 0030 added shared runtime metadata and sanitized episode evidence.
- Plan 0031 added episode-quality scoring as a non-synthesis consumer.
- Plan 0032 added executable episode replay against fresh runtimes.
- Plan 0033 split task intent, policy hints, expected outcome, and expected
  state from the public candidate wrapper.
- Plan 0034 added deterministic reward-label export over sanitized episode,
  quality, replay, and task-contract evidence.

These consumers prove that the runtime boundary is now more than a contacts
fixture detail. They do not yet justify immediate package extraction because
the consumers still run inside this repository and some runtime/domain facts are
still hard-coded in replay and reward modules.

## Decision

Adopt a six-phase path:

1. Harden the internal runtime kernel.
2. Invert replay, quality, and reward consumers to use runtime capabilities.
3. Add a rollout-ready runtime API without implementing RL.
4. Generalize the local adapter surface without connecting external MCP
   servers.
5. Run an extraction-readiness review.
6. Extract an `awm_runtime` package only if the review says the boundary is
   ready.

The intended future extraction unit is an `awm_runtime`-style runtime kernel:
runtime descriptors, runtime sessions, action envelopes, adapter manifest
primitives, and episode evidence contracts. Contacts and mobile remain domain
packs, not the package boundary.

## Phase Index

- [0025 Phase A: Internal Runtime Kernel Hardening](../completed/0025-phase-a-internal-runtime-kernel-hardening.md)
  - Centralize runtime capabilities and descriptor lookup so replay/reward
    consumers do not own contacts/mobile allowlists.
  - Completed on 2026-06-19.
- [0025 Phase B: Runtime Consumer Inversion](../completed/0025-phase-b-consumer-inversion.md)
  - Make episode quality, replay, and reward labels consume `episode_log_v1`
    plus runtime capabilities rather than domain branches.
  - Completed on 2026-06-19.
- [0025 Phase C: Rollout-Ready Runtime API](0025-phase-c-rollout-ready-runtime-api.md)
  - Add reset/checkpoint/list-tools/execute-action/episode-export semantics
    needed by future rollout collectors, without RL training.
- [0025 Phase D: Adapter Surface Generalization](0025-phase-d-adapter-surface-generalization.md)
  - Generalize the local in-process adapter surface from contacts-specific
    assumptions to runtime descriptors and action envelopes.
- [0025 Phase E: Extraction Readiness Review](0025-phase-e-extraction-readiness-review.md)
  - Produce an evidence-backed decision to keep runtime internal, continue
    hardening, or activate extraction planning.
- [0025 Phase F: AWM Runtime Package Extraction](0025-phase-f-awm-runtime-package-extraction.md)
  - Extract stable runtime primitives only after Phase E says the boundary is
    ready.

## Phase Lifecycle

Phase A moved to `completed/` after adding descriptor and registry evidence for
replay/reward consumers. Phase B moved to `completed/` after episode quality,
replay, and reward-label consumers aligned on descriptor-backed capability
semantics. Reward-label export from plan 0034 supplied enough pressure for the
0025 sequence, but not for package extraction.

Keep Phases C-F deferred until their prerequisites complete:

- Phase C requires Phase B consumer inversion.
- Phase D requires Phase C runtime sessions and action envelopes.
- Phase E requires Phase D or equivalent runtime/adapter evidence.
- Phase F requires Phase E status `ready_for_extraction_plan`.

## Out of Scope for the Overall 0025 Sequence

- Reward model training, policy optimization, PPO, DPO, GRPO, or GPU
  infrastructure.
- Distributed rollout workers or async orchestration from plan 0014.
- External MCP server discovery or remote adapter execution before a separate
  plan explicitly activates it.
- Moving contacts or mobile domain packs out of this repository.
- Changing dataset release, profile promotion, source governance, or public
  sample schemas except where they consume runtime evidence.

## Architecture Direction

The target shape is:

```text
domain pack
  -> RuntimeDescriptor
  -> RuntimeSession
  -> action request/result envelopes
  -> episode_log_v1
  -> synthesis / replay / reward / rollout / adapter consumers
```

Domain packs own domain-specific state, tools, fixtures, source importers,
task generation, scripted policies, and verifiers.

The runtime kernel owns cross-domain execution semantics: identity, capability
declaration, reset/rebuild, checkpoint/restore, tool/action envelope execution,
state-change evidence, adapter manifest primitives, and episode logging.

Synthesis remains separate from runtime. Dataset versioning, release admission,
profile decisions, LLM provider configuration, source governance, and quality
reports must not leak into runtime metadata or runtime descriptors.

## Validation Pattern

Each phase must run:

```bash
uv run python scripts/validate_docs.py
uv run python -m unittest
```

Each implementation phase must also run its focused tests named in the phase
document. Phase E is documentation/audit focused and should validate the
readiness report plus any boundary-audit tests it adds.

## Completion Criteria for the Full 0025 Sequence

The full 0025 sequence is complete only when one of these outcomes is recorded:

- `keep_internal`: the runtime boundary is useful but not mature enough for
  extraction, with revisit triggers documented.
- `continue_hardening`: additional internal runtime work is needed before an
  extraction decision.
- `extracted`: Phase F has moved stable runtime primitives behind an approved
  package boundary while preserving synthesis behavior.

Until then, this index remains the umbrella for staged runtime-kernel work.
