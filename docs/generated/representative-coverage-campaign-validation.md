# Representative Coverage Campaign Validation

Generated on 2026-07-31 for
[coverage campaign ticket 06](../../.scratch/coverage-driven-representative-synthesis/issues/06-representative-coverage-campaign.md).

## Decision

**`revise-catalog`**

The deterministic three-domain pilot improved structural coverage and
concentration relative to the prior representative baseline, but the
thirty-target plans contain the same distinct structural cells as the
twelve-target plans. Increasing the target would therefore add repetitions
within existing cells rather than new structural coverage. The ticket's
growth rule prevents a success conclusion, so no paid provider authorization
was requested and no paid campaign was run.

This is diagnostic evidence only. It does not promote a profile, admit a
dataset release, or establish downstream training value.

## Preflight

- The representative v1 pilot profiles compile twelve accepted targets per
  domain with a twenty-four-attempt ceiling.
- Versioned v2 catalogs and fixtures make thirty accepted targets statically
  reachable with a sixty-attempt ceiling without raising the grounding-reuse
  limit above two.
- A serial deterministic fake provider fulfilled all three twelve-target
  pilots: 36 accepted, zero rejected, 36 attempts, and a combined ceiling of
  72.
- A deterministic thirty-target probe then fulfilled 90 accepted samples with
  zero rejections and 90 of 180 allowed attempts. It confirmed that accepted
  counts grow while distinct structural-cell counts do not.
- The campaign CLI previews LLM-backed coverage plans without `--use-llm`,
  provider configuration, credentials, or network calls.
- Focused coverage, assignment, and CLI tests pass. The repository-wide test
  and documentation checks are recorded in the implementation commit.

## Baseline Comparison

The prior baseline is `artifacts/representative-campaign-30-v5`. The pilot is
the deterministic diagnostic output under
`artifacts/coverage-campaign-fake-pilot`. Runtime paths are not persisted in
dataset artifacts.

| Domain | Baseline accepted/rejected | Pilot accepted/rejected | Structural families | Largest family share | Distinct grounding | Max grounding reuse | Executable rate | Verification rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Contacts | 27 / 3 | 12 / 0 | 2 → 3 | 0.556 → 0.417 | 6 → 6 | 6 → 2 | 1.000 → 1.000 | 0.900 → 1.000 |
| Mobile messages | 28 / 2 | 12 / 0 | 3 → 5 | 0.357 → 0.250 | 3 → 7 | 10 → 2 | 0.933 → 1.000 | 1.000 → 1.000 |
| Workspace tasks | 30 / 0 | 12 / 0 | 3 → 5 | 0.333 → 0.250 | 3 → 7 | 10 → 2 | 1.000 → 1.000 | 1.000 → 1.000 |

The baseline rejection causes were three exact duplicates for contacts, two
tool runtime errors for mobile messages, and none for workspace tasks. The
fake-provider pilot had no rejection causes. Its difficulty distributions
were:

- contacts: 5 basic, 5 intermediate, 2 recovery;
- mobile messages: 3 basic, 1 constrained, 6 intermediate, 2 recovery; and
- workspace tasks: 3 basic, 1 constrained, 6 intermediate, 2 recovery.

The fake provider consumed zero remote tokens and zero provider cost. The
baseline recorded 102,260 contacts tokens, 116,464 mobile-message tokens, and
105,816 workspace-task tokens; its provider cost fields were empty.

## Thirty-Target Gate

The thirty-target plans compile and retain bounded sixty-attempt ceilings, but
their projected distinct structural-cell counts remain:

- contacts: 3 at target 12 and 3 at target 30;
- mobile messages: 5 at target 12 and 5 at target 30; and
- workspace tasks: 5 at target 12 and 5 at target 30.

The initial static inability to compile target 30 was classified as a
`catalog-capacity` deficit and corrected by versioned, executable fixture
capacity. The remaining failure is also catalog-side: the current structural
taxonomy saturates before target 12. There were no provider-contract,
execution, verification, safety, duplicate, or attempt-exhaustion failures in
the fake pilot.

The next campaign should add independently executable and verifiable cells
that represent new ambiguity, cross-step constraints, and recovery behavior.
It must not manufacture growth through instruction paraphrases or higher
grounding reuse.
