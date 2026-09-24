# 09 — Run Independent Three-Domain Dataset Acceptance

**What to build:** Establish engineering readiness and independently reviewed
Agent dataset quality across three Domains, with a separate optional result
for judge-enforcement eligibility.

**Blocked by:** [05 — Add the Workspace Tasks Domain adapter](05-add-workspace-tasks-domain-adapter.md), [06 — Resume and scale local synthesis runs](06-resume-and-scale-local-runs.md), [07 — Add shadow quality review and blind-label import](07-add-shadow-quality-review.md)

**Status:** in-progress

**Assignee:** Codex

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [ ] An offline rehearsal freezes source/slot scope, disjoint pilot/development task groups, model settings, limits, structural examples, and review rubric before any live authorization request.
- [ ] The campaign requires fresh explicit authorization for task/Agent models, any optional independent shadow judge, and total/per-role physical-request, retry, and task-attempt ceilings.
- [ ] Shadow runs target forty demonstrations per Domain with at most eighty task attempts each; every selected Episode records Agent-rollout lineage and no scripted oracle counts.
- [ ] Every demonstration passes deterministic gates, has no duplicate semantic key, and contains no unauthorized mutation; no unintended persistent state change occurs during the campaign.
- [ ] Reviewed classification examples support the seven/twelve/nine family floors for Contacts/Mobile Messages/Workspace Tasks; no Domain largest-family share exceeds 0.35 and redundant calls cannot inflate counts.
- [ ] Freeze the first forty admitted Episodes per Domain in stable sequence before human labels. All 120 demonstrations receive blind review; pilot, calibration development, and negatives are excluded from this denominator.
- [ ] Human pass rate is at least 90% overall and in every Domain, with zero critical safety failures. Fail/uncertain/missing labels are not passes; any missing label leaves acceptance incomplete.
- [ ] No human-failed Episode is removed or replaced to improve the cohort rate. Any changed candidate set requires a fresh bounded acceptance campaign.
- [ ] The report records engineering readiness, dataset acceptance, and optional enforcement eligibility separately. Missing Ticket 08 or an unavailable/unqualified judge cannot turn passing engineering and dataset evidence into a cutover failure.
- [ ] The cohort may evaluate an already frozen judge policy only if untouched by development. Any tuning informed by its labels requires fresh held-out evaluation for the revised policy.
- [ ] Report yield, rejection causes, recovery, diversity, human verdicts, observed/unknown usage, retries, elapsed time, and tokens per deterministic/human-passed Episode; unavailable prices and downstream benefit remain unclaimed.
- [ ] Engineering checks include core/Domain/model behavior, locality, replay, request-budget recovery, architecture, docs, clean installation, and accepted engine-scale evidence.
- [ ] Failed engineering or dataset acceptance preserves bounded inspectable evidence and blocks cutover without automatic reruns or weakened gates. Failed judge activation records shadow-only operation without blocking core cutover.

## Scope guard

Do not call providers without fresh authorization, pool error-enriched reviews
into the acceptance rate, tune thresholds after seeing outcomes, publish data,
or treat statistical judge eligibility as required engineering functionality.
A complete review establishes measured cohort quality; only individually
human-passed Episodes may be described as human-approved.

## Current campaign state

- A provider-free rehearsal is frozen at
  `artifacts/agent-first-acceptance-20260924/rehearsal.json`, fingerprint
  `sha256:28b293c2903b10b8771d3fa2a45c3a33bf78fd0ca225e92fdd5ca3c90991ae42`.
  Its local sources expose 80 Contacts, 96 Mobile Messages, and 97 Workspace
  Tasks slots; the first 80 per Domain are frozen. Contacts grounding entities
  are disjoint from the earlier fixture pilot. No calibration-development
  campaign has run in this rebuild.
- The rehearsal fixes `deepseek-v4-flash` for task generation and Agent
  rollout, disables the optional shadow judge, and caps the campaign at 240
  task attempts and 1,980 physical requests: 30 generator and 1,950 Agent,
  with zero transport retries. The operator has requested fresh authorization
  for that exact plan. No acceptance provider call or human label exists yet.
- The Workspace Tasks adapter now has a versioned `all_unique` target scope for
  enough unique task slots, while its representative default and reviewed
  nine-family semantics remain intact. The campaign runner refuses plan drift,
  freezes the first forty admitted Episodes per completed Domain, and uses the
  existing blind-label import. The decision report keeps engineering, dataset,
  and optional judge results separate.
- Focused suites, compilation, a clean offline installation, and the two-axis
  implementation review passed. The full suite passed 1,113 tests in an
  isolated copy with only the unrelated Ticket 08 title restored to its
  committed form; documentation validation passed there too. In the shared
  working tree, the pre-existing malformed Ticket 08 title still fails docs
  validation and its corresponding full-suite test. No static typechecker is
  configured; compilation checks passed. Engineering readiness remains
  unpassed in the actual workspace until that title is resolved.
