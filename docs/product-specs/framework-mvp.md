# Framework MVP

## Problem

Agent training data is scarce because real interactions rarely expose complete observations, thoughts, tool calls, state transitions, failures, and recovery paths. A useful framework must synthesize complete executable trajectories, not just final answers.

## MVP User Flow

1. User provides a domain config and optional seed records.
2. System builds a small executable environment.
3. System registers typed tools over that environment.
4. System loads remote LLM configuration from `AGENT_DATA_LLM_BASE_URL`, `AGENT_DATA_API_KEY`, and `AGENT_DATA_LLM_MODEL`.
5. System generates candidate tasks by difficulty level through the remote LLM provider.
6. System executes candidate solutions and captures trajectories.
7. System verifies candidates independently.
8. System exports accepted samples and quality reports.

## MVP Acceptance

- Works through a local runner without distributed infrastructure or local LLM cluster deployment.
- Uses a remote OpenAI-compatible LLM API for LLM-backed generation.
- Produces verifiable JSONL samples.
- Records lineage and quality metrics.
- Makes failures inspectable.
- Keeps generated artifacts separate from canonical docs.
