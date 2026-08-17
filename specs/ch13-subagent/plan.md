# Dragon Code ch13 SubAgent 子任务分发 Plan

## 架构概览

ch13 在现有 `Agent.run()` 外增加一层轻量的子任务编排，不新建第二套 Agent Loop，也不引入
通用 `AgentRuntime`。整体分为六个部分：

1. **Agent 定义目录**：启动时从项目、用户和内置三层目录读取 Markdown + YAML 定义，校验后
   保存成稳定有序的 `AgentDefinition`。
2. **SubAgentHost**：根据定义式、Fork 或 Skill fork 请求，创建隔离的 Conversation、
   ContextManager、PermissionEngine、SkillRuntime、HookEngine 和子 Agent。
3. **BackgroundTaskManager**：统一管理前台、后台和排队任务，最多同时运行三个；转后台只解除
   前台等待，不重启已经运行的协程。
4. **Agent/任务工具**：主 Agent 固定获得 `Agent`、`TaskList`、`TaskGet`、`TaskStop`、
   `SendMessage` 五个系统工具。定义式子 Agent 看不到这些工具；Fork 保留相同 Schema，但执行
   时由来源和历史标记拒绝。
5. **事件与动态提醒**：任务管理器把前台子 Agent 事件、状态变化和完成通知放进内存队列。
   TUI 负责显示；主 Agent 在下一次正常请求时取走 `<task-notification>`，提醒不进入持久历史。
6. **Skill fork 适配**：ch11 的 inline Skill 保持原路径，fork Skill 改为委托
   `SubAgentHost`，统一后台运行、任务查询、通知和清理。

核心关系如下：

```text
主 Agent.run()
  └─ 模型调用 Agent 工具
       └─ SubAgentHost.launch()
            ├─ 创建隔离 SubAgentSession
            ├─ BackgroundTaskManager.submit()
            │    ├─ 有空位：运行同一个 Agent.run()
            │    └─ 无空位：FIFO 排队
            └─ 前台等待 / 立即后台 / Fork 强制后台

BackgroundTaskManager
  ├─ task events ───────────────→ TUI 状态行与前台明细
  ├─ terminal notification ─────→ 下一次主 Agent reminder
  └─ task snapshots/results ────→ TaskList / TaskGet / TaskStop / SendMessage
```

## 核心数据结构

### `AgentDefinition`

```python
@dataclass(frozen=True)
class AgentDefinition:
    name: str
    description: str
    system_prompt: str
    allowed_tools: tuple[str, ...]
    disallowed_tools: tuple[str, ...]
    model: str
    max_iterations: int
    permission_mode: PermissionMode
    background: bool
    source: AgentDefinitionSource
    source_path: Path
```

- `allowed_tools` 为空表示不额外收窄；非空时只保留其中存在且通过其他过滤层的工具。
- `disallowed_tools` 始终在白名单前生效。
- 定义式默认模型为 `deepseek-v4-flash`，默认最大迭代数沿用主 Agent 上限。
- YAML 字段采用教材命名：`name`、`description`、`tools`、`disallowedTools`、`model`、
  `maxTurns`、`permissionMode`、`background`。

### `AgentDefinitionSource`

```python
class AgentDefinitionSource(IntEnum):
    PLUGIN = 0
    BUILTIN = 1
    USER = 2
    PROJECT = 3
```

数值越高优先级越高。`PLUGIN` 只作为加载入口参数保留，本章默认没有插件目录。

### `AgentDefinitionIssue`

```python
@dataclass(frozen=True)
class AgentDefinitionIssue:
    source_path: Path
    code: str
    message: str
```

用户级和项目级坏文件转成 issue 并跳过；内置定义损坏抛出启动错误。

### `QuerySource`

```python
class QuerySource(StrEnum):
    MAIN = "main"
    DEFINED_SUBAGENT = "defined_subagent"
    FORK_SUBAGENT = "fork_subagent"
    SKILL_FORK = "skill_fork"
```

它描述“当前模型请求从哪里发起”，用于工具执行前的嵌套防护。该值只存在于运行时，不发送给
模型，也不写入 Conversation。

