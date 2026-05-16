# Plan 0004: Remote LLM Generation Lineage and Retry Loop

## Status

Completed on 2026-05-16.

## Goal

Make the `--use-llm` path as inspectable and deterministic-at-the-boundary as the
local fixture path before expanding into multi-role agentic generation. The next
development slice should preserve real provider lineage on generated candidates,
retry transient provider failures within a small budget, and write structured
failure artifacts when remote generation fails.

## Basis

This plan follows [0003-quality-reporting-and-curriculum-foundation](0003-quality-reporting-and-curriculum-foundation.md). The repository now has quality
reports, metric slices, duplicate gates, logical gates, parent comparison, and
curriculum metadata. The remaining gap is that the remote LLM generation path is
still thin:

- [../../ROADMAP.md](../../ROADMAP.md) Stage 1 requires remote OpenAI-compatible
  task generation, and Stage 2 requires retry loops and failure classification.
- [../../DATA.md](../../DATA.md) requires LLM lineage to preserve provider host,
  model id, prompt/config hashes, retry count, error class, token counts, and cost
  metadata when available.
- [../../BACKEND.md](../../BACKEND.md) assigns provider request/response capture,
  retry policy, cost metadata, and model configuration to `synthesis.llm`.
- [../../DESIGN.md](../../DESIGN.md) makes lineage mandatory and keeps LLM calls
  behind a configured remote OpenAI-compatible API.

## Scope

- Propagate LLM generation lineage from `OpenAICompatibleClient.generate_json`
  through generated candidates into accepted samples and relevant rejections.
- Record a prompt/template hash for LLM-backed task generation without storing
  raw secrets or provider credentials.
- Add a bounded retry loop for transient remote provider failures such as timeouts,
  transport errors, HTTP 429, and HTTP 5xx responses.
- Classify non-retryable provider and response-shape failures separately from
  candidate contract failures.
- Ensure remote generation failures still produce inspectable dataset artifacts:
  `rejections.jsonl`, `manifest.json`, and `quality_report.json`.
- Add tests with `httpx.MockTransport` for success lineage, retry behavior,
  exhausted retries, invalid JSON content, and invalid candidate payloads.
- Update data and backend docs if implementation changes the canonical output
  contract or module responsibilities.

## Out of Scope

- Multi-agent generator, solver, critic, or judge roles.
- LLM-as-judge quality scoring.
- Semantic duplicate detection.
- Distributed orchestration, queue workers, MCP adapters, or dashboards.
- Local LLM serving, model routing infrastructure, or GPU scheduling.
- Interactive review UI for failed LLM generations.

## Architecture

Keep the next slice narrow and explicit:

- `synthesis.llm`: owns remote request execution, retry policy, sanitized provider
  error classification, prompt/config hashing, usage extraction, and provider
  lineage dictionaries.
- `synthesis.tasks`: owns conversion from provider JSON into `CandidateTask`
  values and should attach generation metadata without coupling task validation
  to HTTP details.
- `synthesis.pipeline`: owns catching generation-stage failures and converting
  them into dataset-level rejections so failed LLM runs remain inspectable.
- `synthesis.datasets`: owns sample, rejection, manifest, and quality report
  serialization. It should consume lineage already prepared by upstream modules
  rather than reconstructing provider metadata from environment variables.
- `synthesis.contracts`: owns any new rejection cause allowlist entries and
  validation for optional lineage fields added to rejections.

## File Map

- Modify `synthesis/llm.py` to add retry policy, sanitized error metadata, and
  prompt/template hashing.
- Modify `synthesis/tasks.py` to retain generation lineage on LLM-backed
  candidates or a small wrapper returned by the LLM candidate generator.
- Modify `synthesis/datasets.py` so accepted samples use candidate-specific
  generation lineage instead of rebuilding generic lineage from `LLMConfig`.
- Modify `synthesis/pipeline.py` to emit structured generation-stage rejections
  when remote generation fails before candidate execution.
- Modify `synthesis/contracts.py` if new rejection causes or optional rejection
  lineage fields are introduced.
- Extend `tests/test_llm_provider.py` for retry, lineage, and provider failure
  cases.
