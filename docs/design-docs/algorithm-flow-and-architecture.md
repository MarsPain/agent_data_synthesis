# Agent Data Synthesis Algorithm Flow And Architecture

本文是一份面向理解的说明报告。它不替代 [../DESIGN.md](../DESIGN.md)、[../DATA.md](../DATA.md)、[../BACKEND.md](../BACKEND.md) 和 [../SECURITY.md](../SECURITY.md)，而是把当前代码、规范和 Agent data synthesis 思想串成一条更容易阅读的主线。

本项目的核心不是“批量生成问答文本”，而是生成可执行、可验证、可追溯的 Agent 训练轨迹。一个合格样本必须保留环境状态、工具能力、任务意图、动作、观察、最终回答、验证结果、质量判断和血缘元数据之间的关系。

## 1. 核心心智模型

Agent data synthesis 在本项目里是一条受治理的数据生产流水线：

```text
source bundle / fixture
  -> source governance gate
  -> executable environment
  -> typed tool registry
  -> seed and task curriculum
  -> candidate task
  -> candidate schema gate
  -> solution policy
  -> trajectory execution
  -> independent verification
  -> quality gates
  -> accepted sample or classified rejection
  -> dataset artifacts and quality report
```

这条链路里的关键判断是：训练数据不是孤立的 instruction/response 对，而是一个经过环境、工具、执行、验证和 lineage 共同约束的记录。

也可以把当前系统理解为三条相互连接的流：

```text
环境流: source bundle -> provenance/license/network/sandbox gates -> environment input -> SQLite world
生成流: seed -> task generation/expansion -> solution policy -> tool trajectory -> final response
治理流: contract validation -> verification -> quality gates -> rejection/review/sample -> manifest
```

当前 foundation implementation 入口位于 [../../synthesis/pipeline.py](../../synthesis/pipeline.py)。它使用 contacts fixture 或受控网络输入构建一个 SQLite-backed contacts environment，再围绕这个环境生成和验证工具使用样本。

主要模块包括：

- [../../synthesis/sources.py](../../synthesis/sources.py): source record、license decision、network policy、sandbox policy、controlled fetch 和 source-event audit。
- [../../synthesis/environments.py](../../synthesis/environments.py): contacts SQLite 环境、reset recipe、checkpoint/restore 和环境元数据。
- [../../synthesis/tools.py](../../synthesis/tools.py): typed tool registry、tool schemas、side effects、capability gap 和 curated tool admission。
- [../../synthesis/tasks.py](../../synthesis/tasks.py): candidate task、task suggestion、edited task、curriculum ordering 和 seed transformation。
- [../../synthesis/execution.py](../../synthesis/execution.py): solution policy、ordered tool steps、branch execution、trajectory capture 和 adapter routing。
- [../../synthesis/verification.py](../../synthesis/verification.py): independent verifier 和 state-aware checks。
- [../../synthesis/datasets.py](../../synthesis/datasets.py): accepted samples、rejections、manifest、quality report 和 lineage assembly。
- [../../synthesis/quality.py](../../synthesis/quality.py): duplicate detection、logical-support checks、review routing 和 quality slices。
- [../../synthesis/refinement.py](../../synthesis/refinement.py): repairability decision 和 critic/refinement rerun。
- [../../synthesis/mcp.py](../../synthesis/mcp.py): opt-in local MCP-compatible adapter boundary。
- [../../synthesis/roles.py](../../synthesis/roles.py): role registry 和 remote LLM role lineage。

## 2. 贯穿案例：从联系人任务到可验证样本

为了让后面的流程更直观，可以先看一个当前 foundation pipeline 已经支持的 case。

系统有一个 contacts environment，包含联系人：

```text
Alice Zhang -> alice.zhang@example.test
Ben Carter  -> ben.carter@example.test
```

候选任务是：

```text
Find Alice Zhang's email address using the contact database.
```

这不是直接交给模型回答的静态问题。pipeline 会把它变成一个 `CandidateTask`，至少包含：

