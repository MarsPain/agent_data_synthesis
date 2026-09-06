# 02 — Run Provider-Neutral Multi-Turn Agent Episodes

**What to build:** Generate and compile tasks, then run bounded multi-turn Agent
interaction through the JSON model interface, including recovery, serial
provider-budget accounting, and deterministic replay.

**Blocked by:** [01 — Prove the Agent-first core seam with a test Domain](01-prove-agent-first-core-seam.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [ ] Production OpenAI-compatible and deterministic fake adapters satisfy the same JSON interface and sanitized role-lineage contract using mock transport.
- [ ] Generation uses bounded batches and persisted slot identities; the Domain compiles proposals and persists Task cases before Agent execution rather than trusting provider identity, expected state, or authorization.
- [ ] Allocated slots count toward the task-attempt ceiling even when generation, compilation, or duplicate admission fails. Batches fit the remaining slot budget; retries reuse slots while consuming physical-request budget.
- [ ] Each Agent decision is exactly one tool call or final response; extra keys, reasoning, and unsupported types are rejected.
- [ ] Agent context contains only the public task, tool schemas, observable history, and remaining step budget. Oracle fields cannot enter model requests.
- [ ] Unknown tools, invalid arguments, and ordinary tool failures become bounded observations; unauthorized mutation terminates before changing state.
- [ ] One malformed-decision repair per Episode, two transport retries per logical request, timeouts, response/token bounds, and step/attempt ceilings are enforced without unbounded generator or judge repair loops.
- [ ] The serial path reserves every physical request in SQLite before dispatch and respects total/per-role ceilings, including repair and retry requests; unknown outcomes retain their charge and unknown token usage.
- [ ] Replay reconstructs the frozen initial fixture state and saved Task case, executes recorded tool calls, and reports observation or assessment drift without a provider call.
- [ ] End-to-end tests cover success, recovery, malformed output, timeout, response bounds, unknown tool, invalid arguments, unauthorized mutation, request exhaustion, and replay.
- [ ] Credentials and unrestricted request/response payloads are absent from Episodes, public reports, errors, and logs.

## Scope guard

Do not port production Domains, add concurrent scheduling or resume commands,
implement a quality judge, or enable native provider tool calling. Serial
request accounting is required before the early live pilot; it is not deferred
to the later scheduler ticket. No paid calls are authorized by this ticket.
