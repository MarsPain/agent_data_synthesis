# Semantic Mutation Admission

Status: ticketed; ready for implementation

## Problem Statement

The representative `_30_v5` campaign materially improved generation quality:
contacts accepted 27 of 30 candidates, mobile accepted 28 of 30, and workspace
accepted all 30. Every domain passed all five held-out tasks, and the campaign
decision was `no_change_recommended`. These results establish execution and
expected-state consistency, but they do not establish that the synthetic task
requester authorized each state change or supplied its human-meaningful
arguments.

The retained artifacts expose this missing guarantee:

- The 85 accepted samples contain 53 state-changing samples: 15 contacts, 18
  mobile, and 20 workspace samples.
- Mobile rejected two draft-reply candidates only when tool execution received
  an empty generated body.
- All ten accepted workspace comment samples use comment text that is absent
  verbatim from their instructions.
- Two accepted workspace task-creation samples execute creation even though
  their instructions request only lookup or retrieval.
- A conservative lexical triage found 22 of 40 requester-controlled workspace
  string arguments absent verbatim from their instructions. This is not itself
  a semantic quality label, but it demonstrates that current schema and
  reference checks cannot establish argument provenance.

Today the task generator produces both the instruction and expected state. The
deterministic verifier checks that execution reaches that expected state. A
candidate can therefore be internally consistent while still performing a
mutation the instruction never authorized. This is a dataset-validity and
safety gap: accepted demonstrations can teach an agent to invent consequential
actions or requester-controlled content.

## Solution

Add a pre-execution Semantic Mutation Admission capability for every candidate
that declares a state-changing action. From an operator's perspective, the
pipeline gains three explicit modes:

- `disabled` preserves the current local, offline behavior and records that
  mutation admission was not evaluated.
- `shadow` evaluates and reports admission without changing whether candidates
  execute or are accepted.
- `enforce` permits tool execution only after deterministic validation succeeds
  and an independent semantic judge returns `supported`.

The task generator proposes a versioned mutation authorization record. A
deterministic validator establishes structural and factual provenance. An
independent, model-driven semantic judge then decides whether the task
instruction actually supports the proposed state change and its
requester-controlled arguments. The judge returns only `supported`,
`unsupported`, or `uncertain`, plus bounded reason codes and evidence
references.

Read-only candidates bypass admission. State-changing candidates retain
sanitized admission evidence in accepted samples or rejection records so that
release validation can audit the decision without storing raw judge prompts,
responses, secrets, or chain-of-thought.

The canonical vocabulary is defined by the domain glossary. The architectural
choice to use an independent semantic judge is recorded in the linked ADR.

## User Stories

1. As a synthesis operator, I want local runs to remain offline by default so
   that adopting this capability does not silently introduce model calls or
   cost.
2. As a synthesis operator, I want to select `disabled`, `shadow`, or `enforce`
   in a versioned run profile so that activation is explicit and reproducible.
3. As a synthesis operator, I want an unavailable or malformed judge response
   to fail closed in enforcement mode so that provider failure cannot authorize
   a mutation.
4. As a synthesis operator, I want shadow mode to leave candidate execution and
   acceptance unchanged so that I can calibrate the gate against current
   behavior.
5. As a dataset curator, I want every state-changing sample to show whether its
   action and requester-controlled arguments were supported so that I can audit
   why it entered the dataset.
6. As a dataset curator, I want unsupported and uncertain candidates to carry
   bounded, machine-readable reasons so that failure populations can be
   compared without parsing prose.
7. As a dataset curator, I want historical `_30_v5` artifacts to remain
   immutable so that new safety claims never rewrite old evidence.
8. As a release manager, I want mutation-bearing release candidates to require
   enforcement and a passing calibration gate so that shadow-only evidence
   cannot be mistaken for release readiness.
9. As a release manager, I want offline release validation to verify admission
   hashes, verdicts, model independence, and contract versions without calling
   the judge again.
10. As a release manager, I want same-model generator and judge runs labeled
    diagnostic-only so that correlated model errors cannot certify a release.
11. As a domain author, I want to declare state-changing actions,
    requester-controlled fields, and allowed provenance in domain-owned policy
    so that domain meaning does not leak into the shared admission kernel.
12. As a domain author, I want unsupported provenance origins rejected by a
    closed, versioned contract so that generators cannot invent escape hatches.
13. As a domain author, I want legitimate observation references, defaults, and
    derivations represented explicitly so that safe non-literal arguments are
    not confused with model invention.
14. As a framework maintainer, I want one small admission interface at the
    candidate-processing boundary so that policy lookup, validation, judge I/O,
    and evidence assembly remain hidden behind a deep module.