### `SubAgentLaunchRequest`

```python
@dataclass(frozen=True)
class SubAgentLaunchRequest:
    prompt: str
    description: str
    role_name: str = ""
    model_override: str = ""
    run_in_background: bool = False
    task_name: str = ""
    kind: SubAgentKind = SubAgentKind.DEFINED
    skill_name: str = ""
    skill_arguments: str = ""
```

`kind` 由 `Agent` 工具或 SkillExecutor 决定，不直接信任模型提供的任意字符串。

### `SubAgentSession`

```python
@dataclass
class SubAgentSession:
    key: str
    name: str
    kind: SubAgentKind
    definition: AgentDefinition | None
    agent: Agent
    conversation: Conversation
    hook_engine: HookEngine
```

这是可继续对话的隔离状态。`SendMessage` 创建新的任务执行记录，但复用同一个
`SubAgentSession` 和 Conversation；旧任务仍保持终态，不做 `completed → running` 的非法
回退。

### `TaskStatus` 与 `TaskSnapshot`

```python
class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class TaskSnapshot:
    id: str
    name: str
    description: str
    kind: SubAgentKind
    status: TaskStatus
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    result: str
    error: str
    usage: TokenUsage
    tool_count: int
    last_activity: datetime
    attached: bool
    queued_position: int | None
```

合法状态转换只有：

```text
queued ──→ running ──→ completed
   │           ├─────→ failed
   │           └─────→ cancelled
   └────────────────→ cancelled
```

前台转后台只把 `attached` 从 `True` 改成 `False`，不改变任务状态、不创建新协程。

### `SubAgentEvent`

```python
@dataclass(frozen=True)
class SubAgentEvent:
    type: str
    task_id: str
    task_name: str
    agent_name: str
    attached: bool
    text: str = ""
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None
    usage: TokenUsage | None = None
    status: TaskStatus | None = None
    running_count: int = 0
    queued_count: int = 0
```

子 Agent 仍产生原有 `AgentEvent`。`SubAgentHost` 只负责加上任务身份并转换成
`SubAgentEvent`，不改变主 Agent 与 TUI 的既有事件协议。

### `SubAgentResult`

```python
@dataclass(frozen=True)
class SubAgentResult:
    text: str
    usage: TokenUsage
    tool_count: int
    stop_reason: str
```

普通异常在任务边界转成安全错误摘要，不保存堆栈或密钥。

## 核心接口

### `AgentDefinitionLoader` / `AgentCatalog`

```python
class AgentDefinitionLoader:
    def __init__(
        self,
        project_root: Path,
        *,
        user_home: Path | None = None,
        builtin_root: Path | None = None,
        plugin_roots: tuple[Path, ...] = (),
    ) -> None: ...

    def load(self) -> AgentCatalog: ...


class AgentCatalog:
    def get(self, name: str) -> AgentDefinition | None: ...
    def list_definitions(self) -> list[AgentDefinition]: ...
    def issues(self) -> list[AgentDefinitionIssue]: ...
    def summary_text(self) -> str: ...
```

目录固定为：

- 项目：`<project>/.dragon-code/agents/*.md`
- 用户：`~/.dragon-code/agents/*.md`
- 内置：包内 `dragon_code/subagents/builtin/*.md`

候选文件按名称排序；覆盖后再按角色名排序，保证工具描述跨轮稳定。加载仅在应用启动时发生。

### `SubAgentHost`

```python
class SubAgentHost:
    def bind_parent(self, parent: Agent) -> None: ...

    async def launch(
        self,
        request: SubAgentLaunchRequest,
        *,
        call: ToolCall | None = None,
    ) -> SubAgentLaunchOutcome: ...

    async def continue_named(self, name: str, prompt: str) -> SubAgentLaunchOutcome: ...
    async def close(self) -> None: ...
```

职责：

1. 解析定义或建立 Fork 临时定义。
2. 选择模型、权限模式和最大迭代数。
3. 过滤 registry，并创建隔离运行状态。
4. 构造一个调用现有 `child_agent.run(prompt)` 的 runner。
5. 把 runner 交给任务管理器，不自行维护队列和状态机。

