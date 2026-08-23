# Agent Data Synthesis（智能体数据合成）

[English](README.md)

Agent Data Synthesis 是一个本地优先的 Python 框架，用于生成、执行、验证和
打包智能体训练数据。只有可执行环境状态、工具调用、观察结果、验证、数据血缘和
质量证据共同支撑的记录才会被接受；它不是简单扩展指令—回答对的工具。

## 当前状态

项目仍处于早期阶段，但框架已经可用。默认工作流离线且具确定性；目前通过统一的
领域流水线边界支持 Contacts、合成移动消息和 Workspace 任务三类领域。

- 默认运行同步的本地基础流水线。经过验证的运行配置（run profile）可选择启用
  持久化本地编排，获得有界并发、恢复、取消和脱敏使用量证据。
- 受治理的数据源、隔离的候选任务执行、任务契约与状态验证、重放、奖励标签、
  留出集评估、覆盖率证据、发布准入报告以及哈希绑定的证据包，均已实现为显式
  可选能力。
- 一次经单独授权、使用真实 Provider 的 Workspace 验收已经完成，其脱敏证据可
  离线重放。该证据仅建立一个 **Release Candidate**，不代表发布批准、训练建议或
  下游模型效果提升。
- 本地 LLM 服务、分布式工作节点、外部 MCP 服务器以及独立发布 `awm_runtime`
  包仍在延期范围内。

实时工作状态、依赖关系和技术债以
[本地问题跟踪器](.scratch/README.md)为准；它是这些信息在仓库中的唯一事实来源。

## 环境要求

- Python 3.13 或更新版本
- [uv](https://docs.astral.sh/uv/)

## 快速开始

```bash
uv sync
uv run python main.py
uv run python scripts/validate_docs.py
uv run python -m unittest
```

默认运行将输出写入 `artifacts/foundation/`：

```text
samples.jsonl
rejections.jsonl
manifest.json
quality_report.json
```

## 选择工作流

### 运行本地域配置

使用仓库中已检入的配置运行 Workspace 路径，并写出可执行重放和奖励标签证据：

```bash
uv run python main.py \
  --run-profile tests/fixtures/run_profiles/profile-local-workspace-tasks.json \
  --write-episode-replay-report \
  --write-reward-label-report \
  --output-dir artifacts/profile-local-workspace
```

### 在不调用 Provider 的情况下检查覆盖率

覆盖计划预览在本地执行，不会创建 Provider 客户端：

```bash
uv run python main.py \
  --run-profile tests/fixtures/run_profiles/contacts-coverage-smoke.json \
  --preview-coverage-plan
```

### 使用异步或 Provider 支持的工作流

- 有关持久化本地作业、恢复、取消和 Provider 调用预算，请参阅
  [本地合成运维指南](docs/OPERATIONS.md)。
- `--use-llm` 调用与 OpenAI 兼容的远程 API。请在环境中配置凭据；框架不会将
  密钥、原始 Provider 载荷、提示词或私有源数据行写入持久化的公开产物。请参阅
  [安全说明](docs/SECURITY.md)。
- 如需发布报告、发布包、质量审计及产物模式，请先阅读
  [数据说明](docs/DATA.md)，并以 `uv run python main.py --help` 作为当前 CLI
  契约。
- Live Workspace 验收是单独的、会产生 Provider 成本的命令；每次尝试均须重新
  获得明确授权。它不是普通测试或默认流水线模式，请遵循其
  [操作流程](docs/OPERATIONS.md#live-workspace-release-candidate-acceptance)。

所有非默认产物类别都需显式启用。证据与资格认定产物本身不会发布数据集、授权训练，
也不证明下游收益。

## 文档导航

- [ARCHITECTURE.md](ARCHITECTURE.md) — 顶层领域与包结构图。
- [CONTEXT.md](CONTEXT.md) — 规范的领域术语表。
- [docs/README.md](docs/README.md) — 核心文档、深度设计、规格、ADR、参考资料、
  生成分析和历史记录的索引。
- [docs/DESIGN.md](docs/DESIGN.md) — 系统契约与限界上下文。
- [docs/OPERATIONS.md](docs/OPERATIONS.md) — 异步与经明确授权的 Live Provider
  操作。
- [docs/DATA.md](docs/DATA.md) — 模式、产物类别、数据血缘与质量规则。
- [docs/SECURITY.md](docs/SECURITY.md) — 数据源、沙箱、Provider 与密钥处理边界。
- [AGENTS.md](AGENTS.md) — 面向编码智能体的精简工作地图与操作约束。

## 仓库约定

- 根目录文件是导航图；规范的设计、规格和操作细节位于 `docs/` 下。
- `CONTEXT.md` 负责术语，`.scratch/` 负责当前工作状态。
- 运行时产物位于 `artifacts/`。
- 修改实现时，应同时更新受影响的文档。
