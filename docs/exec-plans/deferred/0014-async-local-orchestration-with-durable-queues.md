# Plan 0014: Async Local Orchestration with Durable Queues and Manifest-Based Resumption

> **Legacy record.** This document preserves historical design and delivery
> analysis. Canonical desired behavior is in the
> [async local orchestration spec](../../product-specs/async-local-orchestration.md);
> current status and activation triggers live only in
> [ISSUE-0001](../../../.scratch/ISSUE-0001-async-local-orchestration.md).

## Status

Planned on 2026-05-23. **Deferred** — see the "补充思考" section for the
deferral rationale. Not scheduled for implementation until single runs exceed
~10 minutes or 100+ candidates.

## Goal

Add the first async orchestration layer for the local pipeline: job lifecycle
management, durable file-backed queues, manifest-based resumption, bounded
concurrency, cancellation, and per-role cost tracking. This plan should make
longer synthesis jobs recoverable and observable without introducing distributed
workers, external message brokers, or multi-process actors.

The default `uv run python main.py` behavior must remain synchronous,
deterministic, and unchanged. The async path should be an explicit opt-in
available from the CLI or programmatic API.

## Basis

This plan follows the MCP-compatible adapter boundary established in
[../completed/0013-mcp-compatible-environment-tool-adapters.md](../completed/0013-mcp-compatible-environment-tool-adapters.md).
The repository now has local executable environments, curated tools, role-backed
generation, refinement, tool expansion, branching, task expansion, source
provenance, controlled HTTPS ingestion, and a local MCP adapter shim.

Stage 4 in [../../ROADMAP.md](../../ROADMAP.md) continues with orchestration
before distributed workers or dashboards. The next narrow step is a durable,
resumable job runner that can manage candidate-level work items, survive
interruptions, report progress, and track per-role costs without adding external
infrastructure.

Relevant current constraints:

- [../../DESIGN.md](../../DESIGN.md) defines the `Orchestration` bounded context
  as owning job lifecycle, queues, concurrency, cancellation, retries, metrics,
  and worker placement. It currently has no runtime implementation.
- [../../BACKEND.md](../../BACKEND.md) states: "Start with a local async runner.
  Move to an actor or queue-based runner only when local orchestration cannot
  satisfy throughput goals."
- [../../DATA.md](../../DATA.md) requires versioned manifests, lineage, and
  quality reports. The orchestration layer must preserve and extend these
  artifacts rather than replace them.
- [../../SECURITY.md](../../SECURITY.md) requires external access to remain
  explicit, logged, bounded, and isolated from secrets. The orchestration layer
  must not introduce new secret surfaces or network connections.

## Scope

- Define a job lifecycle record with job id, status, created timestamp, config
  hash, target candidate count, and completion tracking.
- Define a durable work-queue record shape for candidate-level tasks, supporting
  pending, running, completed, failed, and cancelled states.
- Implement a file-backed queue (JSONL) that persists work items to the output
  directory and can be reloaded for resumption.
- Add an async local runner that consumes the queue with bounded concurrency,
  executes candidates through the existing pipeline, and writes results back to
  the queue and manifest.
- Add manifest-based resumption: if a job directory already contains a queue
  file and partial manifest, resume from the first pending or interrupted item
  instead of restarting.
- Add cancellation support via signal handling and a cooperative cancellation
  token that stops new work pickup and waits for in-flight candidates to finish.
- Add per-role cost tracking: remote LLM call counts, token estimates, and
  provider alias summaries per role, attached to the job record and quality
  report.
- Keep the existing pipeline modules (`synthesis.pipeline`, `synthesis.execution`,
  `synthesis.datasets`) intact. The orchestration layer should call them, not
  replace them.

## Out of Scope

- External message brokers (Redis, RabbitMQ, SQS, Pub/Sub).
- Distributed workers, Ray, Celery, multi-process actors, or container
  orchestration.
- A web service, REST API, gRPC service, or interactive control endpoint.
- Real-time dashboards, WebSocket progress streams, or metrics exporters.
- Row-level scheduling, message offloading, or worker placement logic for
  distributed topologies.