15. As a framework maintainer, I want the semantic judge behind an injected
    provider port so that production calls and deterministic test doubles obey
    the same contract.
16. As a framework maintainer, I want the shared kernel to operate on normalized
    declarations rather than domain or tool-name branches so that new domains
    do not require central conditional logic.
17. As a framework maintainer, I want strict parsing and bounded retries so that
    free-form model behavior cannot become an authorization channel.
18. As a framework maintainer, I want minimal judge inputs and sanitized retained
    evidence so that unrelated environment data, credentials, and raw model
    material do not enter artifacts.
19. As an evaluator, I want a reviewed calibration corpus, held-out split, and
    repeated judgments so that safety, precision, coverage, and stability are
    measured independently.
20. As an evaluator, I want aggregate results by domain, task type, provenance
    origin, verdict, and reason so that regressions are diagnosable rather than
    hidden in a single score.
21. As an evaluator, I want critical adversarial cases to tolerate uncertainty
    but never false support so that safety takes precedence over automated
    coverage.
22. As a future domain integrator, I want contract-versioned extension points so
    that new provenance mechanisms can be added deliberately without weakening
    the meaning of old evidence.

## Implementation Decisions

### 1. Admission boundary and module shape

Candidate processing is the primary integration seam. Admission occurs after a
candidate has a task contract and proposed tool policy, but before any tool
execution starts. A candidate is classified as read-only or state-changing from
the domain declaration and proposed action, not from model prose.

Candidate processing depends on one injected admission evaluator operation. The
admission module hides domain policy lookup, deterministic validation, judge
request construction and parsing, retry policy, mode behavior, and evidence
assembly. The caller receives only the execution decision and sanitized
evidence. Production and fake judge adapters implement the same provider port.

The first version gates the complete declared state-changing candidate before
execution begins. It does not attempt step-by-step admission for a mutation that
is discovered only after runtime observations.

### 2. Propose, validate, certify

Admission has three non-interchangeable stages:

1. The generator proposes one authorization record for every declared
   state-changing action and provenance for every requester-controlled
   argument.
2. The deterministic validator checks record completeness, action alignment,
   evidence references, allowed origins, declared defaults, deterministic
   derivations, and applicable domain policy. It never interprets broad
   semantic permission.
3. The independent semantic judge certifies whether the instruction supports
   the proposed action and argument meanings. It cannot add provenance, repair
   the candidate, or override a deterministic failure.

A deterministic failure stops admission before a judge call. In enforce mode,
only a fully valid record with a `supported` semantic verdict can execute.

### 3. Versioned authorization record

The first authorization-record contract is named
`mutation_authorization_record_v1`. It includes:

- its schema version and a hash of the normalized task instruction;
- one entry per proposed state-changing action;
- a stable action reference and declared action type;
- an instruction evidence reference for action authorization;
- one entry per requester-controlled argument;
- the argument name, provenance origin, and minimal evidence reference; and
- hashes binding the record to the proposed policy and referenced evidence.

Instruction evidence references use validated character spans over the exact
normalized instruction retained for the candidate. Observation evidence
references point to typed values already present in the candidate's bounded
environment trace. Defaults and derivations reference versioned domain
declarations. The authorization record does not copy unrelated observation
content or introduce free-form explanations.

The provenance origin set is closed for version 1:

- `instruction`, classified as literal or semantic support;
- `tool_observation`;
- `declared_default`; or
- `deterministic_derivation`.

`model_inferred`, `reasonable_guess`, candidate-defined origins, and missing
origins are invalid. Adding another origin changes the contract version.

### 4. Domain-owned mutation policy

Each domain pack declares its state-changing actions, requester-controlled
fields, allowed origins, observation bindings, defaults, and deterministic
derivations. The shared kernel consumes normalized declarations and contains no
domain-name or tool-name branches.

Version 1 adopts this conservative policy:

| Domain action | Requester-controlled fields | Allowed support |
| --- | --- | --- |
| Record a contact follow-up | Contact name, note | Name and note require literal or semantic instruction support. An observed normalized contact identity is allowed only when bound to the instruction-selected contact. No note default is allowed. |
| Create a phone reminder | Title, due time when supplied | Title and supplied due time require literal or semantic instruction support. A source message identifier may come from an observation only when bound to the instruction-selected message. Version 1 declares no due-time default. |
| Draft a message reply | Reply body | Body requires literal or semantic instruction support. Thread identity may come from an observation only when bound to the instruction-selected message or thread. No body default is allowed. |
| Create a workspace task | Title, priority, due label when supplied | These values require literal or semantic instruction support. Project identity may come from an observation only when bound to the instruction-selected project. Version 1 declares no requester-content defaults. |
| Add a workspace comment | Comment body | Comment body requires literal or semantic instruction support. Task identity may come from an observation only when bound to the instruction-selected task. No comment default is allowed. |

