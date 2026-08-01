# 06 — Validate Representative Coverage Campaigns

**What to build:** Validate the completed coverage-driven path first with a
small serial provider pilot and then, only if its structural evidence passes,
with a three-domain campaign of thirty target candidates per domain. Compare
coverage, concentration, quality, and provider usage with the previous
representative baseline.

**Blocked by:** None

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Coverage-Driven Representative Synthesis](../../../docs/product-specs/coverage-driven-representative-synthesis.md)

## Acceptance criteria

- [x] All deterministic tests, documentation validation, and fake-provider three-domain probes pass before paid calls are requested.
- [x] The synthesis operator explicitly authorizes the provider, model, credentials, and bounded campaign budget before any paid call.
- [x] A serial pilot of approximately ten to twelve target candidates per domain completes within its declared attempt ceiling.
- [x] The pilot demonstrates growth in fulfilled structural cells, bounded family concentration, and non-degenerate grounding use rather than instruction-only variation.
- [x] Pilot failures are classified as catalog-capacity, provider-contract, execution, verification, safety, duplicate, or attempt-exhaustion deficits with no unbounded retry.
- [x] The thirty-per-domain campaign runs only when pilot evidence supports continuing.
- [x] Final evidence compares structural-cell coverage, largest family share, grounding reuse, difficulty distribution, rejection causes, token or cost usage, executable rate, and verification rate against the prior representative baseline.
- [x] The result records an evidence-backed proceed, revise-catalog, revise-scheduler, expand-environment, or stop decision without automatically promoting a dataset release.
- [x] Structural coverage that fails to grow with target size prevents a success conclusion even when accepted counts are high.
- [x] Artifacts remain diagnostic unless all separately governed representative and release requirements pass.

## Preflight result

The expanded deterministic fake-provider preflight grows from twelve to
thirteen fulfilled cells between targets 12 and 30 in all three domains, with
grounding reuse capped at two. Its gate decision was
`ready-for-authorized-pilot`; the separately authorized pilot below has now
cleared that gate. See the
[preflight report](../../../docs/generated/representative-coverage-campaign-validation.md).

## Pilot authorization

On 2026-07-31, the synthesis operator authorized a serial provider pilot using
`api.deepseek.com`, model `deepseek-v4-flash`, and the currently configured
`AGENT_DATA_API_KEY`, bounded to at most 72 provider calls across the three
domains. The authorization does not include the thirty-per-domain campaign.

## Pilot result

The pilot fulfilled its bounded coverage and quality gate. Its evidence-backed
decision is `ready-for-authorized-campaign`; detailed measurements and baseline
comparisons are retained in the
[validation report](../../../docs/generated/representative-coverage-campaign-validation.md).
At that point the ticket remained externally blocked because the synthesis
operator had not yet authorized the thirty-per-domain campaign. No campaign
call or dataset promotion occurred during the pilot stage.

## Campaign authorization

On 2026-07-31, the synthesis operator separately authorized the
thirty-per-domain campaign using `api.deepseek.com`, model
`deepseek-v4-flash`, and the currently configured `AGENT_DATA_API_KEY`. The
campaign is bounded to at most 180 logical generation calls across the three
serial domain runs and permits the provider client's existing bounded
transport retries.

## Campaign result

The serial campaign fulfilled target 30 and all 13 v3 cells in each domain
within the 180-call authorization. Contacts' common-taxonomy family count did
not grow between pilot and campaign, so the evidence-backed decision is
`revise-catalog` rather than a success conclusion. Detailed measurements,
baseline availability gaps, and release boundaries are in the
[validation report](../../../docs/generated/representative-coverage-campaign-validation.md).
The artifacts remain diagnostic, and no dataset release was promoted.

## Scope guard

Do not run paid calls without explicit authorization, tune against held-out or
downstream benchmark outcomes, implement unrelated async orchestration, or
silently redefine profile thresholds in response to campaign results.
