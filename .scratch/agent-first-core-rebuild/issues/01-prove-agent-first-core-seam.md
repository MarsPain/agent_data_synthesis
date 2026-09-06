# 01 — Prove the Agent-First Core Seam With a Test Domain

**What to build:** Run a complete isolated synthesis trace through the new
library interface with deterministic Domain/model adapters, establishing a
provisional seam and inspectable public artifacts over a private ledger.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [ ] Two focused superseding ADRs record the Domain seam and bounded public-intent compilation with deterministic pre-mutation authorization, shadow review, and separately gated optional enforcement.
- [ ] The new engine accepts validated configuration and registered Domain/model adapters without importing legacy packages or changing the legacy entrypoint.
- [ ] A test Domain supplies deterministic slots, compiles public/private Task cases, opens isolated state, executes tools, and assesses a complete observable Episode.
- [ ] Compilation rejects a hidden exact-note requirement unsupported by the public task; a public request with multiple acceptable outcomes passes through a Domain-owned allowed-result set or predicate.
- [ ] A successful Episode enters demonstrations and a deterministic rejection enters negatives; admission mode is explicit and neither is claimed human-approved.
- [ ] The private ledger retains initial fixture state and compiled Task cases before execution; exported Episodes exclude oracle fields, secrets, unrestricted provider material, absolute source paths, and hidden reasoning.
- [ ] A manifest binds normalized sanitized configuration and final artifact files without nested evidence graphs or object-level hash chains.
- [ ] Persistence models are owned and validated by their modules; no central contracts module or unrestricted domain-data bus is introduced.
- [ ] Architecture tests reject core imports of legacy packages, production Domain implementations, or a release lab.
- [ ] The core-focused test command completes within five seconds. The seam remains provisional until the first two production Domains and locality exercise validate it.

## Scope guard

Do not add a production provider, production Domain, concurrency/resume,
enforcement, or release-lab skeleton. Do not treat the toy Domain as proof that
production task semantics or extensibility are already solved.
