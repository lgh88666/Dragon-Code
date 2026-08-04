# 系统提示工程化 Plan

## 架构概览

ch05 在 ch04 的 Agent Loop 与 LLM Client 之间增加一条“提示装配管线”。管线将请求所需上下文分成三类：

1. **稳定系统提示**：七个固定模块和非空的可选模块，跨轮保持逐字一致。
2. **动态环境信息**：工作目录、平台、日期、Git 摘要、版本和模型，每次 `Agent.run()` 采集一次。
3. **临时补充提醒**：按当前模式和 Agent Loop 轮次生成，仅加入本次请求副本。

Agent 不再把模式提示直接拼到系统提示尾部，而是构造统一的 `LLMRequest`。Anthropic 与 OpenAI 的协议差异、缓存字段和临时消息格式全部留在对应 LLM Client 内部处理。

```text
TUI 提交请求
    ↓
Agent 构造稳定提示 + 采集环境信息
    ↓
每轮生成临时 system-reminder
    ↓
构造统一 LLMRequest
    ↓
AnthropicClient / OpenAIClient 序列化请求
    ↓
模型返回文本、工具调用和 Token 用量
    ↓
Agent 执行工具并更新正式历史
    ↓
继续下一轮或结束
```

## 核心数据结构

### PromptModule

```python
@dataclass(frozen=True)
class PromptModule:
    name: str
    priority: int
    content: str
```

- `name`：模块名称，用于阅读和测试。
- `priority`：装配优先级，数值越小越靠前。
- `content`：模块正文；空白内容在装配时跳过。
- 使用不可变数据类，避免构造后被意外修改而破坏缓存确定性。

### EnvironmentInfo

```python
@dataclass(frozen=True)
class EnvironmentInfo:
    working_dir: str
    platform: str
    current_date: str
    git_branch: str = ""
    git_status: str = ""
    version: str = ""
    model: str = ""

    def render(self) -> str: ...
```

Git 状态只包含分支、工作区是否有修改和修改数量，不包含文件内容、diff 或敏感环境变量。

### SystemPrompt

```python
@dataclass(frozen=True)
class SystemPrompt:
    stable: str
    environment: str
```

这两个字段在 Dragon Code 内部始终分开保存。具体协议可以采用不同的序列化方式，但不能改变两段的先后关系。

### LLMRequest

```python
@dataclass
class LLMRequest:
    messages: list[Message]
    tools: list[ToolDefinition]
    system: SystemPrompt
    reminder: str | None = None
```

- `messages` 是正式历史的请求副本。
- `reminder` 是独立字段，不和真实用户输入拼接，也不写回 `Conversation`。
- LLM Client 只在协议序列化阶段把 reminder 放到合法位置。

### TokenUsage

```python
@dataclass
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    cache_write_tokens: int = 0
    cache_read_tokens: int = 0
```

`add()` 同时累加四项用量。兼容端点不提供某个字段时按 `0` 处理。

## 核心接口

### 提示装配

```python
def fixed_prompt_modules() -> list[PromptModule]: ...

def optional_prompt_modules(
    custom_instructions: str = "",
    active_skills: str = "",
    memory: str = "",
) -> list[PromptModule]: ...

def assemble_system_prompt(modules: list[PromptModule]) -> str: ...

def build_system_prompt(...) -> SystemPrompt: ...
```

固定模块优先级为：

| 优先级 | 模块 |
|---:|---|
| 10 | 身份 |
| 20 | 系统约束 |
| 30 | 任务模式 |
| 40 | 动作执行 |
| 50 | 工具使用 |
| 60 | 语气风格 |
| 70 | 文本输出 |
| 80 | 自定义指令（可选） |
| 90 | 已激活 Skill（可选） |
| 100 | 长期记忆（可选） |

装配器只负责过滤空内容、按优先级排序并以一个空行连接，不针对具体模块写条件分支。

### 环境采集

```python
async def gather_environment(
    working_dir: Path,
    version: str,
    model: str,
) -> EnvironmentInfo: ...
```

