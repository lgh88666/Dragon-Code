# Hook 生命周期自动化系统 Plan

## 架构概览

本章新增一个独立但轻量的 `HookEngine`，负责在 Dragon Code 的 11 个确定生命周期节点执行声明式自动化规则。Hook 系统不会替换现有 `AgentEvent`，也不会扩展成全局发布订阅框架。

```text
hooks.yaml
    ↓
HookLoader：加载、合并、校验
    ↓
HookDefinition：统一保存有效 Hook
    ↓
HookEngine.trigger(生命周期事件)
    ├─ Matcher：判断事件与条件是否匹配
    ├─ HookActionExecutor：执行 shell / prompt / http / subagent
    ├─ 返回 HookOutcome：允许、拒绝、警告、提醒
    └─ 跟踪 only_once、异步任务和超时
```

主要组件：

- **数据模型**：定义 11 种事件、Hook 配置、事件上下文、执行结果和加载问题。
- **统一匹配器**：实现 exact、glob、regex、not；权限规则调用相同实现，但旧配置格式不变。
- **配置加载器**：读取项目级和用户级 `hooks.yaml`，按项目优先、追加合并。
- **动作执行器**：处理 Shell、Prompt、HTTP，并为 Subagent 返回占位结果。
- **HookEngine**：筛选、执行、拦截、超时、异步任务和 `only_once` 状态的唯一编排者。
- **现有模块接线**：在 Agent、TUI、会话切换和上下文压缩的准确位置直接触发 Hook。

```text
Agent/TUI 到达生命周期节点
        ↓
构造 HookContext
        ↓
HookEngine 查找并执行匹配的 Hook
        ↓
允许 ──→ 原流程继续
拒绝 ──→ 阻止操作并生成结构化结果
提醒 ──→ 下一次模型请求加入 <hook-notification>
失败 ──→ 显示警告，原流程继续
```

复杂度控制：

- 不建立全局发布订阅系统。
- 不让 HookEngine 操作 Textual 控件。
- 现有 `AgentEvent` 只增加 Hook 展示所需的轻量字段。
- 11 个生命周期节点统一调用 `HookEngine.trigger()`，不各自实现执行逻辑。
- HTTP 使用异步客户端，Shell 使用异步子进程，不阻塞 TUI。

## 核心数据结构

### Matcher

```python
@dataclass(frozen=True)
class Matcher:
    kind: MatcherKind
    pattern: str

    def matches(self, value: str, *, path_mode: bool = False) -> bool: ...
```

`MatcherKind` 支持：

- `EXACT`：精确相等。
- `NOT`：不相等。
- `REGEX`：正则匹配。
- `GLOB`：通配符匹配。

旧权限规则中的字符串参数仍默认转换为 `GLOB`，因此 `Bash(git *)` 的行为不变。

### Condition 与 ConditionGroup

```python
@dataclass(frozen=True)
class Condition:
    field: str
    matcher: Matcher


@dataclass(frozen=True)
class ConditionGroup:
    mode: str
    conditions: tuple[Condition, ...]
```

`mode` 只允许 `all_of` 或 `any_of`。`args.command` 等字段从事件上下文逐层读取；字段不存在时判定为不匹配。

### HookAction

为保持代码直接，不为四类动作建立继承树：

```python
@dataclass(frozen=True)
class HookAction:
    type: HookActionType
    command: str = ""
    prompt: str = ""
    url: str = ""
    method: str = "POST"
    headers: dict[str, str] = field(default_factory=dict)
    body: str = ""
    task: str = ""
```

加载时按动作类型校验必要字段：Shell 需要 `command`，Prompt 需要 `prompt`，HTTP 需要 `url`，Subagent 需要 `task`。

### HookDefinition

```python
@dataclass(frozen=True)
class HookDefinition:
    name: str
    event: HookEvent
    condition: ConditionGroup | None
    action: HookAction
    only_once: bool
    run_async: bool
    timeout: float
    source: str
    source_path: Path
```

