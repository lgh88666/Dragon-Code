# Dragon Code ch11 Skill 系统 Tasks

## 状态

- 阶段：等待用户审批
- 日期：2026-08-14
- 输入：已批准的 `spec.md` 与 `plan.md`
- 教材参考：`Vibe Coding提示词复制` ch11 Python 部分

## 文件清单

| 操作 | 文件 | 职责 |
|---|---|---|
| 新建 | `src/dragon_code/skills/__init__.py` | 导出 Skill 公共接口 |
| 新建 | `src/dragon_code/skills/parser.py` | Skill 类型、frontmatter 解析和参数替换 |
| 新建 | `src/dragon_code/skills/directory.py` | `tool.json`、脚本路径、Schema 和安全声明 |
| 新建 | `src/dragon_code/skills/loader.py` | 三级扫描、覆盖、错误隔离和热更新 |
| 新建 | `src/dragon_code/skills/manager.py` | SkillSnapshot、SkillManager、SkillRuntime |
| 新建 | `src/dragon_code/skills/tools.py` | LoadSkillTool 和 SkillScriptTool |
| 新建 | `src/dragon_code/skills/executor.py` | inline 与 fork 编排 |
| 新建 | `src/dragon_code/builtin_skills/commit/SKILL.md` | commit 内置 Skill |
| 新建 | `src/dragon_code/builtin_skills/review/SKILL.md` | review 内置 Skill |
| 新建 | `src/dragon_code/builtin_skills/test/SKILL.md` | test 内置 Skill |
| 修改 | `src/dragon_code/agent.py` | Runtime、提醒、白名单、Skill 执行与生命周期 |
| 修改 | `src/dragon_code/prompt.py` | 稳定 Skill 摘要与动态 SOP 合并 |
| 修改 | `src/dragon_code/models.py` | Skill 来源事件字段 |
| 修改 | `src/dragon_code/tools/base.py` | 系统工具标记 |
| 修改 | `src/dragon_code/tools/registry.py` | Registry 组合、系统工具和 Skill 工具 |
| 修改 | `src/dragon_code/tool_scheduler.py` | 自定义工具强制串行 |
| 修改 | `src/dragon_code/permissions/engine.py` | Skill 工具权限和命令参数检查 |
| 修改 | `src/dragon_code/permissions/rules.py` | Skill 工具规则名称支持 |
| 修改 | `src/dragon_code/permissions/sandbox.py` | 自定义工具路径参数检查 |
| 修改 | `src/dragon_code/command/command.py` | 动态来源和参数 Handler |
| 修改 | `src/dragon_code/command/registry.py` | 原子替换 Skill 命令 |
| 修改 | `src/dragon_code/command/dispatch.py` | 只向 Skill 命令传递自由文本参数 |
| 修改 | `src/dragon_code/command/builtins.py` | `/skill` 注册与 review 迁移 |
| 修改 | `src/dragon_code/command/builtin_prompt.py` | 删除硬编码 review SOP |
| 修改 | `src/dragon_code/command/ui.py` | Skill 管理与执行 UI 接口 |
| 修改 | `src/dragon_code/command_screens.py` | Skill 管理界面 |
| 修改 | `src/dragon_code/tui.py` | Skill 事件、fork、取消和会话清理接线 |
| 修改 | `src/dragon_code/cli.py` | 创建并注入 SkillManager |
| 修改 | `src/dragon_code/clients/factory.py` | fork 模型覆盖客户端创建 |
| 修改 | `src/dragon_code/dragon_code.tcss` | Skill 管理界面和事件样式 |
| 修改 | `pyproject.toml` | 确保内置 Skill 资源进入 wheel |
| 新建 | `tests/test_skill_parser.py` | Skill 格式与参数替换测试 |
| 新建 | `tests/test_skill_loader.py` | 三级加载、目录型 Skill、冲突和热更新测试 |
| 新建 | `tests/test_skill_runtime.py` | 激活、白名单、提醒和生命周期测试 |
| 新建 | `tests/test_skill_tools.py` | LoadSkill、脚本协议、权限和取消测试 |
| 新建 | `tests/test_skill_executor.py` | inline、fork、模型、上下文和回流测试 |
| 修改 | `tests/test_agent.py` | Agent 工具过滤、历史和清理测试 |
| 修改 | `tests/test_command.py` | 动态 Skill 命令、参数、冲突和 `/r` 测试 |
| 修改 | `tests/test_prompt.py` | 稳定摘要与动态 SOP 测试 |
| 修改 | `tests/test_permission_engine.py` | 自定义工具五层权限测试 |
| 修改 | `tests/test_permission_sandbox.py` | 自定义路径参数沙箱测试 |
| 修改 | `tests/test_tool_registry.py` | 系统工具和组合 Registry 测试 |
| 修改 | `tests/test_tool_scheduler.py` | Skill 工具串行顺序测试 |
| 修改 | `tests/test_tui.py` | `/skill`、fork 事件、取消和会话生命周期测试 |
| 修改 | `docs/PROJECT_HANDOFF.md` | 验收后记录 ch11 状态与证据 |
| 修改 | `docs/learning-notes.md` | 源码回顾后记录 Skill 核心知识 |
| 新建 | `specs/ch11-skill-system/acceptance-report.md` | 逐项验收证据 |

