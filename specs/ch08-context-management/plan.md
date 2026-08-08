# ch08：上下文管理 Plan

## 状态

- 阶段：已批准（2026-08-08）。
- 上游文档：`spec.md` 已于 2026-08-08 批准。
- 本文档已完成逐段确认；实现必须遵守本文档的架构边界。

## 设计总览

ch08 在现有 `Agent → LLMRequest → LLMClient` 主链路中加入一个长生命周期的 `ContextManager`。它由当前会话的 `Agent` 持有，负责：

1. 接收一轮完整工具结果，在写入 Conversation 和 TUI 前执行落盘与预览替换。
2. 在每次主模型请求前估算完整请求 Token。
3. 达到阈值时调用独立摘要 Client，生成压缩后的历史。
4. 保存替换账本、usage 锚点、摘要熔断计数和会话目录。

```text
TUI 创建主 Client + 摘要 Client
  ↓
创建一个长生命周期 Agent + ContextManager
  ↓
用户输入
  ↓
Agent 生成本轮唯一 tools 定义列表
  ↓
ContextManager.prepare_request(...)
  ├─ 对历史中遗漏的大结果执行第 1 层
  ├─ 估算 Token
  └─ 必要时调用摘要 Client 并返回压缩历史
  ↓
Agent 组装 LLMRequest 并调用主 Client
  ↓
模型请求工具
  ↓
PermissionEngine + ToolScheduler + ToolRegistry
  ↓
ContextManager.process_tool_results(...)
  ├─ 单条 50KB 判断
  └─ 单轮 200KB 聚合判断
  ↓
处理后的 ToolResult → TUI + Conversation
```

## 为什么不照搬教材的 SessionRuntime

教材对应的 MewCode 会在每轮输入时重建 Agent，因此需要额外 `SessionRuntime` 保存跨轮状态。Dragon Code 在选择 Provider 后只创建一次 Agent，并在整个进程会话中复用：

```text
DragonCodeApp._activate_provider()
  ↓
Agent(...) 只创建一次
  ↓
多次 Agent.run(...)
```

因此本章直接让 `Agent` 持有一个 `ContextManager`。替换账本、熔断计数和 Token 锚点自然跨多轮存在，不增加只为绕过旧生命周期而设的容器。

## 新增包结构

```text
src/dragon_code/context/
├── __init__.py
├── constants.py
├── state.py
├── summary.py
└── manager.py
```

### `constants.py`

集中保存 Spec 已批准的固定阈值：

- 工具结果单条和单轮字节限制。
- 预览行数和字节数。
- Token 估算比例。
- 自动和手动安全余量。
- 近期历史下界。
- 熔断阈值。

这些值不从 YAML 读取，避免配置面无限扩大。

### `state.py`

保存简单状态类型，不包含 Provider 调用：

- `SessionPaths`：会话 ID、会话目录、工具结果目录。
- `ReplacementDecision`：某个调用 ID 的保留或替换决定、稳定预览和文件路径。
- `ReplacementLedger`：调用 ID 到冻结决定的映射。
- `UsageAnchor`：最近一次主请求真实 usage、该响应结束时已被 usage 覆盖的字符量以及是否有效。
- `CompactCircuitBreaker`：自动摘要连续失败次数与熔断状态。
- `CompactStats`：压缩原因、前后 Token、落盘数量和错误。

Dragon Code 当前由一个 asyncio 事件循环串行驱动单会话；状态方法保持同步和短小。真正的磁盘 I/O 使用 `asyncio.to_thread`，且所有状态只通过 `ContextManager` 修改。这样不引入不必要的异步锁，同时保留以后加锁的单一入口。

### `summary.py`

只放可离线测试的摘要纯逻辑：

- 把协议无关 `ChatMessage` 序列化为稳定文本。
- 构造禁止工具调用的摘要 Prompt。
- 提取并校验 `<summary>`。
- 从尾部选择同时满足 10000 Token 和 5 条消息的近期原文。
- 修正边界，避免拆开 Assistant ToolCall 与 Tool Result。
- 构造“摘要 + 固定边界提示 + 近期原文”的新历史。

### `manager.py`

实现 `ContextManager`，作为 Agent 的窄入口：

- `process_tool_results(results)`：处理一轮完整结果，返回可写入 TUI/Conversation 的新结果列表。
- `prepare_request(...)`：在普通请求前执行兜底第 1 层、Token 估算和可选自动摘要。
- `force_compact(...)`：手动 `/compact` 共用的摘要路径。
- `record_main_usage(...)`：只记录主请求的 usage 锚点。
- `cancel_active()`：取消正在运行的摘要请求。

具体命名可在实现中保持等价微调，但 Agent 只依赖这一组职责，不直接操作账本或熔断器。

## 核心数据流