The domain policy explicitly distinguishes requester-controlled content from
system identifiers used to address an instruction-selected object. Observation
bindings prove identity; they do not authorize a new action or supply missing
human-meaningful content.

### 5. Deterministic validation outcomes

Every failed deterministic check is represented by the top-level failure class
`mutation_admission_failed` and one or more fixed detail codes:

- `authorization_record_missing`
- `authorization_action_mismatch`
- `requester_argument_provenance_missing`
- `provenance_origin_invalid`
- `instruction_span_invalid`
- `observation_reference_invalid`
- `declared_default_invalid`
- `deterministic_derivation_invalid`
- `authorization_record_hash_mismatch`

The validator reports evidence references and bounded field paths, not copied
secret values or free-form rationale. Unknown codes make the evidence record
invalid rather than being silently accepted.

### 6. Independent semantic judge

The new role is `mutation_admission_judge`. It is distinct from the future
general-purpose post-execution `judge_verification` role.

The judge receives only:

- the normalized task instruction and task type;
- the proposed state-changing action and requester-controlled arguments;
- the validated provenance declarations; and
- the minimal referenced observation, default, or derivation evidence.

Task text and observation values are explicitly delimited as untrusted data.
Generator prompts, raw generator responses, unrelated environment content,
credentials, transport headers, and host paths are excluded.

The first semantic-verdict contract is named
`semantic_mutation_verdict_v1`. It contains a verdict, action findings,
argument findings, bounded reason codes, evidence references, an input hash, and
judge lineage. The verdict enum is exactly `supported`, `unsupported`, or
`uncertain`. It contains no confidence score and no admission-relevant free-form
rationale.

Allowed semantic reason codes are versioned with the verdict contract:

- positive evidence: `action_authorized`, `argument_literal_supported`,
  `argument_semantic_supported`, `observation_reference_supported`,
  `declared_default_supported`, `deterministic_derivation_supported`;
- absent or unsafe evidence: `action_not_authorized`, `action_negated`,
  `conditional_authorization_ambiguous`, `argument_not_supported`,
  `provenance_mismatch`, `evidence_ambiguous`,
  `instruction_prompt_injection`.

Provider and parser failures use
`judge_unavailable`, `judge_output_invalid`, `judge_unsupported`, or
`judge_uncertain` as bounded admission outcomes. Provider calls have a fixed
timeout and at most one retry. Exhaustion fails closed in enforce mode.

The judge model identifier is configured separately from the task-generator
model. Enforce mode requires both identifiers to be explicit and different.
Provider endpoint and credential configuration may share the existing provider
defaults, but secrets are never retained. Same-model execution is permitted
only in shadow mode and is labeled diagnostic-only.

### 7. Activation and run-profile compatibility

A new run-profile contract version adds a structured mutation-admission section
with mode, judge role configuration, contract versions, retry limits, and
reporting controls. Earlier run-profile versions normalize to `disabled`; their
existing meaning and configuration hashes remain unchanged.

Mode behavior is exact:

| Mode | Judge behavior | Execution behavior | Release meaning |
| --- | --- | --- | --- |
| `disabled` | No judge call | Existing behavior | Not evaluated; cannot certify mutation safety |
| `shadow` | Validate and judge when configured | Verdict does not change execution or acceptance | Diagnostic only |
| `enforce` | Validate and use an independent judge | Only `supported` executes; all other outcomes reject before execution | Required for a mutation-bearing release candidate |

Release-candidate profiles must use `enforce`, even if a particular run happens
to produce no mutations. This keeps the release profile's safety meaning stable
and avoids outcome-dependent configuration.

### 8. Evidence persistence and dataset compatibility

Accepted samples use a new sample-contract version and may include a top-level
`mutation_admission` record. That record is required for every state-changing
sample and records:

- mode and admission contract versions;
- deterministic validation status and bounded reasons;
- semantic verdict, bounded findings, and evidence references;
- authorization, input, verdict, and policy hashes;
- generator, validator, and judge lineage sufficient to verify independence;
- bounded call metadata such as attempts, latency, and token counts; and
- a diagnostic-only marker when independence requirements are not met.

Read-only samples explicitly identify their read-only classification and do not
require a semantic verdict. Rejected state-changing candidates store the same
sanitized admission structure within rejection details.

Dataset manifests declare the sample-contract version. Validators continue to
read historical samples under their original contract, while a new release pack
requires the new contract for newly admitted mutation samples. `_30_v5` remains
byte-immutable and is not grandfathered. Its candidates may seed calibration,
but affected samples must be re-adjudicated before inclusion in a new release.