```text
candidate_id: candidate_contacts_alice
instruction: Find Alice Zhang's email address using the contact database.
constraints.must_use_tool: lookup_contact_email
difficulty.tool_count: 1
tool_name: lookup_contact_email
arguments.name: Alice Zhang
expected_answer: alice.zhang@example.test
seed_ids: [...]
```

随后系统选择或生成一个 `SolutionPolicy`：

```text
policy_id: policy_candidate_contacts_alice
steps:
  - lookup_contact_email({"name": "Alice Zhang"})
final_response_template: "{name}'s email is {email}."
```

执行层不会让 policy 直接读取数据库。它只通过 `ToolRegistry` 调用声明过 schema 和 side effect 的工具。工具返回 observation 后，execution layer 记录轨迹：

```text
action: lookup_contact_email({"name": "Alice Zhang"})
observation: {"name": "Alice Zhang", "email": "alice.zhang@example.test"}
final_response: "Alice Zhang's email is alice.zhang@example.test."
```

然后 verifier 独立检查最终回答是否包含 expected answer。质量门再检查这个样本是否重复、最终回答是否被 observation 支撑。只有这些关口都通过，`datasets` 才会组装 accepted sample：

```text
environment + tools + task + trajectory + final_response
  + verifier + verification + quality + lineage
```

如果任务改成“找到 Ben Carter 的邮箱”，但 expected answer 错写成 `ben@example.test`，trajectory 仍然可以执行，但 verifier 会失败。这个 candidate 不会成为训练样本，而会进入 `rejections.jsonl`，带着 `verification_failed` 或更具体的 failure cause。

因此，系统训练出来的不是“会编答案”的文本，而是“在可执行环境里用工具完成任务，并能被独立验证”的轨迹。

## 3. 架构分层

整体架构可以简化成下面这张图：

```text
CLI / Local Runner
        |
        v
Foundation Pipeline
        |
        +--> Source Governance
        |       provenance / license / network / sandbox / audit
        |
        +--> Environment
        |       SQLite state / reset recipe / checkpoint
        |
        +--> Tool Registry
        |       schemas / side effects / handlers / capability gaps
        |
        +--> Task and Curriculum
        |       seeds / candidate tasks / expansion / difficulty
        |
        +--> Execution
        |       solution policy / tool steps / observations / branches
        |
        +--> Verification and Quality
        |       independent checks / duplicate gates / logical support / review
        |
        v
Dataset Artifacts
 samples.jsonl / rejections.jsonl / manifest.json / quality_report.json
```

最重要的方向约束是：生成者可以提出任务、策略、修复或工具 proposal，但不能自己认证样本有效。认证必须经过独立的 contract validation、environment execution、verifier 和 quality gates。

各层职责可以概括为：

- `Source Governance`: 决定 source bundle 是否能影响环境和数据集输出。它先于环境构建运行，避免不合格来源进入后续 pipeline。
- `Environment`: 拥有可执行状态和 business rules。当前实现是 contacts SQLite environment，后续可以扩展为 MCP-compatible environment server。
- `Tool Registry`: 暴露 Agent 可调用能力。工具有输入 schema、版本和 side-effect 标签，Agent 不能绕过工具直接改环境状态。
- `Task and Curriculum`: 从 seed 生成候选任务，并保留 difficulty、taxonomy、persona 或 expansion lineage。
- `Execution`: 执行 solution policy，捕获 action、observation、state_change 和 final_response。
- `Verification`: 用独立检查判断 trajectory 是否满足任务，而不是相信 generator 的自我声明。
- `Quality and Dataset Assembly`: 处理 duplicate、logical support、review routing、accepted sample assembly、rejection assembly 和 report generation。
- `Role Registry`: 管理 remote LLM-backed roles 的启用状态、输出类型和 lineage，防止未来角色在未明确启用前越界调用 provider。

## 4. Source 到 Environment 的治理流

当前 pipeline 的第一道门不是 task generation，而是 source governance：

```text
SourceBundle
  -> validate_source_bundle
       -> source record shape
       -> license policy decision
       -> network policy
       -> sandbox policy
  -> SourceGovernanceResult
  -> accepted provenance or source_policy_rejected
```

