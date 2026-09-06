# 09 — Run Independent Three-Domain Dataset Acceptance

**What to build:** Establish engineering readiness and independently reviewed
Agent dataset quality across three Domains, with a separate optional result
for judge-enforcement eligibility.

**Blocked by:** [05 — Add the Workspace Tasks Domain adapter](05-add-workspace-tasks-domain-adapter.md), [06 — Resume and scale local synthesis runs](06-resume-and-scale-local-runs.md), [07 — Add shadow quality review and blind-label import](07-add-shadow-quality-review.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

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
