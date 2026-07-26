# 11 — Run the Representative Activation or No-go Gate

**What to build:** Execute the final evidence workflow using approved
human-reviewed labels and a judge model independent from task generation. Run
the reviewed activation evaluation and a fresh representative enforce-mode
pipeline, validate the resulting release evidence offline, and record an
explicit activation or no-go decision without weakening any threshold.

**Blocked by:** [08 — Audit Admission in Release Artifacts](08-audit-release-admission-evidence.md), [10 — Evaluate the Independent Judge Activation Gate](10-evaluate-activation-gate.md); approved human review of calibration labels; explicit synthesis-operator authorization and credentials for any paid independent-model calls

**Status:** blocked

**Assignee:** Codex

**Parent spec:** [Semantic Mutation Admission](../../../docs/product-specs/semantic-mutation-admission.md)

## Acceptance criteria

- [ ] The evaluated corpus satisfies the required case count, adversarial balance, held-out size, domain coverage, and action coverage.
- [ ] Three repeated evaluations use identical normalized inputs and a judge model distinct from the generator model.
- [ ] The activation evidence records corpus, split, configuration, model lineage, report hashes, costs, failures, and limitations.
- [ ] Activation occurs only when every safety, precision, coverage, and repeatability threshold passes exactly as specified.
- [ ] Any failed threshold produces a no-go decision, and no profile or release artifact claims mutation-safe readiness.
- [ ] A fresh representative enforce-mode run produces auditable evidence without modifying `_30_v5`.
- [ ] Offline release validation passes for the new evidence and rejects controlled tampered variants.
- [ ] Focused tests, the full unit suite, documentation validation, and retained-material scans pass.
- [ ] Final evidence distinguishes framework activation from dataset release readiness and records unresolved limitations.

## Scope guard

Do not initiate paid or credentialed provider calls without explicit operator
authorization. Do not lower thresholds, relabel critical cases, or alter the
held-out split to obtain a passing result.

## Implementation note

The repository now supports representative `run_profile_v4` enforce campaigns,
hash-bound activation-report validation, protected `_30_v5` tree checks, final
activation/no-go evidence assembly, and offline reconstruction with tamper
rejection. No provider call was made while implementing this ticket. The
acceptance checklist remains open until an operator supplies approved reviewed
labels, explicitly authorizes the independent-model calls, and runs the final
workflow.
