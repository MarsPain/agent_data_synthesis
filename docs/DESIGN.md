# Design

## Design Goal

Build an Agent data synthesis framework that produces executable, verifiable, versioned training trajectories. A valid output sample must preserve the relationship among environment state, available tools, task intent, actions, observations, final answer, verification result, and lineage metadata.

## Core Invariants

- **Executable first:** tasks, tools, and verifiers should be runnable whenever possible.
- **Generation and verification are separate:** never let the same component both invent and certify a sample without an independent check.
- **Environment-tool-task consistency:** generated tasks must be grounded in the environment and only require tools that exist or are explicitly synthesized.
- **Curriculum-aware generation:** data should cover difficulty levels from simple single-tool tasks to ambiguous, multi-step, branching tasks.
- **Quality is multidimensional:** track executable success, semantic clarity, logical consistency, diversity, coverage, and cost.
- **Lineage is mandatory:** every output sample must reference source seed, environment version, tool version, generator version, verifier version, and quality gate decisions.
- **Remote LLM boundary:** LLM calls go through a configured remote OpenAI-compatible API; this project does not deploy or manage local LLM clusters.

## Bounded Contexts

### Seed Intake

Owns source registration, task taxonomy selection, domain constraints, and seed normalization. It should not execute tools or validate trajectories.

### Environment Synthesis

Owns executable environment construction, state schema, fixture generation, reset/checkpoint behavior, and environment versioning.

Profile-local source payload parsing is domain-owned. Shared source governance
admits bytes, license decisions, source bundles, policy hashes, and sanitized
events; domain importers convert admitted content into typed environment inputs
for contacts, mobile messages, or workspace tasks without teaching the central
pipeline each domain schema. Workspace source ingestion is profile-local JSON
only; it excludes external workspace APIs, browser profiles, credentials, and
real user data.

Environment implementations also satisfy the extracted `awm_runtime` boundary.
Contacts, mobile, and workspace fixtures expose `runtime_metadata_v1`,
checkpoint/restore, and candidate-local rebuild semantics through the same
protocol while keeping domain-owned SQLite state and tool behavior inside their
domain modules. Runtime sessions wrap those environments with tool registries
so rollout-facing consumers can list tools, execute
`runtime_action_request_v1` envelopes, receive `runtime_action_result_v1`
records, and checkpoint/restore without learning contacts or mobile business
rules.

### Tool Registry

Owns tool schemas, typed parameters, return types, side-effect declarations, dependency graph edges, and compatibility rules.

### Task Curriculum

Owns task generation, difficulty scoring, ambiguity controls, persona controls, and progression rules.

`CandidateTask` remains the compatibility wrapper for deterministic and remote
task generators, task expansion, rejections, and public artifact assembly. The
pipeline derives internal task contracts from it before execution: task intent,
policy hints, expected final-answer evidence, and expected state checks are
separate internal records.

Representative remote generation is domain-aware. Each domain bundle owns a
validated generation specification for task types, curated tools,
expected-state vocabulary, synthetic grounding context, and batch limits. The
shared generator emits `TaskContract` values before crossing the existing
`CandidateTask` compatibility boundary.

Coverage planning is a separate pre-generation contract. A domain pack owns its
versioned reachable-cell catalog and capacity projection; the shared compiler
validates that data with a named coverage profile, selected run features,
accepted-sample target, candidate budget, and bounded emphasis overrides. The
candidate budget must equal the profile-derived attempt ceiling. The compiler
emits a sanitized, hash-bound `coverage_plan_v1` with an accepted-sample
distribution and that separate attempt ceiling. Contacts provides the first
catalog and authoritative version registry. Plan preview may write this
artifact without constructing a provider client or executing a candidate.
Coverage-enabled contacts execution schedules the deterministic initial wave
from that plan, prioritizing mandatory floors and then largest normalized
deficits with stable cell-id tie-breaking. Each locally hashed assignment
projects one task type, its ordered tools, and one grounding unit into the
existing remote-generation contract. Local membership validation runs before
candidate processing; conforming candidates reuse the existing mutation
admission, execution, verification, exact-duplicate, and assembly path. After
each processing wave, the scheduler reconciles planned, in-flight, accepted,
rejected, and remaining counts by cell. Only accepted, locally validated
assignments reduce the deficit; bounded replacement waves stop at the plan
ceiling. `PipelineResult.coverage_reconciliation` exposes the deterministic
non-artifact completion snapshot for orchestration and tests. Hash-bound public
coverage evidence and representative fulfillment gates remain a later
contract.

### Trajectory Execution

Owns policy execution, tool call recording, observation capture, retries, and error classification.

