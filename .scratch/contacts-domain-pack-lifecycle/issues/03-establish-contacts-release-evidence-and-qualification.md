# 03 — Establish Contacts Release Evidence and Qualification

**What to build:** Let a release manager verify a new, canonical Contacts
release subject through exact machine evidence, a standalone release pack, a
Contacts Domain assessment, and the existing cumulative qualification boundary
without promoting legacy Contacts artifacts.

**Blocked by:** [02 — Bind Contacts Capabilities to Coverage and Assessment Evidence](02-bind-contacts-capabilities-to-evidence.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Contacts Domain Pack Lifecycle and Second-Domain Validation](../../../docs/product-specs/contacts-domain-pack-lifecycle.md)

## Acceptance criteria

- [ ] A versioned Contacts release-candidate profile selects the exact Contacts Pack, runtime, capability, coverage, held-out, mutation, completeness, and machine-gate contracts without borrowing Workspace capability meanings or thresholds.
- [ ] Fresh canonical Contacts evidence that meets every applicable machine requirement yields an independently verifiable release pack and a qualification subject bound to its exact artifact identity.
- [ ] Qualification returns Release Candidate only for an exact current subject that passes the Contacts assessment, release completeness, quality audit, and standalone release-pack verification; Publishable and Training Recommended remain false unless their separate evidence exists.
- [ ] Missing, malformed, stale, revoked, tampered, incomplete, non-passing, or identity-mismatched Contacts evidence produces a bounded denied or insufficient decision and cannot retain an invalid higher claim.
- [ ] Fixture and conformance paths remain explicitly non-real where appropriate, while legacy Contacts compatibility chains remain historical-only and cannot establish a current qualification.
- [ ] A byte-changing repack or changed Pack, runtime, capability, or evidence binding creates a new qualification subject with no implicit carry-over.
- [ ] Offline tests verify the positive current-evidence path, controlled negative variants, qualification dependency invalidation, and absence of publication or training side effects.

## Scope guard

Do not freeze provider responses, construct an acceptance proof root, create a
live command, seek external authority, or run a paid provider campaign. This
ticket establishes the current Contacts release-evidence and qualification path
needed by a later acceptance proof.
