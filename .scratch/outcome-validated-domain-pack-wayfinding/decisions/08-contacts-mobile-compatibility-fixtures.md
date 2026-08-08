# Define Contacts and Mobile Compatibility Fixtures

- **Status:** closed
- **Assignee:** Codex
- **Label:** `wayfinder:task`
- **Parent map:** [Outcome-Validated Domain Pack](../README.md)
- **Blocked by:** [Define Domain Pack Versioning and Compatibility](04-domain-pack-versioning-and-compatibility.md)

## Question

Which checked-in Contacts and Mobile profiles, manifests, release packs,
reports, domain labels, task labels, and capability labels form the bounded
legacy compatibility matrix, and what fixture-level assertions must prove that
the first Domain Pack specification preserves readability, supported execution,
canonical-only output, historical claim verification, and fail-closed current
evidence admission?

## Resolution comment

Freeze a bounded, hash-manifested compatibility corpus. The corpus is an
explicit migration input, not every file that happens to pass the current test
suite and not a promise to support future legacy-shaped artifacts.

### Checked-in profile baseline

The historical profile baseline is the following 26 JSON files as they exist at
the corpus cutoff. Their raw bytes and SHA-256 hashes must be recorded before a
Domain Pack adapter is implemented.

| Domain | Schema | Positive and claim-bearing profiles | Diagnostic or negative profiles |
| --- | --- | --- | --- |
| Contacts | `run_profile_v1` | `foundation-fixture.json`, `foundation-release-candidate.json` | `foundation-scale-probe-25.json`, `contacts-coverage-smoke.json` |
| Contacts | `run_profile_v2` | `profile-local-contacts.json` | `profile-local-contacts-bad-license.json`, `profile-local-contacts-bad-schema.json`, `profile-local-contacts-missing-file.json` |
| Contacts | `run_profile_v4` | `contacts-coverage-pilot-12.json`, `contacts-coverage-campaign-30.json`, `contacts-coverage-structural-pilot-12.json`, `contacts-coverage-structural-campaign-30.json`, `contacts-representative-llm-100.json` | `contacts-coverage-backfill.json`, `contacts-coverage-catalog-probe.json`, `contacts-coverage-tracer.json` |
| Mobile | `run_profile_v1` | `mobile-messages-release-candidate.json` | `mobile-agent-fixture.json` |
| Mobile | `run_profile_v2` | `profile-local-mobile-messages.json` | `profile-local-mobile-messages-bad-schema.json` |
| Mobile | `run_profile_v4` | `mobile-messages-coverage-pilot-12.json`, `mobile-messages-coverage-campaign-30.json`, `mobile-messages-coverage-structural-pilot-12.json`, `mobile-messages-coverage-structural-campaign-30.json`, `mobile-messages-representative-llm-100.json` | `mobile-coverage-catalog-probe.json` |

The v4 pilot, campaign, and structural profiles deliberately cover coverage
profile/catalog generations v1, v2, and v3. Redundant files remain in the byte
baseline because profile purpose, target size, feature flags, and source or
mutation modes affect historical claims even when their semantic labels match.

There is no checked-in Contacts or Mobile `run_profile_v3` JSON file. Generic
contract tests exercise v3 only through inline records. To honor the previously
decided v1-through-v4 reader floor without inventing history, the first
implementation must add one frozen valid v3 schema-bridge fixture per domain,
label both as synthetic compatibility fixtures, and never describe them as
historical profiles.

### Artifact baseline and the discovered gap

No complete Contacts or Mobile manifest, report set, or release pack is
currently checked in. Runtime outputs live under `artifacts/`, and tests build
their records in temporary directories or inline helper functions. Those
builders prove current behavior but cannot serve as immutable compatibility
evidence: changing the production writer and the helper together would silently
move the supposed baseline.

The first implementation must therefore materialize four self-contained golden
chains under a dedicated compatibility-fixture directory, with a top-level
corpus manifest that hashes every byte:

1. Contacts historical chain: `dataset_manifest_v1`, `quality_report_v1`,
   `evaluation_report_v1`, `profile_decision_report_v1`,
   `dataset_release_report_v1`, and `dataset_release_pack_v1`.
2. Mobile historical chain with the same v1 forms.
3. Contacts mutation-aware chain: `dataset_manifest_v2`,
   `mutation_admission_report_v1`, the same currently supported report forms,
   and `dataset_release_pack_v2`.