- Changing the default synchronous pipeline behavior.

## Architecture

The orchestration layer sits above `synthesis.pipeline` and below the CLI:

- `synthesis.orchestration` owns job records, queue records, queue file I/O,
  async runner lifecycle, concurrency semaphore, cancellation token, and
  per-role cost accumulation.
- `synthesis.pipeline` continues to own the synchronous candidate execution path.
  The orchestration runner calls `pipeline.run_candidate()` or an equivalent
  boundary for each queued work item.
- `synthesis.datasets` continues to write manifests, samples, rejections, and
  quality reports. The orchestration layer may aggregate per-job metadata into
  the manifest.
- `synthesis.quality` continues to compute quality slices. The orchestration
  layer adds job-level aggregates (total time, per-role cost, throughput) without
  changing slice semantics.
- `synthesis.llm` continues to own remote provider calls. The orchestration
  layer intercepts or records call metadata for cost tracking.
- `synthesis.roles` continues to guard enabled/disabled roles. The orchestration
  layer must not bypass role guardrails.
- `synthesis.sources` and `synthesis.mcp` remain unaffected at the pipeline
  level; their opt-in flags are passed through the job config.

Queue design:

- One queue file per job: `{output_dir}/queue.jsonl`.
- Each line is a work item with `item_id`, `candidate_index`, `status`,
  `attempt_count`, `created_at`, `started_at`, `completed_at`, `result_summary`,
  and `error_class`.
- The queue file is append-only for status transitions; the runner rewrites or
  appends status updates.
- On startup, the runner scans the queue file to compute the resumption offset:
  skip items with status `completed` or `failed` (if retries exhausted), and
  re-enqueue items with status `running` (treating them as interrupted).

## File Map

- Add `synthesis/orchestration.py` with job records, queue records, file-backed
  queue I/O, async runner, cancellation token, and cost tracker.
- Modify `synthesis/pipeline.py` if a clean programmatic boundary for single-
  candidate execution is needed. Prefer exposing an existing internal function
  rather than restructuring the pipeline.
- Modify `synthesis/datasets.py` only if the manifest needs job-level metadata
  fields (job id, queue path, resumption flag, total wall time).
- Modify `synthesis/quality.py` only if job-level aggregate slices are added.
- Modify `main.py` with an opt-in `--async` or `--enable-async-runner` flag,
  plus `--max-concurrency`, `--job-id`, and `--resume` options.
- Add `tests/test_orchestration.py` for queue I/O, resumption logic, cancellation,
  and cost tracking.
- Extend `tests/test_cli.py` for async runner flags and no-op behavior when
  disabled.
- Update [../../BACKEND.md](../../BACKEND.md), [../../DATA.md](../../DATA.md),
  and [../../ROADMAP.md](../../ROADMAP.md) as implementation details settle.

## Implementation Tasks

### Task 1: Define Job and Queue Contracts

- [ ] Add a `JobRecord` with job id, status, config hash, created timestamp,
  target count, completed count, failed count, cancelled flag, and total wall
  time.
- [ ] Add a `QueueItem` record with item id, candidate index, status,
  attempt count, timestamps, result summary, and error class.
- [ ] Add a `JobCostRecord` with per-role call counts, token estimates, and
  provider alias summaries.
- [ ] Add contract tests for invalid state transitions, missing job ids, and
  malformed queue items.

### Task 2: Implement File-Backed Queue and Resumption

- [ ] Implement queue file creation, append, and idempotent status updates.
- [ ] Implement queue reload that computes resumption offset and resets
  interrupted `running` items to `pending`.
- [ ] Ensure queue file is written atomically or with append semantics to avoid
  corruption on crash.
- [ ] Add tests for queue creation, append, reload, resumption, and corruption
  recovery.

### Task 3: Add Async Local Runner

- [ ] Build an async runner that reads pending queue items, bounds concurrency
  with a semaphore, and calls the existing pipeline for each candidate.
