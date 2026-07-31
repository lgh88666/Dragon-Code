# Dragon Code Agent Loop Plan

## 架构概览

ch04 在现有 Provider、Conversation、ToolRegistry 和 TUI 之间增加独立的 Agent 执行层。核心分为七个部分。

### 1. Provider 协议适配层

AnthropicProvider 和 OpenAIProvider 继续负责：

- 构造各自协议的请求。
- 解析文本和工具参数分片。
- 组装完整助手消息。
- 提取本轮输入、输出 Token。
- 统一输出 ProviderEvent。

Provider 不负责 Agent 循环，也不执行工具。

### 2. 流式收集器

每次模型请求创建一个新的收集器：

- 文本增量立即转成 AgentEvent 交给 TUI。
- 完整消息、工具调用和 Token 用量保存在收集器中。
- 流结束后，Agent 读取收集结果判断下一步。
- 流没有产生完整消息时报告协议错误。

收集器只保存一轮响应，下一轮重新创建。

### 3. Agent 主循环

新增独立的 Agent 类，代替 ChatSession 的单轮工具闭环。它负责：

- 最多执行 50 次模型迭代。
- 每轮发送进度事件。
- 请求 Provider 并消费流式事件。
- 判断自然完成或继续执行工具。
- 维护连续未知工具计数。
- 累计本次任务 Token。
- 处理取消、上限和错误收尾。
- 向上层输出统一 AgentEvent。

核心使用直观的循环，不引入复杂状态机框架。

### 4. 工具调度器

新增轻量工具调度模块：

- 按原始顺序扫描工具调用。
- 连续并发安全工具组成一个批次。
- 不安全、具有副作用或未知工具单独成批。
- 批次依次执行，安全批次内部并发执行。
- 执行结果按照原始调用顺序返回。
- 取消时为未开始或状态不确定的工具生成结构化结果。

调度器只负责“一轮中的工具”，不负责模型循环。

### 5. Conversation 历史

保留现有协议无关消息结构，但调整提交时机：

- 模型流未完整结束时，不提交当前响应。
- 完整助手消息和对应工具结果准备齐全后一起提交。
- 已经完成的迭代立即进入历史。
- 取消工具批次时补齐所有结果后再提交。
- 下一次模型请求直接读取完整历史。

### 6. 模式控制

Agent 内部保存简单的当前模式：

- `default`：提供全部六个工具。
- `plan`：只提供 Read、Glob、Grep，并追加 Plan Mode 提示。
- `/plan` 切换为 plan；成功完成计划回复后记录“已有计划”。
- `/do` 校验计划状态，切换为 default，并使用内部执行指令启动循环。

ToolRegistry 提供按名称选取工具子集的能力，保证 Plan Mode 不只是隐藏工具定义，也无法实际执行 Write、Edit、Bash。

### 7. TUI 消费层

TUI 不再调用 ChatSession，而是：

- 启动一个 Agent 异步 Worker。
- 消费 AgentEvent 更新文本、工具行、结果、进度和计时。
- `Esc` 调用 Agent 的取消入口，不直接销毁整个 Worker。
- 根据完成、取消、限制或错误事件统一恢复输入框。
- 显示当前 Default/Plan 模式和本次任务 Token。

### 完整调用关系

```text
用户输入
   ↓
TUI ──启动──→ Agent Loop
                 ↓
              Provider
                 ↓ ProviderEvent
            流式收集器
                 ↓ AgentEvent
TUI ←────────────┘
                 ↓ 完整工具调用
             工具调度器
                 ↓
            ToolRegistry
                 ↓ 工具结果
            Conversation
                 ↓
             下一轮模型
```

取消路径：

```text
用户按 Esc
   ↓
TUI 通知 Agent
   ↓
Agent 取消当前网络流或工具任务
   ↓
补齐合法历史
   ↓
发出 cancelled 事件
   ↓
TUI 恢复输入
```

## 核心数据结构

### TokenUsage

```python
@dataclass
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None

    def add(self, other: "TokenUsage") -> "TokenUsage":
        """合并两轮用量；任一轮未知时，对应累计值保持未知。"""

    @property
    def total_tokens(self) -> int | None:
        """输入和输出都已知时返回总数，否则返回 None。"""
```

用途：

- Provider 记录单次请求用量。
- Agent 跨迭代累计本次任务用量。
- TUI 统一格式化显示。
- `None` 表示兼容端点没有提供数据，不使用 `0` 冒充未知。

### ProviderEvent

