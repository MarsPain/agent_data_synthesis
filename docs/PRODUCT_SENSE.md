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
- Human review minutes per accepted sample.
- Downstream model improvement on held-out Agent tasks.

## Non-Goals

- Do not optimize for flat instruction-response generation as the primary product.
- Do not build a distributed cluster framework before local contracts are stable.
- Do not build or operate local LLM clusters; call remote OpenAI-compatible LLM APIs instead.
- Do not rely on prompt-only correctness when executable validation is possible.
