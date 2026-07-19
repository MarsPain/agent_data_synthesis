# Semantic Duplicate Detection

## Desired Behavior

Detect candidate tasks that are meaningfully equivalent despite paraphrased
instructions or reordered commutative actions, so accepted dataset size and
curriculum coverage are not inflated by near-duplicates.

## Constraints

- Preserve the current exact-duplicate gate as a deterministic baseline.
- Keep admission decisions reproducible and report the reason and comparison
  evidence without storing sensitive raw provider data.
- Make any embedding, model, or provider dependency explicit and optional.
- Measure false-positive and false-negative trade-offs before the semantic gate
  can affect release admission.

## Testing Decisions

- Evaluate paraphrase families, commutative action reorderings, legitimately
  distinct tasks with shared vocabulary, and cross-domain lookalikes.
- Compare semantic decisions with the exact baseline and a reviewed held-out
  set.
- Treat threshold and provider changes as versioned policy changes.

## Acceptance

- The detector identifies reviewed semantic duplicate families at an agreed
  recall without collapsing reviewed distinct tasks.
- Reports separate exact and semantic duplicate evidence.
- Runs remain deterministic for a fixed policy, representation provider, and
  input set.
- The feature can be disabled without changing the existing exact gate.

Current scheduling and activation state live only in
[ISSUE-0002](../../.scratch/ISSUE-0002-semantic-duplicate-detection.md).