YAML 中的 `async` 加载后保存为 `run_async`，避免使用 Python 保留字。

### HookContext

```python
@dataclass(frozen=True)
class HookContext:
    event: HookEvent
    session_id: str
    cwd: Path
    mode: str
    data: dict[str, object]

    def get(self, field_path: str) -> object | None: ...
```

事件、会话、目录和模式使用固定字段；工具参数、用户输入、压缩信息等事件专属内容放入 `data`，避免创建 11 套相似类型。

### HookExecution 与 HookOutcome

```python
@dataclass(frozen=True)
class HookExecution:
    hook_name: str
    action_type: HookActionType
    status: str
    message: str = ""
    blocked: bool = False


@dataclass
class HookOutcome:
    blocked: bool = False
    reason: str = ""
    executions: list[HookExecution] = field(default_factory=list)
```

`HookOutcome` 是一次生命周期触发的汇总结果，不直接操作 TUI。

### HookIssue 与 HookSnapshot

```python
@dataclass(frozen=True)
class HookIssue:
    source_path: Path
    hook_name: str
    message: str


@dataclass(frozen=True)
class HookSnapshot:
    hooks: tuple[HookDefinition, ...]
    issues: tuple[HookIssue, ...]
```

启动警告和 `/hooks` 使用同一快照，防止界面显示与实际执行配置不一致。

### 核心接口

```python
class HookLoader:
    def load(self) -> HookSnapshot: ...


class HookActionExecutor:
    async def execute(
        self,
        hook: HookDefinition,
        context: HookContext,
    ) -> HookExecution: ...


class HookEngine:
    def begin_session(self, session_id: str) -> None: ...

    async def trigger(self, context: HookContext) -> HookOutcome: ...

    def take_reminders(self) -> list[str]: ...

    def drain_background_results(self) -> list[HookExecution]: ...

    async def close(self) -> None: ...
```

- `begin_session()`：切换会话并重置 `only_once` 状态。
- `trigger()`：匹配并执行当前事件的 Hook。
- `take_reminders()`：取出 Prompt 动作产生的提醒。
- `drain_background_results()`：取得已完成的异步 Hook 结果。
- `close()`：有限等待后台任务，然后取消剩余任务并清理资源。

`AgentEvent` 增加：

```python
hook_execution: HookExecution | None
rejected_text: str
```

TUI 据此显示 Hook 状态，并在用户输入被拒绝后恢复原文。

## 模块设计

### `matching.py`

**职责：** 提供 Hook 与权限系统共用的匹配逻辑。

```python
def compile_matcher(kind: MatcherKind, pattern: str) -> Matcher: ...


def match_value(
    matcher: Matcher,
    value: object,
    *,
    path_mode: bool = False,
) -> bool: ...
```

- 正则在配置加载期编译并校验。
- Windows 路径匹配忽略大小写；普通命令与文本保持大小写敏感。
- 权限规则继续使用旧字符串格式，只把内部 glob 逻辑换成公共实现。

### `hooks/config.py`

**职责：** 读取、解析、校验和合并项目级与用户级配置。

单条件示例：

```yaml
hooks:
  - name: block-dangerous-command
    event: PreToolUse
    if: 'args.command =~ /rm\s+-rf/'
    action:
      type: shell
      command: "python scripts/reject.py"
```

条件组示例：

```yaml
if:
  all_of:
    - 'tool.name == "Write"'
    - 'args.path glob "**/*.py"'
```

固定条件语法：

```text
field == "value"          精确匹配
field != "value"          反向匹配
field =~ /regex/          正则匹配
field glob "pattern"      glob 匹配
```

加载顺序：

```text
项目级 .dragon-code/hooks.yaml
        ↓
用户级 ~/.dragon-code/hooks.yaml
        ↓
遇到同名 Hook：保留项目级，跳过用户级并记录 HookIssue
```