## T1：定义 Skill 核心数据类型

**文件：** `src/dragon_code/skills/parser.py`、`src/dragon_code/skills/__init__.py`

**依赖：** 无

**步骤：**

1. 定义 `SkillDefinition`、`SkillToolSpec`、`SkillPathArgument`、`SkillLoadIssue`。
2. 使用普通 frozen dataclass 保存不可变定义。
3. 定义 Skill 文件、tool.json 和输出体量常量。
4. 从 `skills/__init__.py` 导出公共类型。

**验证：** `uv run python -c "from dragon_code.skills import SkillDefinition, SkillToolSpec, SkillLoadIssue"` 无错误。

## T2：实现 SKILL.md 解析与参数替换

**文件：** `src/dragon_code/skills/parser.py`、`tests/test_skill_parser.py`

**依赖：** T1

**步骤：**

1. 分离 YAML frontmatter 与 Markdown 正文，使用 `yaml.safe_load`。
2. 校验名称、描述、mode、context、model 和 allowedTools 类型。
3. 限制文件最大 256KB，并让错误包含来源路径。
4. 实现 `$ARGUMENTS` 的直接文本替换；无参数时替换为空字符串。
5. 测试合法 Skill、缺字段、非法名称、坏 YAML、错误 mode/context 和超大文件。

**验证：** `uv run pytest -q tests/test_skill_parser.py` 通过。

## T3：解析目录型 Skill 工具声明

**文件：** `src/dragon_code/skills/directory.py`、`tests/test_skill_loader.py`

**依赖：** T1、T2

**步骤：**

1. 读取最大 128KB 的 `tool.json`。
2. 校验工具名称、描述、参数 Schema 和 Python 脚本字段。
3. 解析 MCP 风格 readOnly/destructive 注解，缺失时使用保守默认值。
4. 解析 `security.commandArguments` 和 `security.pathArguments` 顶层参数声明。
5. 解析符号链接后确认脚本仍位于 Skill 目录内。
6. 为工具生成 `skill__<skill>__<tool>` 全局名称并检测重复。

**验证：** `uv run pytest -q tests/test_skill_loader.py -k "directory or tool_json or script_path"` 通过。

## T4：实现三级稳定扫描与覆盖

**文件：** `src/dragon_code/skills/loader.py`、`tests/test_skill_loader.py`

**依赖：** T2、T3

**步骤：**