### `BackgroundTaskManager`

```python
class BackgroundTaskManager:
    async def submit(
        self,
        session: SubAgentSession,
        prompt: str,
        runner: Callable[[str], Awaitable[SubAgentResult]],
        *,
        description: str,
        attached: bool,
    ) -> TaskSnapshot: ...

    async def wait_until_detached_or_done(
        self,
        task_id: str,
        timeout_seconds: float = 120.0,
    ) -> TaskWaitOutcome: ...

    def move_foreground_to_background(self) -> str | None: ...
    async def stop(self, task_id: str) -> TaskSnapshot: ...
    def find_session_by_name(self, name: str) -> SubAgentSession | None: ...
    def list(self) -> list[TaskSnapshot]: ...
    def get(self, task_id: str) -> TaskSnapshot | None: ...
    def drain_events(self) -> list[SubAgentEvent]: ...
    def take_reminders(self) -> list[str]: ...
    async def reset_session(self) -> None: ...
    async def close(self) -> None: ...
```

实现约束：

- 使用 `deque` 保存 FIFO 队列，使用一个短时持有的 `asyncio.Lock` 保护状态转换。
- `_start_available()` 在 `running < 3` 时按顺序启动；不使用阻塞线程。
- 120 秒从任务真正进入 `running` 后计算，排队时间不算运行超时。
- 等待使用 `asyncio.shield`/`asyncio.wait`，超时和手动转后台不会取消底层任务。
- `TaskStop` 和退出才真正调用 `Agent.request_cancel()` 并取消 runner。
- 完成通知只为已经转后台或一开始就在后台的任务生成；前台直接完成不重复通知。
- 通知摘要最多 2,000 字符，Task 工具返回最多 50,000 字符，内存保存结果最多 100,000
  字符，超过时附 `[truncated]`。

### Fork 历史辅助函数

```python
FORK_BOILERPLATE_TAG = "<fork-boilerplate>"


def build_fork_messages(
    committed: list[ChatMessage],
    pending_assistant: ChatMessage | None,
    task_prompt: str,
) -> list[ChatMessage]: ...


def is_fork_context(messages: list[ChatMessage]) -> bool: ...
```

`Agent` 在执行当前 assistant 的工具调用期间，暂存该 assistant 消息。Fork 先深拷贝已提交
历史，再复制当前 assistant 消息，并给其中所有尚未完成的 ToolCall 补一条
`fork_placeholder` ToolResult，最后追加 Boilerplate + 子任务。主 Conversation 不会收到这些
占位结果。

### 工具过滤

```python
MAIN_AGENT_ONLY_TOOLS = {"Agent", "TaskList", "TaskGet", "TaskStop", "SendMessage"}

BACKGROUND_ALLOWED_CORE = {"Read", "Write", "Edit", "Bash", "Glob", "Grep"}


def filter_subagent_registry(
    registry: ToolRegistry,
    definition: AgentDefinition | None,
    *,
    source: QuerySource,
    background: bool,
) -> ToolRegistry: ...
```

过滤顺序固定为：

1. 从原 registry 的注册顺序开始。
2. 定义式移除 `MAIN_AGENT_ONLY_TOOLS` 和 `LoadSkill`。
3. 后台只保留六个核心工具，以及命名为 `mcp__*`、`skill__*` 的外部工具。
4. 应用角色 `disallowedTools`。
5. `tools` 非空时再做角色白名单交集。

Fork 为 Prompt Cache 保留父 registry 的完整定义顺序，但 `Agent` 执行工具前检查
`Tool.main_agent_only`。只要 `QuerySource` 不是 `MAIN`，或 Conversation 中检测到 Fork 标记，
就返回 `nested_agent_denied`，不会进入权限引擎。

### 非交互权限

`Agent.__init__` 新增：

```python
query_source: QuerySource = QuerySource.MAIN
interactive_permissions: bool = True
stable_system_override: str = ""
runtime_reminder_source: RuntimeReminderSource | None = None
```

