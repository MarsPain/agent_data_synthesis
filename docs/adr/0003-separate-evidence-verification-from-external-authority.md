# Separate Evidence Verification from External Authority

## Status

Accepted on 2026-08-08.

The framework verifies release, governance, authority, and downstream experiment
evidence and computes bounded qualification decisions, but it does not replace
human publication authority or own external model training. Release Candidate,
Publishable, and Training Recommended are cumulative qualifications over one
exact artifact identity. They establish progressively stronger, scoped claims;
they are not independent badges or aliases for individual pipeline statuses.

Publishable requires authenticated publication approval for an exact
distribution scope in addition to still-valid machine evidence. Risk acceptance
and publication approval are distinct attestations, and hard integrity, source,
mutation, governance, and authority gates cannot be waived. External/public
distribution with residual risk requires separate authenticated risk and
publication principals.

Training Recommended requires a still-valid Publishable release plus a
pre-registered external matched experiment. The external experiment owner
selects and runs the model, training system, benchmark, control, and evaluation;
the framework imports content-addressed evidence, verifies internal consistency,
and recomputes the declared result. It does not train, tokenize, access sealed
samples, or attest facts that cannot be independently verified at the import
boundary.

## Considered Options

- Treating a passing machine release report as publication approval was rejected
  because machine admission cannot grant human distribution authority.
- Treating completed review or accepted review items as risk acceptance was
  rejected because review disposition lacks authenticated scope and authority.
- Treating the three qualifications as independent badges was rejected because
  it permits contradictory claims and lets downstream evidence bypass release
  governance.
- Running training and benchmark evaluation inside the framework was rejected
  because it would expand the system into model, credential, compute, and sealed
  benchmark ownership.
- Trusting a positive downstream point estimate was rejected because it lacks a
  pre-registered meaningful-gain rule, leakage controls, and reproducible
  uncertainty evidence.
- Requiring signatures for the initial external experiment import was rejected
  for the first protocol; submitter provenance is an explicit trusted boundary,
  while every supplied identity, hash, membership rule, and statistic remains
  verified.

## Consequences

Qualification evaluators are deterministic and side-effect free. They never
publish a dataset, start training, promote a model, repair a release, or mutate
review state. A failed higher-level attempt preserves a valid lower
qualification; invalidating lower evidence removes dependent current claims
while preserving append-only history.

Test authority and experiment fixtures are permanently non-qualifying. They may
prove Publishable or Training Recommended conformance but cannot alter effective
qualification. Real approval requires an authenticated authority path, and a
real training recommendation remains scoped to the exact release, external
model, recipe, seed, benchmark, split, and registered protocol.

The full behavior and acceptance boundary are in the
[Outcome-Validated Domain Pack product spec](../product-specs/outcome-validated-domain-pack.md),
and the verification mechanics are in the
[deep design](../design-docs/outcome-validated-domain-pack.md).