### `hooks/conditions.py`

**职责：** 解析固定条件语法并执行一层 `all_of` 或 `any_of` 判断。

```python
def parse_condition(expression: str) -> Condition: ...


def parse_condition_group(raw: object) -> ConditionGroup | None: ...


def condition_matches(
    group: ConditionGroup | None,
    context: HookContext,
) -> bool: ...
```

不调用 `eval()`，不执行 YAML 中的 Python 代码，不支持条件组嵌套。

### `hooks/template.py`

**职责：** 为 Prompt 和 HTTP 动作安全替换 `{{field.path}}`：

```text
{{event}}
{{session_id}}
{{tool.name}}
{{args.path}}
{{result.success}}
```

字段不存在时返回可读失败，不把未展开占位符发送到外部。

Shell 动作不做字符串插值。完整 `HookContext` 以 JSON 发送到子进程 stdin，常用字段同时通过 `DRAGON_*` 环境变量提供，防止不可信文件名或命令参数被直接拼入 Shell 命令。

### `hooks/actions.py`

**职责：** 执行四类动作并统一返回 `HookExecution`。

#### Shell

- 工作目录固定为项目根目录。
- 通过 stdin 写入上下文 JSON，并提供安全的 `DRAGON_*` 环境变量。
- 捕获 stdout、stderr 和退出码。
- 退出码 `2` 只在同步 `PreToolUse` 或 `UserPromptSubmit` 中表示拒绝。
- 超时或取消时终止子进程。
- stdout 与 stderr 截断，避免撑爆界面。

#### Prompt

- 渲染模板后包装成 `<hook-notification>`。
- 写入 HookEngine 提醒队列，下一次请求取出并清空。
- 不写入 Conversation 或 JSONL。

#### HTTP

- 使用 `httpx.AsyncClient`。
- 支持 method、headers、body 和 timeout。
- 同步前置事件收到 `{"block": true, "reason": "..."}` 时表示拒绝。
- 网络错误、非成功状态码和非法拒绝结构转成 Hook 失败，不抛到 Agent Loop。

#### Subagent

- 校验 `task` 字段。
- 返回 `not_implemented` 状态和 ch13 占位说明。
- 不创建 Agent、Worker 或新会话。

### `hooks/engine.py`

**职责：** 统一编排 Hook。

```text
收到 HookContext
  → 按事件筛选
  → 判断条件
  → 跳过本会话已执行的 only_once
  → 同步 Hook 按配置顺序逐个执行
  → 首个 block 出现后停止后续 Hook
  → 异步 Hook 创建受跟踪的后台任务
  → 返回 HookOutcome
```

内部状态：

- `_executed_once`：当前会话已执行的 Hook 名称。
- `_pending_reminders`：等待下一次模型请求使用的提醒。
- `_background_tasks`：受跟踪的异步任务。
- `_background_results`：异步任务完成或失败后的安全结果。

两个拦截事件不允许 `async: true`。单个非拦截 Hook 失败后，后续可执行 Hook 继续运行。

### `permissions/rules.py`

**职责：** 删除私有 glob 转换实现，调用 `matching.py`。`PermissionRule.pattern` 与所有现有 YAML 文本格式保持不变。

### `prompt.py`

新增：

```python
def hook_notification(contents: list[str]) -> str: ...


def combine_reminders(*reminders: str | None) -> str | None: ...
```

Plan Mode、Active Skill 与 Hook 提醒可以同时进入一次请求，但都不写入持久历史。

### `command/`

新增只读 `/hooks` Handler。`CommandUI` 增加：

```python
def hook_items(self) -> tuple[list[HookDefinition], list[HookIssue]]: ...
```

命令只展示名称、事件、动作、来源、once 和 async，不展示完整命令、请求头或正文。

### `agent.py`

新增统一内部入口：

