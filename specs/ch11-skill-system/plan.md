# Dragon Code ch11 Skill 系统 Plan

## 架构概览

ch11 在现有 Agent、工具注册中心、权限系统、Slash Command 和 TUI 之上增加 Skill 层，不重写这些已有模块。

整体调用链如下：

```text
Skill 文件
  → SkillLoader 扫描和解析
  → SkillManager 保存有效定义快照
  → SkillRuntime 保存当前会话的激活状态
  → Slash Command 或 LoadSkill 触发
  → SkillExecutor 选择 inline / fork
  → Agent Loop 使用动态 SOP 和工具子集
  → ToolRegistry + PermissionEngine 执行工具
```

### SkillLoader

负责读取项目级、用户级和内置级 Skill。它只处理文件、格式、覆盖顺序和错误收集，不负责执行 Skill。

### SkillManager

保存当前有效的不可变 Skill 快照，为 System Prompt、Slash Command、管理界面和新会话提供同一份定义。重新加载时先构造完整新快照，成功后再整体替换，避免出现半更新状态。

### SkillRuntime

每个 Agent 各自拥有一个 Runtime，用于记录当前已激活的 inline Skill、动态 SOP 和临时工具白名单。新建、切换、恢复或清空会话时清除 Runtime，但 SkillManager 中的定义继续保留。

### SkillExecutor

负责显式命令与 `LoadSkill` 的执行编排。inline 模式复用主 Agent；fork 模式创建临时独立 Agent，实时转发事件，结束后只返回摘要。

### LoadSkillTool

模型根据用户意图自动激活 Skill 的系统工具。它始终可见，只返回简短状态，不把完整 SOP 重复写入 ToolResult。

### SkillScriptTool

把目录型 Skill 的 `tool.json` 适配为现有 `Tool` 接口。工具脚本通过独立 Python 子进程执行，参数和结果使用 JSON 管道传递。

### SkillCommandHandler

把有效 Skill 动态注册成 Slash Command，支持 `$ARGUMENTS`。原有内置命令仍保持零参数和交互式行为。

### SkillManagementScreen

由零参数 `/skill` 打开，负责列表、详情、加载错误和重新扫描。界面不直接解析 Skill 文件。

## 核心数据结构与接口

### SkillDefinition

```python
@dataclass(frozen=True)
class SkillDefinition:
    name: str
    description: str
    prompt_body: str
    allowed_tools: tuple[str, ...]
    mode: str
    model: str | None
    context: str
    source_level: str
    source_path: Path
    skill_dir: Path
    custom_tools: tuple[SkillToolSpec, ...]
```

- `mode` 只允许 `inline` 或 `fork`。
- `context` 只允许 `full`、`recent` 或 `none`，仅 fork 使用。
- inline 忽略 `model`，继续使用当前会话模型。
- `allowed_tools` 为空表示该 Skill 不额外开放普通工具，系统工具仍保留。

### SkillPathArgument

```python
@dataclass(frozen=True)
class SkillPathArgument:
    name: str
    access: str
```

`access` 只允许 `read` 或 `write`，供路径沙箱判断额外只读根目录是否可以使用。

### SkillToolSpec

```python
@dataclass(frozen=True)
class SkillToolSpec:
    name: str
    description: str
    input_schema: dict
    script_path: Path
    read_only: bool
    destructive: bool
    command_arguments: tuple[str, ...]
    path_arguments: tuple[SkillPathArgument, ...]
```

未提供 annotations 时使用保守默认值：非只读、可能破坏、不可并发。所有 Skill 自定义工具无论注解如何都串行执行。

### SkillLoadIssue

```python
@dataclass(frozen=True)
class SkillLoadIssue:
    source_path: Path
    code: str
    message: str
```

用于展示单个 Skill 的解析、依赖、冲突或脚本问题，不携带堆栈和敏感环境变量。

### SkillSnapshot

```python
@dataclass(frozen=True)
class SkillSnapshot:
    skills: tuple[SkillDefinition, ...]
    issues: tuple[SkillLoadIssue, ...]
```

Skill 顺序固定，作为命令顺序和稳定 System Prompt 摘要的唯一来源。

### ActiveSkill

```python
@dataclass(frozen=True)
class ActiveSkill:
    name: str
    rendered_prompt: str
    allowed_tools: tuple[str, ...]
```

