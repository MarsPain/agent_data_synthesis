# Specify the Workspace Training Recommendation Protocol

- **Status:** closed
- **Assignee:** Codex
- **Label:** `wayfinder:grilling`
- **Parent map:** [Outcome-Validated Domain Pack](../README.md)
- **Blocked by:** [Define Training Recommended Evidence](06-training-recommended-evidence.md)

## Question

Which exact external benchmark suite and version, sealed split, base-model and
training-system identities, control corpus, replacement rule, primary metric,
critical guardrails and tolerances, leakage checks, and external attestation
format instantiate the first real Workspace Training Recommendation protocol?

## Resolution comment

The framework owns a verifier contract, not a trainer or a benchmark service.
The first Workspace Training Recommendation protocol is instantiated only when
an external experiment owner registers exact external identities and later
supplies content-addressed experiment and evaluation files. The repository does
not choose a default model, training stack, benchmark, control corpus, or
compute budget, and `external_agent_tasks_v1` remains a conformance-fixture
placeholder rather than a real qualification suite.

### Responsibility boundary

The external experiment owner chooses, funds, pre-registers, and executes both
training arms and the evaluation. It controls model and benchmark access and
supplies the experiment files. This framework:

- verifies the exact Publishable release and registered protocol identities;
- checks file hashes, required fields, arm consistency, the replacement-count
  tolerance, leakage-report status, and paired evaluation membership;
- recomputes the primary metric, bootstrap interval, and bounded decision;
- never selects or loads a model or tokenizer, schedules training, holds
  credentials, reads a sealed evaluation split, or performs duplicate scans.

Submitter provenance is trusted at the explicit import boundary. The protocol
uses ordinary content-addressed files and requires no signatures, keys,
third-party attester, or separation between training and evaluation operators.
The resulting claim is based on operator-supplied external evidence whose
internal consistency the framework verified; it is not an independently
authenticated statement about who performed the work.

### Registration-time protocol identity

Before either arm runs, `workspace_training_protocol_v1` binds:

1. The exact release id, release-pack bytes/hash, `workspace_tasks` Domain Pack
   reference/hash, current Publishable evidence, and its validity window.
2. Externally selected benchmark suite id/version, sealed evaluation split
   id/hash, ordered evaluation task-id manifest/hash, scoring-code id/hash, and
   the time at which those identities were frozen.
3. Externally selected initial model weights id/hash, declared tokenizer
   id/hash, training-system id/version, training-code commit/hash, environment
   or container id/hash, hyperparameters, seed, schedule, stopping rule, and
   permitted failure/exclusion policy. These are evidence fields; the framework
   does not materialize or execute them.
4. Every common non-release training input, baseline control-corpus
   manifest/hash, deterministic control-selection rule, expected removed
   control-record count, treatment release-record manifest/hash, and expected
   inserted release-record count.
5. `task_success_rate` as the sole qualification metric,
   `paired_percentile_bootstrap_v1`, 10,000 paired resamples, an explicit
   bootstrap seed, a two-sided 95% percentile interval, and the strict
   lower-bound threshold of more than one-percent relative improvement.
6. The exact leakage-report schema/method id and the bounded experiment and
   evaluation result schemas to be imported.

Any change after registration creates a new protocol id and cannot reuse the
old result. Model aliases, mutable URLs, display names, or unpinned "latest"
versions are insufficient identities.

### Approximate sample-count replacement

The control/release replacement unit is a training record in the content-bound
input manifests. Let `removed` be baseline control records removed from the
treatment mix and `inserted` be records from the exact release added to it. A
valid comparison requires `removed > 0`, `inserted > 0`, and:

```text
abs(inserted - removed) / removed <= 0.10
```

The same declared initial model, code, environment, hyperparameters, seed,
schedule, stopping rule, and common non-release inputs apply to both arms.
Exact token, step, elapsed-time, or compute equality is not required. External
systems may report token and compute observations, but they are non-gating and
the framework does not run a tokenizer. The retained sample-count difference
means the result is an approximate-size utility comparison, not proof that the
release is the only causal influence.

### External evidence files

One real import contains ordinary files equivalent to:

```text
experiment_protocol.json
baseline_manifest.json
treatment_manifest.json
evaluation_manifest.json
paired_results.jsonl
leakage_report.json
```