- [ ] Write status transitions (`pending` → `running` → `completed`/`failed`)
  back to the queue file.
- [ ] Aggregate results into the existing manifest, samples, rejections, and
  quality report artifacts.
- [ ] Add tests proving the async runner produces the same artifacts as the
  synchronous pipeline for a deterministic fixture.

### Task 4: Add Cancellation and Signal Handling

- [ ] Add a cooperative cancellation token that stops new work pickup.
- [ ] Add SIGINT/SIGTERM handlers that set the cancellation token and wait for
  in-flight candidates to reach a terminal state.
- [ ] Ensure partial job output is valid and resumable after cancellation.
- [ ] Add tests for cancellation mid-job and resumption from the cancelled state.

### Task 5: Add Per-Role Cost Tracking

- [ ] Record each remote LLM call by role name, provider alias, model id, and
  estimated token count.
- [ ] Aggregate into `JobCostRecord` and attach to the job record and quality
  report.
- [ ] Ensure secrets (API keys, headers) are never written to queue files,
  job records, or cost artifacts.
- [ ] Add tests for cost accumulation accuracy and redaction.

### Task 6: Add CLI and Default-Path Stability

- [ ] Add `--enable-async-runner`, `--max-concurrency`, `--job-id`, and
  `--resume` CLI flags.
- [ ] Keep normal `uv run python main.py` synchronous and deterministic.
- [ ] Add CLI tests for missing flags, invalid concurrency values, resumption
  without an existing queue, and successful async fixture runs.

### Task 7: Docs and Validation

- [ ] Update backend and data docs with job lifecycle, queue contracts, and
  resumption behavior.
- [ ] Update roadmap wording once the local async runner exists.
- [ ] Run `uv run python scripts/validate_docs.py`.
- [ ] Run `uv run python -m unittest`.
- [ ] Run a deterministic async fixture command and confirm artifact equivalence
  with the synchronous path.

## Validation

- `uv run python scripts/validate_docs.py`
- `uv run python -m unittest`
- Deterministic async fixture command that produces manifest, samples,
  rejections, and quality report artifacts equivalent to the synchronous path.

## Acceptance Criteria

- Default local synthesis remains synchronous and performs no async execution
  unless explicitly enabled.
- The async runner uses a durable file-backed queue that survives process
  interruption and supports resumption.
- Resumption skips completed items and re-enqueues interrupted items without
  data loss or duplicate samples.
- Cancellation stops new work pickup and waits for in-flight candidates to
  finish, leaving valid partial artifacts.
- Per-role cost tracking records call counts and token estimates without
  exposing secrets.
- The async runner produces the same deterministic artifacts as the synchronous
  pipeline for identical inputs.
- Source governance, sandbox policy, role guardrails, MCP adapter, and network
  source controls remain enforced in the async path.
- Documentation validation and the unit suite pass.

## Risks

- File-backed queues can corrupt on hard crashes. Use append-only writes and
  validate queue file integrity on reload.
- Async execution can introduce subtle ordering differences. Use equivalence
  tests against the synchronous path.
- Cancellation can leave candidates in ambiguous states. Define clear terminal
  states and treat `running` items as interrupted on resumption.
- Cost tracking can leak provider details. Record only aliases, model ids,
  hashes, counts, and estimates; never write API keys or raw prompts.
- The async runner can become a bypass around existing pipeline controls. Ensure
  it calls the same pipeline boundary and does not reimplement source,
  sandbox, or role logic.

## Notes

This plan creates the local orchestration boundary needed before distributed
workers or external queues are considered. It is intentionally not a distributed
scheduler or cluster orchestration plan.

## 补充思考：当前阶段的必要性评估（备忘）

> 以下分析基于 2026-05-23 对实际代码和运行模式的检查。

### 当前状态：0014 在默认模式下是过度设计

- `generate_foundation_candidates()` 默认仅生成 **3 个硬编码 fixture 候选**（Alice、Ben、followup），启用 branching 后也才 4 个。
- 无 `--use-llm` 时单次运行**秒级完成**，无网络调用。
- 即使启用 `--use-llm`，候选数量也受模型输出限制，通常仅为十几个到几十个。

