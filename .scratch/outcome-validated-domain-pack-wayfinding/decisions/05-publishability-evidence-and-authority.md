# Define Publishability Evidence and Decision Authority

- **Status:** closed
- **Assignee:** Codex
- **Label:** `wayfinder:grilling`
- **Parent map:** [Outcome-Validated Domain Pack](../README.md)
- **Blocked by:** [Define Release Qualification Levels and Allowed Claims](01-release-qualification-levels.md)

## Question

Which machine-verifiable artifacts, audit outcomes, review resolutions,
governance checks, and human authority are required to declare a dataset
publishable, and how should an explicit approval or accepted-risk decision bind
to immutable release evidence without turning review completion into approval?

## Resolution comment

Publishable requires a still-valid Release Candidate, an independently
verifiable exact release pack, complete machine governance evidence, disposition
of every applicable review finding, and independently authenticated human
authorization for a declared distribution scope. No individual pipeline status
or review-completion flag is an alias for this cumulative decision.

### Publishability evidence bundle

The publishability decision binds one canonical evidence bundle containing
references and hashes for:

1. The exact release id, release-pack bytes, manifest, dataset version, Domain
   Pack reference/hash, capability references, component contracts, and runtime
   evidence required by the Release Candidate decision.
2. Independent release-pack verification and the complete machine Release
   Candidate decision, including coverage, held-out evaluation, release
   completeness, source governance, mutation safety, provenance, and artifact
   integrity.
3. A publication-governance report covering applicable license and export
   eligibility, retention, privacy/consent policy, sensitive-material and secret
   scans, access restrictions, redistribution terms, known limitations, and the
   proposed distribution scope. Unknown or non-applicable checks are explicit;
   they are never silently omitted.
4. The release-quality audit and its threshold/configuration identity.
5. The exact review queue and review-resolution evidence when the audit or
   governance report raises review findings.
6. Every required risk-acceptance attestation, the publication-approval
   attestation, the bound authority policy, and the current revocation evidence.

The bundle has its own canonical hash. Relative filenames are not identities;
every referenced artifact is content-bound. A byte-changing repack, changed
governance report, expanded distribution scope, added or removed finding, or
changed limitation creates a new approval subject.

The implementation specification should introduce versioned contracts for a
publication-governance report, risk-acceptance record, publication-approval
record, and deterministic publishability-decision report. The decision report
may summarize verification, but the underlying artifacts and attestations
remain independently verifiable.

### Hard gates and review semantics

- Release-pack integrity, identity and contract binding, applicable source
  licence/export/retention rules, sensitive-material controls, mutation safety,
  and authority validity are hard gates. Human approval or accepted risk cannot
  waive them.
- `release_quality_audit.status == clear` means no configured quality finding
  needs disposition. It does not approve publication; an authorized publication
  approval is still required.
- `watch` may proceed only when every finding is either cleared as inapplicable
  with bounded evidence or covered by a valid risk-acceptance record.
- `blocked`, `insufficient_evidence`, pending review, `confirmed_issue`, or
  `needs_follow_up` denies Publishable. Remediation that changes any release
  artifact produces a new release subject and restarts affected verification.
- The existing `review_resolution_report_v1.status == reviewed` means only that
  each queued item has a syntactically valid decision. Its current
  `accepted_risk` outcome is review evidence, not authoritative risk acceptance;
  it must be covered by the new authenticated risk record before publication.
- Review completion, audit clearance, pack verification, risk acceptance, and
  publication approval remain separate evidence facts. None mutates another.

### Authenticated authority

A bare local `reviewer_alias`, unchecked JSON file, or possession of the output
directory cannot establish Publishable. Risk acceptance and publication
approval must be canonical payloads protected by a digital signature or an
equivalently independently verifiable external attestation.

The bound authority policy identifies a trust root and grants opaque principals
specific roles and scopes. Verification checks the attestation, principal/key,
role, authority-policy version/hash, decision time, validity interval, and
revocation state without storing personal names, email addresses, credentials,
or free-form sensitive material.

The publication approval binds at least:

- release id and release-pack hash;
- publishability-evidence-bundle hash and all governing policy hashes;
- Domain Pack reference/hash;
- exact distribution scope and known-limitations digest;
- approval decision, authorized principal/key, authority-policy reference,
  issuance time, and validity policy.

A risk-acceptance record additionally binds exact finding ids, residual-risk
category and severity, bounded reason codes, compensating controls, permitted
scope, and a mandatory expiry. It cannot name a hard gate as waivable.

The requested use must be equal to or a machine-verifiable subset of the
approved distribution scope. Broader audience, purpose, access, retention, or
redistribution rights require a new approval.

### Separation of duties

- Risk acceptance and publication approval are always separate attestations,
  even when policy permits one principal to hold both roles.
- When residual risk is accepted for external or public distribution, the risk
  owner and publication approver must be different authenticated principals.
- A release with no residual accepted risk needs one authorized publication
  approver; no artificial second signature is required.
- For bounded internal use, one principal may perform both acts only when the
  bound authority policy explicitly grants both roles and permits that
  combination for the requested scope.

### Effective qualification and revocation

The deterministic publishability decision is `passed`, `denied`, or
`insufficient_evidence`; it never publishes artifacts or changes external
systems. Missing, malformed, unknown-version, mismatched, expired, revoked, or
out-of-scope evidence fails closed.

Approval and revocation history is append-only. Expiry or revocation of a risk
acceptance, publication approval, authority grant, or lower-level Release
Candidate dependency removes the current Publishable qualification and every
dependent Training Recommended qualification while preserving the historical
record. A routine later policy revision does not rewrite history, but current
verification must consume the bound policy snapshot plus explicit revocation
state.

The human confirmed independently authenticated approval on 2026-08-07. The
human also confirmed distinct risk-owner and publication-approver principals
for external/public distribution with residual accepted risk, while allowing
policy-controlled role combination for bounded internal use.