默认 foundation run 使用 fixture source bundle，不访问外部网络。只有显式启用 controlled network path 时，系统才会用 `FetchedSourceRequest` 拉取一个 allowlisted HTTPS JSON source，并把它转换成 `ContactsEnvironmentInput`。

受控网络路径的约束包括：

- URL 必须是 HTTPS。
- host 必须在 allowlist 中。
- request budget 必须为正。
- content type 必须是受支持的 JSON。
- payload size、timeout 和 redirect 行为受限。
- source audit 开启时只写 sanitized events，不写 raw payload 或 credential。

source bundle 通过后，environment layer 才能创建 SQLite world：

```text
source governance accepted
  -> source_provenance
  -> ContactEnvironment.create_fixture(...)
     or ContactEnvironment.create_from_input(...)
  -> environment metadata + reset recipe
```

如果 admitted source input 无法构建环境，pipeline 会生成 `source_policy_rejected` rejection，并写入 `environment_source_rejected` audit event。这个设计让“不合格来源”和“环境构建失败”不会伪装成普通 verifier failure。

## 5. Environment 与 Tool 的关系

当前环境是 `ContactEnvironment`。它拥有真实 SQLite state：

```text
contacts(name, email)
contact_followups(name, note, created_at)
```

工具是访问环境的受控接口：

```text
lookup_contact_email(name)        -> read_only
record_contact_followup(name,note)-> state_mutating
```

这个边界很重要。Agent 训练轨迹应该展示“通过工具观察和改变环境”的过程，而不是展示一个模型凭空声明结果。

当前工具注册流程是：

```text
ContactEnvironment
  -> build_contact_tool_registry(environment)
  -> ToolRegistry.register(ToolDefinition, handler)
  -> registry.export() enters sample.tools
```

工具调用执行时有三类基础保护：

- 工具名必须存在，否则产生 `ToolMissingError`。
- 参数必须符合 JSON-schema-like contract，否则产生 `ToolSchemaError`。
- 工具 handler 执行失败会被分类为 runtime failure 或 capability gap。

如果开启 branching，registry 还会使用 environment checkpoint/restore。每个 branch attempt 从同一个 baseline state 开始，失败分支不会污染后续 fallback 分支。

## 6. Task 与 Curriculum 生成流

任务生成层负责提出“在当前环境里可执行且可验证”的目标。当前默认 generator 是 deterministic foundation candidates；也可以通过 role registry 使用 remote LLM-backed task generation。

基础任务结构是 `CandidateTask`：

```text
candidate_id
instruction
constraints
difficulty
tool_name
arguments
expected_answer
seed_ids
generation_lineage
expected_state
branch_plan
```

这里的关键字段不是 instruction，而是 instruction 与 constraints、tool_name、arguments、expected_answer、expected_state 之间的一致性。一个 task 如果只在自然语言上合理，但要求不存在的工具、不可达的状态或无法验证的结果，就不应该进入 accepted sample。

当前任务生成有三条路径：

```text
default path:
  foundation_seed -> generate_foundation_candidates

remote generation path:
  foundation_seed -> task_generation role -> CandidateTask[]

task expansion path:
  seed transformations -> task_suggester -> task_editor -> CandidateTask[]
```

task expansion 特别强调 suggestion 和 edit 的分离：suggester 只提出 intent-level `TaskSuggestion`，editor 才能把 suggestion 变成候选任务，而且 edited task 仍必须走普通 candidate contract validation。被拒绝的 suggestion 或 edit 会进入 rejection artifacts，而不是静默消失。

## 7. Policy、Execution 与 Trajectory

CandidateTask 通过 schema validation 后，pipeline 会为它选择或生成 solution policy：

```text
CandidateTask
  -> validate_candidate_task
  -> _ensure_generation_lineage
  -> scripted_solution_policy or solution_policy role
  -> validate_solution_policy
```

`SolutionPolicy` 是“如何完成任务”的可执行计划：