```python
async def _trigger_hook(
    self,
    event: HookEvent,
    **data: object,
) -> HookOutcome: ...
```

Agent 自动补齐会话标识、项目目录和权限模式，并把同步 Hook 结果转换为 `AgentEvent`。

### `tui.py`

**职责：** 触发会话级 Hook、显示 Hook 结果、恢复被拒绝的输入，并轻量读取异步结果。TUI 不解析配置，也不执行动作。

### `cli.py`

**职责：** 启动时加载一次 HookSnapshot，打印安全警告，创建 HookEngine；退出时在其他外部资源关闭前调用 `HookEngine.close()`。

## 模块交互

### 启动与清理

```text
加载普通配置
  → HookLoader.load()
  → 输出 HookIssue
  → 创建 HookEngine
  → 启动 TUI
  → TUI 结束后触发必要的 SessionEnd
  → HookEngine.close()
  → 清理会话、记忆和 MCP
```

Hook 配置每次程序启动只加载一次，本章不热重载。

### 11 个事件接入位置

| Hook 事件 | 接入位置 |
|---|---|
| `SessionStart` | 新会话和 Agent 准备完成后 |
| `SessionEnd` | 退出、清空或切换当前会话前 |
| `SessionResume` | 历史恢复并替换 Agent 会话后 |
| `UserPromptSubmit` | `Agent.run()` 最开始、用户消息进入历史前 |
| `Stop` | 模型自然完成且没有工具调用时 |
| `PreUserMessage` | Agent Loop 每次请求模型前 |
| `PreToolUse` | 每次工具调用进入权限引擎前 |
| `PostToolUse` | 工具成功或失败形成最终 `ToolResult` 后 |
| `PreCompact` | 手动或自动压缩开始前 |
| `PostCompact` | 手动或自动压缩完成或失败后 |
| `Notification` | 权限询问、模型流错误等通知出现前 |

### 用户输入拒绝

```text
用户按 Enter
  → TUI 暂时清空并禁用输入框
  → Agent.run 触发 UserPromptSubmit
  ├─ 允许：正常进入 Agent Loop
  └─ 拒绝：不提交 Conversation
            → AgentEvent 携带 rejected_text
            → TUI 恢复原输入
            → 显示 Hook 名和原因
```

### 工具前置拦截

```text
模型产生 ToolCall
  → 显示 tool_start
  → PreToolUse Hook
  ├─ 拒绝
  │   → 不进入 PermissionEngine
  │   → 不执行工具
  │   → 生成 error_code="hook_denied" 的 ToolResult
  │   → 回灌模型
  └─ 允许
      → PermissionEngine
      → ToolScheduler
      → ToolRegistry
```

`PostToolUse` 对工具成功、工具失败、权限拒绝、Hook 拒绝、超时和取消形成的最终结果触发。Hook 自己执行的 Shell/HTTP 不转换成 ToolCall，因而不会递归触发工具 Hook。

### 动态提醒

```text
触发 PreUserMessage
  → Prompt Hook 写入提醒队列
  → 取出 Hook reminders
  → 与 Plan Mode、Active Skills reminder 合并
  → 构造 LLMRequest
```

请求可以同时包含：

```text
<system-reminder>Plan Mode / Skill SOP</system-reminder>

<hook-notification>Hook 动态提醒</hook-notification>
```

### 上下文压缩

```text
PreCompact
  → ContextManager 执行手动或自动压缩
  → PostCompact 携带成功状态、压缩前后 Token 和错误信息
```

压缩 Hook 不阻止压缩，只执行自动动作或通知。

### 会话切换

新建会话：

```text
旧会话 SessionEnd
  → 创建并切换新会话
  → HookEngine.begin_session(new_id)
  → SessionStart
```

恢复会话：

```text
旧会话 SessionEnd
  → 恢复并校验历史
  → 切换会话
  → HookEngine.begin_session(restored_id)
  → SessionResume
```

