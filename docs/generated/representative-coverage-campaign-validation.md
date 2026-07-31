# Representative Coverage Campaign Validation

Updated on 2026-07-31 for
[coverage campaign ticket 06](../../.scratch/coverage-driven-representative-synthesis/issues/06-representative-coverage-campaign.md)
after the authorized three-domain provider pilot.

## Provider Pilot Decision

**`ready-for-authorized-campaign`**

The synthesis operator authorized `api.deepseek.com`, model
`deepseek-v4-flash`, and the configured `AGENT_DATA_API_KEY` for a serial pilot
bounded to 72 provider calls. Contacts, mobile messages, and workspace tasks
each accepted 12 of 12 generated candidates after issuing 12 of their 24
allowed assignment attempts. The three runs used 36 logical generation calls
and five bounded transport retries, for 41 HTTP attempts in total. No
thirty-per-domain campaign was authorized or run.

All three coverage plans were fulfilled without rejection. Each domain
fulfilled 12 cells, used 10 distinct stable groundings with at most two
accepted samples per grounding, achieved a 1.0 executable rate, and passed its
held-out verification suite at 1.0. The common structural taxonomy also shows
more families and less concentration than the larger prior provider baseline:

| Domain | Baseline / pilot accepted | Fulfilled pilot cells | Common-taxonomy families | Largest family share | Pilot groundings / max reuse |
| --- | ---: | ---: | ---: | ---: | ---: |
| Contacts | 27 / 12 | 12 | 2 → 7 | 0.556 → 0.417 | 10 / 2 |
| Mobile messages | 28 / 12 | 12 | 3 → 11 | 0.357 → 0.167 | 10 / 2 |
| Workspace tasks | 30 / 12 | 12 | 4 → 8 | 0.333 → 0.250 | 10 / 2 |

The family comparison is like-for-like because both sides use
`representative_structural_taxonomy_v1`; its features exclude instruction text,
provider identity, coverage cell ids, and assignment metadata. The pilot's
growth therefore comes from tool, selector, state, binding, and recovery
structure rather than instruction-only variation.

## Quality And Provider Use

| Domain | Baseline → pilot executable rate | Baseline → pilot rejection causes | Baseline → pilot tokens | Pilot logical calls / retries |
| --- | ---: | --- | ---: | ---: |
| Contacts | 1.000 → 1.000 | 3 duplicates → none | 102,260 → 33,176 | 12 / 2 |
| Mobile messages | 0.933 → 1.000 | 2 runtime errors → none | 116,464 → 38,921 | 12 / 2 |
| Workspace tasks | 1.000 → 1.000 | none → none | 105,816 → 37,180 | 12 / 1 |

The pilot used 109,277 total tokens: 57,452 prompt tokens and 51,825
completion tokens. Provider lineage returned no price metadata, so the evidence
uses token counts rather than asserting a dollar cost. All 36 candidates were
executable, locally verified, and accepted. The pilot difficulty distribution
was 3 basic, 2 constrained, 5 intermediate, 3 recovery, and 23
selector-recovery samples. The legacy baseline predates locally normalized
coverage difficulty and grounding-reuse evidence, so those two fields are not
claimed as like-for-like baseline comparisons.

No pilot deficit required classification. The scheduler issued only the first
12 attempts per domain, retained 12 unused attempts per domain, and stopped
after fulfillment. Deterministic tests continue to cover the bounded
catalog-capacity, provider-contract, execution, verification, safety,
duplicate, and attempt-exhaustion outcomes. A retained-material scan of all 77
pilot files found no provider-secret fields, authorization headers, configured
credential value, or local absolute path.

The generic representative-scale consumer classifies these v4 shadow-mode
pilot artifacts as `insufficient_evidence` and recommends
`expand_representative_evidence`. That is expected: the pilot is diagnostic and
cannot establish representative or release eligibility. The narrower pilot
gate supports requesting separate authorization for the thirty-per-domain
campaign, where growth from 12 to 30 accepted targets must still be observed.
If structural coverage does not grow at that scale, ticket 06 cannot conclude
success even if accepted counts remain high.

## Deterministic Decision

**`ready-for-authorized-pilot`**

The deterministic catalog blocker is resolved. Versioned v3 catalogs contain
thirteen executable cells per domain, and deterministic runs fulfill twelve
distinct cells at target 12 and all thirteen at target 30. This evidence
supports requesting separate authorization for the provider pilot governed by
ticket 06.

This preflight decision did not itself authorize a provider, credentials,
model, or budget. The later, separately authorized pilot above made the only
paid calls recorded by this report. No dataset was promoted, and no release or
downstream-value claim follows from either stage.

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

The runtime evidence remains under
`artifacts/coverage-campaign-provider-pilot-v1/`, including per-domain coverage
evidence, quality and evaluation reports, common-taxonomy comparisons, and the
three-domain representative-scale diagnostic. Current authorization, blocking
state, assignment, and activation conditions remain exclusively in the
[local issue tracker](../../.scratch/coverage-driven-representative-synthesis/README.md).