4. Mobile mutation-aware chain with the same v2 forms.

When a chain references a release-quality audit or review-resolution report,
the referenced `release_quality_audit_v1` or `review_resolution_report_v1`
record is part of that chain and hash manifest. Samples, rejections, coverage
evidence, and all other files referenced by a manifest or pack are included as
dependencies; a pack-shaped JSON object without its referenced bytes is not a
compatibility fixture.

These golden chains are captured once from the pre-Domain-Pack contracts and
then reviewed. Expected migrated outputs are separate checked-in files. Tests
must not regenerate either the legacy input or expected output with the reader,
adapter, or writer under test.

### Canonical capability and task targets

The logical `contacts` Domain Pack owns these capability keys:

- `contact_lookup`;
- `followup_recording`;
- `contact_lookup_recovery`;
- `missing_contact_safe_failure`.

Its canonical generated task types are `contact_lookup` and
`contact_followup`. Recovery is an independently validated recovery structure,
and missing-contact safety is a held-out scenario, not additional generated
task types.

The logical `mobile_messages` Domain Pack owns:

- `message_search`;
- `reminder_creation`;
- `draft_reply`;
- `message_search_recovery`;
- `missing_message_safe_failure`.

Its canonical generated task types are `mobile_message_search`,
`mobile_reminder_creation`, and `mobile_draft_reply`. Mobile recovery and
missing-message safety follow the same separation from task types.

Every target above becomes an exact capability reference by adding the
capability-contract version selected by the exact Domain Pack version. Equal
strings in old required-capability fields do not become identities without the
projection-specific mappings below.

### Bounded legacy mappings

Mappings are selected by source schema/version and projection kind. The table
is descriptive shorthand; the compatibility fixture stores exact mapping
version/hash and target references.

| Source projection and legacy value | Canonical interpretation |
| --- | --- |
| Contacts semantic-domain field `contacts` or `contacts_fixture` | logical pack `contacts` |
| Contacts runtime/domain-execution field `contacts_fixture` | runtime `contacts_fixture`; never rewritten as pack identity |
| Contacts task/taxonomy `single_tool_lookup`, `lookup_contact_email`, or `contact_lookup` | task type `contact_lookup`; capability `contacts/contact_lookup` only through the declared projection |
| Contacts task/taxonomy `contact_followup` | task type `contact_followup`; capabilities `contacts/contact_lookup` and `contacts/followup_recording` |
| Contacts task/taxonomy `branch_fallback` or `contact_branch_fallback` | task type `contact_lookup` plus separately validated `contacts/contact_lookup_recovery` |
| Contacts generation required-capability `contact_lookup` | `contacts/contact_lookup` |
| Contacts generation required-capability `contact_followup` | `contacts/followup_recording` |
| Contacts held-out tag `contact_lookup` | `contacts/contact_lookup` |
| Contacts held-out tag `state_change` | `contacts/followup_recording` only when lookup binding, requested mutation, and final state all verify |
| Contacts held-out tag `branching` | `contacts/contact_lookup_recovery` only when the declared failure and fallback outcome verify |
| Contacts held-out tag/task `missing_contact` | `contacts/missing_contact_safe_failure` only when controlled failure and absence of unintended mutation verify |
| Contacts `verification_failure_fixture` | diagnostic scenario only; no capability mapping and no positive evidence |
| Contacts `unsupported_network_research` or `network_contact_research` | unsupported by this pack version; non-runnable and no capability mapping |
| Mobile semantic-domain field `mobile_messages_fixture` | logical pack `mobile_messages` |
| Mobile runtime/domain-execution field `mobile_messages_fixture` | runtime `mobile_messages_fixture`; never rewritten as pack identity |
| Mobile fixture task `mobile_message_lookup` | task type `mobile_message_search`; capability `mobile_messages/message_search` |
| Mobile fixture task `mobile_message_to_reminder` | task type `mobile_reminder_creation`; capabilities `mobile_messages/message_search` and `mobile_messages/reminder_creation` |
| Mobile fixture or canonical task `mobile_draft_reply` | task type `mobile_draft_reply`; capabilities `mobile_messages/message_search` and `mobile_messages/draft_reply` |
| Mobile fixture task `mobile_branch_fallback` | task type `mobile_message_search` plus separately validated `mobile_messages/message_search_recovery` |
| Mobile generation task `mobile_message_search` / required-capability `message_search` | task type `mobile_message_search` / capability `mobile_messages/message_search` in their respective projections |
| Mobile generation task `mobile_reminder_creation` / required-capability `reminder_creation` | task type `mobile_reminder_creation` / capability `mobile_messages/reminder_creation` in their respective projections |
| Mobile generation required-capability `draft_reply` | `mobile_messages/draft_reply` |
| Mobile held-out tag `mobile_message_lookup` | `mobile_messages/message_search` |
| Mobile held-out tag `mobile_message_to_reminder` | `mobile_messages/reminder_creation`, with message search proven separately by the task contract |
| Mobile held-out tag `mobile_draft_reply` | `mobile_messages/draft_reply`, with message search proven separately by the task contract |
| Mobile held-out tag `mobile_branching` | `mobile_messages/message_search_recovery` only when the recovery contract passes |
| Mobile held-out tag/task `mobile_missing_message` | `mobile_messages/missing_message_safe_failure` only when controlled failure and absence of unintended mutation verify |

