# Require Independent Semantic Mutation Admission Before Execution

## Status

Accepted on 2026-07-22.

State-changing candidates must pass deterministic authorization/provenance
validation and an independent `mutation_admission_judge` before execution when
enforcement is enabled. The judge uses a different model from the task
generator for release-grade decisions, returns only a bounded three-value
verdict, and cannot override missing or invalid evidence. This deliberately
places the specialized mutation gate before execution while leaving the future
general `judge_verification` role as a post-execution concern. The decision
prevents a generator from inventing both a mutation and the evidence that
certifies it, while preserving semantic flexibility through reviewed
instruction-to-argument mappings.

## Considered Options

- Deterministic literal matching alone was rejected because it cannot safely
  handle paraphrase, negation, conditional requests, or semantic realization.
- A single unrestricted LLM judge was rejected because it could bypass factual
  contract failures and create unauditable admissions.
- Reusing the generator model for release admission was rejected because its
  errors and assumptions are correlated with the generated candidate.
- Reusing the generic post-execution judge role was rejected because mutation
  authorization has different inputs, timing, and failure semantics.

## Consequences

Domain packs must declare mutation policy, generators must propose evidence,
and accepted mutation samples must retain sanitized admission lineage. Local
runs remain available through explicit disabled and shadow modes, but
release-grade mutation data requires enforcement after reviewed calibration. Existing
mutation samples are not grandfathered into the new contract.

The full desired behavior and activation thresholds are in the
[semantic mutation admission product spec](../product-specs/semantic-mutation-admission.md).
