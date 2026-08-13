# ch10：Slash Command 内置命令框架 Tasks

## 状态

- 阶段：开发完成，已执行自动化与 tmux 验收
- 日期：2026-08-13
- 输入：已批准的 `spec.md` 与 `plan.md`
- 教材参考：`Vibe Coding提示词复制` ch10 Python 部分

## 文件清单

| 操作 | 文件 | 职责 |
|---|---|---|
| 新建 | `src/dragon_code/command/__init__.py` | 导出命令公共接口 |
| 新建 | `src/dragon_code/command/command.py` | CommandKind、Command、异步 Handler |
| 新建 | `src/dragon_code/command/registry.py` | 注册、冲突检测、查找和主名补全 |
| 新建 | `src/dragon_code/command/dispatch.py` | 零参数解析、忙碌保护和异步分发 |
| 新建 | `src/dragon_code/command/ui.py` | CommandUI、CommandStatus |
| 新建 | `src/dragon_code/command/builtin_local.py` | `/help`、`/status` |
| 新建 | `src/dragon_code/command/builtin_ui.py` | 本地 UI 类 Handler |
| 新建 | `src/dragon_code/command/builtin_prompt.py` | `/do`、`/review` 和审查提示 |
| 新建 | `src/dragon_code/command/builtins.py` | 12 条主命令和别名集中注册 |
| 新建 | `src/dragon_code/command/completion.py` | 补全状态机 |
| 新建 | `src/dragon_code/command_widgets.py` | Textual 补全菜单 |
| 新建 | `src/dragon_code/command_screens.py` | 帮助、会话、记忆、权限、审查和确认弹窗 |
| 修改 | `src/dragon_code/tui.py` | CommandUI 接线、输入分流、交互回调和状态栏 |
| 修改 | `src/dragon_code/dragon_code.tcss` | 补全菜单和命令弹窗样式 |
| 修改 | `src/dragon_code/agent.py` | 一次性只读运行和会话替换选项 |
| 修改 | `src/dragon_code/tools/registry.py` | 内置/MCP 工具计数 |
| 修改 | `src/dragon_code/sessions/manager.py` | 安全删除非当前会话 |
| 修改 | `src/dragon_code/memory/models.py` | MemoryInfo |
| 修改 | `src/dragon_code/memory/manager.py` | 记忆列表、读取、加锁删除和索引刷新 |
| 新建 | `tests/test_command.py` | 命令核心和 Handler 单元测试 |
| 新建 | `tests/test_command_completion.py` | 补全状态测试 |
| 修改 | `tests/test_tui.py` | 输入、菜单、弹窗、状态与忙碌保护测试 |
| 修改 | `tests/test_agent.py` | 一次性只读和 clear 模式测试 |
| 修改 | `tests/test_session.py` | 安全删除测试 |
| 修改 | `tests/test_memory.py` | 记忆管理测试 |
| 修改 | `tests/test_tool_registry.py` | 工具计数测试 |
| 修改 | `docs/PROJECT_HANDOFF.md` | 验收后记录 ch10 状态和证据 |
| 修改 | `docs/learning-notes.md` | 验收后记录核心调用链和面试表达 |
| 新建 | `specs/ch10-slash-command/acceptance-report.md` | 逐项验收证据 |

## T1：建立命令核心类型

**文件：** `src/dragon_code/command/command.py`、`src/dragon_code/command/ui.py`、`src/dragon_code/command/__init__.py`

**依赖：** 无

**步骤：**

1. 定义 `CommandKind`、`Command` 和异步 `CommandHandler`。
2. 定义 `CommandStatus`，Token 未知字段允许为 `None`。
3. 定义不依赖 Textual 的 `CommandUI` Protocol。
4. 从包入口导出公共类型。

**验证：** `uv run python -c "from dragon_code.command import Command, CommandKind, CommandStatus, CommandUI"` 无错误。

## T2：实现注册中心

**文件：** `src/dragon_code/command/registry.py`、`tests/test_command.py`

**依赖：** T1

**步骤：**

