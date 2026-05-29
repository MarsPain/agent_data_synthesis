# Technical Debt

Known debt should be recorded here with impact, owner if known, and target resolution stage.

## Resolved Items

### TD-0001: Generated code sandboxing is resolved by plan 0015
- **Impact:** High. Tool expansion (plan 0008) allows structured tool proposals,
  but any generated or dynamically loaded executable code runs without filesystem
  or process isolation. This is a safety gap before external MCP server
  integration or user-provided tools can be safely admitted.
- **Target resolution stage:** Before distributed workers or external tool servers.
- **Prerequisite:** None. The existing pipeline is stable (118 tests passing).
- **Trigger for activation:** When a plan is drafted to enable `environment_generation`
  or `verifier_generation` roles, or to connect to external MCP servers.
- **Resolution:** Completed plan
  [0015-generated-code-sandboxing-and-executable-admission-controls](../completed/0015-generated-code-sandboxing-and-executable-admission-controls.md)
  added generated executable records, static scanning, admission decisions,
  restricted local fixture execution, sanitized sandbox audits, and reporting
  slices. Future stronger isolation can supersede the local helper when external
  execution surfaces are enabled.

## Current Items

### TD-0002: Semantic duplicate detection is not yet implemented
- **Impact:** Medium. Current `quality_duplicate` gate only catches exact task
  instruction + tool-sequence matches. Semantic equivalence (paraphrased intent,
  reordering of commutative actions) inflates dataset size and skews curriculum
  metrics without being detected.
- **Target resolution stage:** Before large-scale dataset generation or curriculum
  effectiveness benchmarking.
- **Prerequisite:** May benefit from an embedding provider or lightweight local
  model; needs cost/benefit analysis before implementation.
- **Trigger for activation:** When dataset volume exceeds manual review capacity,
  or when curriculum effectiveness metrics show suspiciously high success rates
  due to near-duplicate tasks.
