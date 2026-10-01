# Agent Data Synthesis

[English](README.md)

本项目使用 Agent-first 引擎，从 Contacts、Mobile Messages 和 Workspace Tasks
三个本地 Domain 生成可执行的 Agent Episode。引擎负责有界模型请求、隔离执行、
确定性准入、私有 SQLite 状态、回放以及经过净化的数据集输出。默认质量模式是
shadow；确定性准入不等于人工批准。

## 快速开始

需要 Python 3.13 或更新版本，以及 `uv`。

```bash
uv sync
uv run python main.py --help
uv run python scripts/validate_docs.py
uv run python -m unittest
```

`main.py` 提供 `run`、`resume`、`replay`、`create-review-queue` 和
`import-review-labels` 命令。
运行时须提供经过验证的配置，以及离线脚本响应或单独授权的远程模型。
默认不会调用模型服务。用法见[运行手册](docs/OPERATIONS.md)。

三 Domain 冻结队列共 120 条。AI 诊断审核为 106 条通过、13 条失败、
1 条存疑；它不构成直接人工验收。操作人明确要求在此例外下推进切换。
当前状态见[工作跟踪](.scratch/README.md)。

[架构](ARCHITECTURE.md) · [术语](CONTEXT.md) · [文档目录](docs/README.md) · [Agent 工作规则](AGENTS.md)
