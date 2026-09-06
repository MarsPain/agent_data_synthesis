# 02 — Run Provider-Neutral Multi-Turn Agent Episodes

**What to build:** Let a synthesis operator generate Candidate tasks and run
multi-turn Agent tool interaction through one provider-neutral JSON model
interface, including bounded recovery and replay, without exposing private
oracle data to the Agent.

**Blocked by:** [01 — Prove the Agent-first core seam with a test Domain](01-prove-agent-first-core-seam.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [ ] The production OpenAI-compatible adapter and deterministic fake adapter satisfy the same JSON model interface and return sanitized role lineage.
- [ ] Task proposals are generated in bounded batches and compiled by the Domain rather than trusted for Candidate identity, expected outcome, or authorization.
- [ ] Every Agent turn accepts exactly one tool-call decision or final-response decision and rejects extra keys, hidden reasoning, or unsupported decision types.
- [ ] Agent context contains only the public Task view, tool schemas, prior observable events, and remaining step budget.
- [ ] Unknown tools, invalid arguments, and ordinary tool failures become bounded observations that the Agent may recover from within the configured step limit.
- [ ] An unauthorized state-changing action terminates before the tool mutates Domain state and produces a classified negative Episode.
- [ ] One malformed model decision may receive exactly one repair request; exhausted repair, step, transport, or provider limits produce bounded negatives.
- [ ] Replay starts a fresh Domain Episode, re-executes recorded tool calls through the same interface, and reports observation or final-assessment drift.
- [ ] Provider credentials and unrestricted request or response content are absent from Episodes, manifests, errors, and logs.
- [ ] End-to-end tests exercise direct success, recovery, malformed output, timeout, unknown tool, unauthorized mutation, and replay using mock transport rather than paid calls.

## Scope guard

Do not migrate Contacts, Mobile Messages, or Workspace Tasks, implement durable
multi-candidate scheduling, add a quality judge, or enable native provider tool
calling. This ticket completes the generic Agent loop only.