Git 信息使用异步子进程采集，并设置 2 秒超时。命令不可用、当前目录不是 Git 仓库、超时或解析失败时省略 Git 信息，不中断请求。

### 补充提醒

```python
def system_reminder(content: str) -> str: ...


def plan_reminder(iteration: int) -> str: ...
```

完整 Plan Mode 提醒出现在第 `1、6、11……` 轮，即 `(iteration - 1) % 5 == 0`；其他轮次使用精简提醒。默认模式不注入 Plan reminder。

### LLM Client

```python
class LLMClient:
    async def stream(self, request: LLMRequest) -> AsyncIterator[LLMEvent]: ...
```

旧的 `stream(messages, system_prompt, tools)` 一次性迁移为统一请求对象，不长期保留两套接口。

## 模块设计

### `prompt.py`

**职责：**

- 保留当前终端 Banner。
- 定义提示模块与环境信息模型。
- 提供七个固定模块和三个可选位置。
- 拼装稳定提示。
- 采集、渲染环境信息。
- 构造 `<system-reminder>` 和 Plan Mode 提醒。

稳定模块中不允许出现工作目录、日期、Git 状态、模型、当前模式或迭代次数。

### `models.py`

**职责：**

- 增加 `SystemPrompt` 和 `LLMRequest`。
- 扩展 `TokenUsage` 的缓存写入、读取字段。
- 保持 ch04 的 Agent 事件类型和用量累计语义不变。

### `agent.py`

**职责：**

- 每次 `Agent.run()` 构造一次稳定提示并采集一次环境信息。
- 每轮根据当前模式和迭代次数生成 reminder。
- 从正式历史创建请求副本并构造 `LLMRequest`。
- 消费 LLM Client 事件并累计四类 Token 用量。
- 继续复用 ch04 的循环停止、取消、并发工具执行和事件流。

Agent 不操作任何 Anthropic/OpenAI 专属字段。

### `clients/anthropic.py`

**职责：**

- 将 `LLMRequest.system` 映射到一个 `system` 字段。
- 该字段的值包含两个文本内容块：
  - `system[0]`：稳定提示块，设置 `cache_control: {"type": "ephemeral"}`。
  - `system[1]`：动态环境块，不设置缓存标记。
- 保持工具定义顺序固定。
- 将 reminder 临时放入协议允许的消息内容块中。
- 解析 Anthropic 的缓存创建量和缓存读取量。

Anthropic 的缓存前缀顺序为 `tools → system → messages`。因此，稳定提示块末尾的一个显式缓存断点即可覆盖“全部工具定义 + 稳定提示”，同时排除其后的环境块和消息历史；不在最后一个工具上重复设置断点。

### `clients/openai.py`

**职责：**

- 把稳定提示和环境信息序列化为一条 system 消息。
- 稳定提示完整位于环境信息之前，中间使用固定的两个换行符。
- 不发送 Anthropic 专属缓存字段。
- 把 reminder 作为临时带标签消息加入请求副本。
- 解析兼容端点可能提供的 `prompt_tokens_details.cached_tokens`。
- 缓存写入量固定为 `0`，缺少读取字段时也为 `0`。

### `tools/file_tools.py` 与 `tools/bash.py`

**职责：**

- `Edit` 描述明确“编辑前必须先 Read”和“旧文本必须唯一匹配”。
- `Bash` 描述明确读取、查找、搜索优先使用 `Read`、`Glob`、`Grep`。
- 只强化描述，不改变工具执行行为。

### `tui.py`

**职责：**

- 创建 Agent 时提供工作目录、应用版本和当前模型。
- 继续消费已有 Agent 事件。
- 不新增缓存命中面板。

## 模块交互与历史合法性

每一轮请求使用以下顺序：

1. Agent 从 `Conversation` 读取正式历史并创建副本。
2. Agent 生成本轮 reminder，放入 `LLMRequest.reminder`。
3. LLM Client 在不修改正式历史的前提下生成协议消息。
4. Anthropic 中，已有 `tool_result` 内容块必须排在 reminder 文本块之前；不能把 reminder 插在 `tool_use` 和对应 `tool_result` 回合之间。
5. OpenAI 中，已有 `tool` 结果消息保持紧邻相应 assistant tool call；reminder 只能放在完整工具结果组之后。
6. 模型返回的 assistant 消息和真正的工具结果按 ch04 规则写入正式历史。
7. 环境信息和 reminder 永远不写入 `Conversation`。