1. 按项目级、用户级、内置级扫描单文件和目录型 Skill。
2. 固定目录和文件排序，项目级同名覆盖用户级和内置级。
3. 单个损坏 Skill 转为 `SkillLoadIssue`，不阻断其他 Skill。
4. 校验 allowedTools 引用、工具重名和 Skill 名与保留命令冲突。
5. 测试三级覆盖、顺序确定性、失败隔离和降级到低优先级版本。

**验证：** `uv run pytest -q tests/test_skill_loader.py -k "priority or order or isolation or conflict"` 通过。

## T5：实现 SkillManager 原子快照

**文件：** `src/dragon_code/skills/manager.py`、`tests/test_skill_runtime.py`

**依赖：** T4

**步骤：**

1. 定义 `SkillSnapshot` 并保存稳定 Skill 顺序与加载问题。
2. 实现 get、list、issues 和稳定 summary_text。
3. 实现先构造新快照、成功后整体替换的 reload。
4. 保证调用方不会观察到半注册命令或半注册工具。

**验证：** `uv run pytest -q tests/test_skill_runtime.py -k "manager or snapshot or summary"` 通过。

## T6：实现热更新与有效版本回退

**文件：** `src/dragon_code/skills/loader.py`、`src/dragon_code/skills/manager.py`、`tests/test_skill_loader.py`

**依赖：** T5

**步骤：**

1. 执行前按来源路径重新读取文件型或目录型 Skill。
2. 解析成功时返回最新定义。
3. 解析失败时保留上次有效定义并返回 warning。
4. 删除或移动来源时也使用结构化 warning，不抛堆栈。

**验证：** `uv run pytest -q tests/test_skill_loader.py -k "reload or fallback"` 通过。

## T7：实现会话级 SkillRuntime

**文件：** `src/dragon_code/skills/manager.py`、`tests/test_skill_runtime.py`

**依赖：** T5

**步骤：**

1. 实现激活、重复激活更新、激活顺序和 clear。
2. 用 `$ARGUMENTS` 生成 `ActiveSkill.rendered_prompt`。
3. 按激活顺序生成动态 reminder 文本。
4. 计算多个 Skill 的 allowedTools 并集。
5. 区分“没有激活 Skill”和“已激活但白名单为空”。

**验证：** `uv run pytest -q tests/test_skill_runtime.py -k "activate or reminder or whitelist or clear"` 通过。

## T8：扩展 Tool 与 ToolRegistry 的系统工具能力

**文件：** `src/dragon_code/tools/base.py`、`src/dragon_code/tools/registry.py`、`tests/test_tool_registry.py`

**依赖：** T5

**步骤：**

1. 给 Tool 增加默认关闭的 `is_system_tool` 标记。
2. 实现 Registry 的稳定名称读取和组合，不修改原 Registry。
3. 实现白名单 subset 后重新加入系统工具。
4. 保持内置/MCP 工具统计的旧语义，Skill 工具单独识别。

**验证：** `uv run pytest -q tests/test_tool_registry.py` 通过。

## T9：实现 LoadSkillTool

**文件：** `src/dragon_code/skills/tools.py`、`tests/test_skill_tools.py`

**依赖：** T6、T7、T8

**步骤：**

1. 定义只接收 Skill 名称的参数模型。
2. 把 LoadSkill 标记为只读、系统工具和可并发工具。
3. 调用 Manager 热重读并激活到当前 Runtime。
4. ToolResult 只返回简短状态，不复制完整 SOP。
5. 不存在或最新文件损坏时返回可恢复结果或回退 warning。

**验证：** `uv run pytest -q tests/test_skill_tools.py -k load_skill` 通过。

## T10：实现 SkillScriptTool 正常执行路径

**文件：** `src/dragon_code/skills/tools.py`、`tests/test_skill_tools.py`

**依赖：** T3、T8

**步骤：**