Scripted contacts, mobile, and workspace policies can consume internal policy
hints while the public policy-generator API continues to accept
`CandidateTask`. This keeps deterministic trajectories stable while reducing
coupling between generator-era task records and execution planning.

Execution can now derive internal `episode_log_v1` evidence from existing
trajectories. Episode evidence records ordered actions, observations,
state-change summaries, final responses, runtime identity, policy identity, and
verifier identity for diagnostics and opt-in quality scoring. It is not part of
the default dataset sample schema and is not a release artifact.

### Verification

Owns executable checks, logical checks, LLM-as-judge checks, diversity checks, and human review routing.

The accepted target design requires declared state-changing candidates to pass
deterministic mutation authorization/provenance validation and an independent
semantic mutation judge before execution when enforcement is enabled. This
specialized admission judge is distinct from a future general post-execution
quality judge; read-only candidates bypass mutation admission. Desired behavior
and activation evidence are defined in the
[semantic mutation admission spec](product-specs/semantic-mutation-admission.md).
Its model identity is selected in the mutation-admission profile independently
from `AGENT_DATA_LLM_MODEL`; provider endpoint and credentials still use the
shared remote-adapter environment defaults and are never retained in profiles.
Admission-enabled runs persist `mutation_admission_report_v1` aggregates and a
`dataset_manifest_v2` that declares sample/admission contract versions and
hash-binds samples, rejections, and the report. The offline release boundary
accepts a mutation-safe `dataset_release_pack_v2` only when the retained profile
uses enforce mode, every accepted state-changing sample has an independently
supported verdict, all admission artifacts match their hashes, and retained
material passes the admission-specific sanitization scan. Historical v1
manifests and packs remain readable but do not certify mutation safety.

The exact-answer/state verifier reads internal expected-outcome and
expected-state contracts. Compatibility wrappers still accept `CandidateTask`,
and verifier ids, versions, check names, sample schemas, and episode schemas
remain stable.

### Episode Quality

Owns the first non-synthesis consumer of runtime episode evidence. It reads
opt-in `episodes.jsonl` records, validates the `episode_log_v1` contract, scores
transition completeness and descriptor-derived state-change support, and writes
`episode_quality_report_v1` summaries without raw arguments, observations,
final responses, prompts, provider payloads, credentials, source payloads, or
host paths. It consumes `awm_runtime` primitives and repository-owned
descriptor lookup; it does not own candidate admission, dataset release,
profile promotion, reward model training, executable replay, or Agentic RL
rollout collection.

### Episode Replay

Owns the first execution-facing consumer of runtime episode evidence. It reads
opt-in `episodes.jsonl` records, validates `episode_log_v1`, resolves replay
support and rebuild seeds through runtime descriptors, rebuilds fresh supported
fixture runtimes, re-executes action transitions through
`RuntimeSession.execute_action(...)`, compares replayed observation and
state-change hashes, and writes
`episode_replay_report_v1` summaries without raw arguments,
observations, final responses, prompts, provider payloads, credentials, source
payloads, or host paths. It consumes `awm_runtime`, repository-owned descriptor
lookup, `synthesis.episode_quality`, and `synthesis.domain_pipeline`; it does
not own candidate admission, dataset release, profile promotion, reward model
training, external MCP environment servers, async orchestration, or runtime
package publishing.

### Reward Labels

Owns the deterministic training-signal consumer over runtime episode evidence.
It reads validated `episode_log_v1` records plus optional episode-quality and
episode-replay evidence, derives scalar `reward_label_v1` records and
preference-group metadata from descriptor-backed reward/state support, and
writes `reward_label_report_v1` summaries without raw task instructions,
expected answers, expected state, tool arguments, observations, final responses,
prompts, provider payloads, credentials, source payloads, or host paths. It
consumes `awm_runtime`, repository-owned descriptor lookup,
`synthesis.episode_quality`, `synthesis.episode_replay`, and
`synthesis.contracts`; it does not train reward models, collect RL rollouts,
change release admission, promote profiles, call external MCP environment
servers, or own runtime package publishing.

### Diagnostic Rollouts

Owns the repo-local diagnostic rollout collector. It drives contacts and mobile
scripted policies through `RuntimeSession` action envelopes, enforces a bounded
max-step limit, exports sanitized `episode_log_v1` records, and proves those
episodes can be consumed by replay and reward-label consumers. It is not policy
optimization, reward-model training, distributed rollout collection, external
MCP execution, dataset release admission, profile promotion, or default CLI
output.

### Dataset Assembly

Owns canonical output format, split assignment, versioning, deduplication, manifest generation, and export adapters for training.

### Orchestration

Owns job lifecycle, queues, concurrency, cancellation, retries, metrics, and worker placement.

## Required Sample Shape

