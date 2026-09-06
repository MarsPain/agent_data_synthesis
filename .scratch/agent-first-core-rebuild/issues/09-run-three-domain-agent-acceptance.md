# 09 — Run Three-Domain Agent Acceptance

**What to build:** Let the synthesis operator establish whether the replacement
core produces sufficiently correct, diverse, efficient, and human-approved
Agent demonstrations across Contacts, Mobile Messages, and Workspace Tasks
before the legacy entrypoint can be replaced.

**Blocked by:** [06 — Resume and scale local synthesis runs](06-resume-and-scale-local-runs.md), [08 — Gate semantic enforcement on human calibration](08-gate-semantic-enforcement-on-calibration.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [ ] The campaign requires fresh explicit authorization for the selected task, Agent, and independent judge models and their bounded attempt and retry ceilings.
- [ ] Each production Domain targets forty accepted demonstrations with at most eighty attempts, producing at least one hundred twenty Agent demonstrations overall when fulfilled.
- [ ] Every demonstration records Agent-rollout policy lineage; no scripted oracle Episode is counted as formal campaign data.
- [ ] Every demonstration passes deterministic assessment, semantic-key duplicate count is zero, and no unauthorized mutation or unintended persistent state change occurs.
- [ ] Contacts, Mobile Messages, and Workspace Tasks retain at least seven, twelve, and nine structural families respectively, and no Domain largest-family share exceeds 0.35.
- [ ] At least one hundred Episodes receive human blind-review labels, with at least thirty per Domain and the approved fail, uncertain, task-type, difficulty, and structural sampling coverage.
- [ ] Human blind-review pass rate is at least 90 percent and contains zero critical safety failures.
- [ ] The judge activates only if the imported real labels satisfy every approved global and per-Domain calibration threshold; otherwise the campaign records a non-qualifying result and the core remains in shadow mode.
- [ ] The campaign reports accepted yield, rejection causes, recovery rate, structural distribution, review outcomes, judge error rates, model calls, retries, tokens, and unavailable price data without claiming publication or downstream training benefit.
- [ ] A failed campaign preserves inspectable bounded evidence but does not authorize cutover, relax a gate, or trigger an automatic retry campaign.

## Scope guard

Do not make provider calls without fresh user authorization, infer prices,
change acceptance thresholds after seeing campaign outcomes, publish a dataset,
or begin legacy removal unless every cutover criterion passes.
