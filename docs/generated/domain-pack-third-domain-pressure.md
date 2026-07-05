# Domain Pack Third Domain Pressure

Generated on 2026-07-05 from plan 0037 implementation evidence.

## Summary

`workspace_tasks_fixture` is the third deterministic domain pack. It proves a
new domain can join the synthesis pipeline through domain-owned modules,
runtime descriptors, domain bundle registration, and generic runtime-session
consumers.

## Domain Pack Surface

- Environment: `synthesis.workspace_environment.WorkspaceTasksEnvironment`
  stores synthetic projects, tasks, lightweight documents, and comments in a
  local SQLite fixture.
- Tools: `search_workspace_items`, `create_workspace_task`, and
  `add_workspace_comment`.
- Candidates and policies: `synthesis.workspace_tasks` generates lookup, task
  creation, comment update, and branch fallback candidates with scripted
  policies.
- Runtime id: `workspace_tasks_fixture`.
- Run profile mode: `workspace_fixture`.
- Held-out suite: `workspace_tasks_heldout_v1`.

## Boundary Evidence

Workspace support is registered through `synthesis.domain_pipeline` and
`synthesis.runtime_registry`. Core consumers remain descriptor/session driven:

- `episode_quality.py` reads runtime identity and state-changing tools from
  descriptors.
- `episode_replay.py` rebuilds through the domain bundle and executes actions
  with `RuntimeSession.execute_action(...)`.
- `reward_labels.py` reads reward support and preference groups from
  descriptors.
- `rollouts.py` collects diagnostic episodes through runtime sessions.
- `mcp.py` exposes the generic runtime-backed local adapter shim.
- `profile_decisions.py` and `dataset_release.py` use domain-aware evidence
  fields without workspace allowlists.

`tests/test_domain_pack_contract.py` scans core consumers to prevent
workspace-specific branches or tool allowlists from entering those modules.

## Representative Commands

Replay and reward evidence:

```bash
uv run python main.py --run-profile tests/fixtures/run_profiles/workspace-tasks-fixture.json --write-episode-replay-report --write-reward-label-report --output-dir artifacts/workspace-third-domain-probe
```

Observed result: accepted `4`, rejected `0`, with replay and reward-label
reports written.

Evaluation and profile decision evidence:

```bash
uv run python main.py --run-profile tests/fixtures/run_profiles/workspace-tasks-fixture.json --write-evaluation-report --write-profile-decision-report --output-dir artifacts/workspace-third-domain-evaluation
```

Observed result: accepted `4`, rejected `0`,
`workspace_tasks_heldout_v1` passed, and profile promotion passed for
`workspace_tasks_fixture`.