重复激活同一个 Skill 时更新内容，不重复增加条目；多个 Skill 保持首次激活顺序。

### SkillLoader

```python
class SkillLoader:
    def load_all(self) -> SkillSnapshot: ...
    def reload_one(
        self, previous: SkillDefinition
    ) -> tuple[SkillDefinition, SkillLoadIssue | None]: ...
```

### SkillManager

```python
class SkillManager:
    def reload(self) -> SkillSnapshot: ...
    def get(self, name: str) -> SkillDefinition | None: ...
    def list_skills(self) -> list[SkillDefinition]: ...
    def issues(self) -> list[SkillLoadIssue]: ...
    def summary_text(self) -> str: ...
    def create_runtime(self) -> SkillRuntime: ...
    def build_registry(self, base_registry: ToolRegistry) -> ToolRegistry: ...
```

### SkillRuntime

```python
class SkillRuntime:
    def activate(self, skill: SkillDefinition, arguments: str = "") -> ActiveSkill: ...
    def clear(self) -> None: ...
    def active_skills(self) -> list[ActiveSkill]: ...
    def reminder_text(self) -> str: ...
    def allowed_tool_names(self) -> set[str] | None: ...
```

- 没有激活 Skill 时返回 `None`，表示不额外限制现有工具。
- 有激活 Skill 时返回白名单并集。
- 系统工具由 Agent 在过滤后重新加入。

### SkillExecutor

```python
class SkillExecutor:
    async def run_explicit(self, name: str, arguments: str = ""): ...
    async def execute_load_call(self, name: str): ...
```

它把执行过程转换为现有 AgentEvent，不直接调用 Textual 控件。

### Command 扩展

现有 UI-only Handler 保留，命令增加可选的参数 Handler 和来源字段。只有动态 Skill 命令使用参数 Handler，旧内置命令继续拒绝参数。

### AgentEvent 扩展

事件增加可选 `skill_name`，并补充 `skill_start`、`skill_end` 和 `skill_warning` 类型。TUI 仍只消费事件，不理解 Skill 内部实现。

## 模块设计

### `skills/parser.py`

**职责：** 定义 Skill 数据类型，解析 YAML frontmatter 与 Markdown 正文，校验名称、模式、上下文、白名单和 `$ARGUMENTS`。

**限制：** 单个 `SKILL.md` 最大 256KB；YAML 使用 `safe_load`；错误必须包含来源路径。

### `skills/loader.py`

**职责：** 扫描以下三层并处理覆盖：

1. `<project>/.dragon-code/skills`
2. `~/.dragon-code/skills`
3. Dragon Code 内置 Skill 资源

同时支持单文件 Skill 和目录型 Skill。扫描和覆盖顺序固定。单个无效 Skill 被跳过并记录问题；热更新失败时回退上一次有效版本。

### `skills/directory.py`

**职责：** 解析 `tool.json`、JSON Schema、风险注解、安全参数和脚本路径。

脚本真实路径必须仍在当前 Skill 目录内。工具采用 `skill__<skill-name>__<tool-name>` 命名空间。重复名称、不存在脚本、非法 Schema 和不存在的 `allowedTools` 在加载阶段报告。

### `skills/manager.py`

**职责：** 实现应用级 SkillManager 和会话级 SkillRuntime，向 Prompt、命令、Agent 和管理界面提供一致数据。

### `skills/tools.py`

**职责：** 实现 `LoadSkillTool` 和 `SkillScriptTool`。

脚本使用 `sys.executable` 启动，工作目录为 Skill 目录；stdin 写入参数 JSON，stdout 读取结果 JSON。超时 30 秒，stdout 和 stderr 各限制 100KB。取消时终止子进程并关闭管道。

### `skills/executor.py`

**职责：** 编排 inline 与 fork。

- inline：激活 Skill，复用主 Agent 和当前模型。
- fork：创建独立 Conversation、ContextManager、SkillRuntime 和 Agent；复用 Provider 配置、项目根目录、权限引擎和审批控制器。
- `recent` 携带最近 5 组合法对话。
- fork 事件附带 Skill 名实时转发，结束后只向主会话回流最终摘要。

### `agent.py`

在五个位置接入 Skill：

1. 每轮请求前构造动态 Skill reminder。
2. 根据 Runtime 生成工具子集。
3. 始终保留系统工具。
4. 提供 fork Skill 的运行入口。
5. 新建、恢复、切换或清空会话时清除 Runtime。