1. 根据 JSON Schema 构造可被 Tool 基类使用的参数模型或等价校验入口。
2. 使用 `sys.executable`、Skill 目录 cwd 和 asyncio 子进程启动脚本。
3. 把参数 JSON 写入 stdin，并关闭输入流。
4. 读取 stdout JSON，转换为成功 ToolResult。
5. 不导入脚本模块，不把主进程对象传入脚本。

**验证：** `uv run pytest -q tests/test_skill_tools.py -k "script_success or stdin or stdout"` 通过。

## T11：完成脚本失败、体量和取消保护

**文件：** `src/dragon_code/skills/tools.py`、`tests/test_skill_tools.py`

**依赖：** T10

**步骤：**

1. 处理参数错误、启动失败、非零退出、非法 JSON 和结果字段错误。
2. 实现 30 秒超时与可在测试中注入的短超时。
3. 限制 stdout/stderr，各自最多保留 100KB。
4. 错误结果不返回环境变量全集、堆栈或未经控制的 stderr。
5. 收到取消时终止子进程，等待回收并重新抛出 CancelledError。

**验证：** `uv run pytest -q tests/test_skill_tools.py -k "failure or timeout or limit or cancel"` 通过。

## T12：让自定义工具经过现有权限系统

**文件：** `src/dragon_code/permissions/engine.py`、`src/dragon_code/permissions/rules.py`、`src/dragon_code/permissions/sandbox.py`、`tests/test_permission_engine.py`、`tests/test_permission_sandbox.py`

**依赖：** T3、T10

**步骤：**

1. 识别 `skill__<skill>__<tool>` 工具名并允许完整名称规则。
2. 对声明的 commandArguments 逐项调用危险命令黑名单。
3. 对声明的 pathArguments 做符号链接解析和项目根边界检查。
4. 未命中规则时，只读工具仍按模式判断；其他 Skill 工具默认 Ask。
5. 会话允许和永久允许仅针对当前完整工具名，不泛化参数。
6. 测试危险命令、项目外路径、deny/allow、模式和用户确认路径。

**验证：** `uv run pytest -q tests/test_permission_engine.py tests/test_permission_sandbox.py -k skill` 通过。

## T13：保证 Skill 自定义工具串行调度

**文件：** `src/dragon_code/tool_scheduler.py`、`tests/test_tool_scheduler.py`

**依赖：** T10

**步骤：**

1. 识别 SkillScriptTool 或 skill 命名空间。
2. 即使 readOnly 注解为真，也把每个自定义工具拆成单独串行批次。
3. 保持模型给出的调用顺序和结果回灌顺序。
4. 不改变内置只读工具和 MCP 工具的现有调度。

**验证：** `uv run pytest -q tests/test_tool_scheduler.py` 通过。

## T14：接入稳定 Skill 摘要和动态 SOP

**文件：** `src/dragon_code/prompt.py`、`tests/test_prompt.py`

**依赖：** T5、T7

**步骤：**

1. 增加稳定“可用 Skills”模块，只包含名称和描述。
2. 按 SkillSnapshot 固定顺序输出，空列表时跳过模块。
3. 把 Active Skills SOP 与 Plan Mode reminder 合并为一次动态注入。
4. 验证完整 SOP 不进入稳定 System Prompt 或普通历史。

**验证：** `uv run pytest -q tests/test_prompt.py -k skill` 通过。

## T15：把 SkillRuntime 接入主 Agent Loop

**文件：** `src/dragon_code/agent.py`、`src/dragon_code/models.py`、`tests/test_agent.py`

**依赖：** T7–T9、T13、T14

**步骤：**

1. Agent 接收 Manager、Runtime 和包含 LoadSkill 的完整 Registry。
2. 每次 LLM 请求前生成当前动态 reminder。
3. 有激活 Skill 时按白名单并集过滤工具，再补回系统工具。
4. 在执行阶段再次拒绝模型伪造的白名单外调用。
5. 给 AgentEvent 增加可选 skill_name 和 Skill 生命周期事件。
6. 保持 Plan Mode、权限、上下文压缩和历史回灌原路径。

