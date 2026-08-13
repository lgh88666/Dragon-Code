# ch10：Slash Command 内置命令框架 Plan

## 状态

- 阶段：已批准
- 日期：2026-08-13
- 输入：已批准的 `spec.md`
- 教材参考：`Vibe Coding提示词复制` ch10 Python 部分

## 架构概览

ch10 在现有 Textual 输入入口与 Agent 之间增加一层独立的命令系统。普通文本仍进入
Agent；以 `/` 开头的文本先由命令解析器解析，再由注册中心查找并执行对应处理函数。

整体拆为五个部分：

1. **命令核心层**：定义命令元数据、三种命令类型和统一处理函数签名。
2. **注册与分发层**：集中注册 12 条主命令，检查名称/别名冲突，提供查找、帮助列表、
   前缀补全和统一执行入口。
3. **内置处理层**：按 `local`、`local-ui`、`prompt` 三类组织命令实现；处理函数只调用
   抽象的界面控制能力，不直接操作 Textual 控件。
4. **TUI 接线层**：`DragonCodeApp` 实现界面控制协议，把命令动作桥接到现有 Agent、
   SessionManager、MemoryManager 和权限模式；输入提交时先做命令分流。
5. **补全与确认层**：在输入框上方增加轻量候选菜单；会话和记忆删除复用一个确认弹窗，
   真正删除仍由对应管理器负责。

命令层不依赖 Textual，也不直接依赖具体模型协议，因此可用普通单元测试验证。TUI 只负责
把现有能力接到命令层，并渲染菜单、列表、确认框和系统消息。

### 与教材 ch10 Python 方案的差异

教材同样采用“命令核心包 + Registry + UI Protocol + TUI 补全状态机”的分层，Dragon Code
保留这条主架构。根据已经批准的 Spec，本项目增加以下差异：

- Dragon Code 现已与教材统一：所有内置命令均为零参数，处理函数只接收 UI 控制接口；会话、
  记忆、权限和审查目标都在命令打开的交互界面中选择。
- 教材的 `/session`、`/memory`、`/permission` 只展示；Dragon Code 增加受约束的恢复、删除和
  运行时切换能力。
- 教材补全只匹配主命令且 Enter/Tab 直接执行；Dragon Code 主命令与别名都可匹配，Enter/Tab
  只填入输入框，用户再次 Enter 才执行。
- 教材 local 命令可在忙碌态执行；Dragon Code 所有命令统一只在空闲态执行，减少状态竞争。
- 教材 `/review` 直接发送固定提示；Dragon Code 先通过界面选择当前 Git 改动或指定路径，再
  通过一次性的只读工具集运行，不改变会话原有权限模式。

## 核心数据结构与接口

### `CommandKind`

使用简单枚举区分命令执行方式：

```python
class CommandKind(Enum):
    LOCAL = "local"
    LOCAL_UI = "local-ui"
    PROMPT = "prompt"
```

- `LOCAL`：只读取并展示本地状态，如 `/help`、`/status`。
- `LOCAL_UI`：改变界面或运行状态，如 `/clear`、`/session`、`/permission`。
- `PROMPT`：最终会把预设任务交给 Agent，如 `/do`、`/review`。

### `Command`

每条命令使用一个简单数据类集中保存元信息：

```python
@dataclass
class Command:
    name: str
    aliases: tuple[str, ...]
    description: str
    usage: str
    kind: CommandKind
    handler: CommandHandler
    hidden: bool = False
```

`name` 和 `aliases` 保存时统一为不含 `/` 的小写形式；显示时再补 `/`。本章所有命令都是
零参数，因此不设置 `argument_hint`，处理函数签名保持为 `handler(ui)`。

### `CommandHandler`

```python
CommandHandler = Callable[[CommandUI], Awaitable[None]]
```

处理函数与教材一致使用异步签名并保持短小，只负责调用 UI 控制接口。压缩、扫描、恢复、删除
等可能耗时的动作仍由 `DragonCodeApp` 使用现有 Textual Worker 异步执行，不阻塞界面。

### `CommandRegistry`

```python
class CommandRegistry:
    def register(self, command: Command) -> None: ...
    def find(self, name: str) -> Command | None: ...
    def visible(self) -> list[Command]: ...
    def complete(self, prefix: str) -> list[Command]: ...
```

