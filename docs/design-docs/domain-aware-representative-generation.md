# Domain-Aware Representative Generation Design

## Purpose

Plan 0042 established an offline evidence boundary for three-domain scale runs,
release packs, and downstream benchmark exchange. It did not create the
representative workloads that boundary needs. The current remote task generator
is contacts-specific even though run profiles allow `generation.mode: llm` for
all supported domains. This design closes that mismatch without activating
async orchestration, semantic duplicate detection, model training, or external
tool servers.

## Decision

Introduce a domain-owned generation specification consumed by one shared LLM
task-contract generator. Each supported domain declares its task types, tool
schemas, expected-state vocabulary, bounded grounding context, and remote
disclosure policy. The shared generator requests structured task-contract
records, validates them against the selected domain specification, converts
them through the existing `TaskContract` compatibility boundary, and submits
only valid candidates to the existing execution, verification, and dataset
assembly flow.

Representative eligibility becomes explicit evidence. An `llm` generation
mode alone is not sufficient: a run must use an approved representative profile,
an allowed generation-context policy, complete source-admission evidence when a
profile source is used, and a fulfilled candidate-count contract. Plan 0042's
aggregator continues to consume existing reports, but it validates these new
facts before classifying a run as `representative`.

## Alternatives Considered

### Separate LLM generator per domain

Contacts, mobile messages, and workspace tasks could each own a complete prompt,
parser, retry loop, and provider integration. This is direct, but it duplicates
provider handling and makes schema behavior drift likely. It also creates three
places where prompt redaction, candidate-count enforcement, and lineage rules
must stay synchronized.

### Tool-registry-only generic generation

The shared generator could infer everything from exported tool schemas. Tool
schemas describe arguments and side effects, but not valid task types,
multi-step policy expectations, expected-state checks, or which environment
facts may be sent to a remote provider. This is too weak for grounded,
independently verifiable generation.

### Domain generation specification plus shared generator

This approach keeps domain semantics with domain owners and provider mechanics
in one place. It reuses existing tool definitions and task-contract types while
adding only the missing generation vocabulary. It is the selected approach.

## Architecture

### Domain generation specifications

`synthesis.domain_generation` owns immutable generation records and shared
validation. A `DomainGenerationSpec` contains:

- the canonical domain id and specification version;
- supported task types and required tools;
- allowed expected-state check types;
- exported curated tool schemas and side-effect classes;
- a bounded, domain-produced grounding context;
- an explicit context policy of `synthetic_fixture` or
  `governed_source_opt_in`; and
- a maximum candidates-per-provider-call budget.

Domain modules build their own specifications because they own task semantics.
The shared module must not contain contacts/mobile/workspace allowlists beyond
generic contract validation.

### Grounding and remote disclosure

Grounding context is an ephemeral provider input, not a dataset artifact. It
may contain only the minimum values needed to create executable tasks. It must
never contain credentials, host paths, provider headers, unrestricted source
payloads, or arbitrary profile JSON.

Synthetic fixtures may be used under `synthetic_fixture`. Profile-local source
rows are default-denied for remote disclosure. A future or current run may use
`governed_source_opt_in` only when the run profile explicitly enables remote
generation context, the source passed admission, and the domain builder emits
a bounded allowlisted context. The plan adds the explicit policy now and keeps
source-backed remote disclosure disabled unless all checks are present.

No prompt or grounding payload is persisted. Existing provider lineage may
record hashes, model aliases, provider host, retry count, and token/cost data.

### Structured generation output

The provider returns `task_contracts`, not the contacts-oriented flat candidate
shape. Each item contains:

- `candidate_id`, `instruction`, `task_type`, and difficulty;
- required capabilities and required tools;
- primary tool plus arguments or an allowed branch plan;
- `final_answer_contains`;
- zero or more typed expected-state checks; and
- no caller-supplied lineage, source, provider, path, or credential fields.

The parser builds the existing `TaskContract`, validates it, and converts it to
`CandidateTask` only at the current compatibility boundary. Provider lineage is
attached locally and cannot be asserted by the provider response.

### Bounded batch semantics

For `generation.mode: llm`, `target_candidate_count` becomes required. The
shared generator splits that target into bounded calls, rejects empty or
oversized batches, enforces globally unique candidate ids, and stops exactly at
the declared target. A provider response that cannot fulfill the target within
the configured call budget produces a classified generation-stage rejection;
partial candidates are not silently presented as a fulfilled representative
run.

The implementation remains synchronous. Candidate batching supplies evidence
for, but does not pre-implement, plan 0014.

### Representative eligibility

The manifest's sanitized run-profile metadata records:

- `generation_mode`;
- `target_candidate_count`;
- `generation_spec_version`;
- `generation_context_policy`;
- `representative_generation_eligible`; and
- fixed reason codes when eligibility is false.

Eligibility requires an LLM generation mode, an approved specification, a
positive fulfilled target, an allowed context policy, consistent domain and
profile identities, and valid source-admission evidence when source-backed
context is used. The scale-evidence consumer reads and validates these fields;
it does not infer eligibility from `generation_mode` alone.

## Data Flow

```text
run profile + admitted environment
  -> domain pipeline bundle
  -> domain generation specification
  -> bounded grounding context + tool/task contract vocabulary
  -> shared remote LLM task-contract generator
  -> TaskContract validation
  -> CandidateTask compatibility conversion
  -> existing policy execution and verifier
  -> existing quality/evaluation/release artifacts
  -> representative eligibility validation
  -> plan 0042 three-domain scale evidence
```

## Error Handling

- Unknown domain generation specifications fail before a provider call.
- Unsafe grounding content fails before a provider call with a fixed local
  error classification.
- Unknown task types, tools, expected-state checks, extra keys, malformed
  schemas, duplicate candidate ids, and oversized batches become sanitized
  `llm_response_schema_error` failures.
- Target underfill or overflow becomes a deterministic generation contract
  failure and cannot be representative.
- Provider failures preserve current bounded retry and sanitized lineage rules.
- Invalid representative metadata yields `insufficient_evidence`, never an
  activation recommendation.

## Testing Strategy

Use fake OpenAI-compatible clients and deterministic domain inputs. Contract
tests cover exact keys, unsafe values, task types, tool membership, state-check
vocabulary, batch bounds, and eligibility metadata. Domain tests prove at least
one read-only and one state-mutating generated task for mobile and workspace,
plus contacts compatibility. CLI tests exercise three LLM profiles without
network access and prove that generated artifacts feed the existing evaluation,
profile-decision, release, audit, and scale-evidence consumers.

Real provider calls and a real representative campaign are operational evidence,
not unit-test prerequisites. Completion of the implementation plan means the
repository can run such a campaign safely; it does not claim that the campaign
has already occurred.

## Out of Scope

- Async orchestration, durable queues, workers, cancellation, or resumption.
- Semantic embeddings, clustering, or near-duplicate admission.
- LLM-generated tools, environments, verifiers, policies, or executable code.
- Model training, fine-tuning, Agentic RL, or training-service integration.
- External MCP servers, browser automation, real workspace APIs, or a fourth
  domain.
- Automatic plan activation or release admission changes based on scale
  evidence.

## Documentation Impact

Implementation must update `docs/BACKEND.md`, `docs/DATA.md`,
`docs/SECURITY.md`, `docs/ROADMAP.md`, and `docs/PLANS.md`. Root maps change only
where the active-plan pointer or operator commands change. Plan 0014 and TD-0002
remain deferred until a completed representative campaign activates their
existing evidence gates.