- 主 Agent 保持 `interactive_permissions=True`。
- 子 Agent 使用 `False`。权限结果为 `ASK` 时直接生成 `permission_denied` ToolResult，不创建
  Approval Future、不发送权限弹窗事件。
- `PermissionEngine.new_session()` 返回共享 RuleStore、黑名单和沙箱配置的新实例，但
  `session_allowed_tools` 为空，从而隔离父会话临时批准。
- 每个子 Agent 使用 `HookEngine(parent.snapshot)`，共享定义快照但隔离 only-once、提醒和后台
  Hook task。

### Agent 和任务工具

`AgentArguments` 使用 Pydantic 校验：

```python
class AgentArguments(BaseModel):
    prompt: str
    description: str
    role: str = ""
    model: str = ""
    run_in_background: bool = False
    name: str = ""
```

- `role` 非空：定义式；为空：Fork。
- `AgentTool.description` 在启动时把排序后的角色名和说明写入工具描述。运行期文件变化不会
  改变当前工具定义。
- `AgentTool` 和四个任务工具设置 `is_system_tool=True`、`main_agent_only=True`；任务查询工具
  只操作本会话内存，不经过文件权限确认。
- `SendMessage(name, prompt)` 只接受唯一、已完成且当前未运行的命名 session；继续执行生成新
  task ID，旧 TaskSnapshot 保持 completed。
- `Agent` 和任务控制工具由权限引擎识别为主 Agent 系统操作并直接允许；真正的读写、命令、
  MCP 和 Skill 工具仍在子 Agent 内逐次经过完整权限判断。`Agent`、`TaskStop` 和
  `SendMessage` 标记为不可并发调度。
- 主 Agent 处于 Plan Mode 时，Host 不允许角色权限模式升级：子 Agent 强制保持只读 registry
  和 Plan 权限模式，避免通过委派绕过计划模式。

## 模块设计

### Agent 定义解析与目录

**职责：** 解析 frontmatter、校验字段、按来源覆盖、提供稳定摘要。

**依赖：** `yaml`、`PermissionMode`、标准库 `importlib.resources`。

**边界：** 不读取插件配置，不监听文件变化，不执行定义中的任意代码。

### SubAgentHost

**职责：** 把“角色 + 父 Agent + 任务”变成隔离的子 Agent session 和 runner。

**依赖：** 现有 `Agent`、`Conversation`、`ContextManager`、`LLMClient` factory、
`ToolRegistry`、`PermissionEngine`、`SkillManager`、`HookEngine`。

**边界：** 不维护任务状态机、不直接渲染 TUI、不持久化子对话。

### BackgroundTaskManager

**职责：** ID、命名 session、状态、并发、队列、转后台、取消、继续任务、事件和通知。

**依赖：** asyncio 与 subagent 数据模型；不依赖 Textual。

**边界：** 不创建 LLMClient，不理解 Agent 定义，不修改主 Conversation。

### Agent Loop 扩展

**职责：** 暴露当前待执行 assistant 消息，执行前做来源保护，支持非交互 Ask，合并任务提醒。

**依赖：** 只依赖小型 Protocol/枚举，不反向依赖任务管理器具体类。

**边界：** ReAct 循环、流式收集、上下文压缩、工具调度和历史提交顺序不重写。

### TUI 集成

**职责：** 构造并绑定 Host/Manager，轮询 `SubAgentEvent`，处理 `Ctrl+B`，刷新后台/排队计数，
在新建、恢复和退出时清理任务。

**行为：**

- 前台且 `attached=True`：显示带 `[agent_name]` 的文本、工具行、结果、轮次和用量。
- 后台：只显示启动、排队、移交和终态摘要，不显示完整内部对话。
- `Ctrl+B` 仅在有 attached 子任务时生效；否则显示简短提示，不影响主 Agent。
- `/clear`、`/new`、`/resume` 在替换主 Conversation 前调用 `reset_session()`。
- 状态栏新增独立任务状态文字，例如 `Agents 2 running · 1 queued`。

### Skill fork 适配