### `prompt.py`

把 Skill 名称和描述按固定顺序加入稳定 System Prompt；完整 SOP 与 Plan Mode 提醒一起走动态 system-reminder，不写入持久历史。

### `command/`

命令模型增加动态来源与参数 Handler；分发器只给 Skill 命令传递原始参数。注册中心支持原子替换全部 Skill 命令。移除硬编码 `/review` 提示，由 review Skill 接管并保留 `/r`。

### `command_screens.py` 与 `tui.py`

增加 Skill 列表、详情、错误和重新加载界面。TUI 复用 `_start_turn()` 与 `_consume_turn()` 展示 inline 和 fork 事件，并在取消时清理 Worker、子 Agent 和子进程。

### `builtin_skills/`

提供 commit、review、test 三个 `SKILL.md`。它们使用与用户 Skill 相同的解析和执行路径，不在 Python 中硬编码 SOP。

## 模块交互

### 启动与发现

```text
启动
  → SkillLoader 扫描三层目录
  → 解析 SKILL.md / tool.json
  → 校验依赖、冲突、Schema 和脚本路径
  → SkillManager 原子替换 SkillSnapshot
  → 注册动态命令
  → 稳定 Skill 摘要进入 System Prompt
```

### inline 执行

1. Slash Command 或 `LoadSkill` 取得最新有效 Skill。
2. `$ARGUMENTS` 替换后写入 SkillRuntime。
3. Runtime 生成动态 SOP 和工具白名单并集。
4. Agent 过滤工具，再补回系统工具。
5. 主 Agent 使用当前模型和历史继续 Agent Loop。

### fork 执行

1. SkillExecutor 按 context 构造独立合法历史。
2. 创建临时 Agent 和 Runtime。
3. 子 Agent 使用相同权限与审批路径运行。
4. 子事件实时转发给 TUI。
5. 结束后只把最终摘要回流主会话。

### 自定义工具执行

```text
ToolCall
  → Skill 白名单检查
  → PermissionEngine
  → 必要时用户确认
  → SkillScriptTool 启动子进程
  → stdin JSON / stdout JSON
  → ToolResult 回灌 Agent Loop
```

`tool.json.security.commandArguments` 指定需经过危险命令黑名单的顶层参数；`pathArguments` 指定需经过路径沙箱的顶层参数。未声明的语义不进行猜测，但工具默认按有副作用处理并触发 Ask。

### 热更新与生命周期

- 文件型 Skill 每次执行前重读，失败使用上次有效版本并发出 warning。
- `/skill` 可手动重新扫描全部 Skill。
- `/clear`、新建、切换和恢复会话清除 Active Skills 与临时白名单。
- 取消 fork 或脚本时取消 Worker、终止子进程并保持主历史合法。

## 文件组织

```text
src/dragon_code/
├── skills/
│   ├── __init__.py
│   ├── parser.py
│   ├── loader.py
│   ├── directory.py
│   ├── manager.py
│   ├── tools.py
│   └── executor.py
├── builtin_skills/
│   ├── commit/SKILL.md
│   ├── review/SKILL.md
│   └── test/SKILL.md
├── command/                    — 扩展动态 Skill 命令与参数 Handler
├── permissions/                — 扩展 Skill 工具权限、命令与路径检查
├── agent.py                    — Runtime、提醒、白名单和 fork 接入
├── prompt.py                   — 稳定 Skill 摘要
├── models.py                   — Skill 来源事件
├── tool_scheduler.py           — 自定义工具强制串行
├── command_screens.py          — Skill 管理界面
├── tui.py                      — Skill 事件展示与取消
└── cli.py                      — 启动组装
```

测试新增：

```text
tests/
├── test_skill_parser.py
├── test_skill_loader.py
├── test_skill_runtime.py
├── test_skill_tools.py
└── test_skill_executor.py
```

同时修改现有 Agent、Prompt、Command、Permission 和 TUI 测试，验证回归行为。