Each final sample should contain:

- `environment`: environment id, version, state snapshot or reset recipe.
- `tools`: tool schemas, versions, dependencies, and side-effect metadata.
- `task`: natural language instruction, structured constraints, difficulty score, and expected capabilities.
- `trajectory`: ordered thought/action/observation/final-response events or a policy-compatible equivalent.
- `verifier`: verifier id, executable checks, logical checks, and result details.
- `quality`: executable rate, success outcome, clarity score, diversity tags, and review status.
- `lineage`: seed ids, generator versions, model ids, prompt/config hashes, and timestamps.

## First Implementation Bias

Start local and deterministic:

- SQLite-backed environments.
- Domain packs own their domain state, tool registry, deterministic candidates,
  scripted policy generation, and profile-local source payload import into typed
  environment inputs. The synchronous pipeline owns shared synthesis flow: source
  governance, domain selection, candidate-local isolation, execution,
  verification, deterministic merge, and artifact assembly.
- Runtime metadata is lifecycle evidence, not dataset or release metadata.
  Runtime-aware code should use `runtime_metadata()` for environment identity,
  reset recipe class, state backend, and checkpoint strategy; sample assembly
  continues to use `metadata()` for the public dataset environment field.
- Runtime capability descriptors, registry primitives, sessions, action
  envelopes, metadata safety checks, and package-neutral episode primitives live
  under `awm_runtime`. The repository-owned contacts/mobile/workspace default
  descriptor registry lives under `synthesis.runtime_registry`. Runtime-facing
  production code imports package-neutral primitives from `awm_runtime` and
  repository-owned default descriptor lookup from `synthesis.runtime_registry`;
  the one-cycle `synthesis.runtime` and `synthesis.episodes` compatibility
  window is closed.
  Replay and reward consumers should ask the registry for capability facts
  instead of owning contacts/mobile/workspace runtime allowlists. The runtime
  boundary also owns the sanitized capability-status vocabulary: `supported`,
  `unsupported`, `insufficient_evidence`, and `malformed`.
- Runtime sessions and action envelopes standardize list-tools, execute-action,
  checkpoint/restore, and rebuild behavior while leaving domain state, rebuild
  policy, and tool semantics in domain packs.
- Episode-quality reporting is a repo-local, synchronous runtime evidence
  consumer. It reads known-runtime and state-changing-tool facts from runtime
  descriptors, proving the episode boundary can serve another data-quality
  reader.
- Episode-replay reporting is a repo-local, synchronous execution consistency
  consumer. It proves the current runtime boundary can serve a non-synthesis
  executor that rebuilds fixture runtimes and replays actions through
  `RuntimeSession.execute_action(...)`, while keeping separate package
  publishing deferred.
- Reward-label reporting is a repo-local, synchronous scoring consumer. It
  proves sanitized episode, quality, and replay evidence can produce
  preference-ready deterministic labels while keeping reward training, Agentic
  RL rollout collection, and release admission changes deferred.
- Diagnostic rollout collection is repo-local and synchronous. It executes
  scripted policies through runtime sessions, emits sanitized `episode_log_v1`
  evidence, and keeps RL training, online policy optimization, distributed
  workers, default CLI output, and package publishing deferred.
- Domain packs remain responsible for domain state, domain tools, scripted
  policies, verifiers, source import semantics, and rebuild seeds. Consumer
  modules may read descriptor capability facts, but they should not learn
  contacts, mobile, or workspace business rules or hard-code domain-specific
  runtime branches. The third-domain workspace probe preserves this contract:
  workspace-specific code lives in workspace-owned modules plus domain
  registration/evaluation/run-profile boundaries, while replay, reward labels,
  episode quality, rollouts, adapters, profile decisions, and dataset release
  continue to consume descriptors, runtime sessions, action envelopes, and
  generic report fields.
- Task-intent, policy-hint, expected-outcome, and expected-state contracts are
  internal only. They de-risk future reward/RL/runtime consumers without
  changing `CandidateTask.export()`, `samples.jsonl`, `rejections.jsonl`, or
  episode report schemas.
- Python callable tools with explicit schemas.
- Local job runner with resumable manifests.
- Remote LLM provider adapter configured by `AGENT_DATA_LLM_BASE_URL`, `AGENT_DATA_API_KEY`, and `AGENT_DATA_LLM_MODEL`.
- Deterministic mutation admission before state-changing execution; executable
  verification before any general post-execution LLM-as-judge verification.
- JSONL output plus a dataset manifest.

Distributed Ray-style orchestration, MCP servers, and multi-model routing should be added after local contracts are stable. These additions may scale workers and route provider calls, but they should not turn the project into a local LLM serving platform.
