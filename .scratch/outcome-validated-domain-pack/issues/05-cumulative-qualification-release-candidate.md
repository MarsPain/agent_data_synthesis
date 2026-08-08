# 05 — Add Cumulative Qualification and Workspace Release Candidate

**What to build:** Add the pure cumulative qualification evaluator and establish the first real Workspace Release Candidate path from exact machine evidence and an independently verified release pack. Preserve lower valid qualifications when higher attempts fail and invalidate dependent current claims when lower evidence becomes stale, revoked, or mismatched.

**Blocked by:** [04 — Carry canonical Workspace capabilities to Release Candidate evidence](04-workspace-capability-release-candidate.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Outcome-Validated Domain Pack](../../../docs/product-specs/outcome-validated-domain-pack.md)

## Acceptance criteria

- [ ] The only forward state path is Unqualified to Release Candidate to Publishable to Training Recommended; no evaluation can skip a level or borrow another release's evidence.
- [ ] Qualification binds one exact artifact subject, release-pack hash, Domain Pack reference, runtime, capabilities, component contracts, profile, and evidence graph.
- [ ] Workspace Release Candidate requires passing all applicable machine gates, Domain assessment, release completeness, release-quality audit, and standalone release-pack verification.
- [ ] A release-candidate profile purpose, generation mode, coverage status, held-out report, audit result, or dataset-release status alone establishes no qualification.
- [ ] Missing, malformed, unknown-version, stale, revoked, cancelled, incomplete, non-passing, or identity/hash-mismatched evidence produces a bounded denied or insufficient result.
- [ ] Failed Publishable or Training Recommended evaluation leaves a still-valid Release Candidate unchanged.
- [ ] Invalidating or revoking Release Candidate evidence removes dependent effective qualifications while preserving append-only historical decisions.
- [ ] Any byte-changing repack or identity-changing mutation creates a new qualification subject with no implicit carry-over.
- [ ] The evaluator is deterministic and never publishes, trains, promotes, changes review records, or mutates tracker state.
- [ ] Existing legacy dataset-release statuses remain historically readable and are not silently renamed as Release Candidate.

## Scope guard

Do not implement authenticated publication approval or the external Workspace
training protocol in this ticket. Provide the cumulative state machinery and
real machine Release Candidate boundary only.