```text
policy_id
role
steps: ToolStep[]
final_response_template
lineage
branch_plan
```

执行层按步骤调用工具，并把每一步写成 trajectory event：

```text
ToolStep
  -> action event
  -> registry.execute(...) or adapter_shim.call(...)
  -> observation event
  -> optional state_change event
  -> final_response event
```

最终 sample 的 trajectory 当前支持：

- `action`: 工具名和参数。
- `observation`: 工具返回的结构化结果。
- `state_change`: 工具造成的状态变化摘要。
- `final_response`: policy template 根据 observation 生成的最终回答。

如果启用 branch plan，execution layer 会按顺序尝试多个 branch：

```text
baseline checkpoint
  -> branch 1 from clean state
       -> accepted? yes: selected trajectory
       -> failed? record rejected branch outcome
  -> restore baseline
  -> branch 2
  -> ...
```

accepted sample 只保留 selected successful trajectory 作为顶层 trajectory，失败分支进入 `lineage.branching.branch_outcomes` 或 rejected details。这样训练样本保持干净，同时保留恢复路径证据。

## 8. Verification 与 Quality Gates

执行成功不等于样本合格。当前 `_run_candidate_attempt` 在 execution 后继续跑独立 verifier：

```text
ExecutionResult
  -> ExactAnswerVerifier.verify(...)
       -> final_response_contains_expected_answer
       -> optional state checks
  -> VerificationResult
```

对于 state-changing task，verifier 不只看最终文本，还会检查 environment state。例如 contact follow-up task 必须真的在 `contact_followups` 表里写入期望 note。

Verifier 通过后，quality gates 继续检查：

```text
candidate_duplicate_signature
  -> reject exact duplicate task + tool sequence

final_answer_is_logically_supported
  -> reject answer unsupported by observations/verifier expectation
```

这些 gates 的意义是把“可执行”“验证通过”“适合进入数据集”分开。一个 trajectory 可以运行，一个 verifier 可以通过，但如果它重复已有样本或最终回答无法从 observation 推出，仍然不应该进入 accepted dataset。

## 9. Rejection、Repair 与 Tool Expansion

pipeline 对失败的处理不是简单丢弃，而是分类、记录和可选修复。

常见 rejection causes 包括：

- `candidate_schema_error`: candidate task 形状不符合 contract。
- `tool_missing`: policy 需要的工具不存在。
- `tool_schema_error`: 工具参数不符合 schema。
- `tool_runtime_error`: 工具执行失败。
- `verification_failed`: verifier 未通过。
- `solution_logic_error`: 最终回答或状态逻辑不成立。
- `quality_duplicate`: 与已接受样本重复。
- `source_policy_rejected`: source governance gate 拒绝来源。
- `adapter_contract_rejected`: opt-in adapter path 的 request/result contract 失败。
- `llm_provider_error` 或 `llm_response_schema_error`: remote role 调用或响应结构失败。

如果失败暴露 capability gap，pipeline 可以选择请求一个 `tool_generation` proposal：

```text
ToolMissingError / ToolSchemaError
  -> CapabilityGap
  -> tool_generation role proposes ToolProposal
  -> admit_curated_tool(...)
       -> admitted: rerun same candidate
       -> rejected: attach proposal to rejection
```

这里的 tool generation 只允许输出结构化 proposal，不允许直接生成可执行代码或安装包。真正被加入 registry 的只能是 curated local implementation。

如果失败是 repairable verifier 或 logical-support 问题，pipeline 可以选择 critic/refinement：

```text
rejection
  -> repairable(cause)?
  -> critic_refinement role
  -> revised candidate or revised policy
  -> rerun execution + verification + quality gates
```

原始 failure 不会被覆盖。修复成功时，accepted sample 的 lineage 会记录 refinement attempt；修复失败时，rejection details 会保留 refinement 元数据。

## 10. MCP-Compatible Adapter Path

默认执行路径直接调用本地 `ToolRegistry`。当显式启用 `--enable-mcp-adapter` 时，同样的 policy steps 会通过 local in-process adapter shim：

