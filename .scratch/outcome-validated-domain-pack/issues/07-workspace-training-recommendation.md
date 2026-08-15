# 07 — Verify the Workspace Training Recommendation Protocol

**What to build:** Add the verifier-only Workspace training protocol, content-addressed external experiment import, exact arm and evaluation consistency checks, leakage declarations, deterministic paired bootstrap, bounded outcomes, and permanent isolation between real external evidence and conformance fixtures.

**Blocked by:** [06 — Verify publishability evidence and external authority](06-publishability-evidence-authority.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Outcome-Validated Domain Pack](../../../docs/product-specs/outcome-validated-domain-pack.md)

## Acceptance criteria

- [x] Registration binds the exact Publishable release, model, tokenizer declaration, training system/code/environment, hyperparameters, seed, schedule, stopping/exclusion rules, common inputs, control/release manifests, benchmark/split/task/scoring identities, leakage method, and result schemas before training.
- [x] The framework reads ordinary content-addressed protocol, baseline, treatment, evaluation, paired-result, and leakage files without loading a model/tokenizer, starting training, accessing sealed samples, or running overlap scans.
- [x] Baseline and treatment use identical registered training identities and common inputs; inserted and removed training-record counts are positive and differ by no more than ten percent relative to removed records.
- [x] Paired results contain every registered ordered task exactly once for both arms with binary outcomes; missing, duplicate, extra, reordered, selectively excluded, or arm-specific ids invalidate the experiment.
- [x] The implementation recomputes both task-success rates and the deterministic 10,000-replicate paired percentile-bootstrap interval using the specified SHA-256 draw rule and nearest ranks.
- [x] The observed baseline rate must be positive and Training Recommended requires a strict relative lower bound greater than 0.01; equality yields no detected meaningful gain.
- [x] Leakage evidence binds the frozen split and scoring identities, confirms pre-training registration and no evaluation use for training, and reports zero unresolved overlap.
- [x] Real imports produce only training recommended, no detected meaningful gain, invalid experiment, or insufficient evidence with bounded reasons.
- [x] A failed or invalid experiment preserves a still-valid Publishable qualification and performs no training, release repair, publication, or model promotion.
- [x] Conformance fixtures can pass the full numerical path but cannot be relabeled or interpreted as real Training Recommended evidence.

## Scope guard

Do not choose a default model, tokenizer, trainer, benchmark, control corpus, or
compute budget; do not require exact tokens/compute; and do not add default
model-level guardrails or sample-level re-analysis to the first protocol.
