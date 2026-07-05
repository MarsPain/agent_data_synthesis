# Framework MVP

## Problem

Agent training data is scarce because real interactions rarely expose complete observations, thoughts, tool calls, state transitions, failures, and recovery paths. A useful framework must synthesize complete executable trajectories, not just final answers.

## MVP User Flow

1. User provides a `run_profile_v1` or `run_profile_v2` file for the current
   local MVP. The profile maps domain config and optional seed records to
   validated seed metadata, generation mode, target candidate count when
   applicable, profile purpose, and supported feature flags. A `run_profile_v2`
   file may also declare one governed profile-relative JSON source for contacts,
   mobile messages, or workspace tasks.
2. System validates any profile-declared source through source policy, byte
   limits, license labels, local-file sandbox rules, and domain-owned typed
   environment input parsing, then builds a small executable environment from
   the admitted source or from the default fixture.
3. System registers typed tools over that environment.
4. System loads remote LLM configuration from `AGENT_DATA_LLM_BASE_URL`, `AGENT_DATA_API_KEY`, and `AGENT_DATA_LLM_MODEL`.
5. System generates candidate tasks by difficulty level through the remote LLM provider.
6. System executes candidate solutions and captures trajectories.
7. System verifies candidates independently.
8. System exports accepted samples and quality reports.

## MVP Acceptance

- Works through a local synchronous runner without distributed infrastructure or local LLM cluster deployment.
- Uses a remote OpenAI-compatible LLM API for LLM-backed generation.
- Supports deterministic foundation, contacts scale-probe, and profile-local
  governed source profiles before async orchestration is activated.
- Supports local release-candidate evidence packs for contacts, mobile
  messages, and workspace tasks through explicit evaluation, profile decision,
  dataset release, release pack, release audit, and release card artifacts.
- Keeps profile-local source artifacts sanitized by storing source ids, hashes,
  license labels, and policy hashes instead of raw local paths or payloads.
- Produces verifiable JSONL samples.
- Records lineage and quality metrics.
- Makes failures inspectable.
- Keeps generated artifacts separate from canonical docs.
