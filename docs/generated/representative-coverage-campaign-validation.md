# Representative Coverage Campaign Preflight

Updated on 2026-07-31 for
[coverage campaign ticket 06](../../.scratch/coverage-driven-representative-synthesis/issues/06-representative-coverage-campaign.md)
after completing
[structural catalog ticket 07](../../.scratch/coverage-driven-representative-synthesis/issues/07-expand-representative-structural-catalogs.md).

## Deterministic Decision

**`ready-for-authorized-pilot`**

The deterministic catalog blocker is resolved. Versioned v3 catalogs contain
thirteen executable cells per domain, and deterministic runs fulfill twelve
distinct cells at target 12 and all thirteen at target 30. This evidence
supports requesting separate authorization for the provider pilot governed by
ticket 06.

This decision does not authorize a provider, credentials, model, or budget. No
paid call was made, no dataset was promoted, and no release or downstream-value
claim follows from this preflight.

## Expanded Catalog Evidence

The v3 catalog identities are:

| Domain | Catalog | Cells | Catalog hash |
| --- | --- | ---: | --- |
| Contacts | `contacts_coverage_v3` | 13 | `sha256:545d3e1549f09d1aab483e971eff028ddaf8f7f274f05d86ad9bcaa1094e07d5` |
| Mobile messages | `mobile_messages_coverage_v3` | 13 | `sha256:e8bae0758752d1f94802d89e999b20db4cb87874b5f6e3ed0fd419c6976edc1e` |
| Workspace tasks | `workspace_tasks_coverage_v3` | 13 | `sha256:7941dd93f4372bbc485f6ea5b2ad6cd611b421c7061fdd3d35eba78f617a814d` |

Each added cell contains an executable failed-selector branch and an observed,
successful fallback. Catalog validation executes both paths locally and checks
each declared stable grounding ID against the returned contact, message, or
workspace-item observation.

The deterministic fake provider produced the following evidence under
`artifacts/coverage-campaign-fake-structural/`:

| Domain | Accepted at 12 / 30 | Fulfilled cells at 12 / 30 | Stable groundings at 30 | Max reuse | Attempts at 12 / 30 |
| --- | ---: | ---: | ---: | ---: | ---: |
| Contacts | 12 / 30 | 12 / 13 | 15 | 2 | 12 / 30 |
| Mobile messages | 12 / 30 | 12 / 13 | 15 | 2 | 12 / 30 |
| Workspace tasks | 12 / 30 | 12 / 13 | 16 | 2 | 12 / 30 |

All six runs fulfilled their plans with zero rejection and stayed within the
existing two-samples-per-grounding limit and the declared 24- or 60-attempt
ceiling. Growth comes from executed recovery structures, not instruction
paraphrases or increased grounding reuse.

## Common Structural Taxonomy

The versioned
[`representative_structural_taxonomy_v1`](../design-docs/representative-structural-taxonomy.md)
classifies both the prior baseline and coverage-driven samples from task
constraints, ordered tool use, primary-selector fields, state behavior,
cross-step observation bindings, and recovery transitions. It excludes
instruction wording and coverage assignment or cell identity.

The classifier hash is
`sha256:59cdf375ed46482bcd426f73d27844639e67be7e23aaa6ca3bde58809b95e028`.
Applied to `artifacts/representative-campaign-30-v5` and the deterministic v3
thirty-target runs, it reports:

| Domain | Baseline classified / unclassifiable | V3 fake classified / unclassifiable | Distinct families | Largest family share |
| --- | ---: | ---: | ---: | ---: |
| Contacts | 27 / 0 | 30 / 0 | 2 → 7 | 0.556 → 0.333 |
| Mobile messages | 28 / 0 | 30 / 0 | 3 → 12 | 0.357 → 0.133 |
| Workspace tasks | 30 / 0 | 30 / 0 | 4 → 9 | 0.333 → 0.200 |

These are like-for-like structural measurements because both sides use the same
classifier. They are not an overall quality comparison: the baseline used a
paid provider, while the new campaign is deterministic fake-provider evidence.

The reusable comparison command is:

```bash
uv run python scripts/write_structural_taxonomy_comparison.py \
  --comparison-id contacts \
  --baseline-samples artifacts/representative-campaign-30-v5/contacts/samples.jsonl \
  --campaign-samples artifacts/coverage-campaign-fake-structural/contacts_coverage_structural_campaign_30/samples.jsonl \
  --output artifacts/coverage-campaign-fake-structural/contacts_structural_taxonomy_comparison.json
```

## Compatibility

The v1 and v2 catalogs and profiles remain registered and unchanged. Regression
tests pin all six legacy catalog hashes, including the original workspace v1
declaration whose historical grounding identity is not retroactively changed.
The v3 catalogs opt into observation-backed identity validation. Existing
default fixtures, non-coverage profiles, release thresholds, and representative
thresholds are unchanged.

## Prior Blocker

The earlier preflight decision was `revise-catalog`: v1 twelve-target and v2
thirty-target plans could accept more samples but exposed only three contacts
cells and five mobile or workspace cells. The v2 fixture expansion solved
aggregate capacity without solving structural saturation. Ticket 07 introduced
the v3 catalogs and common taxonomy rather than weakening the reuse policy.

## Work-State Boundary

This report retains deterministic evidence only. Current authorization,
blocking state, assignment, and activation conditions remain exclusively in
the [local issue tracker](../../.scratch/coverage-driven-representative-synthesis/README.md).