**职责：** `SkillExecutor` 保留 inline 逻辑；fork 分支把 Skill 的 context、allowed tools、model、
SOP 和参数转换为 `SubAgentLaunchRequest`。

**行为：** fork Skill 立即返回任务 ID，不再把子摘要自动提交到主 Conversation；完成后统一由
通知和 `TaskGet` 交付。Skill 的 `full/recent/none` 历史范围在 Host 构建 Fork 消息前应用。

## 模块交互

### 启动流程

```text
cli._run_app()
  ├─ 加载基础工具 / MCP / Skill / Hook
  ├─ AgentDefinitionLoader.load()
  │    ├─ 内置损坏 → 可读启动错误并退出
  │    └─ 用户/项目损坏 → warning 后继续
  └─ DragonCodeApp(..., agent_catalog)

DragonCodeApp._activate_provider()
  ├─ 创建 BackgroundTaskManager
  ├─ 创建 AgentTool（暂未绑定 Host）和四个任务工具
  ├─ 按固定顺序合并 registry
  ├─ 创建主 Agent(runtime_reminder_source=task_manager)
  ├─ 创建 SubAgentHost 并 bind_parent(main_agent)
  └─ 创建 SkillExecutor(..., subagent_host)
```

### 定义式前台任务

```text
模型 → Agent(role="explore", run_in_background=false)
  → Catalog 解析角色
  → 创建空 Conversation + 隔离状态
  → Manager 提交（有槽位则 running，否则 queued）
  → Host 消费 child Agent.run(prompt)
  → Manager 把 attached 事件交给 TUI
  ├─ 120 秒内完成：Agent 工具返回最终文本
  ├─ Ctrl+B：解除 attached，Agent 工具立即返回 task_id
  └─ 运行满 120 秒：解除 attached，Agent 工具立即返回 task_id
```

等待被取消时，`AgentTool` 调用 `TaskStop` 同一内部路径取消当前 attached 子任务，然后重新抛出
`CancelledError`，由现有主 Agent 取消逻辑合法收尾。

### Fork 后台任务

```text
模型 → Agent(role="")
  → 读取父 committed history + current assistant tool calls
  → deep copy + placeholder tool results + fork boilerplate
  → 继承父 model、stable system、registry 顺序
  → source=FORK_SUBAGENT、interactive_permissions=false
  → Manager 后台提交并立即返回 task_id
```

### 后台完成通知

```text
child Agent 进入终态
  → Manager 更新 TaskSnapshot
  → SubAgentEvent(status=completed/failed/cancelled)
  → TUI scrollback 显示摘要
  → Manager 保存截断后的 <task-notification>
  → 用户下一次正常输入
  → 主 Agent.run 每轮 combine_reminders 时 take_reminders()
  → LLMRequest.reminder 注入；Conversation/JSONL 不写入该块
```

### `SendMessage`

```text
SendMessage(name, prompt)
  → 按唯一名称找到空闲且已完成的 SubAgentSession
  → 创建新 TaskSnapshot（新 task_id）
  → 复用 session.agent 和 session.conversation 调 Agent.run(prompt)
  → 按并发限制排队或运行
```

## 文件组织

