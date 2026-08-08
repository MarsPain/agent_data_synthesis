# Representative Coverage Campaign Validation

Updated on 2026-07-31 for
[coverage campaign ticket 06](../../.scratch/coverage-driven-representative-synthesis/issues/06-representative-coverage-campaign.md)
after the authorized three-domain, thirty-per-domain provider campaign.

## Final Campaign Decision

**`revise-catalog`**

The separately authorized campaign used `api.deepseek.com`, model
`deepseek-v4-flash`, and the configured `AGENT_DATA_API_KEY`. It accepted 30
samples in each domain and fulfilled all thirteen v3 coverage cells per domain.
Contacts issued 36 of 60 allowed logical calls, mobile messages issued 30 of
60, and workspace tasks issued 31 of 60. The campaign therefore used 97 of its
180-call budget plus 24 bounded transport retries, for 121 HTTP attempts.

Structural-cell coverage grew from 12 cells in every pilot to 13 cells in every
campaign run. Grounding reuse remained bounded at two: contacts and mobile
messages each used 15 distinct groundings, while workspace tasks used 16. The
common taxonomy provides the like-for-like baseline comparison:

| Domain | Baseline / campaign accepted | Fulfilled cells, pilot → campaign | Common families, baseline → pilot → campaign | Largest share, baseline → pilot → campaign | Campaign groundings / max reuse |
| --- | ---: | ---: | ---: | ---: | ---: |
| Contacts | 27 / 30 | 12 → 13 | 2 → 7 → 7 | 0.556 → 0.417 → 0.333 | 15 / 2 |
| Mobile messages | 28 / 30 | 12 → 13 | 3 → 11 → 12 | 0.357 → 0.167 → 0.133 | 15 / 2 |
| Workspace tasks | 30 / 30 | 12 → 13 | 4 → 8 → 9 | 0.333 → 0.250 → 0.200 | 16 / 2 |

The campaign completes operationally but does not satisfy the cross-scale
structural-growth hypothesis. Mobile messages and workspace tasks add one
independently classified common family between pilot and campaign, while
contacts remains at seven. Treating contacts' extra locally named cell as
independent structural growth would contradict the common taxonomy and the
ticket's fail-closed growth gate. The result therefore rejects a success
conclusion and selects `revise-catalog`.

Bounded backfill still filled every target deficit, all accepted assignments
executed and verified, grounding reuse did not increase, and concentration
stayed below the prior baseline. Those quality results do not override the
growth failure. All catalogs are also exhausted at thirteen cells, and
contacts and mobile consume their available grounding capacity at the reuse
limit. A revised contacts catalog should add a taxonomy-distinct executable
family and may require expanded environment capacity before another scale
claim is attempted.

## Final Quality And Provider Comparison

| Domain | Baseline → campaign executable rate | Baseline → campaign rejection causes | Baseline → campaign tokens | Baseline → campaign logical calls | Campaign retries |
| --- | ---: | --- | ---: | ---: | ---: |
| Contacts | 1.000 → 0.944 | 3 duplicates → 4 duplicates, 2 provider errors | 102,260 → 111,649 | 6 → 36 | 7 |
| Mobile messages | 0.933 → 1.000 | 2 runtime errors → none | 116,464 → 107,304 | 15 → 30 | 7 |
| Workspace tasks | 1.000 → 0.968 | none → 1 provider error | 105,816 → 90,142 | 15 → 31 | 10 |

Across the campaign, 94 of 97 attempts generated executable candidates, 90
were accepted, and all 90 accepted samples passed local verification. All 15
held-out tasks also passed. The seven bounded rejections comprise four exact
duplicates and three exhausted provider errors; no execution, verification, or
safety rejection occurred. The campaign used 309,095 tokens: 151,330 prompt
tokens and 157,765 completion tokens. Provider lineage returned no price
metadata, so no dollar-cost claim is made.

The campaign's locally normalized difficulty distribution is 10 basic, 2
constrained, 20 intermediate, 6 recovery, and 52 selector-recovery samples.
The final comparison records both comparable values and legacy evidence gaps:

| Metric | Prior baseline | Campaign | Comparison status |
| --- | --- | --- | --- |
| Structural-cell coverage | Not emitted by pre-coverage runs | 13 fulfilled cells per domain | No baseline comparison; pilot provides 12 → 13 scale evidence |
| Largest family share | 0.556 / 0.357 / 0.333 | 0.333 / 0.133 / 0.200 | Like-for-like under the common taxonomy |
| Grounding reuse | Not emitted | 15 / 15 / 16 groundings; max reuse 2 | Baseline unavailable |
| Difficulty distribution | Provider-shaped, not locally normalized | 10 basic, 2 constrained, 20 intermediate, 6 recovery, 52 selector-recovery | Baseline unavailable |
| Rejection causes | 3 duplicates, 2 runtime errors | 4 duplicates, 3 provider errors | Like-for-like bounded causes |
| Token usage | 324,540 | 309,095 | Like-for-like provider usage |
| Executable rate | 88 / 90, or 0.978 | 94 / 97, or 0.969 | Like-for-like quality evidence |
| Accepted-sample verification | 85 / 85, or 1.000 | 90 / 90, or 1.000 | Like-for-like local verification |
| Held-out verification | 15 / 15, or 1.000 | 15 / 15, or 1.000 | Like-for-like evaluation suites |

Unavailable legacy fields are not reconstructed from instructions. The
explicit gaps prevent an overstated like-for-like claim while preserving the
complete comparison required for a revise decision.

The generic representative-scale consumer correctly classifies all three v4
shadow-mode runs as `insufficient_evidence` and recommends
`expand_representative_evidence`. The campaign therefore validates the
campaign's bounded execution path but not the structural-growth hypothesis,
release eligibility, or full representative eligibility. The scale evidence
records contacts and mobile runtimes above 600 seconds. At campaign completion,
the resulting activation disposition was recorded in the
[local async-orchestration issue](../../.scratch/ISSUE-0001-async-local-orchestration.md);
the campaign itself did not implement that out-of-scope work. Dataset release
reports remain ineligible, release-quality audits remain `watch`, and no
dataset was promoted. A scan of all 138 campaign files found no provider-secret
fields, authorization headers, configured credential value, or local absolute
path.

## Provider Pilot Decision

**`ready-for-authorized-campaign`**

The synthesis operator authorized `api.deepseek.com`, model
`deepseek-v4-flash`, and the configured `AGENT_DATA_API_KEY` for a serial pilot
bounded to 72 provider calls. Contacts, mobile messages, and workspace tasks
each accepted 12 of 12 generated candidates after issuing 12 of their 24
allowed assignment attempts. The three runs used 36 logical generation calls
and five bounded transport retries, for 41 HTTP attempts in total. No
thirty-per-domain campaign had been authorized or run at that stage.

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
gate supported requesting separate authorization for the thirty-per-domain
campaign; the final campaign result is recorded above.

## Deterministic Decision

**`ready-for-authorized-pilot`**

The deterministic catalog blocker is resolved. Versioned v3 catalogs contain
thirteen executable cells per domain, and deterministic runs fulfill twelve
distinct cells at target 12 and all thirteen at target 30. This evidence
supports requesting separate authorization for the provider pilot governed by
ticket 06.

This preflight decision did not itself authorize a provider, credentials,
model, or budget. The later provider pilot and campaign above each received
separate authorization. No dataset was promoted, and no release or
downstream-value claim follows from any stage.

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

Pilot runtime evidence remains under
`artifacts/coverage-campaign-provider-pilot-v1/`; final campaign evidence is
under `artifacts/coverage-campaign-provider-30-v1/`. Both retain per-domain
coverage, quality, evaluation, taxonomy-comparison, and three-domain diagnostic
evidence. Current authorization, status, assignment, and activation conditions
remain exclusively in the
[local issue tracker](../../.scratch/coverage-driven-representative-synthesis/README.md).