**验证：** `uv run pytest -q tests/test_agent.py -k "skill or whitelist or system_tool"` 通过。

## T16：扩展命令框架支持动态 Skill 参数

**文件：** `src/dragon_code/command/command.py`、`src/dragon_code/command/registry.py`、`src/dragon_code/command/dispatch.py`、`tests/test_command.py`

**依赖：** T5

**步骤：**

1. 保留现有 `handler(ui)`，增加仅供动态 Skill 使用的参数 Handler。
2. 解析器返回命令名和原始参数文本，不提前拆词。
3. 旧命令遇到参数继续显示“不接收参数”。
4. Registry 支持按 source 原子替换动态 Skill 命令。
5. 检测 Skill 主名与内置主名/别名冲突，隐藏命令不进入补全。

**验证：** `uv run pytest -q tests/test_command.py -k "argument or dynamic or skill_command or conflict"` 通过。

## T17：提供内置 Skill 并迁移 review

**文件：** `src/dragon_code/builtin_skills/commit/SKILL.md`、`src/dragon_code/builtin_skills/review/SKILL.md`、`src/dragon_code/builtin_skills/test/SKILL.md`、`src/dragon_code/command/builtins.py`、`src/dragon_code/command/builtin_prompt.py`、`pyproject.toml`、`tests/test_skill_loader.py`、`tests/test_command.py`

**依赖：** T4、T16

**步骤：**

1. 按教材 Python 样板编写 commit、review、test 的 frontmatter 和中文 SOP。
2. commit/test 使用 inline，review 使用 fork；配置各自 allowedTools 和 context。
3. 删除 Python 中硬编码的 review 提示和注册项。
4. 为 review Skill 保留 `/r` 别名，其他 Skill 不自动生成别名。
5. 构建 wheel 并验证三个 Markdown 资源被包含。

**验证：**

```bash
uv run pytest -q tests/test_skill_loader.py tests/test_command.py -k "builtin or review or alias"
uv build
```

## T18：实现 Skill 管理界面

**文件：** `src/dragon_code/command/ui.py`、`src/dragon_code/command_screens.py`、`src/dragon_code/command/builtins.py`、`src/dragon_code/dragon_code.tcss`、`tests/test_tui.py`

**依赖：** T5、T16、T17

**步骤：**

1. 给 CommandUI 增加打开 Skill 管理界面与执行 Skill 的能力。
2. 注册零参数 `/skill`，不增加 list/info/reload 子命令。
3. 展示 Skill 名称、描述、来源、模式、白名单、自定义工具和加载问题。
4. 提供列表选择、查看详情、重新扫描和关闭操作。
5. 重载成功后原子刷新动态命令和补全候选。

**验证：** `uv run pytest -q tests/test_tui.py -k skill_screen` 通过。

## T19：构造 fork 的独立合法上下文

**文件：** `src/dragon_code/skills/executor.py`、`tests/test_skill_executor.py`

**依赖：** T6、T7

**步骤：**

1. 实现 full、recent、none 三种上下文复制。
2. recent 只取最近 5 组完整合法对话，不截断工具调用与结果配对。
3. 新建 Conversation 和 ContextManager，不共享主会话可变列表或 Writer。
4. 在 fork 初始任务中注入已渲染 SOP 和用户参数。

**验证：** `uv run pytest -q tests/test_skill_executor.py -k context` 通过。

## T20：实现 fork 模型覆盖

**文件：** `src/dragon_code/clients/factory.py`、`src/dragon_code/skills/executor.py`、`tests/test_skill_executor.py`

**依赖：** T19

**步骤：**

1. 未填写 model 时复用当前 Provider 配置的模型名。
2. 填写 model 时复制 ProviderConfig，只替换模型名。
3. 协议、base_url、api_key、thinking 和 context_window 保持不变。
4. 客户端创建或首轮请求失败时返回可恢复 Skill 错误，不启动残缺任务。
5. inline 明确忽略 model 字段。