### TUI 展示与异步结果

同步 Hook 通过 AgentEvent 或会话操作结果即时显示：

```text
● Hook format-python：执行成功
● Hook protect-vendor：已拒绝 — 不允许修改 vendor 目录
● Hook notify-server：请求超时，主流程继续
```

异步 Hook 完成结果存入内存列表，TUI 使用轻量定时刷新调用 `drain_background_results()`。这是单一用途的结果读取，不是通用事件总线。

### `/hooks`

```text
已加载 2 个 Hook

format-python
  PostToolUse · shell · project · once=false · async=false

notify-finish
  Stop · http · user · once=true · async=true
```

## 文件组织

```text
src/dragon_code/
├── matching.py                 — exact、not、regex、glob 统一匹配器
├── hooks/
│   ├── __init__.py             — 对外导出 Hook 类型和加载入口
│   ├── models.py               — Hook 数据模型
│   ├── conditions.py           — 条件解析与判断
│   ├── template.py             — Prompt/HTTP 安全模板替换
│   ├── config.py               — 两层 YAML 加载、校验、合并
│   ├── actions.py              — 四种动作执行
│   └── engine.py               — 匹配、执行、拦截和生命周期
├── permissions/rules.py        — 改用公共 Matcher
├── command/builtin_local.py    — /hooks Handler
├── command/builtins.py         — 注册 /hooks
├── command/ui.py               — CommandUI 增加 hook_items()
├── agent.py                    — Agent 生命周期接入
├── models.py                   — AgentEvent Hook 字段
├── prompt.py                   — hook-notification 与提醒合并
├── tui.py                      — 会话 Hook、展示和输入恢复
└── cli.py                      — HookEngine 启动与关闭

.dragon-code/
└── hooks.yaml.example          — 不含秘密值的配置示例

tests/
├── test_matching.py
├── test_hook_conditions.py
├── test_hook_config.py
├── test_hook_actions.py
├── test_hook_engine.py
├── test_hook_integration.py
├── test_permission_rules.py
├── test_agent.py
├── test_command.py
└── test_tui.py
```

依赖增加：

```toml
httpx>=0.28,<1
```

项目会直接引用 `httpx`，因此不能只依赖上游包间接安装。

安全配置示例：

```yaml
hooks:
  - name: format-python
    event: PostToolUse
    if:
      all_of:
        - 'tool.name == "Write"'
        - 'args.path glob "**/*.py"'
    action:
      type: shell
      command: "python scripts/format_hook.py"
    timeout: 10
```

脚本从 stdin 读取上下文 JSON，不把路径直接拼入 Shell 命令。示例不包含真实 webhook、Token 或 Authorization。

验收完成后再更新：

```text
docs/PROJECT_HANDOFF.md
docs/learning-notes.md
specs/ch12-hook-system/acceptance-report.md
```