- `register`：同时登记主名称和别名；任何大小写归一化后的冲突立即报错。
- `find`：按主名称或别名查找，大小写不敏感。
- `visible`：按主名称稳定排序，过滤隐藏命令，供帮助界面使用。
- `complete`：仅按主名称做前缀匹配，过滤隐藏命令，结果按主名称排序；别名不进入补全菜单。

### 解析与分发接口

```python
def parse_command(text: str) -> str | None: ...


async def dispatch_command(
    text: str,
    registry: CommandRegistry,
    ui: CommandUI,
) -> bool: ...
```

`parse_command` 只负责识别 `/命令名`，普通文本返回 `None`。若 `/命令名` 后还有空白和内容，
分发器显示“本章命令不接收参数”的用法错误。`dispatch_command` 返回是否已经消费该输入，确保
未知命令和用法错误不会落入 Agent。

### `CommandUI`

命令层只依赖下面这组高层能力，不导入 Textual：

```python
class CommandUI(Protocol):
    def show_message(self, text: str, *, error: bool = False) -> None: ...
    def open_help(self, commands: list[Command]) -> None: ...
    def get_status(self) -> CommandStatus: ...
    def quit(self) -> None: ...
    def force_compact(self) -> None: ...
    def clear_session(self) -> None: ...
    def enter_plan_mode(self) -> None: ...
    def execute_plan(self) -> None: ...
    def open_sessions(self, *, resume_only: bool = False) -> None: ...
    def open_memories(self) -> None: ...
    def open_permissions(self) -> None: ...
    def open_review(self) -> None: ...
```

`DragonCodeApp` 实现这些方法。内置命令处理函数只调用接口，例如 `/resume` 调用
`open_sessions(resume_only=True)`，不直接查找 Textual Widget。

### `CommandStatus`

`/status` 通过一个只读快照获得展示数据，避免命令层逐个访问 App 属性：

```python
@dataclass
class CommandStatus:
    version: str
    cwd: str
    provider: str
    model: str
    permission_mode: str
    session_id: str
    input_tokens: int
    output_tokens: int
    cache_write_tokens: int
    cache_read_tokens: int
    estimated_context_tokens: int
    builtin_tool_count: int
    mcp_tool_count: int
    user_memory_count: int
    project_memory_count: int
```

### 交互列表使用的数据

- `SessionInfo`：沿用 ch09，补充管理界面所需的当前会话标记由 TUI 临时计算。
- `MemoryInfo`：新增只读数据类，包含层级、文件名、类型、标题和正文摘要。
- `CompletionState`：保存当前候选、光标、滚动偏移和打开状态；只管理状态，不渲染 Textual。

### 与教材 ch10 Python 方案的差异

- `Command`、`CommandKind`、`handler(ui)` 和 Registry 接口与教材保持一致；Dragon Code 因所有
  命令已改为零参数，不再增加 `CommandContext`。
- Handler 与教材一致使用异步函数；当前短处理函数可以不产生实际等待，但统一签名为后续需要
  等待交互结果的命令保留稳定入口。
- 教材的 UI Protocol 主要暴露零散查询方法；Dragon Code 用 `CommandStatus` 一次提供状态快照，
  并增加会话、记忆、权限、审查四个高层交互入口，避免命令层知道 Textual 弹窗细节。
- 补全与教材一致，只匹配和填充主命令名；别名仅用于直接执行。

## 模块设计

### 命令定义与注册

**职责：** 保存命令元数据，完成名称归一化、冲突检查、主名/别名查找和主名补全。

**设计：**

- 注册时去掉可选的前导 `/` 并转为小写。
- 主名称、别名共用一张查找表，确保任何方向的冲突都能在启动期发现。
- 可见命令保持稳定排序，帮助和补全不各自维护清单。
- 补全只检查主名称；别名只参与执行查找。

### 命令解析与分发

**职责：** 在输入入口判断普通文本和 Slash Command，并统一调用 Handler。

**设计：**