```python
@dataclass
class ProviderEvent:
    type: str
    text: str = ""
    tool_call: ToolCall | None = None
    message: ChatMessage | None = None
    usage: TokenUsage | None = None
```

Provider 事件类型：

```text
text_delta   正文增量
tool_call    已经拼接完整的工具调用
usage        本次模型请求用量
completed    完整助手消息
```

Provider 只处理一次模型请求，不知道 Agent 当前是第几轮。

### AgentEvent

现有 TurnEvent 替换为更完整的 AgentEvent：

```python
@dataclass
class AgentEvent:
    type: str
    text: str = ""
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    usage: TokenUsage | None = None
    iteration: int = 0
    max_iterations: int = 0
    error: Exception | None = None
```

事件类型：

```text
progress      开始新迭代
text          正文增量
tool_start    工具准备执行
tool_end      工具执行完成
usage         单次请求用量
completed     整个任务自然完成
cancelled     用户取消
limit         达到迭代或未知工具限制
error         Provider 或循环错误
```

`completed` 事件同时携带最终文本和本次任务累计用量。

### CollectedResponse 与 StreamCollector

```python
@dataclass
class CollectedResponse:
    message: ChatMessage
    usage: TokenUsage


class StreamCollector:
    def __init__(self):
        self.message: ChatMessage | None = None
        self.usage = TokenUsage()

    def accept(self, event: ProviderEvent) -> AgentEvent | None:
        """收集 Provider 事件；正文增量立即转换为 AgentEvent。"""

    def finish(self) -> CollectedResponse:
        """流结束后返回完整结果；缺少完整消息时报告响应错误。"""
```

处理规则：

- `text_delta`：立即返回 `AgentEvent(type="text")`。
- `tool_call`：由 Provider 负责拼接，收集器等待完整消息统一保存。
- `usage`：保存本次请求用量。
- `completed`：保存完整助手消息。
- `finish()` 不负责工具执行，只检查本轮响应是否完整。

### ToolBatch 与 ToolScheduler

```python
@dataclass
class ToolBatch:
    calls: list[ToolCall]
    concurrent: bool


class ToolScheduler:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self.active_tasks: dict[str, asyncio.Task] = {}

    def partition(self, calls: list[ToolCall]) -> list[ToolBatch]:
        """按原始顺序划分并发安全批次和串行批次。"""

    async def execute_batch(self, batch: ToolBatch) -> list[ToolResult]:
        """执行一个批次，结果顺序与 batch.calls 保持一致。"""

    def cancel_active(self) -> None:
        """向当前正在执行的工具任务发送取消信号。"""

    def make_cancelled_results(
        self,
        calls: list[ToolCall],
    ) -> list[ToolResult]:
        """为尚未开始的调用生成 cancelled 结果。"""
```

取消结果使用两个错误码：

```text
cancelled               工具尚未开始，确定没有执行
cancel_outcome_unknown  工具已经开始，最终是否产生副作用无法确认
```

### Agent

```python
class Agent:
    def __init__(
        self,
        provider: BaseProvider,
        conversation: Conversation,
        system_prompt: str,
        registry: ToolRegistry,
        max_iterations: int = 50,
        unknown_tool_limit: int = 3,
    ): ...

    async def run(self, user_text: str):
        """运行一个完整 Agent 任务，异步产出 AgentEvent。"""

    def request_cancel(self) -> None:
        """由 TUI 调用，取消当前 Provider 或工具任务。"""

    def enter_plan_mode(self) -> None:
        """进入持续 Plan Mode。"""

    def can_execute_plan(self) -> bool:
        """当前是否处于 Plan Mode 且已经成功产生过计划回复。"""

    def enter_default_mode(self) -> None:
        """恢复 Default Mode。"""
```

主要状态：

```python
self.mode = "default"
self.has_plan = False
self.cancel_requested = False
self.task_usage = TokenUsage()
self.active_provider_task = None
```

`max_iterations` 和 `unknown_tool_limit` 在正式运行时使用默认值；测试可以传入小值快速验证边界。

### ToolRegistry 子集

```python
class ToolRegistry:
    ...

    def subset(self, names: set[str]) -> "ToolRegistry":
        """返回共享同一批工具实例的注册中心子集。"""
```

Agent 根据模式选择：

```text
Default → 原始六工具注册中心
Plan    → Read、Glob、Grep 子注册中心
```

子集按照原注册顺序选取工具，不按照 `set` 的无序遍历结果重新排序。

### Prompt 接口