- Extend `tests/test_foundation_pipeline.py` for inspectable artifacts on LLM
  generation failure.
- Update `docs/DATA.md` and `docs/BACKEND.md` only if the artifact contract or
  module boundary text changes during implementation.

## Implementation Tasks

### Task 1: Preserve Candidate-Level Generation Lineage

- [x] Decide whether `CandidateTask` gains an optional `generation_lineage` field
  or whether the LLM generator returns a wrapper that carries a task plus lineage.
- [x] Ensure deterministic fixture candidates continue to produce stable local
  lineage.
- [x] Ensure accepted samples record the real provider host, model, token usage,
  prompt/config hash, retry count, and error class from the generation call.
- [x] Add tests proving the sample lineage comes from the LLM response path, not
  from a fresh `LLMConfig.from_env()` reconstruction.

### Task 2: Add Bounded Provider Retry Policy

- [x] Add a small retry policy for transport failures, timeouts, HTTP 429, and
  HTTP 5xx responses.
- [x] Keep retries deterministic in tests by avoiding real sleep or by injecting
  a no-op sleeper.
- [x] Record final `retry_count` in lineage for successful retried calls.
- [x] Raise sanitized `LLMProviderError` values that include error class without
  leaking prompts, API keys, or raw provider payloads.

### Task 3: Classify Response and Candidate Generation Failures

- [x] Distinguish provider transport/status failures from malformed provider JSON
  and malformed candidate arrays.
- [x] Add rejection causes only where they improve downstream routing, for example
  `llm_provider_error` and `llm_response_schema_error`.
- [x] Mark retry eligibility consistently with the failure class.
- [x] Add tests for invalid chat completion JSON content and invalid candidate
  payloads.

### Task 4: Emit Artifacts for Generation-Stage Failure

- [x] Catch remote generation failures inside the pipeline before candidate
  execution begins.
- [x] Write `rejections.jsonl`, `manifest.json`, and `quality_report.json` for
  failed generation runs.
- [x] Ensure the manifest rejection counts and quality report cause slices include
  the generation-stage failure.
- [x] Keep CLI behavior clear: `--use-llm` with missing configuration may still
  exit nonzero, but provider/runtime failures after configuration should be
  inspectable through artifacts.

### Task 5: Refresh Docs and Validation

- [x] Update [../../DATA.md](../../DATA.md) if sample lineage or rejection
  contracts gain new fields or causes.
- [x] Update [../../BACKEND.md](../../BACKEND.md) if retry or generation failure
  ownership changes module boundaries.
- [x] Run `uv run python scripts/validate_docs.py`.
- [x] Run `uv run python -m unittest`.

## Acceptance Criteria

- `uv run python main.py` still produces the deterministic foundation artifacts.
- `uv run python main.py --use-llm` preserves actual remote generation lineage in
  accepted samples when the provider succeeds.
- Successful retried LLM calls record a nonzero retry count in lineage.
- Exhausted transient provider failures are classified without leaking secrets.
- Malformed provider responses and malformed candidate payloads are classified
  separately from execution and verification failures.
- Generation-stage failures produce `rejections.jsonl`, `manifest.json`, and
  `quality_report.json` with correct counts and rejection-cause slices.
- Existing quality reporting, duplicate gates, logical gates, parent comparison,
  and review queue behavior remain unchanged.
- `uv run python scripts/validate_docs.py` passes.
- `uv run python -m unittest` passes.

## Risks

- Retrying too broadly can hide deterministic prompt/schema bugs. Keep retry
  causes narrow and visible in lineage.
- Adding lineage directly to `CandidateTask` can blur the boundary between domain
  task data and generation metadata. Prefer the smallest shape that keeps sample
  assembly explicit.
- Generation failures can become noisy if every upstream provider status maps to
  a new rejection cause. Use a small stable cause taxonomy.
- Provider payloads may contain sensitive content. Store hashes and sanitized
  error classes, not raw prompts, headers, API keys, or full responses.

## Notes

This plan is the bridge between the current local quality loop and later Stage 3
agentic generation. Do not add new generator roles until the single remote task
generation path has trustworthy lineage, retries, and failure artifacts.