```text
src/dragon_code/
├── agent.py                         — 增加来源保护、非交互权限、待处理 assistant、任务提醒
├── prompt.py                        — 稳定工具委派约定与 task notification 合并入口
├── cli.py                           — 启动加载 AgentCatalog，统一关闭任务管理器
├── tui.py                           — Host/Manager wiring、Ctrl+B、事件和任务状态展示
├── dragon_code.tcss                — 任务状态栏样式
├── tools/
│   ├── base.py                      — Tool.main_agent_only 元信息
│   └── registry.py                  — 按谓词保序过滤的简单 helper
├── permissions/
│   └── engine.py                    — 系统工具判断；new_session() 隔离临时批准
├── hooks/
│   └── engine.py                    — new_session() 共享快照、隔离可变状态
├── skills/
│   └── executor.py                  — fork 分支委托 SubAgentHost
└── subagents/
    ├── __init__.py                  — 对外导出稳定接口
    ├── models.py                    — 定义、来源、任务状态、事件、请求/结果
    ├── parser.py                    — Markdown + YAML frontmatter 解析
    ├── catalog.py                   — 三层加载、覆盖、问题收集
    ├── filtering.py                 — 多层工具过滤与主 Agent 专用工具集合
    ├── fork.py                      — Fork 历史复制、占位结果、Boilerplate 检测
    ├── manager.py                   — 三并发 FIFO、状态、通知、取消和续派
    ├── host.py                      — 隔离 Agent 创建与现有 Agent.run() 复用
    ├── tools.py                     — Agent + TaskList/Get/Stop/SendMessage
    └── builtin/
        ├── explore.md
        ├── plan.md
        └── verify.md

tests/
├── test_subagent_parser.py          — frontmatter、覆盖、坏文件、内置定义
├── test_subagent_fork.py            — 深拷贝、placeholder、标记和历史合法性
├── test_subagent_filtering.py       — 多层过滤、顺序、嵌套阻断
├── test_subagent_manager.py         — 状态机、三并发、FIFO、移交、取消、通知、续派
├── test_subagent_host.py            — 隔离状态、模型选择、权限和 Agent.run 复用
├── test_subagent_tools.py           — 五个工具的成功/错误结果
├── test_skill_executor.py           — fork Skill 统一后台路径
├── test_agent.py                    — 非交互 Ask、来源保护、动态提醒
└── test_tui.py                      — Ctrl+B、事件渲染、状态栏和清理

specs/ch13-subagent/
├── spec.md
├── plan.md
├── task.md
└── checklist.md
```

## Spec 覆盖

| Spec | 设计归属 |
|------|----------|
| F1–F2 | `subagents/tools.py`、固定注册顺序、启动期 Catalog 快照 |
| F3–F5 | `parser.py`、`catalog.py`、三个 builtin Markdown |
| F6–F11 | `SubAgentHost`、隔离 Session、Fork helper、现有 `Agent.run()` |
| F12–F14 | `filtering.py`、`QuerySource`、`Tool.main_agent_only`、非交互权限 |
| F15–F16 | Manager attached 状态、120 秒 shield 等待、Ctrl+B |
| F17–F21 | Manager 状态机、FIFO、五个工具、提醒、取消和 close |
| F22 | `SkillExecutor` fork 适配 |
| F23 | 子 HookEngine 共享 snapshot，现有 Agent Hook 路径 |
| F24 | `SubAgentEvent`、TUI 轮询、scrollback 和状态栏 |
| F25 | 全部上层逻辑只依赖 `LLMClient`，协议转换不改 |

## 技术决策