## 技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| Skill 格式 | YAML frontmatter + Markdown | 与教材一致，方便直接编辑 |
| 加载优先级 | 项目 → 用户 → 内置 | 最具体的项目要求优先 |
| 渐进加载 | 摘要稳定、SOP 动态 | 减少 Token 并保持缓存稳定 |
| 状态拆分 | Manager 管定义，Runtime 管会话激活 | 防止跨会话泄漏 |
| 显式触发 | 动态 Slash Command | 用户可确定执行 |
| 自动触发 | 系统工具 LoadSkill | 模型可按意图激活 |
| inline | 复用主 Agent 和当前模型 | 保留上下文和缓存 |
| fork | 独立 Agent，实时事件，摘要回流 | 隔离长任务历史 |
| recent | 最近 5 组合法对话 | 在上下文和体量之间取平衡 |
| 白名单 | 多 Skill 取并集，系统工具始终保留 | 支持嵌套又限制普通工具 |
| 自定义工具名 | `skill__<skill>__<tool>` | 防冲突且来源清晰 |
| 脚本执行 | 独立 Python 子进程 + JSON | 隔离主进程状态 |
| 调度 | 自定义工具全部串行 | 不猜测第三方脚本并发安全性 |
| 风险默认值 | 非只读、可能破坏 | 对未知工具采取保守策略 |
| 权限 | 白名单后仍进入五层权限 | Skill 不能绕过现有安全边界 |
| 参数安全 | tool.json 声明命令和路径参数 | 让现有黑名单与沙箱可检查 |
| 热更新 | 执行前重读，失败回退 | 快速生效且不中断会话 |
| 管理 | 零参数 `/skill` 交互界面 | 不要求记忆子命令或路径 |
| 内置 Skill | 使用相同文件格式和加载路径 | 可作为用户样板，避免硬编码 |
| 发布 | 使用 Python 包资源 | 安装后仍能读取内置 Markdown |

## 安全边界

Dragon Code 可以限制工具可见性、调用权限、已声明的命令和路径参数、执行时间、输出体量以及取消后的子进程清理。

本章不提供操作系统级沙箱，无法保证脚本源码内部不会访问网络、未声明路径或其他系统 API。文档和 UI 必须明确这一边界。

## 与教材的差异

| 教材 | Dragon Code | 原因 |
|---|---|---|
| fork 示例不含完整权限衔接 | fork 复用五层权限和审批 | 防止权限绕过 |
| 自定义工具直接接入运行时 | 独立 Python 子进程 | 隔离主进程和错误 |
| 风险元信息较简单 | MCP 风格注解 + 参数安全声明 | 接入现有黑名单和路径沙箱 |
| `/skill list/info/reload` | 零参数 `/skill` 交互界面 | 延续 ch10 交互设计 |
| 主要关注 fork 最终结果 | 过程实时显示，主历史只留摘要 | 可观察且不污染主历史 |
| Skill 命令直接收参数 | 仅动态 Skill 命令收参数 | 旧命令行为不退化 |
| review 可能是硬编码命令 | review Skill 接管并保留 `/r` | 验证 Skill 可替代固定工作流 |

## Spec 覆盖

| Spec | 设计归属 |
|---|---|
| F1–F3 | parser、loader、manager、稳定摘要 |
| F4–F7 | LoadSkillTool、SkillRuntime、Agent 工具过滤 |
| F8–F10 | SkillExecutor、fork Agent、权限引擎 |
| F11–F13 | directory、SkillScriptTool、串行调度 |
| F14–F16 | 加载校验、动态命令、Skill 管理界面 |
| F17–F18 | Runtime 生命周期、内置 Skill 资源 |

所有功能需求均有明确模块和调用入口，没有发现未归属需求。

## 自检结果

1. **Spec 覆盖**：F1–F18 均已映射到模块和接口。
2. **接口完整性**：加载、状态、执行、命令、工具和事件边界均已定义。
3. **依赖清晰**：Parser/Loader 不依赖 TUI；Manager 不执行工具；Executor 通过 AgentEvent 与界面解耦，没有新增循环依赖。
4. **历史合法性**：SOP 不持久化；fork 只回流摘要；取消不写入半截子历史。
5. **缓存确定性**：稳定摘要由 SkillSnapshot 固定排序生成，完整 SOP 只走动态提醒。
6. **安全一致性**：白名单是附加限制，不替代权限系统；自定义脚本边界没有被描述成 OS 沙箱。
7. **复杂度控制**：不增加数据库、文件监听器、通用 SubAgent 树或依赖注入框架。
8. **教材差异**：所有关键差异均已记录理由。