```text
SolutionPolicy step
  -> ToolCallRequest envelope
  -> LocalContactsAdapterShim
  -> ToolCallResult envelope
  -> normal trajectory event + adapter lineage
```

这条路径的目标是验证未来 MCP-compatible 环境/工具边界，而不是启动外部 MCP server。当前 adapter path 明确排除：

- external MCP server discovery。
- browser automation。
- credential brokering。
- remote filesystem access。
- generated tool handlers。

Adapter metadata 不改变顶层 trajectory event contract。成功样本把 adapter call metadata 放在 `lineage.adapter`，adapter contract failure 进入 `adapter_contract_rejected`。

## 11. Dataset Assembly 与 Artifacts

一个 accepted sample 的形状由 [../DATA.md](../DATA.md) 约束。当前 `assemble_sample(...)` 会输出：

```text
sample_id
dataset_version
environment
tools
task
trajectory
final_response
verifier
verification
quality
lineage
```

lineage 是理解样本可信度的关键。它可能包含：

- source seed ids。
- generator role lineage。
- solution policy lineage。
- verifier id/version。
- source provenance。
- refinement lineage。
- tool expansion lineage。
- branching lineage。
- adapter lineage。
- seed transformation、task suggester 和 task editor lineage。

默认 artifact set 是：

```text
samples.jsonl          accepted training records
rejections.jsonl       classified rejected candidates
manifest.json          dataset counts, versions, artifact paths, lineage summaries
quality_report.json    rates, rejection causes, role outcomes, deterministic slices
```

可选 artifact 包括：

- `tool_proposals.jsonl`: capability gap、proposal 和 local admission decision。
- `source_events.jsonl`: sanitized source audit records。
- `review_queue.jsonl`: reviewable failures。
- `parent_comparison.json`: parent dataset comparison。

这些 artifact 的共同作用是让 dataset version 可复现、可审计、可比较，而不是只输出一批样本文本。

## 12. 当前实现与目标架构的关系

当前 foundation pipeline 是目标架构的本地、确定性、可测试切片。它故意把高风险自动化推迟到 contracts 稳定之后。

当前已经实现或部分实现的能力：

- SQLite-backed contacts environment。
- typed local tools with side-effect metadata。
- deterministic foundation tasks。
- optional remote LLM-backed task generation、solution policy、task suggestion、task editor、critic refinement 和 tool proposal roles。
- independent exact-answer/state verifier。
- source provenance、license、network、sandbox gates。
- controlled network-backed contacts source path。
- failure classification、review routing、quality report slices。
- branch plan execution with checkpoint/restore。
- local MCP-compatible adapter shim。
- accepted/rejected artifacts with lineage。

有意暂不做或仅作为未来方向的能力：

- 不部署本地 LLM cluster。
- 不允许未治理的 arbitrary generated code execution。
- 不默认抓取外部网络 source。
- 不让 judge-only result 认证 tool/environment task。
- 不把 MCP adapter 等同于外部 server discovery 或 credential broker。
- 不把 task generation、solution generation、verification 合并成一个不可审计的大模型调用。

这就是当前算法架构的核心：先构造一个可执行世界，再暴露受控工具，然后生成可验证任务，执行轨迹，独立验证，最后以完整 lineage 组装或拒绝样本。

## 13. 阅读路线

如果只想理解整体流程，先读本文。

如果要确认系统不变量，读 [../DESIGN.md](../DESIGN.md)。

如果要看完整目标架构和未来演进，读 [agent-data-synthesis-framework.md](agent-data-synthesis-framework.md)。

如果要理解 AWM environment model 等概念背景，读 [architecture-explainers.md](architecture-explainers.md)。

如果要看 sample、rejection、manifest、quality report 的字段契约，读 [../DATA.md](../DATA.md)。

如果要看模块边界和 job lifecycle，读 [../BACKEND.md](../BACKEND.md)。

如果要看 source、network、sandbox 和 generated-code 边界，读 [../SECURITY.md](../SECURITY.md)。