## 技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 整体架构 | 独立 HookEngine + 11 个直接接入点 | 调用链清晰，不引入通用事件总线 |
| 配置层级 | 项目级优先，再追加用户级 | 项目规则更具体 |
| 重名处理 | 保留项目级，跳过用户级并警告 | 避免同名 Hook 执行两次 |
| 执行顺序 | 配置文件原始顺序 | 本章不增加显式 priority |
| 条件解析 | 固定小语法，不使用 `eval()` | 可读且避免任意代码执行 |
| 逻辑组合 | 单条件或一层 all_of/any_of | 满足需求，不做复杂表达式树 |
| 统一匹配 | 公共 Matcher，旧权限文本仍按 glob | 增加能力但不破坏 ch06 配置 |
| Shell 上下文 | stdin JSON + `DRAGON_*` 环境变量 | 避免不可信值拼入命令 |
| Shell 执行 | 异步子进程 | 可超时、可取消，不冻结 TUI |
| HTTP 执行 | `httpx.AsyncClient` | 原生异步，清理明确 |
| HTTP 拒绝 | `{"block": true, "reason": "..."}` | 简单、可测试、原因清晰 |
| 拦截范围 | PreToolUse 与 UserPromptSubmit | 覆盖工具和用户输入入口 |
| 拦截异步 | 两个拦截事件禁止 async | 后台任务无法及时阻止操作 |
| 拒绝顺序 | 首个拒绝停止剩余 Hook | 避免拒绝后继续产生副作用 |
| Hook 权限 | 配置视为用户授权 | 避免 Hook 自身陷入 HITL 循环 |
| Hook 递归 | 动作不转成 ToolCall | 防止递归触发 |
| Prompt 注入 | 动态 hook-notification | 保持历史合法和缓存稳定 |
| only_once | 当前会话内存状态 | 不增加持久状态文件 |
| 恢复会话 | 重置 only_once | 新建和恢复均重新计算 |
| 异步结果 | Engine 保存、TUI 轻量读取 | Engine 不依赖 Textual |
| Subagent | 清晰占位结果 | 留给 ch13 |
| `/hooks` | 只读文本输出 | 控制复杂度 |
| 故障策略 | 记录失败，主流程继续 | Hook 不能拖垮 Agent |
| 退出策略 | 有限等待后取消 | 防止退出挂死或资源泄漏 |

## 与教材的差异

| 教材 | Dragon Code | 原因 |
|---|---|---|
| `.mewcode/hooks.yaml` | `.dragon-code/hooks.yaml` | 统一现有项目目录 |
| 动作名 `command/agent` | `shell/subagent` | 与现有 Bash、未来 SubAgent 概念区分 |
| 主要强调 PreToolUse 拒绝 | 同时支持 UserPromptSubmit 拒绝 | 来自已批准 Spec |
| `$FILE_PATH` 等变量 | stdin JSON + `DRAGON_*` 环境变量 | 避免直接字符串拼接并覆盖复杂上下文 |
| 可抽象成通用生命周期总线 | 直接接入 11 个位置 | 更轻、更容易调试和学习 |
| Hook 状态查看较简单 | `/hooks` 展示来源和加载问题 | 便于排查两层配置 |
| 子 Agent 动作 | 本章占位 | 按章节顺序留到 ch13 |

## Spec 覆盖

| Spec | 设计归属 |
|---|---|
| F1–F2 | `hooks/config.py`、HookSnapshot、HookIssue |
| F3 | `matching.py`、`permissions/rules.py` |
| F4 | `hooks/conditions.py`、HookContext |
| F5–F6 | HookEvent、HookContext、11 个接入点 |
| F7–F11 | `hooks/actions.py`、提醒队列、占位结果 |
| F12–F14 | `hooks/engine.py`、后台任务与清理 |
| F15 | `/hooks` Handler、CommandUI |
| F16 | AgentEvent、Conversation、动态提醒、ToolResult |

所有 16 条功能需求均有实现归属。

## 自检结果

1. **Spec 覆盖**：F1–F16 均映射到明确模块和调用入口。
2. **接口完整性**：加载、条件、动作、编排、提醒、异步结果和关闭接口均已定义。
3. **依赖清晰**：Matcher 不依赖 Hook；Hook 不依赖 TUI；TUI 只读取结果；没有新增循环依赖。
4. **历史合法性**：Prompt Hook 不持久化；工具拒绝形成配对 ToolResult；用户拒绝不提交历史。
5. **安全性**：Shell 不直接插值事件值；HTTP 和 UI 不展示秘密配置；Hook 不递归进入工具系统。
6. **兼容性**：旧权限规则格式、AgentEvent 主流程、Agent Loop 和会话存档语义不变。
7. **复杂度控制**：没有通用事件总线、数据库、热重载、Hook 管理 UI 或真实 SubAgent。
8. **教材差异**：关键差异均有明确原因，并服从已批准 Spec 与 Dragon Code 现有结构。
