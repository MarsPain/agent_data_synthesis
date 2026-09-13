# 03 — Add Contacts and Establish Early Agent Feasibility

**What to build:** Produce verified Contacts Agent Episodes through the new
seam and test the public-task/oracle contract in a small, separately authorized
real-provider pilot before broadening production adapters.

**Blocked by:** [02 — Run provider-neutral multi-turn Agent Episodes](02-run-provider-neutral-agent-episodes.md)

**Status:** in-progress

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
- [ ] After separate explicit authorization, the pilot yields inspectable real-Agent examples of direct lookup, authorized mutation, and successful recovery, with task/oracle alignment, failures, and usage reviewed.
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
- No live provider call has been requested, authorized, or made. The real-Agent
  pilot criterion remains pending separate explicit authorization. No failed
  rehearsal or offline outcome authorizes a paid rerun or weaker gate.
- No adapter seam revision was required by this slice. The architecture guard
  now permits only this Contacts module as a production Domain while preserving
  the ban on legacy and cross-Domain dependencies.

## Scope guard

Do not import Contacts qualification, compatibility, proofs, canaries, or
provider-evidence freezing machinery. This pilot does not calibrate a judge or
establish dataset acceptance. Build and verify the offline path before any
authorization request; absent authorization leaves live criteria pending. A
failed pilot does not authorize a paid rerun or a weakened acceptance gate.
