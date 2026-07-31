# Representative Coverage Campaign Preflight

Generated on 2026-07-31 for
[coverage campaign ticket 06](../../.scratch/coverage-driven-representative-synthesis/issues/06-representative-coverage-campaign.md).

## Preflight Gate

**`revise-catalog`**

The deterministic fake-provider probe is not the ticket's required provider
pilot. It found that the thirty-target plans contain the same distinct
structural cells as the twelve-target plans. Increasing the target would
therefore add repetitions within existing cells rather than new structural
coverage. The ticket's growth rule prevents proceeding to paid evidence, so no
provider authorization was requested and no paid pilot or campaign was run.

This is diagnostic evidence only. It does not promote a profile, admit a
dataset release, establish downstream training value, or complete ticket 06.

## Preflight

- The representative v1 pilot profiles compile twelve accepted targets per
  domain with a twenty-four-attempt ceiling.
- Versioned v2 catalogs and fixtures make thirty accepted targets statically
  reachable with a sixty-attempt ceiling without raising the grounding-reuse
  limit above two.
- A serial deterministic fake provider fulfilled all three twelve-target
  probes: 36 accepted, zero rejected, 36 attempts, and a combined ceiling of
  72.
- A deterministic thirty-target probe then fulfilled 90 accepted samples with
  zero rejections and 90 of 180 allowed attempts. It confirmed that accepted
  counts grow while distinct structural-cell counts do not.
- The campaign CLI previews LLM-backed coverage plans without `--use-llm`,
  provider configuration, credentials, or network calls.
- Focused coverage, assignment, and CLI tests pass. The repository-wide test
  and documentation checks are recorded in the implementation commit.

## Baseline Context and Comparability

The prior baseline is `artifacts/representative-campaign-30-v5`. The fake probe
is the deterministic diagnostic output under
`artifacts/coverage-campaign-fake-pilot`. Runtime paths are not persisted in
dataset artifacts.

The legacy baseline groups structural families by required-tool sequence. The
coverage evidence groups them by coverage cell, splitting some identical tool
sequences into exact, ambiguity, and recovery cells. Those family counts and
largest-share values are not like-for-like and must not be shown as
improvements. A versioned common classifier with explicit unclassifiable
counts is required before ticket 06 can make the final structural comparison.

| Domain | Legacy grouping | Legacy groups / largest share | Fake-probe grouping | Fake-probe groups / largest share |
| --- | --- | ---: | --- | ---: |
| Contacts | required-tool sequence | 2 / 0.556 | coverage cell | 3 / 0.417 |
| Mobile messages | required-tool sequence | 3 / 0.357 | coverage cell | 5 / 0.250 |
| Workspace tasks | required-tool sequence | 3 / 0.333 | coverage cell | 5 / 0.250 |

The remaining operational metrics are retained as context, not as a completed
campaign comparison. The run sizes and providers differ.

| Domain | Baseline accepted/rejected | Fake probe accepted/rejected | Distinct grounding | Max grounding reuse | Executable rate | Verification rate |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Contacts | 27 / 3 | 12 / 0 | 6 → 6 | 6 → 2 | 1.000 → 1.000 | 0.900 → 1.000 |
| Mobile messages | 28 / 2 | 12 / 0 | 3 → 7 | 10 → 2 | 0.933 → 1.000 | 1.000 → 1.000 |
| Workspace tasks | 30 / 0 | 12 / 0 | 3 → 7 | 10 → 2 | 1.000 → 1.000 | 1.000 → 1.000 |

The baseline rejection causes were three exact duplicates for contacts, two
tool runtime errors for mobile messages, and none for workspace tasks. The
fake-provider probe had no rejection causes. Its difficulty distributions
were:

- contacts: 5 basic, 5 intermediate, 2 recovery;
- mobile messages: 3 basic, 1 constrained, 6 intermediate, 2 recovery; and
- workspace tasks: 3 basic, 1 constrained, 6 intermediate, 2 recovery.

The legacy baseline did not persist difficulty under the coverage profile's
versioned taxonomy, so a like-for-like difficulty comparison is also pending.
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
the fake probe.

The next work item is
[ticket 07](../../.scratch/coverage-driven-representative-synthesis/issues/07-expand-representative-structural-catalogs.md).
It must add independently executable and verifiable cells that represent new
ambiguity, cross-step constraints, and recovery behavior, plus a common
baseline classifier. It must not manufacture growth through instruction
paraphrases or higher grounding reuse. Only after that deterministic gate
passes should ticket 06 request explicit authorization for a bounded provider
pilot.