```python
PLAN_MODE_PROMPT = """
当前处于 Plan Mode……
"""

DO_PLAN_PROMPT = """
请根据上文已经确认的计划开始执行……
"""


def build_agent_prompt(base_prompt: str, mode: str) -> str:
    """Default 返回基础提示；Plan 追加计划模式约束。"""
```

Plan Mode 约束包括：

- 只探索、分析和完善计划。
- 不尝试修改文件或执行命令。
- 最终在对话中给出可执行计划。
- 等待用户继续修改或输入 `/do`。

### TUI 入口

TUI 持有：

```python
self.agent: Agent | None
self.stream_worker: Worker | None
```

关键动作：

```python
def action_cancel_turn(self) -> None:
    """运行中按 Esc 时调用 agent.request_cancel()。"""


async def _consume_task(self, user_text: str) -> None:
    """只消费 AgentEvent 并更新界面。"""
```

`Esc` 不直接调用 `stream_worker.cancel()`，避免 Agent 来不及补齐工具结果。只有应用退出时才强制取消整个 Worker。

## 模块设计

### `models.py`

**职责：**

- 保存协议无关消息、工具调用和工具结果。
- 新增 TokenUsage。
- 扩展 ProviderEvent。
- 用 AgentEvent 替换 TurnEvent。

**不负责：**

- 不执行循环。
- 不解析 SDK 对象。
- 不包含 TUI 渲染逻辑。

### `providers/anthropic.py`

**职责：**

- 继续解析正文、thinking、tool_use 和 JSON 参数分片。
- 从 `message_start` 保存本轮输入 Token。
- 从 `message_delta` 保存最新输出 Token。
- 流结束时先产生 usage，再产生 completed。
- 被取消时关闭流式上下文并继续抛出取消信号。

Anthropic 的输出 Token 是当前消息累计值，收到新的 `message_delta` 时覆盖旧值，不重复相加。

### `providers/openai.py`

**职责：**

- 继续拼接正文与多个工具调用。
- 通过 `stream_options={"include_usage": True}` 请求流式用量。
- 在检查 `chunk.choices` 前先读取 `chunk.usage`，因为最终用量分片可能没有正文选项。
- 流结束时先产生 usage，再产生 completed。
- 兼容端点没有返回 usage 时使用未知值。
- 无论完成、出错或取消，都关闭响应流。

### `stream_collector.py`

**职责：**

- 消费一次 Provider 流的统一事件。
- 把文本事件立即转换为 AgentEvent。
- 保存完整助手消息和本轮用量。
- 流结束后检查 completed 是否存在。

Collector 不解析 JSON；JSON 分片仍由两个 Provider 按各自协议处理。

### `tool_scheduler.py`

**职责：**

- 根据 `is_concurrency_safe` 划分 ToolBatch。
- 执行单个串行批次或并发批次。
- 保存当前批次活动任务。
- 接收取消请求。
- 把取消状态转成 ToolResult。

分批算法：

```text
创建空的安全批次

从左到右读取工具调用：
  如果工具存在并且 is_concurrency_safe=True：
      加入当前安全批次
  否则：
      先保存当前安全批次
      再把当前调用保存为单独串行批次

扫描结束后保存剩余安全批次
```

未知工具没有安全声明，因此作为单独串行批次，由 ToolRegistry 返回 `unknown_tool`。

并发执行规则：

- 同一安全批次的工具各自创建独立任务。
- 一次等待整个批次完成。
- 单个任务异常只转换该工具的失败结果。
- 按创建任务时的下标恢复原始顺序。
- 不把多个工具写入同一个共享结果槽位。

### `session.py`

**职责：**

- 保留 Conversation。
- 移除 ch03 的单轮 ChatSession 编排职责。
- 提供读取历史副本和批量提交合法消息的能力。

提交规则：

第一次完整工具迭代：

```text
user → assistant(tool calls) → tool(results)
```

后续工具迭代：

```text
assistant(tool calls) → tool(results)
```

自然结束：

```text
assistant(final text)
```

只有完整消息才提交。第一次响应尚未完整就出错或取消时，本次用户消息也不进入历史，保持与 ch03 当前错误行为一致。

### `agent.py`

**职责：**

- ReAct 主循环。
- Provider 流消费。
- AgentEvent 输出。
- 工具调度。
- 历史提交。
- Token 累计。
- 五种停止条件。
- Default/Plan 模式。
- 取消收尾。

### `prompt.py`

**职责：**

- 保留基础 System Prompt。
- 新增 Plan Mode 提示。
- 新增 `/do` 内部执行提示。
- 根据当前模式组合最终提示文本。

