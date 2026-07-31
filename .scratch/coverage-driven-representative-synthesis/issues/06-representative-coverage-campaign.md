# 06 — Validate Representative Coverage Campaigns

**What to build:** Validate the completed coverage-driven path first with a
small serial provider pilot and then, only if its structural evidence passes,
with a three-domain campaign of thirty target candidates per domain. Compare
coverage, concentration, quality, and provider usage with the previous
representative baseline.

**Blocked by:** None

**Status:** blocked

**Assignee:** Codex

**Parent spec:** [Coverage-Driven Representative Synthesis](../../../docs/product-specs/coverage-driven-representative-synthesis.md)

## Acceptance criteria

- [x] All deterministic tests, documentation validation, and fake-provider three-domain probes pass before paid calls are requested.
- [ ] The synthesis operator explicitly authorizes the provider, model, credentials, and bounded campaign budget before any paid call.
- [ ] A serial pilot of approximately ten to twelve target candidates per domain completes within its declared attempt ceiling.
- [ ] The pilot demonstrates growth in fulfilled structural cells, bounded family concentration, and non-degenerate grounding use rather than instruction-only variation.
- [ ] Pilot failures are classified as catalog-capacity, provider-contract, execution, verification, safety, duplicate, or attempt-exhaustion deficits with no unbounded retry.
- [x] The thirty-per-domain campaign runs only when pilot evidence supports continuing.
- [ ] Final evidence compares structural-cell coverage, largest family share, grounding reuse, difficulty distribution, rejection causes, token or cost usage, executable rate, and verification rate against the prior representative baseline.
- [x] The result records an evidence-backed proceed, revise-catalog, revise-scheduler, expand-environment, or stop decision without automatically promoting a dataset release.
- [x] Structural coverage that fails to grow with target size prevents a success conclusion even when accepted counts are high.
- [x] Artifacts remain diagnostic unless all separately governed representative and release requirements pass.

## Preflight result

The expanded deterministic fake-provider preflight now grows from twelve to
thirteen fulfilled cells between targets 12 and 30 in all three domains, with
grounding reuse capped at two. Its gate decision is
`ready-for-authorized-pilot`. This is not the required provider pilot: no paid
authorization was requested, no paid provider call was made, and no dataset
release was promoted. The ticket remains externally blocked until the
synthesis operator explicitly authorizes the provider, model, credentials, and
bounded campaign budget. See the
[preflight report](../../../docs/generated/representative-coverage-campaign-validation.md).

## Scope guard

Do not run paid calls without explicit authorization, tune against held-out or
downstream benchmark outcomes, implement unrelated async orchestration, or
silently redefine profile thresholds in response to campaign results.
