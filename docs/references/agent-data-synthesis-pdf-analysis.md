# Agent-数据合成.pdf Analysis

Source: `Agent-数据合成.pdf`, 20 pages, read on 2026-05-15.

## Executive Summary

The PDF argues that Agent training data is structurally different from ordinary pretraining data. Ordinary text data can often be represented as static single-turn sequences; Agent data must represent dynamic multi-turn trajectories: environment state, tools, user intent, dialogue history, reasoning, tool actions, observations, final response, and verification. Because real Agent trajectories are rarely public and rarely include internal tool calls or state transitions, scalable synthesis is necessary.

The strongest design direction is a fused architecture:

- DeepSeek-style autonomous environment synthesis for task-environment-tool-verifier consistency.
- AgentInstruct-style multi-agent collaboration for content transformation, instruction generation, and refinement.
- Matrix-style distributed orchestration for large-scale throughput.
- Agent World Model-style executable environments and MCP-like standard tool interfaces for transferability.

## Core Problem Definition

Agent data teaches procedural knowledge: how to perceive state, choose tools, recover from errors, and complete tasks. It must cover three coupled dimensions:

- **Dialogue reasoning:** intent tracking, ambiguity handling, slot filling, clarification, and user changes.
- **Tool use:** schema understanding, tool choice, parameter construction, result parsing, error handling, and multi-tool composition.
- **Task planning:** goal decomposition, dependency management, resource constraints, execution monitoring, and dynamic replanning.

The PDF frames the central trade-off as scale, quality, and diversity:

- Scale is required for broad behavior coverage.
- Quality is required because wrong tool calls or invalid reasoning poison training.
- Diversity is required to avoid overfitting to narrow workflows.

## DeepSeek-V3.2 Pattern: Autonomous Environment Synthesis

The DeepSeek-style pattern treats data generation itself as an Agent task. A synthesis Agent builds the environment, writes tools, generates tasks, executes solutions, verifies outputs, and uses failures to expand capability.

### Nine-Step Loop

1. Prepare domain input and initial config.
2. Build a structured environment such as a domain database.
3. Synthesize Python tools over the environment.
4. Generate task description, solution function, and verification function.
5. Execute the solution function.
6. Execute the verification function.
7. Save validated samples.
8. Increase task difficulty or repair failures.
9. Expand the toolset when errors reveal missing capability.

### Design Lessons

- The environment, tools, tasks, and verifiers must be co-designed.
- Tools should be typed, documented, and single-purpose.
- Difficulty should increase by adding constraints, tool calls, ambiguity, state dependence, and global consistency requirements.
- Solution logic and verification logic must be separate.
- Failure handling needs root-cause classes: generator error, verifier error, tool gap, environment gap, and infrastructure failure.

## AgentInstruct Pattern: Multi-Agent Refinement

AgentInstruct uses a three-stage pipeline:

1. Content transformation converts raw materials into normalized intermediate representations.
2. Seed instruction generation expands those representations across task taxonomies and skills.
3. Instruction refinement uses specialized agents such as suggester and editor roles to increase quality and complexity.

The important architectural contribution is role specialization. A single generic generator is weaker than a pipeline of agents with explicit responsibilities, quality gates, and feedback paths.

## Matrix Pattern: Distributed Orchestration

Matrix replaces a central coordinator with message-driven peer-to-peer execution. Each task is an orchestrator instance carrying its own state. Stateless or mostly stateless worker agents consume work, process it, and forward the state to the next role.

Key lessons:

- Keep task state in durable messages or object storage.
- Use row-level scheduling to avoid slow tasks blocking fast ones.
- Use actor-style workers only after local contracts are stable.
- Monitor queue depth, token throughput, GPU utilization, failure classes, and cost per accepted sample.

## Agent World Model Pattern: Executable Environments

A world-model-driven environment generator converts natural-language domain descriptions into executable environments: database schemas, initial data, APIs, business rules, and standard tool interfaces.

Key lessons:

- Environments must be stateful and resettable.
- Database constraints and business logic should encode physical or semantic rules.
- A task should be feasible in the generated environment.
- Standard interfaces such as MCP improve portability across synthetic and real tools.

## Quality System

The PDF identifies three quality layers:

- **Execution verification:** run code, tools, or APIs and compare results with objective checks.
- **Logical verification:** check consistency across dialogue history, tool choice, parameter use, observations, and final answer.
- **Human review:** focus reviewers on uncertain, high-risk, or novel cases rather than all samples.

Quality metrics should include executable rate, success rate, instruction clarity, response relevance, distribution coverage, long-tail capture, curriculum effectiveness, transfer gain, and cost.

## Recommended Architecture for This Repository

This project should start with a local executable foundation:

- SQLite environments instead of remote services.
- Python callable tools instead of full MCP servers.
- JSON schemas and manifests before distributed storage.
- Executable verifiers before LLM judge layers.
- Local async orchestration before Ray/SLURM-scale deployment.

After these contracts are stable, the project can add:

- MCP-compatible tool/environment adapters.
- Multi-agent generator and critic roles.
- Dynamic tool expansion.
- Distributed message-driven execution.
- Monitoring and cost dashboards.