The root manifest binds the relative path, schema version, SHA-256 digest, and
byte count of every file. Baseline and treatment manifests bind their exact
training identities, common inputs, arm-specific data inputs, record counts,
completion status, and declared observations. The evaluation manifest binds the
benchmark/split/scoring identities and the exact ordered task-id set used for
both arms.

Each `paired_results.jsonl` record contains one unique registered `task_id` and
binary `baseline_success` and `treatment_success` outcomes. Missing, duplicate,
extra, differently ordered, excluded-after-observation, or arm-specific task ids
make the experiment invalid. Aggregate scores supplied by the external system
are informational; the framework recomputes them from these paired records.

### Metric and bootstrap decision

For `N` paired tasks, baseline and treatment success rates are their respective
binary means. The observed baseline must be greater than zero. Each bootstrap
replicate samples `N` paired task rows with replacement using the registered
seed and computes the treatment-minus-baseline absolute-rate difference.
`paired_percentile_bootstrap_v1` derives each draw index as the unsigned integer
value of `SHA-256(UTF-8(seed + ":" + replicate + ":" + draw))` modulo `N`,
where replicate and draw are zero-based decimal integers. After sorting 10,000
replicate differences, the two-sided 95% nearest-rank interval uses one-based
ranks 250 and 9,750 (zero-based indices 249 and 9,749). This avoids dependence
on a local random-number-library version.

To avoid an unstable ratio inside individual resamples, the absolute-difference
interval is converted to relative improvement using the fixed observed baseline
rate. Thus:

```text
relative_lower_bound = absolute_delta_lower_bound / baseline_success_rate
```

The utility criterion passes only when `relative_lower_bound > 0.01`; equality
does not pass. An empty evaluation, zero observed baseline, non-binary outcome,
non-finite calculation, unknown bootstrap version, or inability to reproduce
the supplied aggregate result yields invalid or insufficient evidence.

The external benchmark may report reward, latency, token use, capability
slices, or other metrics, but they do not affect the first Workspace
qualification. There are no default sample-level safety checks or mandatory
model-level non-regression guardrails at this stage. Sample correctness,
mutation safety, held-out capability behavior, and publication governance were
owned by Release Candidate and Publishable; this phase treats the exact
Publishable release as one immutable input. A newly discovered release defect
uses a separate revocation or new-release path.

### Minimal leakage evidence

Leakage checking is performed externally. `leakage_report.json` binds the
evaluation split hash, scoring-code hash, check-method id/version, and declares
that the protocol and evaluation identities were frozen before training, the
evaluation split was not used for training or experiment selection, the exact
overlap count, and unresolved-overlap count. Framework validity requires:

- the hashes equal the registered protocol;
- baseline and treatment used the same frozen evaluation identities;
- `protocol_frozen_before_training` is true;
- `evaluation_used_for_training` is false; and
- `unresolved_overlap_count` is zero.

The framework verifies these fields but does not read release, control, or
evaluation samples and does not perform exact, near-duplicate, semantic,
template, entity, or trace-overlap analysis itself.

### Evidence classes and outcomes

`evidence_class: external_experiment` is eligible for a real decision when all
requirements above verify. `evidence_class: conformance_fixture` is permanently
non-qualifying: it may contain known numbers that exercise the complete positive
calculation path, but its effective result is only
`protocol_conformance_passed`, never Training Recommended.

For real evidence the bounded outcomes are:

- `training_recommended`: Publishable is still valid, all exact identities,
  hashes, arm rules, sample-count tolerance, paired evaluation, and leakage
  declarations verify, and the relative 95% lower bound is greater than 1%;
- `no_detected_meaningful_gain`: the experiment is valid but the primary
  threshold is not met;
- `invalid_experiment`: a post-registration change, count mismatch beyond 10%,
  arm/task mismatch, leakage violation, selective exclusion, premature stop,
  or other declared protocol violation invalidates the comparison;
- `insufficient_evidence`: a required file, field, identity, schema, hash, or
  reproducible calculation is missing or unverifiable.

No outcome starts training, changes a release, repairs a sample, or weakens a
prior qualification. A failed or invalid experiment leaves Publishable intact.
Training Recommended is bound only to the exact external model, training
configuration, seed, benchmark, evaluation split, and approximate-size
comparison recorded by this protocol.

The human confirmed this verifier-only, unsigned external-evidence boundary on
2026-08-08; accepted sample-count matching within ten percent; ruled out local
tokenization and exact token/compute matching; removed default Training
Recommended guardrails and sample-level re-analysis; and selected paired
`task_success_rate` as the sole qualification metric.