**验证：** `uv run pytest -q tests/test_skill_executor.py -k model` 通过。

## T21：实现 fork 事件、权限、摘要与取消

**文件：** `src/dragon_code/skills/executor.py`、`src/dragon_code/agent.py`、`tests/test_skill_executor.py`、`tests/test_agent.py`

**依赖：** T12、T15、T19、T20

**步骤：**

1. 为 fork 创建独立 Runtime 和 Agent，但复用项目、权限引擎和审批控制器。
2. 给子 Agent 的文本、工具、权限、进度和错误事件标记 skill_name 并实时转发。
3. 子 Agent 自然完成后提取最终摘要并回流主会话。
4. 主历史不写入完整子对话，不产生悬空工具调用。
5. 取消时停止子 Agent 和脚本任务，随后主 Agent 可继续运行。

**验证：** `uv run pytest -q tests/test_skill_executor.py tests/test_agent.py -k fork` 通过。

## T22：完成 CLI、TUI 和会话生命周期接线

**文件：** `src/dragon_code/cli.py`、`src/dragon_code/tui.py`、`src/dragon_code/command_screens.py`、`src/dragon_code/dragon_code.tcss`、`tests/test_tui.py`

**依赖：** T15–T18、T21

**步骤：**

1. 启动时创建 SkillLoader/Manager，打印安全的加载 warning。
2. 把基础工具、MCP 工具、Skill 工具和 LoadSkill 组合后传给 Agent。
3. 把动态 Skill 命令加入同一个 CommandRegistry 和补全菜单。
4. TUI 复用现有 `_start_turn()`、`_consume_turn()` 和权限确认展示 Skill 事件。
5. `/clear`、新建、恢复和切换会话时清除 Runtime 与临时工具限制。
6. Esc/Ctrl+C 取消 fork 或脚本后回到空闲状态；空闲 Ctrl+C 仍退出。

**验证：** `uv run pytest -q tests/test_tui.py -k "skill or clear or resume or cancel"` 通过。

## T23：完成跨协议、缓存和历史集成回归

**文件：** `tests/test_agent.py`、`tests/test_prompt.py`、`tests/test_skill_executor.py`、`tests/test_tui.py`

**依赖：** T22

**步骤：**

1. 验证 Anthropic 与 OpenAI 请求都只在稳定区包含 Skill 摘要。
2. 验证动态 SOP 不进入 Conversation、JSONL 或缓存稳定前缀。
3. 验证 inline/fork 工具调用与结果始终配对合法。
4. 验证 Plan Mode、上下文压缩、MCP、记忆和会话恢复无回归。
5. 验证加载与错误输出不包含 api_key、Authorization 或环境变量全集。

**验证：** `uv run pytest -q tests/test_agent.py tests/test_prompt.py tests/test_skill_executor.py tests/test_tui.py` 通过。

## T24：运行格式、编译和全量自动化测试

**文件：** 本章全部代码和测试

**依赖：** T1–T23

**步骤：**

1. 同步锁定依赖，不新增不必要运行时包。
2. 统一格式并修复 lint。
3. 运行 Python 编译检查。
4. 运行全量 pytest 并修复 ch02–ch10 回归。
5. 检查 Git 状态和敏感信息，保留 `.idea/`、`321.txt` 等用户无关文件。

**验证：**

```bash
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run python -m compileall -q src tests
uv run pytest -q
```

## T25：执行 tmux 真实端到端验收

**文件：** `specs/ch11-skill-system/checklist.md`、`specs/ch11-skill-system/acceptance-report.md`

**依赖：** T24、已批准的 checklist.md

**步骤：**

