# Architecture

The framework should be developed as a pipeline for executable Agent training data, not as a flat prompt-response generator.
Canonical terminology is defined in [CONTEXT.md](CONTEXT.md); this file owns
only the top-level system and package map.

## Top-Level Domains

1. **Seed and Domain Intake**
   Normalizes source materials, target domains, task taxonomies, and generation goals.

2. **Environment Synthesis**
   Builds executable stateful environments from validated source bundles and domain requirements. Early versions should use SQLite-backed Python environments; later versions can expose environments through MCP-compatible tool servers.

3. **Tool Synthesis and Registry**
   Defines typed tools, schemas, dependency graphs, execution contracts, and versioned tool metadata.

4. **Task and Curriculum Generation**
   Generates tasks from simple to complex, with explicit difficulty dimensions such as tool count, constraints, ambiguity, state changes, and recovery paths.
   The shared remote-generation kernel consumes domain-owned task semantics and
   batch policy as validated data: final-answer evidence ownership,
   expected-state tool ownership, and deterministic per-batch candidate identity
   remain explicit without adding domain-name branches to the kernel.
   Grounding and diversity semantics are likewise domain-owned declarations on
   the generation specification: observation-sourced final answers must be
   grounded in declared observation values, state-tool-derived answers replace a
   fixed provider sentinel with a deterministic value derived from validated
   expected state, declared expected-state references must exactly match
   grounding observations, and per-batch task-type focus rotation, sliding
   grounding windows, and bounded prior-instruction exclusion lists diversify
   repeated batches without persisting instruction text.

5. **Trajectory Execution**
   Runs solution policies or generator agents against environments and records thought/action/observation/final-response traces.

6. **Verification and Quality Gates**
   Separates generation from validation using deterministic contracts,
   pre-execution semantic mutation admission for state-changing candidates,
   executable verification, logical consistency checks, diversity checks, and
   human review queues for uncertain cases.
   A versioned Domain Pack is the semantic authority and deep integration seam
   for domain planning, generation, isolated execution, replay, and typed domain
   assessment. The shared framework retains final cumulative release
   qualification and external-authority verification.

7. **Dataset Assembly and Lineage**
   Emits versioned training examples with environment, tool, task, trajectory, verifier, quality metrics, and provenance metadata.

8. **Source Governance**
   Validates source provenance, license policy, network policy, sandbox policy, and sanitized source-event auditing before external-like material can affect environments or dataset exports.

9. **Orchestration and Scaling**
   Provides opt-in local async orchestration with durable resumption, bounded concurrency, cooperative cancellation, and sanitized usage evidence. It may evolve toward distributed actor-based execution only when throughput demands justify it. Scaling orchestration does not imply deploying a local LLM cluster.

## Canonical Design Docs

- [docs/DESIGN.md](docs/DESIGN.md): architecture contracts and development invariants.
- [docs/BACKEND.md](docs/BACKEND.md): service and job boundaries.
- [docs/DATA.md](docs/DATA.md): data model, lineage, metrics, and output schema.
- [docs/SECURITY.md](docs/SECURITY.md): sandboxing, secrets, external access, and data handling.
- [docs/design-docs/agent-data-synthesis-framework.md](docs/design-docs/agent-data-synthesis-framework.md): detailed technical design.
- [docs/design-docs/algorithm-flow-and-architecture.md](docs/design-docs/algorithm-flow-and-architecture.md): explanatory walkthrough of the current algorithm flow and architecture layers.
- [docs/design-docs/architecture-explainers.md](docs/design-docs/architecture-explainers.md): detailed explanations of architecture and algorithm concepts.
- [docs/design-docs/domain-aware-representative-generation.md](docs/design-docs/domain-aware-representative-generation.md): domain-owned remote generation and representative eligibility boundary.
- [docs/design-docs/outcome-validated-domain-pack.md](docs/design-docs/outcome-validated-domain-pack.md): target Domain Pack interface, identity/version binding, compatibility, cumulative qualification, and Workspace tracer design.
- [docs/adr/README.md](docs/adr/README.md): accepted system-wide architecture decisions.

## Architectural Position

The target architecture combines four ideas from the source analysis:

- DeepSeek-style autonomous environment-tool-task-verifier co-generation.
- AgentInstruct-style multi-agent refinement and quality specialization.
- Matrix-style message-driven orchestration when scaling beyond a single process.
- Agent World Model-style executable environments with standard tool interfaces.

LLM-dependent generation, refinement, trajectory policy execution, and optional judge checks must call a remote OpenAI-compatible LLM API. The repository owns the synthesis pipeline and provider adapter boundary; it does not own local LLM cluster deployment.