Plan Mode 的工具限制由注册中心子集强制保证；Prompt 负责告诉模型如何规划，两者分别承担行为引导和执行边界。

### `tui.py`

**职责：**

- 解析 `/plan`、`/do`、`/exit`。
- 启动 Agent Worker。
- 消费 AgentEvent。
- 处理 `Esc`。
- 控制流式文本、scrollback、状态栏和输入状态。

## 模块交互

### 正常 Agent Loop

```text
1. 清空本次取消标记和 Token 累计
2. 准备“历史 + 当前用户消息”
3. iteration 从 1 递增到 50
4. 发出 progress 事件
5. 请求 Provider
6. 实时转发 text 事件
7. 取得完整助手消息和本轮 usage
8. 累计 usage 并发出 usage 事件
9. 没有工具调用：
      提交最终助手消息
      Plan Mode 下标记已有计划
      发出 completed
      结束
10. 存在工具调用：
      分批执行
      补齐全部结果
      提交助手消息和工具结果
      检查未知工具连续次数
      进入下一迭代
11. 第 50 轮仍请求工具：
      执行并提交该轮工具结果
      发出 limit
      不产生第 51 次请求
```

### 未知工具计数

一轮满足以下两个条件才计数：

```text
本轮至少包含一个工具调用
并且所有结果的 error_code 都是 unknown_tool
```

出现任意已注册工具后计数归零。达到 3 时，当前未知工具结果已经写入历史，然后发出 limit。

### Provider 阶段取消

每次等待下一个 Provider 流事件时创建一个短生命周期活动任务：

```text
Agent 等待 active_provider_task
                 ↑
Esc → request_cancel() → cancel active_provider_task
```

Agent 捕获取消后：

- 关闭当前流迭代器。
- 丢弃尚未 completed 的响应。
- 保留此前完整迭代。
- 发出 cancelled。

### 工具阶段取消

```text
当前批次：
  已完成任务       → 真实 ToolResult
  被取消的活动任务 → cancel_outcome_unknown

后续未启动批次：
  所有调用         → cancelled
```

Agent 按原始顺序发出工具结果事件，然后一次性提交：

```text
assistant(tool calls) → tool(all results)
```

提交完成后发出 cancelled，不进入下一轮。

### `/plan`

```text
/plan
  → 切换 Plan Mode
  → 清空 has_plan
  → 更新状态栏
  → 不请求模型

/plan 任务内容
  → 切换 Plan Mode
  → 更新状态栏
  → 以“任务内容”启动 Agent
```

Plan Mode 中普通消息继续使用只读工具。成功得到一次最终计划回复后，`has_plan=True`。

### `/do`

```text
检查 mode == plan 且 has_plan == True
  ↓ 否
显示提示，不请求模型
  ↓ 是
切换 Default Mode
显示用户输入“/do”
使用 DO_PLAN_PROMPT 启动 Agent
```

执行完成、取消或出错后均保持 Default Mode。

### AgentEvent 渲染

| 事件 | TUI 行为 |
|---|---|
| progress | 更新 `Agent working… N/50` |
| text | 实时追加到动态文本 |
| tool_start | 固定前置文本，写入工具行 |
| tool_end | 写入成功、错误或取消摘要 |
| usage | 更新本次任务用量缓存 |
| completed | Markdown 定型，显示耗时与 Token |
| cancelled | 显示取消提示并恢复输入 |
| limit | 显示黄色限制提示并恢复输入 |
| error | 显示脱敏错误并恢复输入 |

并发批次先按照原始顺序显示全部工具行，批次结束后再按照原始顺序显示结果，确保 scrollback 不因实际完成时间交错。

## 文件组织

```text
src/dragon_code/
├── agent.py                       新建：Agent Loop、停止条件、模式与取消收尾
├── stream_collector.py            新建：单次 Provider 流式响应双路收集
├── tool_scheduler.py              新建：工具分批、并发执行与取消结果
├── models.py                      修改：TokenUsage、ProviderEvent、AgentEvent
├── session.py                     修改：保留 Conversation，移除单轮 ChatSession
├── prompt.py                      修改：Plan Mode 与 /do 内部提示
├── tui.py                         修改：消费 AgentEvent、Esc、/plan、/do
├── providers/
│   ├── base.py                    小幅修改：统一流式事件接口说明
│   ├── anthropic.py               修改：提取 usage、支持流取消
│   └── openai.py                  修改：请求并提取流式 usage、关闭流
└── tools/
    └── registry.py                修改：按名称生成工具子注册中心

tests/
├── conftest.py                    修改：FakeProvider 支持多轮、usage、取消
├── test_agent.py                  新建：循环、停止、历史、取消、Plan Mode
├── test_stream_collector.py       新建：双路收集、缺少 completed
├── test_tool_scheduler.py         新建：分批、并发顺序、失败、取消
├── test_provider_anthropic.py     修改：Anthropic usage 与取消
├── test_provider_openai.py        修改：OpenAI usage-only 分片与关闭
├── test_session.py                修改：只保留 Conversation 行为测试
└── test_tui.py                    修改：事件渲染、Esc、/plan、/do、进度
```