1. 在 WSL tmux 中从临时项目目录启动 Dragon Code。
2. 创建临时项目 Skill，使用自然语言让模型调用 LoadSkill 并读取真实文件。
3. 执行 `/commit 参数`、`/review` fork 和 `/test`，观察白名单、事件与最终回流。
4. 运行一个目录型 Python 自定义工具，验证 JSON 管道、权限确认和结果回灌。
5. 分别触发热更新失败、项目外路径、危险命令和取消，确认程序可继续对话。
6. 对照 checklist 逐项记录实际证据，不能由 tmux 验证的项目标注自动化测试证据。

**验证：** acceptance report 中每项都有命令、测试输出或实际观察结果。

## T26：更新交接、学习笔记并本地提交

**文件：** `docs/PROJECT_HANDOFF.md`、`docs/learning-notes.md`、本章四份设计文档与验收报告

**依赖：** T25

**步骤：**

1. 更新 ch11 功能状态、核心入口、测试数量和 tmux 证据。
2. 记录渐进式披露、SkillRuntime、白名单、inline/fork、子进程协议和安全边界。
3. 安排一次只覆盖核心调用链的源码回顾，不逐文件讲全部实现。
4. 只暂存 ch11 范围文件并创建本地 Git commit。
5. 未收到“推送”指令前不执行 git push。

**验证：** `git show --stat --oneline HEAD` 显示 ch11 提交，`git status --short` 只剩用户原有无关文件或为空。

## 执行顺序

```text
T1 → T2 → T3 → T4 → T5 → T6
                    └────→ T7

T5 → T8 → T9
T3/T8 → T10 → T11 → T12
                    └────→ T13

T5/T7 → T14
T7–T14 → T15
T5 → T16 → T17 → T18

T6/T7 → T19 → T20
T12/T15/T19/T20 → T21

T15/T18/T21 → T22 → T23 → T24 → T25 → T26
```

为便于学习和定位问题，实际开发按编号顺序推进；只有已有独立测试覆盖时才合并执行相邻任务。

## 教材 Python 提示词对照

### 保持一致

- 使用 `SKILL.md` 的 YAML frontmatter + Markdown SOP。
- 采用项目、用户、内置三级加载和同名覆盖。
- 采用摘要先加载、完整 SOP 后加载的渐进式披露。
- 支持 LoadSkill、Slash Command、inline、fork、allowedTools 和 `$ARGUMENTS`。
- 提供 commit、review、test 三个内置样板。

### Dragon Code 差异对应任务

- **T3/T12**：增加命令和路径参数安全声明，接入现有黑名单与路径沙箱。
- **T10/T11**：自定义工具使用独立 Python 子进程，不直接导入主进程。
- **T13**：所有自定义工具固定串行，不引入自定义并发标记。
- **T16/T18**：使用零参数 `/skill` 交互管理，而不是手写 list/info/reload 子命令。
- **T17**：review Skill 接管硬编码 `/review`，保留 `/r`。
- **T20**：只有 fork 可以覆盖当前 Provider 的模型名，inline 不切换模型。
- **T21**：fork 继续经过五层权限，过程实时展示，主历史只保留摘要。
- **T25**：增加项目要求的真实 tmux 端到端验收。

## Task 自检

1. Plan 中 Parser、Loader、Manager、Runtime、Tools、Executor、Prompt、Agent、Command、Permission、TUI 和内置 Skill 均有对应任务。
2. F1–F18 和 N1–N15 均能落到至少一个实现或验证任务。
3. 每个任务都列出具体文件、依赖、步骤和可运行验证。
4. 执行依赖无循环；基础解析和状态先完成，Agent/TUI/fork 后接入。
5. 自定义工具安全声明、OS 沙箱边界和保守默认值保持与已批准 Plan 一致。
6. 没有加入 Skill 市场、远程安装、文件监听器、数据库或完整 SubAgent 管理。
7. 最后明确包含全量测试、tmux 验收、交接、学习笔记和本地提交。
