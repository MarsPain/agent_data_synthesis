# Plan 0025 Phase Index: AWM Runtime Boundary and Shared Environment Kernel

## Status

Planned on 2026-06-09. This is an umbrella phase index and decision record, not
a directly executable implementation plan. The executable work is split into
Phase A-F documents.

Phase A, Phase B, and Phase C completed on 2026-06-19. Phase D and Phase E
completed on 2026-06-20. Phase E returned `continue_hardening`, and Phase E1
completed the reward-label runtime contract hardening follow-up. Phase F
remains deferred behind a future readiness decision.

Do not move Phase F to active unless extraction readiness is revisited after
Phase E1 and produces an explicit `ready_for_extraction_plan` decision.

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
reward-label contracts still hard-code supported runtime ids and reward
preference grouping still encodes contacts/mobile tool branches.

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
- [0025 Phase C: Rollout-Ready Runtime API](../completed/0025-phase-c-rollout-ready-runtime-api.md)
  - Add reset/checkpoint/list-tools/execute-action/episode-export semantics
    needed by future rollout collectors, without RL training.
  - Completed on 2026-06-19.
- [0025 Phase D: Adapter Surface Generalization](../completed/0025-phase-d-adapter-surface-generalization.md)
  - Generalize the local in-process adapter surface from contacts-specific
    assumptions to runtime descriptors and action envelopes.
  - Completed on 2026-06-20.
- [0025 Phase E: Extraction Readiness Review](../completed/0025-phase-e-extraction-readiness-review.md)
  - Produce an evidence-backed decision to keep runtime internal, continue
    hardening, or activate extraction planning.
- [0025 Phase E1: Reward Label Runtime Contract Hardening](../completed/0025-phase-e1-reward-label-runtime-contract-hardening.md)
  - Remove reward-label runtime contract allowlists and domain-specific
    preference grouping before revisiting extraction readiness.
- [0025 Phase F: AWM Runtime Package Extraction](0025-phase-f-awm-runtime-package-extraction.md)
  - Extract stable runtime primitives only after a future readiness review says
    the boundary is ready.

## Phase Lifecycle

Phase A moved to `completed/` after adding descriptor and registry evidence for
replay/reward consumers. Phase B moved to `completed/` after episode quality,
replay, and reward-label consumers aligned on descriptor-backed capability
semantics. Phase C added runtime sessions and diagnostic rollout collection.
Phase D generalized local adapter manifests onto runtime descriptors and
runtime sessions. Phase E completed the extraction review and returned
`continue_hardening`, not `ready_for_extraction_plan`.

Keep Phase F deferred until its prerequisites complete:

- Phase E1 removes reward-label contract allowlists and domain-specific
  preference grouping.
- A future extraction-readiness review returns `ready_for_extraction_plan`.

## Phase E Decision

Phase E produced
[AWM Runtime Extraction Readiness](../../generated/awm-runtime-extraction-readiness.md)
with decision status `continue_hardening`.

Passing evidence:

- Contacts and mobile runtimes use the same descriptor/session boundary.
- Fake runtime tests prove several consumers are not contacts/mobile-specific.
- Runtime descriptor and metadata safety validation rejects dataset release,
  dataset version, profile decisions, provider prompts, credentials, raw
  sources, and host paths.
- Episode quality, replay, rollouts, and local adapters consume runtime
  descriptors, sessions, action envelopes, or episode logs.

Phase E blocking evidence before Phase E1:

- `synthesis.contracts.REWARD_LABEL_RUNTIMES` still gates reward-label and
  reward-label-report validation.
- `synthesis.reward_labels._preference_group_id` still maps contacts/mobile
  tool names to grouping labels.
- `RuntimeSession.rebuild` needs package-boundary exercise or explicit
  experimental status before extraction.

Phase E1 follow-up removed the reward-label runtime allowlist gate and moved
reward preference grouping to runtime descriptor declarations. A future
extraction-readiness review still needs to re-evaluate Phase F activation.

Decision: continue internal hardening through
[0025 Phase E1](../completed/0025-phase-e1-reward-label-runtime-contract-hardening.md). Do
not activate Phase F from the Phase E result.

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
document. Documentation/audit phases should validate their generated reports
plus any boundary-audit tests they add.

## Completion Criteria for the Full 0025 Sequence

The full 0025 sequence is complete only when one of these outcomes is recorded:

- `keep_internal`: the runtime boundary is useful but not mature enough for
  extraction, with revisit triggers documented.
- `continue_hardening`: additional internal runtime work is needed before an
  extraction decision.
- `extracted`: Phase F has moved stable runtime primitives behind an approved
  package boundary while preserving synthesis behavior.

The current outcome is `continue_hardening`. Until a future review records
`keep_internal` or Phase F reaches `extracted`, this index remains the umbrella
for staged runtime-kernel work.