| 决策点 | 选择 | 理由 |
|--------|------|------|
| 子 Agent 循环 | 直接消费现有 `Agent.run()` | Dragon Code 已有完整跑到底循环，避免教材方案新增 `run_to_completion` 后产生两套语义 |
| 运行时抽象 | `SubAgentHost + BackgroundTaskManager` | 满足创建和调度职责，同时保持代码对 Python 学习者可读，不建万能 Runtime |
| 前台转后台 | 对同一个 asyncio Task 解除等待，使用 shield | 超时和 Ctrl+B 不取消、不重启，因此不会重复执行工具或轮次 |
| 转后台按键 | `Ctrl+B` | 用户已审批；保留 Esc 作为取消当前任务，避免一个按键承担两种相反语义 |
| 自动转后台 | 实际运行 120 秒后 | 用户已审批；排队时间不应误算为运行超时 |
| 并发 | Manager 固定 3 个槽位 + FIFO deque | 比无界 `create_task` 安全，且 queued 状态和停止行为可观察 |
| 权限 Ask | 子 Agent 直接得到结构化拒绝 | 与已批准非交互策略一致，不把后台审批弹窗转发给 TUI |
| PermissionEngine | 共享持久规则和安全组件，隔离 session allow 集合 | 教材参考设计共享整个 Engine；Dragon Code 为满足 F10/F14 明确隔离临时批准 |
| HookEngine | 每个子 Agent 新实例，共享 HookSnapshot | 避免提醒、only-once 和后台 Hook 结果在不同 Agent 之间串线 |
| Fork 工具定义 | 与父 registry 同序保留，执行时双重拒绝嵌套 | 保持 Prompt Cache 前缀，同时用 QuerySource + Boilerplate 兜底安全 |
| 定义式工具 | 真实移除 Agent/任务工具 | 无需为缓存保留父前缀，最小权限更直接 |
| 后台白名单 | 六个核心工具 + 已注册 MCP/Skill 工具，再走权限层 | 跟教材主线一致；白名单不等于自动放行，黑名单、沙箱、规则和模式继续生效 |
| `SendMessage` 状态 | 新 task ID，复用旧 session | 保持旧任务终态不可逆，同时继续使用独立 Conversation |
| 完成通知 | TUI 显示 + 下一请求动态 reminder，不自动请求模型 | 用户已审批，避免后台任务突然消耗 Token 或打断当前操作 |
| Skill fork | 迁移到同一个 Host/Manager，强制后台 | 删除重复构造逻辑，让通知、取消、任务查询和嵌套限制一致 |
| 模型 | 定义式默认 `deepseek-v4-flash`，Fork 强制继承父模型 | 与用户选择一致；Fork 不换模型以保留缓存机会 |
| 插件来源 | Catalog 接受 `plugin_roots`，默认空 | 保留教材扩展点，但不伪造尚未实现的插件系统 |
| 文件隔离 | 共享工作目录并明确警告 | ch13 不做 Worktree；真实说明冲突风险，不制造虚假隔离 |

## 与教材参考方案的差异

| 教材参考 | Dragon Code ch13 | 原因 |
|----------|------------------|------|
| 新增 `run_to_completion` 并抽公共 loop helper | 直接复用现有异步生成器 `Agent.run()` | 当前实现已经跑到底，额外拆分会扩大改动和回归面 |
| 前台任务约 30 秒/参考稿 120 秒后自动后台 | 固定 120 秒 | 用户已明确修改并批准 |
| Esc 将前台任务切后台 | `Ctrl+B` 切后台，Esc 继续取消 | 用户已明确选择；交互含义更清楚 |
| 子 Agent 可把 Ask 升级到主 TUI | 非交互，Ask 作为结构化拒绝回灌 | 用户已选择，不让后台任务突然弹权限框 |
| 共享 PermissionEngine | 只共享持久规则、安全组件，临时账本独立 | 满足 Dragon Code 已批准的状态隔离要求 |
| 参考稿允许同一任务 ID 继续 | 新执行使用新 task ID，复用 SubAgentSession | 避免终态任务倒退为 running，状态机更容易验证 |
| 常量中使用教材的小写工具名 | 使用 Dragon Code 现有 `Read/Write/Edit/Bash/Glob/Grep` | 对齐本项目实际注册名 |
| Provider/SessionRuntime 命名 | 使用现有 `LLMClient`、Conversation、ContextManager | 对齐 Dragon Code 已有术语，不引入重复概念 |
| 参考稿拆出独立 `task` 包 | 任务管理留在 `subagents` 包内 | 当前项目规模下减少包间循环和阅读跳转 |

## 自检结果

- **Spec 覆盖**：F1–F25 均有明确模块和交互归属，没有遗漏。
- **接口完整性**：加载、创建、调度、过滤、等待、通知、取消、继续和清理均有入口。
- **依赖方向**：TUI → Host/Manager → Agent；Agent 只依赖 Protocol/枚举，不反向依赖 TUI。
- **循环一致性**：没有第二套 Agent Loop，子任务直接走现有 `Agent.run()`。
- **历史合法性**：Fork placeholder、动态 reminder、子 Conversation 不持久到主历史均有明确边界。
- **安全性**：嵌套双闸、非交互 Ask、独立权限临时账本、既有黑名单和沙箱均保留。
- **范围控制**：没有 Worktree、团队协议、任务持久化、真实插件或通用 Runtime。
- **占位符扫描**：本文没有 TBD、TODO 或未决接口。