- 普通文本返回“未消费”，继续进入原有 `_start_turn()`。
- `/命令` 在注册中心找到后 `await command.handler(ui)`。
- 未知命令显示 `/help` 引导；额外内容显示该命令的零参数用法错误。
- 命令分发前统一检查 App 是否为空闲态，忙碌时只显示等待提示。
- Handler 异常统一转成可读错误，不能让 Textual 消息循环崩溃。

### 本地命令

**职责：** 实现 `/help` 和 `/status`，不调用模型、不修改对话历史。

- `/help` 把 `registry.visible()` 交给帮助界面；选中命令后显示详细元数据。
- `/status` 获取一次 `CommandStatus`，格式化版本、目录、Provider、模型、权限模式、会话 ID、
  Token、上下文估算、工具数量和记忆数量。

### 本地 UI 命令

**职责：** 调用现有能力或打开交互界面。

- `/exit`：复用安全退出，取消 Worker、关闭会话 Writer、记忆任务和 MCP 生命周期。
- `/compact`：复用现有手动压缩事件流。
- `/clear`：异步创建新会话和 ContextManager；全部准备成功后一次切换，再关闭旧 Writer。
- `/plan`：进入只读 Plan Mode，等待下一条普通消息。
- `/resume`：打开只允许“恢复”的会话列表。
- `/session`：打开会话管理列表，选中后选择“恢复”或“删除”。
- `/memory`：打开两级记忆列表，选中后查看详情或删除。
- `/permission`：打开运行时权限模式列表，选择后只更新当前 Agent 与界面，不写 YAML。

### Prompt 命令

**职责：** 把预设任务通过正常用户消息链路交给 Agent。

- `/do`：校验当前已有 Plan，退出 Plan Mode 后发送既有 `DO_PLAN_PROMPT`。
- `/review`：先打开目标选择界面；用户选择“当前 Git 未提交改动”或输入文件/目录后，构造固定
  审查提示并启动 Agent。该次任务强制使用 Read、Glob、Grep，只输出问题报告。

Prompt 命令仍写入 Conversation 和 JSONL，因此恢复会话后可以看到这次任务；弹窗里的选择过程
不写入历史。

### 命令补全

**职责：** 根据输入框内容维护和渲染最多 8 行候选。

- 输入变化时，从注册中心按主命令前缀刷新候选。
- `CompletionState` 只维护候选、光标与偏移；Textual Widget 负责显示名称和描述。
- App 在菜单打开时拦截上、下、Tab、Enter、Esc；菜单关闭时保持原有输入键位行为。
- Tab/Enter 统一把主命令填入输入框但不执行；再次 Enter 才走提交分发。
- 出现空格、多行或失去输入焦点时关闭菜单。

### 交互弹窗

**职责：** 让用户不记会话 ID、记忆文件名、权限值或审查路径语法。

- **帮助界面**：命令列表与选中项详情。
- **会话界面**：沿用搜索能力；管理模式增加恢复/删除动作，恢复模式只提供恢复。
- **记忆界面**：按项目级/用户级展示；支持详情和单条删除。
- **权限界面**：展示三个可选运行模式及说明，Plan Mode 不作为该菜单选项。
- **审查界面**：选择当前 Git 改动或输入一个文件/目录。
- **确认界面**：会话和记忆删除前显示明确目标，确认后才调用管理器。

所有磁盘扫描、恢复与删除仍放入 Worker；弹窗只负责选择，不直接操作文件。

### SessionManager 扩展

**新增接口：**

```python
def delete(self, session_id: str, active_session_id: str) -> None: ...
```

- 拒绝当前会话、非法 ID、目标不存在和越出 sessions 根目录的路径。
- 删除由调用方确认后执行；成功后重新扫描列表。
- 不改变现有 `open_new()`、`restore()` 和 45 天清理行为。

### MemoryManager 扩展

**新增接口：**

```python
def list_memories(self) -> list[MemoryInfo]: ...
def read_memory(self, level: str, filename: str) -> MemoryInfo: ...
async def delete_memory(self, level: str, filename: str) -> None: ...
```

- 文件名继续使用 ch09 的安全格式校验，层级只允许 `user` 或 `project`。
- 删除与后台自动记忆共用现有异步锁，避免同时改文件和索引。
- 删除成功后原子重建对应 `MEMORY.md` 并刷新内存索引。

