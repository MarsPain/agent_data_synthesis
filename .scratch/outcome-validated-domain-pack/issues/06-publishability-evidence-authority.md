# 06 — Verify Publishability Evidence and External Authority

**What to build:** Add strict publication-governance, authority-policy, risk-acceptance, publication-approval, revocation, publishability-bundle, and deterministic decision contracts. Verify authenticated external authority and exact distribution scope without publishing artifacts or treating review completion as approval.

**Blocked by:** [05 — Add cumulative qualification and Workspace Release Candidate](05-cumulative-qualification-release-candidate.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Outcome-Validated Domain Pack](../../../docs/product-specs/outcome-validated-domain-pack.md)

## Acceptance criteria

- [x] The publishability bundle content-binds the exact verified Release Candidate pack, governance report, audit, review evidence, risk records, approval, authority policy, scope, validity, and revocation evidence.
- [x] Integrity, identity, applicable source/license/export/retention/privacy/sensitive-material controls, mutation safety, and authority validity are hard gates that no approval or risk record can waive.
- [x] Audit clearance and syntactically complete review remain separate from publication approval; pending, blocked, confirmed-issue, follow-up, or insufficient evidence denies Publishable.
- [x] A watch finding proceeds only when cleared with bounded evidence or covered by a valid authenticated risk record.
- [x] Risk acceptance binds exact findings, category, severity, bounded reasons, controls, scope, and mandatory expiry and remains separate from publication approval.
- [x] External/public distribution with residual risk requires distinct authenticated risk and publication principals; bounded internal role combination is allowed only by explicit policy.
- [x] Requested audience, purpose, access, retention, and redistribution are equal to or a verifiable subset of approved scope.
- [x] Signature or equivalent attestation, principal/key, role, policy, issuance, validity, expiry, and revocation checks fail closed on any mismatch or unknown version.
- [x] The pure decision returns passed, denied, or insufficient evidence and never copies, uploads, publishes, or changes external access.
- [x] Fixture authority can exercise conformance but is permanently unable to create an effective Publishable qualification.

## Implementation notes

- Added the pure `synthesis.publishability` contract/evaluator and shared contract adapters.
- Added qualification-gate integration with authoritative trust inputs, bounded versioned bundle transport, and the offline `scripts/verify_publishability.py` CLI.
- Added focused adversarial tests for governance, review/risk binding, authority, scope, revocation, fixture provenance, tampering, and qualification integration.

## Scope guard

Do not build a publication portal, distribute a release, manage human identity
profiles, or permit review aliases and unsigned local JSON to establish real
authority.