1. 实现主名称和别名的小写归一化。
2. 实现双向冲突检测，并在错误中包含冲突名称。
3. 实现按主名/别名查找和稳定可见列表。
4. 实现只按非隐藏主命令名匹配的前缀补全。
5. 测试重复主名、主名/别名冲突、别名/别名冲突和隐藏命令。

**验证：** `uv run pytest -q tests/test_command.py -k registry` 通过。

## T3：实现零参数解析与异步分发

**文件：** `src/dragon_code/command/dispatch.py`、`tests/test_command.py`

**依赖：** T1、T2

**步骤：**

1. 区分普通文本、Slash Command、未知命令和多余内容。
2. 对命令名大小写不敏感处理。
3. 空闲时 `await handler(ui)`，忙碌时只输出等待提示。
4. 捕获 Handler 异常并显示可恢复错误。
5. 确认已消费的命令、未知命令和用法错误都不会进入 Agent。

**验证：** `uv run pytest -q tests/test_command.py -k dispatch` 通过。

## T4：注册 12 条命令及别名

**文件：** `src/dragon_code/command/builtin_local.py`、`src/dragon_code/command/builtin_ui.py`、`src/dragon_code/command/builtin_prompt.py`、`src/dragon_code/command/builtins.py`、`tests/test_command.py`

**依赖：** T1–T3

**步骤：**

1. 按 local、local-ui、prompt 实现短小异步 Handler。
2. 实现固定只读审查提示构造函数。
3. 集中注册 12 条主命令、已批准别名、描述和用法。
4. 使用 Fake UI 验证每条主命令与别名调用正确能力。
5. 验证帮助列表完全来自注册中心。

**验证：** `uv run pytest -q tests/test_command.py` 通过。

## T5：实现补全状态机

**文件：** `src/dragon_code/command/completion.py`、`tests/test_command_completion.py`

**依赖：** T2

**步骤：**

1. 保存候选、光标、滚动偏移、打开状态和刚接受文本。
2. 实现候选刷新、上移、下移、选择、关闭和最多 8 行窗口。
3. 保证零候选、单候选、多候选和滚动边界稳定。
4. 验证只匹配主名称，别名和隐藏命令不出现。

**验证：** `uv run pytest -q tests/test_command_completion.py` 通过。

## T6：实现补全 Widget 与输入键位

**文件：** `src/dragon_code/command_widgets.py`、`src/dragon_code/tui.py`、`src/dragon_code/dragon_code.tcss`、`tests/test_tui.py`

**依赖：** T3、T5

**步骤：**

1. 在输入框上方加入最多 8 行的补全 Widget。
2. 监听输入变化，仅在空闲、单行、无空格的 Slash 前缀下显示。
3. 菜单打开时处理上、下、Tab、Enter、Esc，并只在需要时阻止原按键行为。
4. Tab/Enter 只填入主命令；抑制程序写入导致的菜单重开。
5. 菜单关闭后恢复 Alt+Enter、Esc、Ctrl+C 和普通编辑行为。

**验证：** `uv run pytest -q tests/test_tui.py -k completion` 通过。

## T7：实现帮助和状态

**文件：** `src/dragon_code/command_screens.py`、`src/dragon_code/tui.py`、`src/dragon_code/dragon_code.tcss`、`src/dragon_code/tools/registry.py`、`src/dragon_code/memory/manager.py`、`tests/test_tui.py`、`tests/test_tool_registry.py`

**依赖：** T4、T6

**步骤：**

1. 实现命令列表与详情帮助界面。
2. 为 ToolRegistry 增加内置/MCP 数量统计。
3. 为 MemoryManager 增加两级数量读取。
4. 实现 `DragonCodeApp.get_status()` 和状态文本格式化。
5. 验证 `/help`、`/status` 不调用模型、不修改历史。

**验证：** `uv run pytest -q tests/test_command.py tests/test_tool_registry.py tests/test_tui.py -k "help or status or counts"` 通过。

## T8：接入现有退出、压缩和计划命令

**文件：** `src/dragon_code/tui.py`、`tests/test_tui.py`

**依赖：** T4

**步骤：**

