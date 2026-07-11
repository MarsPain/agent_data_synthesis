# Representative Scale And Downstream Evidence Design

## Purpose

This design defines the evidence boundary that should follow the three-domain
release and review workflow completed in plans 0040 and 0041. The next step is
not to pre-emptively add async orchestration or semantic duplicate detection.
It is to run the existing framework at representative scale, aggregate the
resulting evidence, exchange a hash-locked dataset release with an external
training system, and import a sanitized baseline-versus-treatment result.

The repository remains a data-synthesis and evidence system. It does not train
models, provision training infrastructure, manage model credentials, or turn an
external benchmark result into an automatic dataset-admission decision.

## Decision

Adopt one staged evidence campaign with three new versioned artifacts:

- `representative_scale_evidence_v1` aggregates existing run, quality,
  evaluation, release, audit, and review evidence across contacts, mobile
  messages, and workspace tasks.
- `downstream_benchmark_bundle_v1` binds a verified dataset release pack to a
  fixed external evaluation protocol and baseline/treatment comparison.
- `downstream_benchmark_result_v1` imports and validates sanitized results from
  an external training and evaluation system.

The campaign may recommend a later development direction, but it cannot
activate that work by mutating profile decisions, dataset release reports, or
release packs.

## Why This Boundary

The current repository already provides deterministic three-domain release
candidates, held-out evaluation, profile decisions, dataset release admission,
hash-locked release packs, release-quality audits, and explicit release-review
resolution. The remaining uncertainty is empirical:

- whether representative runs reach the existing async trigger of at least 100
  candidates or 600 seconds;
- whether representative runs reach the semantic-duplicate trigger of at least
  100 candidates and an exact duplicate rate of at least 10 percent;
- whether human review identifies repeatable quality problems rather than
  small-fixture noise; and
- whether a released synthetic dataset improves an external held-out Agent
  benchmark relative to a declared baseline.

Mechanically duplicating deterministic fixture candidates is not representative
evidence. It can manufacture duplicate pressure and make an infrastructure
threshold appear meaningful when no real generation workload exists. The
design therefore separates diagnostic scale probes from representative runs and
requires an explicit evidence classification.

## System Flow

```text
representative domain runs
  -> existing manifests and quality reports
  -> held-out/profile/release/audit/review evidence
  -> representative_scale_evidence_v1
  -> verified dataset_release_pack_v1
  -> downstream_benchmark_bundle_v1
  -> external training and evaluation
  -> downstream_benchmark_result_v1
  -> conservative next-development recommendation
```

Every step after generation is an offline consumer of existing artifacts. It
must not rerun generation implicitly, rewrite accepted samples, or change the
meaning of existing admission decisions.

## Representative Run Classification

Each domain run is classified as one of:

- `representative`: the run uses an approved generation mode and admitted
  source configuration that exercise the intended workload without mechanically
  repeating fixture candidates.
- `diagnostic_only`: the run is useful for contract, performance, or threshold
  testing but relies on fixed fixtures, deliberate repetition, or another
  non-representative construction.
- `insufficient_evidence`: required artifacts are absent, malformed,
  cross-dataset, cross-domain, or otherwise cannot support a conclusion.

Classification is evidence, not a user-supplied assertion. The classifier reads
sanitized manifest/profile metadata, generation mode, source admission facts,
candidate counts, and the relevant report identities. A caller may supply a
campaign configuration that names expected domains and artifact directories,
but it cannot override a failed identity or representativeness check.

Only `representative` runs may support recommendations to activate async
orchestration or semantic duplicate detection. Diagnostic runs may expose a
watch signal, but their recommendation must be to gather representative
evidence.

## Representative Scale Evidence Contract

`representative_scale_evidence.json` uses
`schema_version: representative_scale_evidence_v1`. It records:

- a deterministic campaign id derived from canonical input identities;
- the required domain set: contacts, mobile messages, and workspace tasks;
- one sanitized domain summary for each run;
- artifact basenames and hashes for the consumed evidence;
- candidate count, accepted/rejected counts, runtime when present, exact
  duplicate count/rate, held-out status, profile-promotion status, dataset
  release status, release-audit status, and review-resolution status;
- the existing async and semantic-duplicate thresholds without redefining them;
- per-domain evidence classification and triggered signals;
- aggregate human-review counts and minutes, without reviewer aliases or
  decision text; and
- one conservative next-development recommendation.

Allowed recommendations are:

- `activate_async_orchestration`;
- `activate_semantic_duplicate_detection`;
- `improve_generation_or_verification`;
- `expand_representative_evidence`; and
- `no_change_recommended`.

If more than one activation condition is met, the report records all triggered
signals but selects one primary recommendation using a documented stable
priority: evidence remediation first, generation/verification quality next,
semantic duplicate detection next, async orchestration next, and no change
last. The report does not edit plan lifecycle state automatically.

## Downstream Benchmark Bundle Contract

`downstream_benchmark_bundle.json` uses
`schema_version: downstream_benchmark_bundle_v1`. It is created only from a
valid `dataset_release_pack_v1` whose standalone verification passes. The
bundle records:

- a deterministic benchmark id;
- dataset version, release id, release-pack basename, SHA-256 hash, and byte
  count;
- the experiment protocol version;
- a baseline arm that does not consume the referenced synthetic release;
- a treatment arm that consumes exactly the referenced release;
- the external held-out benchmark id and version;
- primary and supporting metric names, direction, and valid numeric ranges;
- required sample/seed identity fields for result reproducibility;
- the expected result schema version; and
- explicit non-claims about causality, release admission, and model promotion.