因此，持久历史仍只包含真实的用户消息、assistant 回复、工具调用和工具结果，取消或失败后仍可继续对话。

## 文件组织

```text
src/dragon_code/
├── prompt.py                 — 模块化提示、环境采集、reminder、Banner
├── models.py                 — SystemPrompt、LLMRequest、TokenUsage
├── agent.py                  — 请求装配和既有 Agent Loop
├── tui.py                    — 向 Agent 提供环境入口参数
├── clients/
│   ├── base.py               — LLMClient 统一接口
│   ├── anthropic.py          — 双内容块 system、显式缓存、用量解析
│   └── openai.py             — 稳定 system 前缀、缓存读取解析
└── tools/
    ├── file_tools.py         — Edit 的编辑前先读规则
    └── bash.py               — 优先专用工具规则

tests/
├── test_prompt.py            — 模块、环境、确定性、reminder 节奏
├── test_agent.py             — LLMRequest、历史与 ch04 回归
├── test_client_anthropic.py  — system 内容块、缓存和消息合法性
├── test_client_openai.py     — system 前缀、缓存和消息合法性
├── test_file_tools.py        — Edit 工具描述关键规则
└── test_bash_tool.py         — Bash 工具描述关键规则
```

实施时优先修改已有测试文件；只有职责独立时才新增文件，避免拆分过细。

## 技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 提示代码组织 | 保留单个 `prompt.py` | 当前规模下更简单，更方便学习和回顾 |
| 模块排序 | 数字优先级 | 新模块只需挂载，不改装配主流程 |
| 稳定提示构造 | 每次 `Agent.run()` 一次 | 保证该次 Loop 内逐字稳定 |
| 环境采集 | 每次 `Agent.run()` 一次 | 避免每轮重复运行 Git 命令 |
| Git 执行 | 异步子进程，2 秒超时 | 避免阻塞 TUI，并能快速降级 |
| Anthropic system | 一个字段、两个文本内容块 | 既符合协议格式，又能分开标记稳定和动态内容 |
| Anthropic 缓存断点 | 只标记稳定 system 块 | 一个断点覆盖工具与稳定提示，不缓存环境和历史 |
| OpenAI system | 稳定段在前、环境段在后的一条消息 | 兼容不同 OpenAI 端点并利用自动前缀缓存 |
| reminder 内部表示 | `LLMRequest` 独立字段 | 不与用户输入混合，不污染正式历史 |
| reminder 注入 | 由具体 LLM Client 完成 | 协议差异留在适配层 |
| Plan 提醒节奏 | 第 1、6、11……轮完整 | 使用已经批准的每隔五轮方案 |
| 工具顺序 | 注册顺序稳定导出 | 保证可缓存前缀确定性 |
| 缓存字段缺失 | 按 `0` 处理 | 兼容不支持统计的端点 |
| 缓存展示 | 测试、烟测或调试输出 | 不扩大本章 TUI 范围 |

## Spec 覆盖

| Spec | 设计归属 |
|---|---|
| F1 | `PromptModule`、固定/可选模块、通用装配器 |
| F2 | `EnvironmentInfo`、异步环境采集、协议映射 |
| F3 | `SystemPrompt`、稳定顺序、Anthropic 断点、OpenAI 前缀 |
| F4 | 扩展 `TokenUsage`、两个 LLM Client 的用量解析 |
| F5 | 工具使用模块、Edit/Bash 描述强化 |
| F6 | `LLMRequest.reminder`、临时协议注入 |
| F7 | `plan_reminder()`、Agent 每轮构造、只读注册中心 |
| F8 | 统一 `LLMRequest` 与两个 LLM Client 适配 |

本设计不改变 ch04 的 Agent Loop、取消、工具并发、流式收集与停止条件，只替换请求上下文的构造和协议序列化入口。