### 1. Provider 配置和两个 Client

`ProviderConfig` 新增：

```text
context_window: int
summary_model: str | None
```

配置解析阶段完成默认值：

- Anthropic：200000。
- OpenAI：128000。

`summary_model` 保留 `None` 表示回退主模型。选择 Provider 后：

1. 原配置创建主 `LLMClient`。
2. 使用 `dataclasses.replace` 复制配置，只把 `model` 换成 `summary_model or model`。
3. 复制配置创建摘要 `LLMClient`。
4. 两个 Client 使用相同协议、API Key 和 `base_url`，但保持不同对象和模型名。

不修改 `LLMRequest` 增加临时 model 字段，避免模型覆盖逻辑渗透到 Provider 适配层。

### 2. 会话目录

选择 Provider 并创建 Agent 时生成一次会话 ID：

```text
<unix_timestamp>-<8位十六进制随机值>
```

目录固定为：

```text
<working_dir>/.dragon-code/sessions/<session_id>/tool-results/
```

调用 ID 不能直接作为不可信路径拼接。文件名使用“安全可读前缀 + 调用 ID 哈希”，并在预览元信息中保留原始调用 ID。这样兼容 Windows 非法字符，也避免不同非法字符清洗后产生同名文件。

`.gitignore` 增加 `.dragon-code/sessions/`，防止运行产物被提交。退出时不删除目录。

### 3. 工具结果处理位置

现有 `_execute_tools()` 会在每个批次完成时立即发出 `tool_end`。为了执行单轮 200KB 聚合判断，本章调整为：

1. 权限检查和调度行为保持不变。
2. 保留所有结果的模型原始调用顺序。
3. 一轮所有工具调用完成后，将完整 `list[ToolResult]` 一次性交给 `process_tool_results()`。
4. 得到预览替换后的结果后，再按原顺序发出 `tool_end`，并写入 Conversation。

这样 TUI 和 Conversation 永远看到同一份处理结果，也不会先展示原文、随后历史却变成预览。

`ToolScheduler`、`PermissionEngine` 和 `ToolRegistry` 不感知上下文压缩。

### 4. 移除工具内提前截断

以下工具改为返回本次完整文本：

- Read：不再按 2000 行或 100000 字符丢弃后半内容。
- Bash：保留完整 stdout/stderr。
- Glob/Grep：保留完整匹配列表和命中行。
- MCP：不再按 100000 字符截断转换结果。

工具仍可通过元数据报告行数、匹配数和退出码。统一结果处理会在内容进入历史前立刻落盘，因此大文本只在内存中短暂存在。

Write/Edit 等小结果也经过统一入口，但通常不会达到阈值。

Read 同时增加向后兼容的行分页参数 `offset`（默认1）和 `limit`（默认读取到末尾）。
工具结果预览包含总行数和分页调用示例，使模型能够分段恢复落盘文件，并避免整体重读后
再次超过50KB而只得到另一份预览。

### 5. 落盘事务和冻结账本

处理每个候选结果时采用以下顺序：

```text
读取账本
  ├─ 已有决定 → 直接复用
  └─ 没有决定
       ↓
     计算是否替换
       ├─ 保留 → 记录保留决定
       └─ 替换
            ↓
          写临时文件
            ↓
          原子改名到最终路径
            ↓
          构造稳定预览
            ↓
          记录替换决定
```

只有最终文件存在后才记录替换决定。任何文件异常都删除本次临时文件、保留原内容且不写账本，下一轮可以重试。

预览由一个确定性函数生成；相同原文、路径和调用 ID 必须得到逐字节相同结果。

### 6. 未提交用户消息与历史替换

当前 `Conversation.build_request_messages()` 会把本轮用户输入追加到历史副本，但在主请求成功或产生工具调用前不正式提交。自动压缩不能意外改变这项语义。

因此 `prepare_request()` 分开接收：

- 已提交历史：`Conversation.get_messages()`。
- 待发送消息：当前尚未提交的用户消息，或空列表。
- 请求附加项：system、tools、reminder。

自动摘要只整体替换“已提交历史”，待发送用户消息始终原样追加在压缩历史之后并参与 Token 估算。主请求失败时，待发送消息仍不会被写入 Conversation。

当 Agent Loop 已经执行过工具后，本轮用户消息、Assistant ToolCall 和 Tool Result 都已提交，此时待发送列表为空，压缩作用于完整已提交历史。

`Conversation` 新增深拷贝式整体替换入口，避免调用方之后修改传入列表污染内部状态。

### 7. 每轮只生成一次工具定义

每次 Agent 迭代开头执行一次：

```text
tool_definitions = active_registry.definitions()
```

同一个列表同时用于：

- Token 估算。
- 最终 `LLMRequest.tools`。

