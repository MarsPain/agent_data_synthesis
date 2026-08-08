# 08 — Assemble the Offline Workspace Tracer Proof

**What to build:** Assemble one content-addressed Workspace tracer proof root and clean offline verifier that combines a replayable Workspace Release Candidate chain, fixture-only Publishable and Training Recommended conformance, the Contacts/Mobile compatibility prerequisite, and every mandatory fail-closed mutation case.

**Blocked by:** [03 — Freeze and preserve Contacts and Mobile compatibility](03-contacts-mobile-compatibility-corpus.md), [05 — Add cumulative qualification and Workspace Release Candidate](05-cumulative-qualification-release-candidate.md), [06 — Verify publishability evidence and external authority](06-publishability-evidence-authority.md), [07 — Verify the Workspace training recommendation protocol](07-workspace-training-recommendation.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Outcome-Validated Domain Pack](../../../docs/product-specs/outcome-validated-domain-pack.md)

## Acceptance criteria

- [ ] One root manifest binds every Domain Pack, plan, source, runtime, provider, assignment, sample, rejection, episode/replay, report, pack, assessment, qualification, compatibility, conformance, and proof-case artifact by schema, relative path, digest, and byte count.
- [ ] Clean verification starts only from the root and reconstructs all hashes, exact identities, dependency edges, effective state, and conformance statuses without mutable defaults or provider calls.
- [ ] The required summary is effective Release Candidate, false Publishable, false Training Recommended, passed Publishable conformance, and passed Training Recommended conformance.
- [ ] Contacts/Mobile compatibility is a required auxiliary result and neither domain runs a second tracer pipeline.
- [ ] Replay uses the production parser, membership checks, isolated execution, mutation admission, verifier, and assessment contracts and rejects any identity drift.
- [ ] Separate negative cases cover plan identity, provider contract, mutation safety, execution evidence, coverage/evaluation, run completeness, artifact integrity, publishability, fixture isolation, training arms, evaluation/leakage, meaningful gain, and cumulative dependency invalidation.
- [ ] Every negative case copies positive bytes, changes one declared fact, returns the exact bounded status/reason, and proves unrelated earlier artifacts are byte-identical.
- [ ] A missing/skipped case, generic exception, parser crash, silent default, post-hoc repair, or flattened passed field fails the root proof.
- [ ] Re-running the verifier over unchanged bytes produces byte-stable bounded decisions and a stable proof identity.
- [ ] Focused CLI and contract tests use this proof root as the highest acceptance seam and extend existing artifact verification styles.

## Scope guard

Do not perform the paid live provider acceptance in this ticket. Use deterministic
provider/replay evidence until Ticket 09 supplies the authorized sanitized real
responses.
