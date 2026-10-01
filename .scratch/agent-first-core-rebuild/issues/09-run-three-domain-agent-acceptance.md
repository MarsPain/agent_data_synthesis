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
  with zero transport retries. The operator explicitly authorized that exact
  plan; the non-secret campaign authorization ID is
  `user-20260924-28b293c2`.
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
- The live run completed once with no transport retries: Contacts admitted
  40 demonstrations from 80 allocated slots, 7 families, largest share 0.275,
  182 physical requests; Mobile Messages admitted 40 from 80, 12 families,
  largest share 0.125, 184 requests; Workspace Tasks admitted 40 from 80,
  9 families, largest share 0.175, 178 requests. All selected Episodes carry
  Agent-rollout lineage, pass deterministic gates, have distinct private
  semantic keys, and align under provider-free replay. Each Domain's first
  forty admitted Episodes are frozen in a separate blind-review cohort.
  Manifest hashes and cohort membership were checked after the run. Known
  token totals are 88,959 / 109,669 / 99,698 respectively, with zero
  unknown-usage requests. The 13 / 12 / 17 negative outcomes remain separate.
- `artifacts/agent-first-acceptance-20260924/review_handoff.md` gives the
  independent human reviewers the three blind queues and label contract.
  No direct-human labels have been imported. Dataset acceptance remains
  incomplete at 0 of 120 reviews; no human-approved Episode is claimed.
  The campaign decision records engineering readiness as failed on the
  unrelated shared-workspace docs title check, dataset acceptance as
  incomplete, and optional semantic enforcement as shadow-only.

## Operator-directed acceptance exception (2026-09-24)

The operator directed work to continue despite the frozen 90% threshold and
the absence of direct-human labels. A separate AI review of all 120 blind
queue items is recorded in
`artifacts/agent-first-acceptance-20260924/ai_review_summary.md` and
`ai_review_diagnostic.jsonl`: 106 pass, 13 fail, and 1 uncertain. Contacts
passed 38/40, Mobile Messages 39/40, and Workspace Tasks 29/40 with one
uncertain. These are AI diagnostic verdicts, not human labels or formal dataset
acceptance. The campaign decision remains incomplete and its frozen evidence
is unchanged. Ticket 10 may proceed under this explicit exception, while this
ticket remains in progress until its stated acceptance criteria are met.

The shared workspace then passed documentation validation and all 1,113
pre-cutover tests. `engineering_readiness.json` was refreshed and the campaign
decision recomputed: engineering readiness is `passed`, dataset acceptance is
still `incomplete`, optional enforcement is `shadow_only_not_evaluated`, and
formal core cutover status remains `blocked`. The operator exception is tracked
separately from that formal decision.