Tool aliases such as `lookup_contact`, `lookup_email`, or `contact_lookup` in a
tool-name field remain tool-ingestion mappings. They do not establish a task or
capability mapping merely because one alias string also appears above.

### Fixture-level assertions

Each corpus row records four independent expected statuses plus bounded reason
codes. Tests assert all of the following.

**Readability**

- Every positive legacy record validates under its declared original schema;
  every intentional negative fixture fails for its frozen reason rather than a
  new incidental parser error.
- Reading preserves original bytes/hash, source schema, projection value, and
  referenced-artifact relationships. Unknown fields are not silently dropped
  and source files are never rewritten in place.
- All pack hashes, byte counts, dataset/profile identities, and original
  historical status fields verify under their original contracts. Tampering or
  a missing referenced artifact fails verification.

**Supported execution**

- Every positive profile whose mode/source remains supported compiles without
  guessing to a deterministic current Domain plan with logical pack
  `contacts` or `mobile_messages`, the declared legacy runtime, exact canonical
  task/capability targets, original profile hash, and migration lineage.
- Diagnostic purpose remains diagnostic; a legacy `release_candidate` purpose
  is historical metadata, not a current qualification.
- Bad license, bad schema, missing source, unsupported network research,
  unknown label/version, ambiguous mapping, and cross-pack references fail
  closed with stable reason codes. An adapter never repairs them by defaulting
  to Contacts or by deleting an unsupported requirement.

**Semantic equivalence and canonical-only output**

- For each mapped positive profile, the exported plan is compared with a
  separately reviewed golden canonical projection, including task requirements,
  recovery structure, held-out outcomes, coverage profile/catalog version,
  source policy, feature flags, and mutation mode.
- New plans, samples, manifests, reports, and packs contain the exact
  `(domain_pack_id, pack_version, pack_hash)` and exact capability references.
  Legacy values may appear only in a namespaced migration-lineage section; no
  canonical Domain Pack, capability, or task field emits `contacts_fixture`,
  `mobile_messages_fixture`, `state_change`, `branching`, or a fixture task
  alias. Exact runtime fields may still emit the legacy-named runtime ids.
- Dropping a required capability, collapsing recovery into search, treating a
  missing-item tag as ordinary search, or mapping an unsupported label is a
  semantic mismatch even if the artifact remains readable or executable.

**Historical claims and current evidence admission**

- A legacy chain can reproduce only its exact historical decision. Verification
  reports that historical status and the original claim vocabulary; it never
  relabels that result as Release Candidate, Publishable, or Training
  Recommended under the new model.
- Every corpus chain is `historical_only` / `insufficient_evidence` for current
  qualification, including valid manifest-v2/release-pack-v2 chains. None
  contains the exact Domain Pack and capability references required by the
  current claim, and mutation-admission evidence cannot fill that gap.
- Missing or unknown mapping version/hash, altered source bytes, unresolved
  labels, cross-domain evaluation, failed original verification, shadow or
  diagnostic mutation evidence, or absent current proof facts must deny current
  admission. The test must assert the missing fact and must not synthesize it
  from task names, tools, or historical pass statuses.

The compatibility corpus is complete only when every selected profile and
golden chain has an expected result on all four axes and the entire corpus
passes a mutation test that injects one unknown semantic label and observes a
fail-closed result. This keeps Contacts and Mobile as compatibility evidence;
it does not turn either into another tracer implementation.