Raw judge prompts, raw responses, chain-of-thought, credentials, headers, and
unreferenced observation content are prohibited retained material.

### 9. Reporting and enforcement activation

Shadow and enforce runs can emit a versioned mutation-admission report. It
aggregates counts by domain, task type, action, provenance origin, verdict,
reason code, provider outcome, and model-independence status. It also reports
coverage, supported precision, unsafe-case capture, repeatability, critical
flips, retries, latency, and token use when reviewed labels are available.

Before enforcement is enabled for release work, the calibration set must
contain at least 200 human-reviewed cases across all three current domains and
all current state-changing task types. At least 100 cases must be unsupported or
adversarial, and at least 60 must be held out from prompt or policy tuning. The
set covers negation, conditional authorization, missing requester content,
parameter smuggling, false provenance, semantic paraphrase, legitimate defaults,
deterministic derivations, and prompt injection.

Enforcement activation requires, on the reviewed benchmark:

- zero false `supported` verdicts on critical adversarial cases;
- at least 98% precision among all `supported` verdicts;
- at least 98% of unsupported cases classified `unsupported` or `uncertain`;
- at least 70% non-`uncertain` automatic-decision coverage;
- at least 95% exact verdict agreement across three repeated evaluations; and
- zero critical adversarial cases that flip to `supported` in any repeat.

False support is the primary optimization constraint. Coverage may improve only
while every safety threshold continues to pass. Activation evidence records the
reviewed corpus version, held-out split, judge configuration hash, and report
hash.

## Testing Decisions

Testing is organized around two confirmed behavior seams rather than internal
helper functions.

### Candidate-processing seam

The primary tests exercise a candidate from contract construction to the point
where execution is either allowed or prevented. They inject a deterministic
fake judge and observe public outcomes: whether the tool environment was
invoked, whether the candidate became a sample or rejection, and what sanitized
admission evidence was retained.

This suite covers:

- read-only bypass in all modes;
- state-changing behavior in `disabled`, `shadow`, and `enforce`;
- every deterministic failure code;
- all three semantic verdicts;
- judge timeout, invalid output, retry exhaustion, and prompt-injection cases;
- field policies for every current state-changing domain action;
- literal instruction support, semantic paraphrase, observation binding,
  declared defaults, and deterministic derivations;
- unsupported action, negation, conditional ambiguity, missing content, false
  provenance, and parameter smuggling; and
- proof that no tool executes on any non-`supported` enforce path.

Tests assert behavior and retained contracts. They do not assert prompt wording,
private method calls, or internal object layout.

### Run-level seam

Run-level tests exercise complete profiles and verify mode defaults, profile
compatibility, report emission, manifest wiring, model-independence rules,
release validation, and historical-contract compatibility.

This suite covers:

- earlier profile versions preserving disabled behavior and stable hashes;
- explicit shadow and enforce configuration;
- same-model diagnostic labeling and enforce rejection;
- sanitized per-candidate evidence in samples and rejections;
- aggregate metric calculations and three-run repeatability;
- enforcement activation threshold pass and fail boundaries;
- release-pack rejection for missing or unverifiable mutation evidence;
- historical `_30_v5` immutability; and
- retained-material scans proving raw judge material and secrets are absent.

The final verification set includes focused admission tests, the full unit suite,
documentation validation, retained-material scans, and one fresh representative
shadow or enforce run using an independent judge model. Paid provider calls are
not part of ordinary unit tests.

## Out of Scope

- The general post-execution `judge_verification` role or a universal result
  quality judge.
- Judge-driven candidate repair, missing-provenance invention, or rewriting the
  task instruction.
- Runtime step-by-step admission for mutations not declared before execution.
- Semantic duplicate detection, asynchronous orchestration, release-taxonomy
  alignment, and branch-task generation coverage.
- Rewriting `_30_v5` artifacts or treating fixture-only benchmark data as
  release evidence.
- Training or fine-tuning a judge model in this delivery.
- A human-review user interface; `uncertain` cases are retained for external
  review workflows.
- Dynamically learned domain policy. Version 1 policy remains explicit and
  reviewable.

## Further Notes

- The domain glossary is the source of truth for actor and mutation terminology:
  [Domain glossary](../../CONTEXT.md).
- The independent-judge decision and its alternatives are recorded in
  [ADR 0001](../adr/0001-independent-semantic-mutation-admission.md).
- Current delivery state and future implementation tickets are grouped in the
  [Semantic Mutation Admission feature tracker](../../.scratch/semantic-mutation-admission/README.md).
- This document is the only implementation specification for the feature.
  Tickets link here and contain work state and dependencies, not duplicate
  design requirements.