The bundle contains no API keys, provider headers, model weights, raw local
paths, arbitrary training commands, or infrastructure-specific configuration.
Model and training-system identities are opaque sanitized aliases.

## Downstream Benchmark Result Contract

`downstream_benchmark_result.json` uses
`schema_version: downstream_benchmark_result_v1`. It is an explicit external
input validated against one benchmark bundle. It records:

- benchmark id, dataset version, release id, and release-pack hash;
- opaque baseline and treatment model aliases;
- external benchmark id/version;
- fixed seed identifiers and evaluation sample counts;
- baseline and treatment metric values;
- deterministic absolute and relative deltas where defined;
- a result status of `improved`, `no_detected_improvement`, or
  `insufficient_evidence`; and
- sanitized validation reasons.

Unknown metrics, missing primary metrics, non-finite values, out-of-range
values, identity mismatches, inconsistent sample counts, duplicate arms, and
malformed inputs produce `insufficient_evidence`. Parser exceptions, local
paths, free-text trainer logs, credentials, and arbitrary external payloads are
not copied into the result.

An `improved` result means only that the declared treatment exceeded the
declared baseline on the fixed primary metric under the supplied protocol. It
does not prove causality, general model quality, or dataset releaseability.

## Component Boundaries

### `synthesis.scale_evidence`

Owns artifact loading, identity matching, representativeness classification,
threshold observation, aggregate review evidence, recommendation selection,
contract construction, and deterministic writing. It consumes existing report
contracts and does not own candidate generation or admission.

### `synthesis.downstream_benchmark`

Owns benchmark bundle construction, release-pack verification integration,
external-result validation, delta calculation, sanitized failure reporting, and
deterministic writing. It does not invoke a trainer or model API.

### Standalone scripts

Standalone commands build scale evidence, create a benchmark bundle, and import
a benchmark result from existing artifact paths. They use explicit inputs,
write only their named outputs, and do not add a combined flag to the default
`main.py` generation path.

### Existing owners

- `synthesis.profile_decisions` remains the owner of async and semantic trigger
  thresholds and per-run decisions.
- `synthesis.dataset_release` remains the owner of release admission.
- `synthesis.release_pack` remains the owner of release-pack construction and
  verification.
- `synthesis.release_review` remains the owner of release-review resolution.
- `synthesis.datasets` may attach new artifact basenames only through narrow,
  validated helpers and only if the implementation plan requires attachment.

## Error And Safety Rules

- Reject absolute paths and parent traversal in persisted artifact references.
- Match dataset version, profile domain, release id, benchmark id, and hashes
  across every consumed boundary.
- Convert unreadable or malformed external results into a validated
  `insufficient_evidence` result with sanitized reason codes.
- Never copy raw sample instructions, trajectories, source rows, prompts,
  provider payloads, headers, credentials, reviewer aliases, or host paths into
  aggregate evidence.
- Preserve the bytes and decisions of existing manifests, release reports, and
  release packs unless a later plan explicitly defines a compatible append-only
  attachment.
- Keep all new workflows opt-in and offline.

## Testing Strategy

Contract tests cover valid records, allowed vocabularies, canonical ids, metric
ranges, path safety, and malformed inputs. Unit tests cover three-domain
aggregation, cross-domain and cross-dataset rejection, diagnostic fixture
classification, stable recommendation priority, release-pack verification,
result identity matching, and delta calculation. CLI tests cover explicit
prerequisites, deterministic output, default-path non-interference, and
redaction sentinels.

An end-to-end fixture proves this offline sequence:

1. consume three existing domain artifact directories;
2. write representative scale evidence;
3. create a benchmark bundle from a verified release pack;
4. import a synthetic external baseline/treatment result; and
5. write a validated recommendation without changing generation or release
   artifacts.

The full unit suite and documentation validator remain required before the
implementation plan can be completed.

## Delivery Stages

The implementation plan should preserve one coherent Plan 0042 while using
reviewable stages:

1. lock existing default and release behavior;
2. add scale-evidence contracts and aggregation;
3. add representativeness classification and recommendation rules;
4. add benchmark bundle construction;
5. add downstream result import and validation;
6. add standalone CLI workflows and three-domain evidence;
7. synchronize canonical docs and record the resulting next-step decision.

The plan is complete when the evidence exchange works and its boundaries are
verified. Actual external training results may remain an operational input; the
repository must provide a deterministic example result for tests without
claiming downstream model improvement.

## Out Of Scope

- Model training, fine-tuning, reward-model training, policy optimization, or
  Agentic RL.
- Training-service APIs, job scheduling, credentials, model registries, or
  model-weight storage.
- Async orchestration, durable queues, distributed workers, dashboards, or
  external MCP servers.
- Semantic embeddings, vector stores, clustering, or near-duplicate admission
  gates.
- Automatic plan activation, profile promotion, dataset admission, or release
  blocking based on downstream results.
- A fourth domain, browser review UI, or real-user data ingestion.

## Documentation Impact

The implementation plan must update `docs/DATA.md` for the new contracts,
`docs/BACKEND.md` for offline consumer boundaries, `docs/PRODUCT_SENSE.md` for
the downstream evidence interpretation, `docs/ROADMAP.md` and `docs/PLANS.md`
for lifecycle state, and root entrypoints only when their navigation or common
commands change. This design remains the canonical rationale for those edits.