本章不把工具列表重复渲染到压缩历史，所以不需要教材中为恢复段设计的列表引用身份断言；但仍避免同一轮独立计算两次导致工具动态变化。

### 8. Token 估算

先把本次请求转换成稳定的“估算字符量”，覆盖：

- `SystemPrompt.stable` 和 `environment`。
- 全部 `ChatMessage` 文本、工具调用参数和工具结果。
- 全部工具名称、描述和 JSON Schema。
- reminder。

没有有效锚点或完成历史压缩后：

```text
estimated = ceil(total_characters / 3.5)
```

存在有效主请求锚点时：

```text
delta = max(0, current_characters - anchor_characters)
estimated = anchor_tokens + ceil(delta / 3.5)
```

`anchor_tokens` 使用最近一次主请求 usage 的 input、output、cache read、cache write 之和。每次主请求结束后替换锚点，不累计多次请求；摘要 usage 不进入锚点。

真实 usage 已经包含该次 Assistant 文本或 ToolCall 输出，因此 `anchor_characters` 不能只记录请求发出前的字符量。主响应收集完成后，以“本次请求字符量 + 本次 Assistant 响应的稳定序列化字符量”作为锚点字符位置：

- 下一轮新增用户消息按增量估算。
- Assistant 已被 usage 计算，不会再作为增量重复计算。
- 随后才产生的 Tool Result 不在该次 provider usage 中，会自然落入下一轮字符增量。

如果主响应没有合法完成或被取消，不更新锚点。

若当前字符量小于锚点字符量，说明历史发生了替换或压缩，旧锚点失效，回退到全量字符估算。

### 9. 自动压缩时序

每次主 API 请求前：

```text
准备本轮唯一 tool_definitions
  ↓
兜底处理已提交历史中的工具结果
  ↓
估算完整请求 Token
  ↓
熔断器是否允许自动摘要？
  ↓
是否达到 context_window - 33000？
  ├─ 否 → 直接发主请求
  └─ 是
       ↓
     发 compact_start 事件
       ↓
     用摘要 Client 请求摘要
       ├─ 成功 → 替换已提交历史、重置锚点、发 compact_end
       └─ 失败 → 原历史不变、记录失败、发 compact_warning、继续主请求
```

第三次连续自动失败时一并发出熔断提示。熔断后自动路径不再调用摘要 Client；手动路径仍可调用。

### 10. 摘要请求和解析

摘要 Client 仍使用现有 `LLMClient.stream(LLMRequest)`，但传入：

- 独立的摘要 System Prompt。
- 序列化后的待压缩历史。
- 空工具列表。
- 无 Plan reminder。

摘要流可复用 `StreamCollector` 收集完整文本与工具调用。以下情况失败：

- 出现任何 ToolCall。
- 流或 Provider 抛错。
- `<summary>` 缺失、为空或出现多个歧义区间。
- 取消任务。

取消异常继续向上传播，不计入自动摘要失败；用户取消不应误触发熔断。

### 11. 近期原文选择

从待压缩历史尾部按“消息组”选择，不直接按单条消息截断：

- 普通 user/assistant 文本各自是一组。
- 带 ToolCall 的 assistant 与紧随其后的 tool message 为不可分割组。

从尾部累加整组，直到同时满足：

- 估算不少于 10000 Token。
- 消息不少于 5 条。

如果整段历史都不足下界，则保留全部。选择结果使用深拷贝，顺序不变。

### 12. 压缩后消息形态

为了让 OpenAI 和 Anthropic 都接受历史开头，摘要和边界提示合并为一条 `role="user"` 的协议无关消息：

```text
<context-summary>
九部分摘要
</context-summary>

<context-boundary>
需要精确文件、错误或代码时请使用 Read 重读，不要根据摘要猜测。
</context-boundary>
```

随后追加近期原文。Provider 继续通过现有适配器转换协议；不新增 Provider 专属压缩逻辑。

如果近期原文第一条也是 user 消息，允许内部历史出现相邻 user 消息；Anthropic 会按协议合并连续同角色消息，OpenAI 也接受连续 user 消息。工具调用/结果配对保持完整。

### 13. 手动 `/compact`

TUI 现有命令判断新增 `/compact` 分支，不创建通用命令注册表。

```text
用户输入 /compact
  ↓
确认当前状态 IDLE 且 Agent 可用
  ↓
禁用输入，显示“正在压缩上下文”
  ↓
await Agent.force_compact()
  ├─ 成功 → 显示 before → after
  └─ 失败 → 显示压缩失败，历史不变
  ↓
恢复 IDLE
```

手动路径跳过自动阈值和熔断，不改变自动失败计数。摘要输入超过 `context_window - 23000` 时直接安全失败；本章不实现丢旧消息组后重试。

`/help` 增加命令说明。