1. 让 `/exit`、`/compact`、`/plan`、`/do` 通过注册中心调用现有能力。
2. 移除输入入口中的对应硬编码条件分支。
3. 保证 `/plan` 只切换模式，下一条普通消息才作为规划任务。
4. 保留 `/do` 无计划提示和有计划执行语义。

**验证：** `uv run pytest -q tests/test_tui.py -k "exit or compact or plan"` 通过。

## T9：实现原子 `/clear`

**文件：** `src/dragon_code/agent.py`、`src/dragon_code/tui.py`、`tests/test_agent.py`、`tests/test_tui.py`

**依赖：** T4

**步骤：**

1. 给会话替换增加明确的权限模式保留选项。
2. 在 Worker 中先准备新会话和 ContextManager，再一次切换。
3. 成功后清空对话区、Token、回合、上下文和计划标记，再关闭旧 Writer。
4. 失败时关闭新 Writer 并保留全部旧状态。
5. 验证模型、权限模式、MCP Registry 和长期记忆保持不变。

**验证：** `uv run pytest -q tests/test_agent.py tests/test_tui.py -k clear` 通过。

## T10：扩展会话管理和交互

**文件：** `src/dragon_code/sessions/manager.py`、`src/dragon_code/command_screens.py`、`src/dragon_code/tui.py`、`tests/test_session.py`、`tests/test_tui.py`

**依赖：** T4、T6

**步骤：**

1. 实现只能删除非当前、新格式、sessions 根目录内会话的管理器接口。
2. 复用搜索列表，实现恢复模式和管理模式。
3. 管理模式为选中会话提供恢复/删除/取消。
4. 删除前显示标题与 ID，确认后 Worker 执行并刷新列表。
5. 将 `/resume` 和 `/session` 都接入注册中心。

**验证：** `uv run pytest -q tests/test_session.py tests/test_tui.py -k "resume or session_delete or session_command"` 通过。

## T11：扩展记忆管理和交互

**文件：** `src/dragon_code/memory/models.py`、`src/dragon_code/memory/manager.py`、`src/dragon_code/command_screens.py`、`src/dragon_code/tui.py`、`tests/test_memory.py`、`tests/test_tui.py`

**依赖：** T4、T6

**步骤：**

1. 定义 `MemoryInfo` 并实现安全列表、详情读取和两级计数。
2. 手动删除复用自动记忆锁、文件名校验、原子索引重建和快照刷新。
3. 实现记忆列表、详情和删除确认界面。
4. 接入 `/memory`，验证项目级与用户级严格区分。

**验证：** `uv run pytest -q tests/test_memory.py tests/test_tui.py -k memory` 通过。

## T12：实现权限模式交互

**文件：** `src/dragon_code/command_screens.py`、`src/dragon_code/tui.py`、`tests/test_tui.py`

**依赖：** T4、T6

**步骤：**

1. 展示 default、acceptEdits、bypassPermissions 和当前模式说明。
2. 选择后只调用 Agent 运行时模式接口并刷新显示。
3. 不提供 Plan Mode 选项，不写 YAML。
4. 验证黑名单和沙箱不受影响。

**验证：** `uv run pytest -q tests/test_tui.py -k permission_command` 通过。

## T13：实现一次性只读 `/review`

**文件：** `src/dragon_code/agent.py`、`src/dragon_code/command_screens.py`、`src/dragon_code/tui.py`、`tests/test_agent.py`、`tests/test_tui.py`

**依赖：** T4、T6

**步骤：**

1. 给 `Agent.run()` 增加一次性只读 Registry 选择，不触发 Plan reminder 或 `has_plan`。
2. 实现当前 Git 改动/项目内路径选择和边界校验。
3. 用固定提示通过 `_start_turn(..., read_only=True)` 发起正常 Agent Loop。
4. 验证 Write、Edit、Bash 不在本次工具定义中，原权限模式始终不变。
5. 验证审查请求进入 Conversation 和 JSONL，选择过程不进入历史。

**验证：** `uv run pytest -q tests/test_agent.py tests/test_tui.py -k review` 通过。

