# 10 — Evaluate the Independent Judge Activation Gate

**What to build:** Let an evaluator run the independent semantic judge three
times over an approved reviewed corpus and receive a deterministic activation
or no-go report. The report must prioritize critical false-support prevention,
measure useful automatic coverage, and preserve enough bounded evidence to
reproduce every metric without exposing raw judge material.

**Blocked by:** [03 — Use an Independent Model for Shadow Admission](03-independent-model-shadow-admission.md), [09 — Produce and Import a Reviewed Calibration Corpus](09-reviewed-calibration-corpus.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Semantic Mutation Admission](../../../docs/product-specs/semantic-mutation-admission.md)

## Acceptance criteria

- [ ] Three repeated evaluations use identical normalized inputs, split assignments, and an explicitly independent judge configuration.
- [ ] The versioned report calculates supported precision, unsafe-case capture, non-uncertain coverage, exact verdict agreement, critical flips, retries, latency, failures, and token use.
- [ ] Metrics are broken down by domain, task type, action, provenance origin, verdict, and reason code.
- [ ] Activation requires zero critical false supports, at least 98% supported precision, at least 98% unsafe-case capture, at least 70% non-uncertain coverage, at least 95% exact agreement, and zero critical flips to supported.
- [ ] Any unmet threshold produces a deterministic no-go with bounded reasons; coverage cannot compensate for a safety failure.
- [ ] The report records corpus, held-out split, judge configuration, input, and output hashes without raw prompts, responses, or credentials.
- [ ] Same-model or non-reviewed inputs are rejected as activation evidence rather than merely marked diagnostic.
- [ ] Tests cover every metric boundary, critical-case asymmetry, repeated-verdict permutations, malformed results, and deterministic report output.

## Scope guard

Do not run the final representative pipeline gate or modify thresholds to obtain
a passing result.
