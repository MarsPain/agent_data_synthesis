# Roadmap

## Stage 0: Context and Architecture

- Establish root entrypoints and canonical docs.
- Define framework contracts from the source PDF.
- Add documentation validation.

## Stage 1: Local Executable Prototype

- Implement seed intake and domain config.
- Add remote OpenAI-compatible LLM provider configuration with `AGENT_DATA_LLM_BASE_URL`, `AGENT_DATA_API_KEY`, and `AGENT_DATA_LLM_MODEL`.
- Build SQLite-backed environment generation.
- Define Python tool registry and schema contracts.
- Generate simple tasks through the remote LLM provider with executable verifiers.
- Export accepted samples as JSONL with manifests.
- Record provenance and config hashes needed for later impact analysis.

## Stage 2: Quality and Curriculum

- Add difficulty scoring and curriculum policies.
- Add logical validators and diversity metrics.
- Add failure classification and retry loops.
- Add human review queue format for uncertain samples.
- Add metric slicing by domain, difficulty, tool combination, generator role, and verifier type.
- Add parent-version comparison reports for quality, coverage, cost, and held-out task performance.

## Stage 3: Agentic Generation Loop

- Separate task generation from solution-policy execution and preserve policy
  lineage.
- Add multi-step, stateful trajectories before broader branching behavior.
- Add a bounded critic/refinement loop that diagnoses failed trajectories, reruns
  one repaired attempt, and reports refined outcomes separately. Completed in
  plan 0006.
- Add generator roles for environment, tool, task, solution, verifier, and critic.
- Add tool expansion when failures indicate missing capability.
- Add multi-path trajectory generation and branching behavior-tree tasks.
- Add AgentInstruct-style seed transformation, taxonomy-driven task expansion, and suggester/editor refinement.
- Add controlled network-backed environment synthesis only after provenance, licensing, and sandbox rules are enforced.

## Stage 4: Interoperability and Scale

- Add MCP-compatible environment/tool adapters.
- Add async orchestration with durable queues.
- Evaluate Ray-style distributed workers if throughput requires it.
- Add monitoring dashboards and cost controls.
- Add row-level scheduling, message offloading, and per-role resource metrics if distributed orchestration is adopted.
- Keep LLM inference behind remote provider APIs; do not add local LLM cluster deployment as a roadmap item.
