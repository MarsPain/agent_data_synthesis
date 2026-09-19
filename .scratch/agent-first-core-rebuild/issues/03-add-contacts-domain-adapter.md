# 03 — Add Contacts and Establish Early Agent Feasibility

**What to build:** Produce verified Contacts Agent Episodes through the new
seam and test the public-task/oracle contract in a small, separately authorized
real-provider pilot before broadening production adapters.

**Blocked by:** [02 — Run provider-neutral multi-turn Agent Episodes](02-run-provider-neutral-agent-episodes.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [x] The adapter admits fixture/local sources and freezes their bytes or normalized initial state privately with a content fingerprint before paid work; core modules do not learn the Contacts source schema.
- [x] Deterministic slots cover lookup, authorized follow-up, and lookup recovery, and disclose known unique-task capacity or slot exhaustion.
- [x] Compilation binds requested contact, action, note constraints, and conditions to public intent and obtainable evidence. Negation, wrong-contact binding, unsupported notes, and uncheckable conditions are rejected.
- [x] An unspecified note is assessed by an allowed-result predicate, not a hidden exact string; an explicitly requested exact note is checked exactly. Oracle fields remain private.
- [x] Candidate isolation, replay, authorization before mutation, final grounding, exact requested effects, and absence of unintended state changes pass the shared compliance suite.
- [x] Semantic keys collapse paraphrases without collapsing material request differences. Reviewed structural examples establish the seven-family baseline and reject family inflation from wording, entity changes, or redundant calls.
- [x] Provider-mock tests emit separated demonstrations/negatives and prove frozen-source replay after the original local file changes.
- [x] A pilot configuration and offline rehearsal are reviewable before seeking authorization; target eight demonstrations with at most sixteen task attempts and explicit model, physical-request, retry, and token bounds.
- [x] After separate explicit authorization, the pilot yields inspectable real-Agent examples of direct lookup, authorized mutation, and successful recovery, with task/oracle alignment, failures, and usage reviewed.
- [x] Pilot outputs are diagnostic, with semantic-task/grounding groups recorded for exclusion from final acceptance. Findings and any necessary seam revisions are recorded in this ticket.

## Implementation notes

- `agent_synthesis.contacts` is the first production adapter. It owns the
  Contacts source parser, source normalization, deterministic task-space,
  public/private compilation, isolated tool state, authorization, assessment,
  semantic identity, and structural taxonomy. Shared core modules remain
  unaware of Contacts fields and do not import legacy Contacts machinery.
- The finite fixture capacity is sixteen slots: direct/directory/recovery
  lookup plus five follow-up topologies per eligible contact. Contacts with an
  existing frozen follow-up retain safe lookup slots while their new-follow-up
  slots are exhausted. `slot_capacity()` exposes both the known capacity and
  whether a requested allocation reaches exhaustion.
- Open follow-up notes use a bounded public predicate; exact note text is
  included in the public instruction and checked exactly. Private task cases
  retain source facts only in the SQLite ledger. Collision-safe semantic keys
  are canonical hashes; seven reviewed structural families ignore paraphrase,
  entity substitution, and redundant read-only calls.
- `ContactsPilotConfiguration` and `rehearse_contacts_pilot()` produce a
  sanitized, provider-free review record. It fixes the eight-demo / sixteen-
  attempt pilot shape, including an executable sixteen-slot ceiling
  configuration, request/retry/token bounds, source fingerprint, and
  hashed semantic-task and grounding exclusion groups. The record is
  diagnostic-only and states `authorization_required`.
- Generic accepted-target replacement, fail-fast capacity admission, and
  stopping once eight demonstrations are accepted remain the bounded
  scheduler/resume work of Ticket 06. This ticket freezes and exposes the
  Contacts pilot ceiling without claiming that the current serial engine can
  perform that later orchestration.
- One separately authorized diagnostic pilot ran on 2026-09-13 as
  `ticket-03-user-authorization-20260913`, using `api.deepseek.com` and
  `deepseek-v4-flash`. It was bounded to eight task attempts, 41 physical
  requests, zero automatic retries, 1,024 output tokens per request, and a
  30-second timeout. Its one task-generation request ended as
  `provider_response_malformed` (sanitized response hash
  `sha256:4a10b63ad371e2b261f339c55dc3efbcdaf143ffd09bba5b761466ada7790a43`),
  so all eight attempts are retained as pre-execution negatives. No Agent
  request, tool call, or mutation occurred; offline replay records all eight
  as `not_executed` and aligned. The diagnostic report under
  `artifacts/agent-first-contacts-pilot/` records the frozen-source exclusion
  groups, failure summary, and sanitized usage (one task-generation request).
- The live result establishes no Agent feasibility conclusion: it exposes an
  unproven provider JSON-envelope compatibility boundary before task or Agent
  behavior can be assessed. No core or Contacts adapter seam revision follows
  from the intentionally non-retained malformed payload. Any later protocol
  investigation or new pilot requires fresh explicit authorization; this
  failed pilot does not authorize a rerun or weaken the unchecked live gate.
- A separate no-Contacts JSON-envelope probe ran on 2026-09-13 against the
  same provider/model with one request, zero retries, a 30-second timeout, and
  a 1,024-output-token cap. It passed the strict generation envelope and
  returned only sanitized evidence: response hash
  `sha256:bbdc7dfce9a8a8fd1ba53644f7c2a30750834354ce1e01f680c4225461132e24`
  and usage of 186 input / 140 output / 326 total tokens. This rules out a
  current system-wide envelope incompatibility but does not establish the
  eight-slot Contacts path. The external safety gate rejected the requested
  replacement pilot as a second Contacts-data export without a newly explicit
  authorization, so no replacement Contact context or Agent work was sent.
- The OpenAI-compatible adapter now exposes a fixed, non-payload
  `diagnostic_code` for malformed response stages while preserving the public
  `provider_response_malformed` outcome and raw-response exclusion. A focused
  mock-transport regression covers a missing message-content envelope.
- The first replacement pilot exhausted its configured 1,024 output-token cap while
  its one-slot no-Contacts probe did not. Current official DeepSeek
  documentation says `deepseek-v4-flash` defaults to thinking mode and supports
  an explicit non-thinking request field. A newly authorized pilot therefore
  sent `thinking: {"type": "disabled"}` with a 4,096 output-token cap while
  preserving eight tasks, 41 physical requests, zero automatic retries, and
  the 30-second timeout. It made 29 physical requests (one task-generation and
  28 Agent requests): seven Episodes passed deterministic task/assessment
  alignment, including direct lookup, authorized mutation, and successful
  recovery; all eight replayed aligned. The sole recovery-follow-up negative
  recorded the requested state change but failed final-response grounding by
  omitting the recorded note; it remains retained with
  `final_response_not_grounded`.
- The initial pilot runner treated the eight-demonstration target as a hard
  feasibility gate and labeled that seven-pass result insufficient. The
  specification instead requires a target of eight but at least one successful
  inspectable Episode of each required behavior. The runner now reports target
  attainment separately from minimum behavior evidence, with an offline
  regression covering this one-target-shortfall case. The real pilot therefore
  establishes Ticket 03 early feasibility while remaining diagnostic-only and
  excluded from final dataset acceptance.
- The architecture guard permits only this Contacts module as a production
  Domain while preserving the ban on legacy and cross-Domain dependencies.

## Scope guard

Do not import Contacts qualification, compatibility, proofs, canaries, or
provider-evidence freezing machinery. This pilot does not calibrate a judge or
establish dataset acceptance. Build and verify the offline path before any
authorization request; absent authorization leaves live criteria pending. A
failed pilot does not authorize a paid rerun or a weakened acceptance gate.
