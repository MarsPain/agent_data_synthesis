# Product Sense

## Users

- Researchers who need controllable Agent training data.
- Engineers building domain-specific Agent fine-tuning or evaluation pipelines.
- Data quality teams that need auditable sample lineage and review queues.

## Value Proposition

The framework should reduce the cost of producing high-quality Agent trajectories by automating environment creation, tool synthesis, task generation, execution, verification, and dataset versioning.

## North-Star Metric

Accepted verified trajectories per dollar at a target quality floor.

## Supporting Metrics

- Verified trajectory yield per seed.
- Distribution coverage across target capabilities.
- Failure diagnosis precision.
- Aggregate release-review minutes recorded for explicit review resolutions.
  This is workflow-cost evidence only, not a measure of reviewer effectiveness
  or downstream model gain.
- Downstream model improvement on held-out Agent tasks. The
  [downstream evidence design](design-docs/representative-scale-and-downstream-evidence.md)
  can record a
  hash-bound baseline/treatment metric comparison supplied by an external
  system. An `improved` result means only that the declared treatment beats the
  declared baseline on the protocol's primary metric; it does not prove
  causality, general model quality, or dataset releaseability.

## Non-Goals

- Do not optimize for flat instruction-response generation as the primary product.
- Do not build a distributed cluster framework before local contracts are stable.
- Do not build or operate local LLM clusters; call remote OpenAI-compatible LLM APIs instead.
- Do not rely on prompt-only correctness when executable validation is possible.