### Agent 与工具注册中心的最小扩展

- `Agent.run(user_text, read_only=False)` 增加一次性只读开关。`read_only=True` 时使用 Plan 的
  Read/Glob/Grep 子注册中心，但不进入 Plan Mode、不注入计划提醒、不修改 `has_plan`。
- `Agent.replace_session(..., preserve_mode=False)` 增加明确选项：恢复历史沿用原行为重置模式；
  `/clear` 使用 `preserve_mode=True` 保留当前权限模式，同时清空计划标记和回合状态。
- `ToolRegistry.counts()` 返回内置工具和以 `mcp__` 开头的 MCP 工具数量，只供 `/status` 使用。

### DragonCodeApp 接线

**职责：** 实现 `CommandUI`，把命令动作映射到现有 TUI 和领域管理器。

- 启动时构建一次命令注册中心；输入提交先调用异步命令分发器。
- 普通文本、AgentEvent 消费和权限审批链路保持原样。
- 新增会话、记忆、权限、审查和确认弹窗的打开/回调方法。
- 状态栏新增空闲命令提示；任务期间继续显示原有进度、计时和 Token。
- `/clear`、恢复、删除和审查目标准备失败时保留当前会话与模式。

### 与教材 ch10 Python 方案的差异

- 教材的会话、记忆和权限命令主要展示信息；Dragon Code 通过交互弹窗提供已批准的恢复、删除
  和运行时切换，但仍不接收命令参数。
- 教材没有一次性只读审查开关；Dragon Code 在 `Agent.run()` 增加布尔开关，复用已有只读工具
  子集，不新增权限模式或第二套 Agent Loop。
- 教材只需要简单恢复菜单；Dragon Code 复用 ch09 的搜索和原子恢复，再增加安全删除。
- 为避免现有单文件 `tui.py` 继续膨胀，Textual 专用的补全组件和命令弹窗会移到独立文件；不把
  `tui.py` 整体迁移成新包，以降低 ch02–ch09 回归风险。

## 模块交互

### 1. 输入提交与命令分流

```text
用户按 Enter
  → DragonCodeApp 检查是否空闲
  → await dispatch_command(text, registry, ui)
      → 普通文本：返回 False
      → Slash Command：查找并 await handler(ui)，返回 True
  → 返回 False 时才调用原有 _start_turn(text)
```

这样未知命令、多余参数和已经执行的命令都不会再次发送给模型。Prompt 命令最终仍调用
`_start_turn()`，所以继续使用原有 AgentEvent、Conversation、JSONL 和 Token 统计链路。

### 2. 实时补全与二次确认执行

```text
输入框文本变化
  → 仅在空闲、单行、以 / 开头且没有空格时更新候选
  → registry.complete(prefix)
  → CompletionState 更新光标和可见 8 行
  → CompletionWidget 重新渲染
```

菜单打开时：

- 上/下只移动高亮项。
- Tab/Enter 把高亮项的主命令写入输入框，关闭菜单，并记录“该文本刚由补全接受”。
- 程序写入导致的那一次文本变化不会重新打开菜单。
- 用户再次按 Enter 时，命令才提交到分发器。
- Esc 只关闭菜单；菜单关闭后 Esc 恢复“取消当前 Agent”的既有行为。

### 3. `/clear` 原子切换

```text
/clear
  → 进入本地工作状态，禁用输入
  → 准备新的 ActiveSession、Conversation、Writer、ContextManager
  → 全部成功
      → Agent 一次替换会话对象并保留当前权限模式
      → active_session 指向新会话
      → 清空对话区和 Token 展示
      → 关闭旧 Writer
  → 任一步失败
      → 关闭已经创建的新 Writer
      → 旧会话、旧界面和旧 Agent 状态保持不变
  → 回到空闲
```

旧会话目录不会删除，随后仍能通过 `/resume` 恢复。

### 4. 会话恢复与删除

```text
/resume 或 /session
  → Worker 扫描 SessionManager.list_sessions()
  → 打开可搜索列表
  → /resume：选中后直接走现有原子恢复
  → /session：选中后显示“恢复 / 删除 / 取消”
      → 恢复：走现有原子恢复
      → 删除：显示标题和 ID，再次确认
          → Worker 调用 SessionManager.delete()
          → 成功后刷新列表
```

