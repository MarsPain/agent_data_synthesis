# Domain Glossary

This file defines current terminology. See [ARCHITECTURE.md](ARCHITECTURE.md)
for the package map and [docs/DESIGN.md](docs/DESIGN.md) for contracts.

- **Agent-first Domain adapter:** A registered Domain implementation that owns
  source normalization, deterministic slots, public and private Task compilation,
  isolated Episode state, tools, mutation authorization, and assessment.
- **Domain run:** A run-scoped adapter instance that exposes bounded slots and
  freezes its normalized initial state for resume and replay.
- **Task slot:** A deterministic, stable generation position with a public
  proposal prompt. An allocated slot may produce a demonstration or negative.
- **Task case:** A Domain-compiled public task and private oracle, bound to a
  semantic key. The oracle stays in private operational storage.
- **Agent Episode:** One bounded sequence of model decisions, tool actions,
  observations, state changes, and a final response against isolated state.
- **Demonstration:** An Episode that passes deterministic admission. This does
  not imply semantic or human approval.
- **Negative:** An attempt rejected by compilation, execution, or deterministic
  admission, retained for inspection.
- **Frozen input:** The persisted normalized Domain state and allocated slots
  used for exact resume and replay, independent of later source-file edits.
- **Private ledger:** SQLite storage for allocated slots, work ownership,
  provider requests, terminal outcomes, and private task cases.
- **Physical request budget:** A durable upper bound on model requests, split
  into task generation, Agent, and optional judge roles, including retries.
- **Blind review cohort:** A frozen set of Episode IDs whose reviewer queue
  exposes only the public task and observable trajectory.
- **Shadow quality judgment:** A post-execution diagnostic assessment that
  cannot change deterministic admission or confer human approval.
- **Human review label:** A direct-human, cohort-bound five-dimension verdict.
  Only human-pass Episodes may be called human-approved.
- **Semantic enforcement eligibility:** Optional held-out evaluation of one
  frozen judge policy. It is separate from core cutover and default shadow mode.
- **Source scope:** The declared local source and task-distribution identity
  bound to a run and its model settings.
- **Legacy Domain Pack:** The removed pre-cutover abstraction; its historical
  design and artifacts are available in repository history only.
