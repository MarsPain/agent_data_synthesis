# Define Training Recommended Evidence

- **Status:** closed
- **Assignee:** Codex
- **Label:** `wayfinder:grilling`
- **Parent map:** [Outcome-Validated Domain Pack](../README.md)
- **Blocked by:** [Define Release Qualification Levels and Allowed Claims](01-release-qualification-levels.md), [Define Publishability Evidence and Decision Authority](05-publishability-evidence-and-authority.md)

## Question

What pre-registered downstream benchmark evidence, leakage controls, baseline
and treatment identities, replication requirements, minimum meaningful gain,
supporting non-regression metrics, and failure semantics are required before a
publishable dataset may be called Training Recommended?

## Resolution comment

Training Recommended requires a still-valid Publishable release and a
pre-registered, hash-bound downstream experiment showing a meaningful benefit
in one exact training and evaluation context. The qualification does not claim
that the release improves other models, recipes, seeds, compute budgets, or
benchmarks, and downstream evidence cannot repair a failed or expired
Publishable qualification.

### Pre-registered experiment identity

Before either arm is trained, an immutable experiment protocol binds:

1. The exact release id, release-pack hash, Domain Pack reference/hash, and
   current Publishable evidence.
2. The benchmark suite, version, sealed evaluation split and scoring-code
   hashes; primary metric, direction, relative-gain calculation, bootstrap
   method, confidence level, and any optional model-level non-regression
   metrics declared by the external protocol.
3. The initial model weights, externally declared tokenizer, training code and
   environment, hyperparameters, training seed, schedule, sample-count
   accounting method, and permitted matching tolerances. Token and compute
   observations may be reported but are not matching gates.
4. Every non-release training input, the control corpus, the release-to-control
   replacement and mixing rule, and all corresponding content hashes.
5. Run-failure handling, stopping rules, exclusions, and the exact
   content-addressed evidence required to validate an externally supplied
   result at the trusted import boundary.

Changing any bound element creates a different experimental subject. Training
or evaluation results selected after inspecting alternatives are not admissible
under the original protocol.

### Matched baseline and treatment

One paired training experiment is sufficient; repeated training seeds are not
required. Both arms start from the same initial model and use the same declared
tokenizer identity, training system, code, hyperparameters, seed, schedule, and
non-release inputs. The framework does not run the tokenizer or require exact
token or compute matching.

The baseline consumes a predeclared control corpus. Under the frozen mixing
rule, the treatment replaces control records with the exact release using the
training-record counts in the content-bound input manifests. The inserted
release count and removed control count may differ by at most ten percent,
calculated relative to the removed control count. Exact token counts, elapsed
time, and compute may be externally reported but do not gate validity. An
optional no-added-data arm is diagnostic and does not replace the matched
baseline.

This is an approximate-size matched comparison rather than proof that the
release is the sole causal variable. A passing claim is scoped to the observed
external experiment and must retain the sample-count difference and this causal
limitation.

Because training-seed replication is not required, the resulting qualification
is scoped to the exact training seed and recipe. It is not evidence of expected
improvement across random initializations or training runs. Additional paired
seeds may strengthen a later claim only under a new or prospectively amended
protocol; they cannot be selectively added or discarded after results are
known.

### Meaningful gain and non-regression

The primary metric must show more than a one-percent relative improvement over
the baseline. For a higher-is-better metric, relative improvement is
`(treatment - baseline) / abs(baseline)`; for a lower-is-better metric the
direction is reversed. A protocol must reject or separately define cases where
the baseline makes that ratio undefined or unstable.

The benchmark evaluation is resampled without retraining using the
pre-registered paired bootstrap procedure. The lower bound of its 95% confidence
interval must be greater than one percent. A point estimate above one percent
is not enough.

The framework defines no universal sample-level or model-level guardrail at the
Training Recommended stage. Sample correctness, mutation safety, held-out
capability behavior, and release governance belong to the preceding Release
Candidate and Publishable qualifications; the Publishable release is consumed
here as one immutable, hash-bound input rather than re-opened for sample repair.

An external protocol may report additional model-level metrics or predeclare a
blocking non-regression threshold, but this is optional and benchmark-specific.
The first Workspace protocol uses only its primary downstream metric as the
utility gate. A newly discovered release defect follows a separate revocation
or new-release path and cannot be repaired inside the registered training
experiment.

### Leakage controls

- The evaluation split and scoring artifacts are frozen, content-bound and
  access-controlled before release selection and training. Benchmark labels and
  held-out instances cannot inform generation, filtering, control selection,
  mixing, hyperparameter choice, thresholds, or stopping.
- Release, control and evaluation artifacts undergo the externally declared
  overlap checks bound by the protocol. The external experiment reports its
  method, counts, and unresolved findings; this framework verifies the report
  and hashes but does not read sealed samples or run duplicate detection.
- Development data is distinct from the sealed evaluation split. Repeated
  evaluation, test-guided protocol changes, unexplained exposure, an unresolved
  duplicate finding, or an unverifiable data boundary invalidates the
  experiment; a fresh clean protocol and evaluation subject are required.
- The result bundle carries enough hashes, access declarations and per-arm
  manifests to verify internal consistency without receiving secrets or
  unrestricted private payloads. Submitter identity is trusted at import; the
  first Workspace protocol requires no signatures or key management.

### Decision and failure semantics

The deterministic decision has bounded outcomes:

- `training_recommended`: Publishable remains valid, all identities and leakage
  controls verify, and the primary 95% interval lower bound exceeds one-percent
  relative gain. Any optional blocking metric declared by that exact external
  protocol must also pass.
- `no_detected_meaningful_gain`: the experiment is valid, but the primary
  criterion is not met.
- `non_regression_failed`: the primary criterion is met but an optional
  blocking model-level metric explicitly declared by that external protocol
  exceeds its predeclared tolerance.
- `invalid_experiment`: leakage, post-registration changes, a sample-count
  mismatch beyond ten percent, another arm mismatch, selective exclusion,
  premature stopping, or another protocol violation makes the comparison
  inadmissible.
- `insufficient_evidence`: required evidence is absent, malformed,
  unknown-version, hash-mismatched, or otherwise internally unverifiable.

Failed, invalid or insufficient downstream evidence leaves an otherwise valid
Publishable qualification intact. Expiry or revocation of Publishable removes
the effective Training Recommended qualification while preserving its
historical record. The existing downstream result's `improved` observation may
remain supporting evidence, but it is not an alias for Training Recommended.
The decision records a claim; it does not start training, promote a model,
publish a dataset, or mutate an external system.

The human confirmed on 2026-08-07 that one matched training pair is sufficient
because repeated training is too costly. The human also confirmed the
one-percent relative-gain threshold at the lower bound of a pre-registered 95%
bootstrap interval and the hard failure of any protocol-declared critical
guardrail beyond its pre-registered tolerance. On 2026-08-08 the human replaced exact
token/step/compute matching with input-manifest training-record matching at a
ten-percent tolerance and explicitly ruled out running a tokenizer in this
framework. The human also removed default Training Recommended guardrails and
sample-level re-analysis: the first Workspace protocol gates utility only on
the primary downstream metric, while any external model-level guardrail is
optional and prospectively declared.