## T14：完成统一输入接线和忙碌保护

**文件：** `src/dragon_code/tui.py`、`tests/test_tui.py`

**依赖：** T6–T13

**步骤：**

1. 输入提交统一先调用命令分发器，删除旧 Slash Command 条件链。
2. 普通文本继续走原 `_start_turn()`。
3. 所有非空闲状态统一拒绝命令，不排队、不写历史。
4. 空闲状态栏显示 `Tab 补全 · /help`，任务期间和结束后正确切换。
5. 确认 Ctrl+C、Esc、Alt+Enter 和权限确认键位没有退化。

**验证：** `uv run pytest -q tests/test_tui.py` 通过。

## T15：运行静态检查和全量测试

**文件：** 本章全部代码和测试

**依赖：** T1–T14

**步骤：**

1. 统一格式并修复 lint。
2. 运行 Python 编译检查。
3. 运行全量测试并修复回归。
4. 检查 Git 状态，确认未包含密钥、会话、记忆、`.idea/` 或 `321.txt`。

**验证：**

```bash
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run python -m compileall -q src tests
uv run pytest -q
```

## T16：执行 tmux 端到端验收

**文件：** `specs/ch10-slash-command/checklist.md`、`specs/ch10-slash-command/acceptance-report.md`

**依赖：** T15、已批准的 checklist.md

**步骤：**

1. 在 WSL tmux 中启动真实 Dragon Code。
2. 实操 `/` 补全、帮助、状态、Plan/Do、清空、会话、记忆、权限和只读审查。
3. 验证删除确认、忙碌保护、滚动历史、退出清理和真实模型链路。
4. 对照 checklist 逐项记录实际证据，不可自动验证的项目明确标注验证来源。

**验证：** acceptance report 中每项都有命令、观察结果或测试证据。

## T17：更新交接、学习笔记并提交

**文件：** `docs/PROJECT_HANDOFF.md`、`docs/learning-notes.md`、本章文档

**依赖：** T16

**步骤：**

1. 更新 ch10 已实现能力、核心入口、测试与 tmux 证据。
2. 记录命令分流、Registry、UI Protocol、补全和只读审查的核心学习点。
3. 只暂存本章范围文件，创建本地 Git commit。
4. 不推送远端，直到用户明确要求“推送”。

**验证：** `git status --short` 仅剩用户原有无关文件或为空，`git show --stat --oneline HEAD` 显示 ch10 提交。

## 执行顺序

```text
T1 → T2 → T3 → T4
      └────→ T5 → T6

T4/T6 → T7 → T8 → T9
             ├→ T10
             ├→ T11
             ├→ T12
             └→ T13

T7–T13 → T14 → T15 → T16 → T17
```

T7–T13 在基础命令和补全完成后可按模块独立实现；为便于学习和验证，实际执行时仍按编号顺序推进。

## 教材 Python 提示词对照

### 保持一致

- `command/` 包按定义、注册、分发、UI、三类 Handler 和集中注册拆分。
- Handler 使用异步 `handler(ui)`。
- 所有内置命令零参数，补全只匹配主命令名。
- 帮助与补全都由同一个注册中心驱动。
- 补全状态独立于 Textual 渲染，最多显示 8 行。

### Dragon Code 差异对应任务

- T6：补全只填入、再次 Enter 执行；教材直接执行。
- T9–T13：实现已批准的交互式 clear、会话、记忆、权限和只读审查；教材主要展示。
- T13：增加一次性只读 Registry；教材没有该 Agent 接口。
- T14：所有命令统一空闲保护；教材允许部分 local 命令在忙碌时执行。
- T16：按项目规则增加真实 tmux 验收；教材任务清单未强制这一验证方式。

## Task 自检

1. Plan 中每个组件至少有一个对应任务。
2. 每个任务都列出文件、依赖、具体步骤和可运行验证。
3. 依赖链无循环，T1–T14 构成功能，T15–T17 负责全量质量、验收和交接。
4. 命令名、类型名和接口与已批准 Plan 一致。
5. 没有实现用户自定义命令、Skill、复杂参数、命令队列或新权限系统。