在这种量级下：
- **并发**：3–4 个候选不需要并发调度。
- **断点续传**：崩了重来只需几秒，恢复价值极低。
- **成本追踪**：无远程调用时成本为零；小规模 LLM 调用下账单本身也有限。
- **优雅取消**：Ctrl+C 后重新运行的成本远低于实现取消机制的工程成本。

### 0014 的真实价值：规模跃迁时的系统性瓶颈

0014 不是解决"现在需要什么"，而是解决"未来想变成什么"。其价值在以下三种规模瓶颈中显现：

**瓶颈 1：候选内部的隐性串行**

即使只有 10 个候选，每个候选内部的调用链已很长：
1. LLM 生成任务描述
2. LLM 生成解决方案策略
3. 执行工具调用（本地，快）
4. 验证失败 → LLM Critic 诊断
5. LLM Refinement 修复 → 重新执行

一个候选平均 4–5 次串行 LLM 调用。10 个候选 × 5 次调用 = 50 次远程请求，串行总时间 1–2 分钟。async 并发可将这些调用"交错"执行。

**瓶颈 2：API 费用的浪费**

假设生成 500 个候选（约 2500 次 LLM 调用），跑到第 499 个时网络闪断崩溃。

- **无 0014**：磁盘上虽有结果文件，但无法确认"哪些已完成质量门、哪些已写入 manifest、哪些只写了一半"。为数据一致性，只能全部重来，已花费的 API 费用浪费。
- **有 0014**：`queue.jsonl` 精确记录每个候选状态，重启后跳过 completed，仅重做 interrupted。

**瓶颈 3：成本归因**

当项目从"个人实验"变成"团队协作"时，需要回答："上个月数据生成花了多少 API 费用？哪个角色最耗 token？"没有 per-role cost tracking，只能看到一笔模糊账单，无法优化。

### 项目定位决定优先级

| 场景 | 描述 | 0014 优先级 |
|------|------|-----------|
| **A. 本地原型验证工具** | 每次生成 3–50 条 fixture 数据，验证管道正确性 | **低**。同步运行 + 手动重试足够 |
| **B. 小型数据生产工具** | Overnight 生成 500–2000 条数据 | **中**。需要恢复机制和成本追踪，但并发控制可简化 |
| **C. 可扩展数据工厂** | 多领域、多种子、大规模生成，未来可能分布式 | **高**。是所有后续扩展的基础设施前提 |

### 建议的触发启动条件

不要因"计划已写"而提前执行。建议在以下真实痛点出现时启动 0014：

1. 开始实际使用 `--use-llm` 跑大规模生成，且**单次运行超过 10 分钟或 100+ 候选**。
2. 第一次遇到"跑了 2 小时崩了，不敢确定哪些结果可用"的恢复痛点。
3. 需要向团队/上级汇报**精确的数据生成成本**（per-role、per-provider）。
4. 项目从 Stage 4 的"MCP 适配"阶段，明确过渡到"大规模生产"阶段。

### 当前更紧迫的事项

在 0014 之前，以下两项 tech-debt 的 ROI 更高：

- **Generated code sandboxing**（tech-debt #1）：安全债。工具扩展（plan 0008）已允许结构化工具提案，但任何生成代码的执行缺乏隔离。越早修复成本越低。
- **Semantic duplicate detection**（tech-debt #2）：质量债。当前仅支持 exact duplicate（任务文本 + 工具序列完全匹配），语义等价（意图相同但表述不同）会膨胀数据集并扭曲 curriculum 指标。

### 一句话总结

> **0014 是一双跑鞋。如果每天只走 50 米，穿跑鞋没必要；但如果计划开始每天跑 5 公里，跑鞋就是必需的基础设施。当前项目还在"50 米散步"阶段。**

**工程建议**：保持 `_run_candidate_attempt()` 的纯净性（不依赖外部可变状态），为未来的 async 封装预留边界，但暂不实现 orchestration 层。