不增加第三方依赖，`pyproject.toml` 的运行依赖保持不变。

## 技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 循环位置 | 新建独立 Agent | 避免 ChatSession 同时承担历史、循环、工具和界面事件 |
| Agent 实现 | 普通类 + 直观循环 | 便于学习和调试，不引入复杂状态机框架 |
| 事件模型 | 单个 AgentEvent 数据类 + 字符串 type | 延续现有代码风格，比多层事件继承简单 |
| 双路收集 | Provider 解析协议，Collector 收集完整结果 | Provider 处理协议差异，Collector 和 Agent 保持协议无关 |
| 工具并发依据 | `is_concurrency_safe` | 直接复用 ch03 已有元信息，不靠工具名称硬编码 |
| 并发方式 | 每个工具创建独立异步任务，整批统一等待 | 单个失败不影响其他工具，返回顺序容易保持 |
| 批次顺序 | 批次串行、批内并发 | 在加速只读操作的同时保持模型给出的依赖顺序 |
| Provider 取消 | 只取消当前流事件等待任务 | 外层 Agent 仍能整理历史并发出 cancelled |
| 工具取消 | 调度器保存活动任务并逐个发送取消 | 能区分已完成、未开始和结果未知 |
| 历史提交 | 每个完整迭代原子提交 | 避免已提交工具调用缺少结果 |
| 第 50 轮行为 | 执行并提交该轮工具结果，禁止第 51 次请求 | 保持历史合法，同时严格限制模型迭代次数 |
| 未知工具计数 | 仅“整轮全部未知”时递增 | 混合调用说明模型仍在使用有效工具，不应过早终止 |
| Plan Mode 限制 | Prompt + ToolRegistry 子集 | Prompt 引导行为，注册中心子集保证写工具无法执行 |
| Plan 状态 | Agent 保存 `mode` 和 `has_plan` | 状态少、逻辑直接，不需要额外计划文件或状态机 |
| `/do` 执行 | 切换 Default 后发送内部用户指令 | 两种 Provider 都能直接利用完整上文计划 |
| Anthropic 用量 | 输入取 `message_start`，输出取最新 `message_delta` | 符合 Anthropic 流式用量结构，避免重复累计 |
| OpenAI 用量 | 请求 `include_usage`，在检查 choices 前读取 usage | 最终用量分片可能没有正文选项 |
| 未知用量 | 对应累计字段保持 `None` | 不用 0 冒充缺失数据 |
| OpenAI 流清理 | 无论完成、错误或取消都关闭响应流 | 防止连接和后台资源泄漏 |
| 正式限制与测试 | 默认值固定，构造时允许测试注入小值 | 用户无法配置，同时测试不必真实循环 50 次 |
| 新依赖 | 不新增 | 当前异步运行库、SDK 和 Textual 已满足需求 |

## Spec 覆盖关系

| 功能需求 | 设计归属 |
|---|---|
| F1 ReAct 循环 | `agent.py` |
| F2 停止条件 | `agent.py` |
| F3 异步事件流 | `models.py`、`agent.py`、`tui.py` |
| F4 流式双路收集 | 两个 Provider、`stream_collector.py` |
| F5 保序分批并发 | `tool_scheduler.py` |
| F6 历史一致 | `agent.py`、`session.py` |
| F7 取消历史收尾 | `agent.py`、`tool_scheduler.py` |
| F8 取消传播 | `agent.py`、`tui.py` |
| F9 Token 用量 | Provider、`models.py`、`agent.py`、`tui.py` |
| F10 迭代进度 | `agent.py`、`tui.py` |
| F11 持续 Plan Mode | `agent.py`、`prompt.py`、`registry.py`、`tui.py` |
| F12 `/do` | `agent.py`、`prompt.py`、`tui.py` |
| F13 跨协议一致 | 两个 Provider 与统一事件模型 |
| F14 TUI 呈现 | `tui.py` |
