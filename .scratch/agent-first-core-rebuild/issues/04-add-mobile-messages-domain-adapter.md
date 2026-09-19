# 04 — Add Mobile Messages and Validate the Second-Domain Seam

**What to build:** Produce verified Mobile Messages Episodes and use this
second production Domain to validate and stabilize the interface through a
concrete task/verifier change-locality exercise.

**Blocked by:** [03 — Add Contacts and establish early Agent feasibility](03-add-contacts-domain-adapter.md)

**Status:** completed

**Assignee:** Codex

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [x] The adapter freezes admitted fixture/local inputs without shared-core knowledge of message, reminder, or draft schemas.
- [x] Deterministic slots cover message search, reminder creation, draft reply, and search recovery, with bounded capacity/exhaustion reporting.
- [x] Public task semantics support selected messages, authorized reminder/draft arguments, and conditions; compilation rejects missing authority, wrong bindings, negation, and unsupported private exact targets.
- [x] Open reply content uses a Domain predicate or allowed-result set; explicit exact content retains exact verification without leaking oracle fields.
- [x] Isolated execution and replay cover search, authorized mutations, recoverable failure, and rejection before unauthorized mutation; final assessment checks grounded response and intended state only.
- [x] Semantic keys preserve material request differences; reviewed structural examples establish the twelve-family baseline and show that paraphrases, entity swaps, and padded tool sequences do not create families.
- [x] The shared compliance suite and provider-mock end-to-end tests pass without Mobile-specific branches in core modules.
- [x] A bounded exercise adds one task type and changes one verifier rule inside a production Domain. Its diff stays in that Domain and its fixtures/docs/tests, with no core edits, generic configuration escape hatch, or copied core workflow.
- [x] Any interface corrections discovered by the second Domain are resolved for both adapters before the locality exercise is repeated and the seam is treated as stable.
- [x] The ticket records changed modules, public-contract count, dependency direction, and test timings; it does not equate fewer lines or passing import rules alone with simpler design.

## Implementation notes

- `agent_synthesis.mobile_messages` owns Mobile Messages source admission and
  normalization, deterministic slots, public/private compilation, candidate-local
  tools, mutation authorization, replay restoration, deterministic assessment,
  semantic identity, and reviewed structural examples. The shared core has no
  message, reminder, or draft schema branch.
- The fixture exposes 24 safe slots (two messages × twelve meaningful task
  structures): direct/directory/recovery search; direct/directory/recovery/
  verified reminders; and direct/directory/recovery/exact/verified drafts.
  Existing reminders or drafts remove only their unsafe mutation slots while
  preserving search capacity, and `slot_capacity()` reports known exhaustion.
- Reminder text/time are explicit public requester arguments. Open replies use
  a bounded courteous-reply predicate; any allowed exact public reply is retained
  in the public task and checked exactly. The selected internal message id is
  obtainable only from a search observation: generator-visible slot ids and
  state-change evidence are opaque, and private case bytes remain in the ledger.
- Source admission excludes targets with ambiguous public search selectors, and
  slot capacity excludes an exact-reply topology when its deterministic default
  would not satisfy the public reply predicate. Slot components are bounded,
  deterministic hashes, including for collision-prone or long source ids.
- The locality semantic change increments the adapter version to
  `mobile_messages_agent_adapter_v2`; replay rejects saved v1 runs. Restored
  private cases must also match a declared action/route/reply-constraint task
  shape before replay can begin.
- The second-Domain exercise found no interface correction: both Contacts and
  Mobile Messages use the unchanged `DomainAdapter`/`DomainRun` seam, shared
  compliance assertions, provider-neutral model interface, and replay engine.
  There are no Contacts imports in the Mobile adapter, no Mobile imports in
  Contacts, and no legacy imports.

### Change-locality record

- Baseline commit `512d383` added the eleven-family adapter and architecture
  registration. Commit `50fd590` adds the production
  `draft-verified` task type, `get_draft_reply` public tool, and the verifier
  rule requiring an observed saved draft. It is limited to this Domain module,
  its fixture-backed test suite, and this ticket; it needs no core edit,
  generic configuration option, or copied workflow.
- Public-contract count: the adapter has six Mobile tool contracts —
  `search_messages`, `list_message_senders`, `create_reminder`,
  `get_reminder`, `create_draft_reply`, and `get_draft_reply`. The locality
  delta is one public tool (`get_draft_reply`) and zero shared-core contracts.
- Dependency direction is inward only: `agent_synthesis.mobile_messages` imports
  generic `configuration`, `domain`, and `episode` contracts; the shared core
  imports neither production Domain. Architecture tests enforce this direction.
- Changed modules: `agent_synthesis/mobile_messages.py`,
  `tests/test_mobile_messages_agent_adapter.py`, and the test-only production
  registration in `tests/test_agent_first_core_architecture.py`; the tracker and
  this ticket record the result. No shared runtime module changed.
- Timings: final affected suites ran 44 tests in 0.240s (18 Mobile, 14
  architecture, and 12 Contacts). The final full suite completed cleanly after
  review fixes; its captured process reached the 31s wait boundary and then
  exited successfully.
- Simplicity is evidenced by this change-locality result and the absence of
  cross-Domain/core behavior changes, not by line count or import checks alone.

### Final validation

- `uv run python -m unittest` completed successfully after the final review
  fixes.
- Two-axis review found no remaining standards or spec issue after rechecks.
- Documentation validation passed after this tracker update.

## Scope guard

Do not port Mobile compatibility corpora, release evidence, legacy profiles, or
Domain Pack projections. Do not add task types solely to inflate structural
counts or create a generic Domain framework to satisfy the locality exercise.
No additional paid campaign is required by this ticket.
