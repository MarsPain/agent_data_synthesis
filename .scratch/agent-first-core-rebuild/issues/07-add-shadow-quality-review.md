# 07 — Add Shadow Quality Review

**What to build:** Let a synthesis operator inspect deterministic admission,
semantic diversity, and independent quality judgments for every completed
Episode while an uncalibrated judge remains unable to change demonstration
admission.

**Blocked by:** [02 — Run provider-neutral multi-turn Agent Episodes](02-run-provider-neutral-agent-episodes.md)

**Status:** ready-for-agent

**Assignee:** Unassigned

**Parent spec:** [Agent-First Core Rebuild](../../../docs/product-specs/agent-first-core-rebuild.md)

## Acceptance criteria

- [ ] Demonstration admission always requires passing tool-schema, isolation, mutation-authorization, deterministic assessment, final-grounding, unsafe-material, and semantic-key duplicate gates.
- [ ] Successful recovery Episodes remain eligible demonstrations; failed, unsafe, duplicate, exhausted, and deterministic-verification failures remain negatives.
- [ ] An independent judge consumes only the public Task, observable events, deterministic results, and bounded rubric.
- [ ] Each judgment reports pass, fail, or uncertain for instruction fidelity, action efficiency, observation grounding, final-response quality, and safety with bounded reasons and event references.
- [ ] Judge identity must differ from Agent identity, and missing or matching identity makes semantic evidence unavailable rather than silently trusted.
- [ ] Shadow judgments cannot alter the demonstrations or negatives collections regardless of verdict.
- [ ] The quality report exposes deterministic yield, semantic duplicate counts, structural-family distribution, largest-family share, judge outcomes, and model usage without constant placeholder scores.
- [ ] Review-queue selection includes every bounded calibration-campaign fail or uncertain judgment and fills remaining capacity by Domain, task type, difficulty, and structural key.
- [ ] Judgment and review artifacts exclude unrestricted model rationale, provider payloads, credentials, private oracle values, and local absolute paths.
- [ ] Tests prove a judge cannot override a deterministic failure and that changing a shadow verdict leaves Episode admission unchanged.

## Scope guard

Do not enable judge-based hard admission, import human labels, tune calibration
thresholds from real data, or run a paid quality campaign. This ticket produces
shadow evidence and a reviewable queue only.