删除动作会再次校验目标不是当前会话，并在真正操作前重新解析安全路径，避免列表打开后目标状态
已经变化。

### 5. 记忆查看与删除

```text
/memory
  → Worker 扫描两级记忆
  → 列表按层级和标题展示
  → 选中后读取并显示详情
  → 选择删除时显示层级、标题和文件名
  → 确认后等待 MemoryManager 的锁
  → 删除单条文件、原子重建对应索引、刷新内存快照和列表
```

若后台自动记忆正在更新，手动删除会等待同一把锁，不会与索引写入交错。

### 6. 权限模式选择

```text
/permission
  → 打开 default / acceptEdits / bypassPermissions 列表
  → 用户选中并确认
  → Agent.set_permission_mode(mode)
  → 更新就绪提示和状态栏
```

该流程不写配置文件，也不会修改危险命令黑名单和路径沙箱。Plan Mode 仍通过 `/plan` 进入，
不会作为权限菜单中的选项。

### 7. `/review` 一次性只读任务

```text
/review
  → 选择“当前 Git 未提交改动”或输入项目内路径
  → 校验目标仍在项目目录内
  → 构造固定审查提示
  → _start_turn(prompt, display_text="/review", read_only=True)
  → Agent.run(prompt, read_only=True)
  → 仅把 Read / Glob / Grep 定义发送给模型
  → 正常流式、工具调用、历史和 JSONL 链路
  → 完成后原权限模式保持不变
```

只读限制来自工具注册中心，而不只是提示词。若模型请求 Write、Edit 或 Bash，会得到未知工具结果，
不会实际执行。

### 8. `/status` 本地数据流

```text
/status
  → DragonCodeApp.get_status()
  → 从现有 App、Agent、Conversation、ToolRegistry、MemoryManager 读取一份 CommandStatus
  → Handler 格式化并显示
```

不发模型请求、不写对话历史，也不读取密钥或配置正文。上下文数字沿用现有字符估算逻辑，明确
标为估算值。

### 9. 忙碌保护

Agent 流式、上下文压缩、会话切换、命令 Worker 或权限确认期间：

```text
提交任意 Slash Command
  → 显示“当前任务结束或取消后再执行命令”
  → 不执行、不排队、不写历史
```

补全菜单同时关闭。任务结束回到空闲后，用户可以重新输入命令。

### 与教材 ch10 Python 方案的差异

- 教材 Enter/Tab 在补全菜单中直接执行；Dragon Code 增加“填入后再次 Enter”的一步，并通过
  一次性抑制标记防止菜单因程序写入立即重开。
- 教材 local 命令在部分忙碌状态仍可执行；Dragon Code 统一由 App 空闲检查拦截，调用链更单一。
- 会话、记忆、权限和审查比教材多一层交互选择，但所有选择都停留在 TUI，不进入模型历史。
- `/review` 仍复用原 Agent Loop，只在本次 `run()` 选择只读 Registry，不创建第二条执行链。

## 文件组织

```text
src/dragon_code/
├── command/
│   ├── __init__.py          — 对外导出命令核心类型与默认注册中心
│   ├── command.py           — CommandKind、Command、异步 Handler 类型
│   ├── registry.py          — 注册、冲突检测、查找、可见列表、主名补全
│   ├── dispatch.py          — 零参数解析、空闲检查与异步分发
│   ├── ui.py                — CommandUI Protocol、CommandStatus
│   ├── builtin_local.py     — /help、/status
│   ├── builtin_ui.py        — 本地 UI 类命令
│   ├── builtin_prompt.py    — /do、/review 与固定审查提示
│   ├── builtins.py          — 12 条主命令及别名的集中注册
│   └── completion.py        — 不依赖 Textual 的 CompletionState
├── command_widgets.py       — Textual 补全菜单 Widget
├── command_screens.py       — 帮助、会话管理、记忆、权限、审查和确认弹窗
├── tui.py                   — CommandUI 实现、输入接线、Worker 与回调
├── dragon_code.tcss         — 补全菜单和新增弹窗样式
├── agent.py                 — 一次性只读 run、会话替换保留模式选项
├── tools/registry.py        — 内置/MCP 工具数量
├── sessions/manager.py      — 安全删除非当前会话
└── memory/
    ├── models.py            — MemoryInfo
    └── manager.py           — 列表、详情、加锁删除与索引刷新

tests/
├── test_command.py          — 元数据、冲突、查找、分发、帮助、别名
├── test_command_completion.py — 补全状态与键位边界
├── test_tui.py              — 实时菜单、各交互弹窗、忙碌保护、状态栏
├── test_agent.py            — 一次性只读审查、模式不变、clear 状态
├── test_session.py          — 会话安全删除
├── test_memory.py           — 记忆列表、详情、加锁删除和索引
└── test_tool_registry.py    — 内置/MCP 数量统计
```

