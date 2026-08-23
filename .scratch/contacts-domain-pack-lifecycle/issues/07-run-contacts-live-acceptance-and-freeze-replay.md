# 07 — Run Contacts Live Acceptance and Freeze Replay Proof

**What to build:** With fresh explicit operator authorization, run one bounded
real-provider Contacts acceptance campaign and record either a valid,
provider-free-replayable current Contacts Release Candidate proof or a
sanitized no-go result that accurately preserves the remaining limitation.

**Blocked by:** [06 — Add Explicitly Authorized Contacts Live Acceptance](06-add-authorized-contacts-live-acceptance.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Contacts Domain Pack Lifecycle and Second-Domain Validation](../../../docs/product-specs/contacts-domain-pack-lifecycle.md)

## Acceptance criteria

- [ ] Before any paid request, the synthesis operator supplies a fresh authorization, a bounded budget, available credentials, and distinct approved generator and mutation-judge identities; the documented preflight must pass.
- [ ] The real run uses the exact Contacts Domain Pack plan, enforced mutation admission, isolated Contacts execution, current coverage and held-out contracts, and the production release-evidence path.
- [ ] If every applicable machine gate passes, the result freezes only sanitized real-provider evidence, independently verifies the Contacts release pack and Release Candidate qualification, and produces an immutable proof that replays with zero provider calls.
- [ ] If any gate fails, the result is a bounded no-go or failure record; it does not freeze reusable responses, construct a real proof, promote a dataset, or overstate the outcome as a qualification.
- [ ] Clean offline verification passes the positive proof, its declared replay behavior, and all required Contacts negative or boundary cases without network access.
- [ ] The final record distinguishes the exact Contacts Release Candidate claim from false Publishable and Training Recommended claims, global mutation-activation status, and any downstream-utility claim.
- [ ] The ticket records an evidence-backed recommendation about whether a Mobile Messages lifecycle decision should be opened, without implementing Mobile Messages work.

## Scope guard

Do not initiate Mobile Messages implementation, publication approval, dataset
distribution, training, or a broader provider campaign. This is one bounded
Contacts acceptance or no-go operation; a fresh authorization is required for
every actual provider-spending attempt.