### 14. TUI 和 AgentEvent

在统一模型中新增 `CompactEvent`，包含：

- `phase`：自动开始、自动完成、自动失败、熔断、手动完成、手动失败。
- `before_tokens`、`after_tokens`。
- `offloaded_results`。
- 安全的公开错误文本。

`AgentEvent` 增加可选 `compact` 字段。自动压缩通过 Agent 事件流交给 TUI；手动压缩由 TUI 调用 Agent 方法后使用同一个格式化函数展示，避免两套文案漂移。

### 15. 取消和错误边界

- `ContextManager` 保存当前摘要流的活动任务；`Agent.request_cancel()` 同时取消主请求、工具调度和摘要任务。
- `CancelledError` 原样传播且不计入熔断。
- 落盘异常转成安全警告，不显示绝对敏感路径之外的堆栈。
- 摘要异常转换成公开错误，不回显 SDK 原始请求或密钥。
- 自动摘要失败后继续主请求；主请求自身 `prompt_too_long` 仍走现有 LLM 错误流程，本章不重试。

## 现有文件改动

| 文件 | 计划改动 |
|---|---|
| `src/dragon_code/models.py` | Provider 新字段、CompactEvent、AgentEvent 扩展 |
| `src/dragon_code/config.py` | 解析 `context_window`、`summary_model` 和协议默认值 |
| `.dragon-code/config.yaml.example` | 展示新增配置 |
| `.gitignore` | 忽略 `.dragon-code/sessions/` |
| `src/dragon_code/session.py` | 深拷贝式整体替换历史 |
| `src/dragon_code/agent.py` | 接入 ContextManager、延后 tool_end、每轮唯一工具定义、usage 锚点、自动和手动压缩 |
| `src/dragon_code/tui.py` | 创建摘要 Client、`/compact`、帮助和压缩状态展示 |
| `src/dragon_code/tools/file_tools.py` | Read 返回完整本次结果 |
| `src/dragon_code/tools/bash.py` | 保留完整 stdout/stderr |
| `src/dragon_code/tools/search_tools.py` | Glob/Grep 返回完整结果 |
| `src/dragon_code/mcp/tool.py` | MCP 返回完整转换结果 |

Provider 的 OpenAI/Anthropic 序列化逻辑原则上不改；摘要仍走统一 `LLMRequest`。

## 测试组织

新增：

```text
tests/test_context_state.py
tests/test_context_summary.py
tests/test_context_manager.py
```

扩展：

- `test_config.py`：新字段、默认值、非法值、旧配置兼容。
- `test_agent.py`：工具结果处理时序、自动摘要事件、主 usage 锚点、失败继续、取消。
- `test_tui.py`：`/compact`、帮助、成功失败文案和运行中保护。
- 各工具测试：由“内部截断”调整为“返回完整结果，统一管理器落盘”。
- Client 测试：摘要请求 tools 为空、摘要模型名正确。

所有摘要测试使用 fake `LLMClient`，不依赖网络。

## 关键技术取舍

### 取舍 1：集中处理，不让每个 Tool 自己落盘

- 优点：内置工具和 MCP 行为一致；阈值、预览、账本和错误处理只有一份。
- 代价：Agent 必须等本轮所有结果齐全后才能发出最终 `tool_end`。

### 取舍 2：两个 Client 对象，不在单个请求覆盖模型

- 优点：协议层保持简单；主模型与摘要模型职责清楚；测试容易隔离。
- 代价：TUI 激活 Provider 时会创建两个 SDK Client。

### 取舍 3：只压缩已提交历史

- 优点：保留现有“主请求失败时不提交当前用户消息”的语义。
- 代价：当前新用户消息不会进入本次摘要，但会原样附在摘要历史后，因此不会丢失意图。

### 取舍 4：本章不做 PTL 紧急恢复

- 优点：先交付教材主体两层压缩，控制复杂度。
- 代价：估算偏差、摘要模型故障或熔断后继续增长仍可能让主 Provider 返回上下文过长；此时用户需要手动 `/compact` 或新开会话。

### 取舍 5：不恢复文件快照和工具列表

- 工具完整结果已有磁盘路径和边界提示，可显式重读。
- 下一次主请求仍携带真实工具定义，不需要在消息中复制一份。
- 近期文件快照留作未来增强，避免本章同时维护另一份原文缓存。

## 实现顺序约束

开发必须保持以下依赖顺序：

```text
配置与模型
  ↓
状态、常量和纯函数
  ↓
工具结果落盘
  ↓
Token 估算和摘要
  ↓
Conversation 替换
  ↓
Agent 集成
  ↓
TUI /compact
  ↓
完整测试和 tmux 验收
```

具体可执行步骤将在 `task.md` 中拆分，验收命令与真实场景将在 `checklist.md` 中定义。