`command/` 的文件布局与教材 Python 方案保持接近，便于逐文件对照。新增的 Textual Widget 和
Screen 放在包外，确保命令核心仍可脱离 Textual 测试。现有 `tui.py` 不迁移成目录包，也不移动
ch02–ch09 的 Provider、权限审批和恢复界面，以减少无关改动。

## 技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 命令参数 | 12 条主命令全部零参数 | 与教材一致，避免记忆会话 ID 和子命令语法 |
| 后续操作 | 交互列表、输入框和确认窗 | 目标可见、可搜索，危险动作可二次确认 |
| Handler | 统一异步 `handler(ui)` | 与教材一致，为未来需要等待的处理保留稳定接口 |
| 命令依赖 | `CommandUI` Protocol | Handler 不依赖 Textual，Fake UI 即可单测 |
| 状态读取 | 单个 `CommandStatus` 只读快照 | `/status` 字段较多，避免 Protocol 出现大量零散 getter |
| 注册查找 | 主名称和别名共用归一化字典 | 冲突检测和大小写不敏感查找保持单一实现 |
| 补全范围 | 只匹配非隐藏主命令名 | 与教材一致，候选稳定且不被别名重复占据 |
| 补全确认 | 第一次 Enter/Tab 填入，第二次 Enter 执行 | 避免误触发清空、删除或模式切换 |
| 命令状态 | 所有命令只在 IDLE 执行 | 避免 Agent、恢复、压缩和审批与命令并发修改状态 |
| 耗时本地操作 | 继续使用 Textual Worker 和 `asyncio.to_thread` | 复用现有模式，磁盘扫描/删除不冻结界面 |
| 会话切换 | 先准备、后替换、失败回滚 | 保证 Conversation、Writer 和 ContextManager 一致 |
| 数据删除 | 管理器内再次校验 + UI 二次确认 | UI 负责意图确认，领域层负责最终安全边界 |
| 记忆并发 | 手动删除复用自动记忆锁 | 防止记忆文件和 `MEMORY.md` 索引写入交错 |
| 审查只读 | `Agent.run(read_only=True)` 复用只读 Registry | 不增加新权限模式、循环或 Agent 实例 |
| Prompt 历史 | 继续走 `_start_turn()` | 保留 AgentEvent、JSONL、上下文和 Token 统计语义 |
| TUI 组织 | 新组件独立文件，保留现有 `tui.py` 主体 | 控制文件体量，同时避免大规模迁移造成回归 |
| 外部依赖 | 不新增依赖 | Textual、dataclass、Protocol 和现有管理器已足够 |

### Plan 自检

1. **Spec 覆盖**：F1–F16 均有明确模块、接口或交互链路，没有未归属需求。
2. **接口完整性**：命令核心、TUI 控制、会话、记忆、Agent 和工具统计接口均已定义。
3. **依赖清晰度**：`command` 只依赖抽象 UI；TUI 依赖 command 和领域模块；领域模块不反向依赖
   TUI，不形成循环依赖。
4. **现有能力保护**：普通文本、AgentEvent、权限审批、MCP、压缩、会话写入和自动记忆仍走原链路。
5. **范围控制**：不实现用户命令、Skill、复杂参数、命令队列、通用事件总线或新权限系统。
6. **教材对照**：保留教材的命令包、异步 Handler、Registry、UI Protocol、三类命令和主名补全；
   Dragon Code 的交互管理、二次 Enter、统一空闲限制和只读审查差异均已说明。
