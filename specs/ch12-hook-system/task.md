# Hook 生命周期自动化系统 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|---|---|---|
| 新建 | `src/dragon_code/matching.py` | 四类统一匹配器 |
| 新建 | `src/dragon_code/hooks/__init__.py` | Hook 包公开入口 |
| 新建 | `src/dragon_code/hooks/models.py` | 事件、配置、上下文和结果类型 |
| 新建 | `src/dragon_code/hooks/conditions.py` | 条件解析与判断 |
| 新建 | `src/dragon_code/hooks/template.py` | Prompt/HTTP 模板替换与 Shell 上下文序列化 |
| 新建 | `src/dragon_code/hooks/config.py` | 两层 YAML 加载、校验和合并 |
| 新建 | `src/dragon_code/hooks/actions.py` | Shell、Prompt、HTTP、Subagent 动作 |
| 新建 | `src/dragon_code/hooks/engine.py` | Hook 匹配、执行、拦截和任务管理 |
| 新建 | `.dragon-code/hooks.yaml.example` | 无秘密值的 Hook 配置示例 |
| 新建 | `tests/test_matching.py` | 匹配器测试 |
| 新建 | `tests/test_hook_conditions.py` | 条件测试 |
| 新建 | `tests/test_hook_config.py` | 配置加载测试 |
| 新建 | `tests/test_hook_actions.py` | 动作执行测试 |
| 新建 | `tests/test_hook_engine.py` | 编排与生命周期测试 |
| 新建 | `tests/test_hook_integration.py` | 11 个事件和历史一致性测试 |
| 修改 | `src/dragon_code/permissions/rules.py` | 权限 glob 改用统一匹配器 |
| 修改 | `src/dragon_code/models.py` | AgentEvent 增加 Hook 字段 |
| 修改 | `src/dragon_code/prompt.py` | hook-notification 与提醒合并 |
| 修改 | `src/dragon_code/agent.py` | 接入轮次、工具、压缩和通知 Hook |
| 修改 | `src/dragon_code/command/builtin_local.py` | `/hooks` Handler 与安全格式化 |
| 修改 | `src/dragon_code/command/builtins.py` | 注册 `/hooks` |
| 修改 | `src/dragon_code/command/ui.py` | CommandUI 增加 Hook 查询接口 |
| 修改 | `src/dragon_code/tui.py` | 会话 Hook、展示、输入恢复和异步结果 |
| 修改 | `src/dragon_code/cli.py` | 启动加载和退出清理 HookEngine |
| 修改 | `pyproject.toml`、`uv.lock` | 声明直接依赖 httpx |
| 修改 | `tests/test_permission_rules.py` | 权限兼容回归 |
| 修改 | `tests/test_agent.py` | Agent Hook 接入测试 |
| 修改 | `tests/test_command.py` | `/hooks` 测试 |
| 修改 | `tests/test_tui.py` | TUI Hook 行为测试 |
| 修改 | `tests/test_cli.py` | 启动加载和关闭测试 |
| 验收时新建 | `specs/ch12-hook-system/acceptance-report.md` | 实际验收证据 |
| 验收时修改 | `docs/PROJECT_HANDOFF.md` | 项目状态和证据 |
| 验收时修改 | `docs/learning-notes.md` | ch12 核心源码回顾入口 |

## T1：定义统一匹配器

**文件：** `src/dragon_code/matching.py`、`tests/test_matching.py`  
**依赖：** 无

**步骤：**

1. 定义 `MatcherKind` 和不可变 `Matcher`。
2. 实现 exact、not、regex、glob 四种匹配。
3. 复用当前权限 glob 对 `*`、`**`、`?` 和反斜杠转义的语义。
4. Windows 路径模式忽略大小写，普通文本保持大小写敏感。
5. 增加合法和非法正则、路径与命令匹配测试。

**验证：** `uv run pytest -q tests/test_matching.py`，期望四类匹配与非法正则测试全部通过。

## T2：迁移权限规则到统一匹配器

**文件：** `src/dragon_code/permissions/rules.py`、`tests/test_permission_rules.py`  
**依赖：** T1

**步骤：**

1. 删除权限模块内部重复的 glob 转正则逻辑。
2. 让 `rule_matches()` 使用公共 glob Matcher。
3. 保留 `PermissionRule.pattern`、现有 YAML 文本和精确授权生成方式。
4. 补充 `Bash(git *)`、路径、转义字符和 Windows 大小写回归测试。

**验证：** `uv run pytest -q tests/test_permission_rules.py tests/test_permission_engine.py`，期望旧权限行为不变。

## T3：定义 Hook 核心模型

**文件：** `src/dragon_code/hooks/models.py`、`src/dragon_code/hooks/__init__.py`  
**依赖：** T1

**步骤：**

1. 定义 11 个 `HookEvent` 枚举值和四个 `HookActionType`。
2. 定义 `Condition`、`ConditionGroup`、`HookAction`、`HookDefinition`。
3. 定义 `HookContext.get()`，支持安全读取嵌套字段。
4. 定义 `HookExecution`、`HookOutcome`、`HookIssue`、`HookSnapshot`。
5. 从 `hooks/__init__.py` 导出上层需要的类型。

**验证：** `uv run python -m compileall -q src/dragon_code/hooks`，期望编译无错误。

## T4：实现固定条件语法解析

**文件：** `src/dragon_code/hooks/conditions.py`  
**依赖：** T1、T3

**步骤：**

1. 解析 `==`、`!=`、`=~ /.../` 和 `glob` 四类表达式。
2. 把字段路径、匹配器类型和模式保存为 `Condition`。
3. 支持单字符串条件以及顶层 `all_of` 或 `any_of`。
4. 拒绝空表达式、未知语法、混用逻辑组和嵌套逻辑组。
5. 禁止使用 `eval()` 或执行配置中的 Python 表达式。

**验证：** `uv run python -m compileall -q src/dragon_code/hooks/conditions.py`，期望编译通过。

## T5：验证条件读取与组合

**文件：** `tests/test_hook_conditions.py`  
**依赖：** T4

**步骤：**

1. 测试 `tool.name`、`args.path`、`result.success` 等嵌套字段。
2. 测试单条件、`all_of` 和 `any_of` 的真与假。
3. 测试字段缺失时返回不匹配而非异常。
4. 测试非法正则、混用和嵌套条件被拒绝。

**验证：** `uv run pytest -q tests/test_hook_conditions.py`，期望全部通过。

## T6：实现安全上下文传递

**文件：** `src/dragon_code/hooks/template.py`、`tests/test_hook_actions.py`  
**依赖：** T3

**步骤：**

1. 实现 Prompt/HTTP 使用的 `{{field.path}}` 替换。
2. 字段不存在时返回明确错误，不保留未替换占位符。
3. 把 HookContext 序列化为 UTF-8 JSON，供 Shell stdin 使用。
4. 生成不包含密钥的 `DRAGON_*` 常用环境变量。
5. 测试嵌套替换、Unicode、缺失字段和 JSON 输出。

**验证：** `uv run pytest -q tests/test_hook_actions.py -k template`，期望模板与上下文测试通过。

## T7：实现单文件 Hook 配置解析

**文件：** `src/dragon_code/hooks/config.py`  
**依赖：** T3、T4

**步骤：**

1. 使用 `yaml.safe_load` 读取 `hooks` 列表。
2. 校验名称、事件、条件、动作、`only_once`、`async` 和 `timeout`。
3. 按动作类型校验必要字段和字段类型。
4. 禁止两个拦截事件配置 `async: true`。
5. 单条无效 Hook 转成 `HookIssue`，其他条目继续加载。

**验证：** `uv run python -m compileall -q src/dragon_code/hooks/config.py`，期望编译通过。

## T8：实现项目级与用户级配置合并

**文件：** `src/dragon_code/hooks/config.py`  
**依赖：** T7

**步骤：**

1. 加载项目 `.dragon-code/hooks.yaml` 和用户 `~/.dragon-code/hooks.yaml`。
2. 保留文件内原始顺序，项目级 Hook 排在用户级之前。
3. 同名时保留项目级，跳过用户级并记录问题。
4. 文件不存在时返回空层；非法 YAML 记录问题，不中断启动。
5. 输出不可变且顺序稳定的 `HookSnapshot`。

**验证：** `uv run python -m compileall -q src/dragon_code/hooks/config.py`，期望编译通过。

## T9：验证配置加载、校验与降级

**文件：** `tests/test_hook_config.py`  
**依赖：** T8

**步骤：**

1. 测试两层追加和项目级重名覆盖。
2. 测试无文件、空文件和合法完整配置。
3. 测试非法 YAML、未知事件、未知动作、缺失字段和非法正则。
4. 测试拦截事件异步配置被拒绝。
5. 断言问题信息包含来源文件与 Hook 名称，且不含敏感正文。

**验证：** `uv run pytest -q tests/test_hook_config.py`，期望全部通过。

## T10：实现 Shell 动作

**文件：** `src/dragon_code/hooks/actions.py`  
**依赖：** T3、T6

**步骤：**

1. 使用异步子进程在项目根目录执行静态命令。
2. 向 stdin 写入 HookContext JSON，并追加安全 `DRAGON_*` 环境变量。
3. 捕获 stdout、stderr、退出码并限制输出体量。
4. 用每条 Hook 的 timeout 包裹执行。
5. 超时或取消时终止子进程并等待回收。
6. 仅在同步拦截事件中把退出码 2 转成 blocked。

**验证：** `uv run pytest -q tests/test_hook_actions.py -k shell`，期望成功、失败、拒绝、超时和取消测试通过。

## T11：实现 Prompt 与 Subagent 动作

**文件：** `src/dragon_code/hooks/actions.py`、`src/dragon_code/prompt.py`  
**依赖：** T6、T10

**步骤：**

1. 实现 Prompt 模板渲染并生成 `<hook-notification>` 内容。
2. 新增 `hook_notification()` 和 `combine_reminders()`。
3. 保持现有 Plan Mode 与 Skill reminder 内容不变。
4. 实现 Subagent 的 `not_implemented` 占位结果。
5. 确认两类动作都不会写入 Conversation。

**验证：** `uv run pytest -q tests/test_hook_actions.py -k "prompt or subagent" tests/test_prompt.py`，期望全部通过。

## T12：实现 HTTP 动作并声明依赖

**文件：** `src/dragon_code/hooks/actions.py`、`pyproject.toml`、`uv.lock`  
**依赖：** T6、T10

**步骤：**

1. 把 `httpx>=0.28,<1` 加入直接依赖并更新锁文件。
2. 使用 `httpx.AsyncClient` 执行 method、headers 和 body 请求。
3. 为 URL、header value 和 body 执行安全模板替换。
4. 解析同步前置事件的 `block/reason` JSON。
5. 把连接失败、状态码错误、超时和非法结构转成 HookExecution。
6. 关闭时释放 HTTP client。

**验证：** `uv sync --locked` 和 `uv run pytest -q tests/test_hook_actions.py -k http`，期望依赖锁定与 HTTP 测试通过。

## T13：补齐四类动作测试

**文件：** `tests/test_hook_actions.py`  
**依赖：** T10、T11、T12

**步骤：**

1. 使用临时脚本验证 Shell 收到正确 stdin JSON 和环境变量。
2. 验证 stdout/stderr 截断与退出码含义。
3. 验证 Prompt 提醒内容和缺失模板字段。
4. 使用本地测试服务验证 HTTP 方法、请求头、正文、拒绝和超时。
5. 验证 Subagent 不创建任务且返回占位结果。

**验证：** `uv run pytest -q tests/test_hook_actions.py`，期望全部通过且没有残留子进程。

## T14：实现同步 HookEngine 编排

**文件：** `src/dragon_code/hooks/engine.py`  
**依赖：** T9、T13

**步骤：**

1. 按事件筛选 Hook，并使用 ConditionGroup 判断是否匹配。
2. 按快照顺序串行执行同步 Hook。
3. 收集每条 HookExecution 到 HookOutcome。
4. 首个 blocked 出现时停止当前事件剩余 Hook。
5. 单个非拦截 Hook 失败后继续后续 Hook。
6. Prompt 成功时加入提醒队列。

**验证：** `uv run python -m compileall -q src/dragon_code/hooks/engine.py`，期望编译通过。

## T15：实现 once、异步任务和关闭

**文件：** `src/dragon_code/hooks/engine.py`  
**依赖：** T14

**步骤：**

1. 实现会话级 `_executed_once`，成功开始执行后即登记。
2. `begin_session()` 重置 once 状态和当前会话标识。
3. 为异步 Hook 创建并跟踪 `asyncio.Task`。
4. 把异步完成、失败和超时结果放入可读取列表。
5. 实现一次性读取 reminders 与 background results。
6. `close()` 有限等待后取消剩余任务，并幂等关闭动作执行器。

**验证：** `uv run python -m compileall -q src/dragon_code/hooks/engine.py`，期望编译通过。

## T16：验证 HookEngine 行为

**文件：** `tests/test_hook_engine.py`  
**依赖：** T15

**步骤：**

1. 验证事件筛选、条件筛选与稳定执行顺序。
2. 验证首个拒绝停止剩余 Hook。
3. 验证非拦截失败隔离。
4. 验证 only_once 同会话一次、新建和恢复会话后重置。
5. 验证异步立即返回、结果可读取且读取后清空。
6. 验证关闭时取消长任务且无任务泄漏。

**验证：** `uv run pytest -q tests/test_hook_engine.py`，期望全部通过。

## T17：扩展 AgentEvent 与提醒合并

**文件：** `src/dragon_code/models.py`、`src/dragon_code/prompt.py`、`tests/test_prompt.py`  
**依赖：** T3、T11

**步骤：**

1. 给 `AgentEvent` 增加可选 HookExecution 和 rejected_text。
2. 保持旧构造方式与所有已有事件兼容。
3. 测试无 reminder、单 reminder 和 Plan/Skill/Hook 多提醒合并。
4. 断言 `<hook-notification>` 不被包成用户持久消息。

**验证：** `uv run pytest -q tests/test_prompt.py tests/test_stream_collector.py`，期望已有流事件与新提醒测试通过。

## T18：接入用户、轮次、完成与通知事件

**文件：** `src/dragon_code/agent.py`、`tests/test_agent.py`  
**依赖：** T15、T17

**步骤：**

1. Agent 可选接收 HookEngine，默认 `None` 保持旧测试简单。
2. 实现 `_trigger_hook()`，统一补齐 session、cwd、mode。
3. 在用户消息提交历史前触发 `UserPromptSubmit`。
4. 在每轮模型请求前触发 `PreUserMessage`，再取得并合并提醒。
5. 在自然完成后触发 `Stop`。
6. 在权限询问和 LLM 流错误前触发 `Notification`。
7. 拒绝用户输入时产出含原文本的 AgentEvent 并结束本轮。

**验证：** `uv run pytest -q tests/test_agent.py -k hook`，期望四类事件、提醒和输入拒绝测试通过。

## T19：接入工具前后 Hook

**文件：** `src/dragon_code/agent.py`、`tests/test_agent.py`  
**依赖：** T18、T2

**步骤：**

1. 在权限引擎之前触发 `PreToolUse`。
2. blocked 时跳过权限与工具执行，生成 `hook_denied` ToolResult。
3. 保留原 tool_start/tool_end 顺序和 call_id。
4. 对成功、失败、权限拒绝、Hook 拒绝、超时和取消的最终结果触发 `PostToolUse`。
5. 确认 Hook Shell/HTTP 不经 ToolRegistry，不递归触发工具 Hook。

**验证：** `uv run pytest -q tests/test_agent.py -k "hook and tool" tests/test_tool_scheduler.py`，期望结构化回灌与原调度测试通过。

## T20：接入手动与自动压缩 Hook

**文件：** `src/dragon_code/agent.py`、`tests/test_agent.py`、`tests/test_context_manager.py`  
**依赖：** T18

**步骤：**

1. 手动压缩调用前后触发 `PreCompact` 与 `PostCompact`。
2. 自动压缩真正开始前后触发相同事件。
3. PostCompact 数据包含成功、失败、前后 Token、落盘结果数和安全错误。
4. Hook 失败不阻止 ContextManager 原流程。
5. 保持连续失败熔断和历史替换语义不变。

**验证：** `uv run pytest -q tests/test_agent.py -k compact tests/test_context_manager.py`，期望压缩 Hook 与旧压缩测试通过。

## T21：验证 11 个事件与历史一致性

**文件：** `tests/test_hook_integration.py`  
**依赖：** T19、T20

**步骤：**

1. 使用记录型动作逐一触发 11 个事件。
2. 断言每个事件时机与通用、专用字段正确。
3. 验证 Prompt 提醒只进入下一次请求，不进入 JSONL。
4. 验证 Hook 拒绝后工具调用与结果配对。
5. 验证输入拒绝、流错误、上限与取消后下一轮仍合法。

**验证：** `uv run pytest -q tests/test_hook_integration.py`，期望 11 个事件与历史测试全部通过。

## T22：新增只读 `/hooks` 命令

**文件：** `src/dragon_code/command/builtin_local.py`、`src/dragon_code/command/builtins.py`、`src/dragon_code/command/ui.py`、`tests/test_command.py`  
**依赖：** T9

**步骤：**

1. 给 CommandUI 增加 `hook_items()`。
2. 实现 `/hooks` Handler 和稳定文本格式化。
3. 注册命令并纳入 `/help` 与 Tab 补全。
4. 展示名称、事件、动作、来源、once、async 和安全问题摘要。
5. 不展示 command、URL headers、body 或敏感配置正文。

**验证：** `uv run pytest -q tests/test_command.py tests/test_command_completion.py`，期望命令、帮助和补全测试通过。

## T23：接入会话开始、结束与恢复

**文件：** `src/dragon_code/tui.py`、`tests/test_tui.py`  
**依赖：** T16、T21

**步骤：**

1. TUI 接收同一个 HookEngine，并实现会话 Hook 辅助方法。
2. Provider 激活并创建新会话后调用 `begin_session()` 和 `SessionStart`。
3. `/clear` 切换前触发旧会话 `SessionEnd`，切换后触发新会话 `SessionStart`。
4. `/resume` 切换前触发旧会话 `SessionEnd`，成功恢复后触发 `SessionResume`。
5. Hook 失败显示警告但不回滚已成功准备的会话对象。
6. 避免同一会话重复触发 SessionEnd。

**验证：** `uv run pytest -q tests/test_tui.py -k "session and hook"`，期望新建、清空和恢复顺序测试通过。

## T24：实现 Hook TUI 展示与输入恢复

**文件：** `src/dragon_code/tui.py`、`tests/test_tui.py`  
**依赖：** T17、T22、T23

**步骤：**

1. 渲染成功、拒绝、失败、超时和异步开始状态。
2. 用户输入被拒绝后恢复原输入、重新启用并聚焦输入框。
3. 实现 `hook_items()`，返回当前快照而非重新读文件。
4. 用轻量定时回调读取异步 Hook 完成结果。
5. 退出或卸载时停止 Hook 刷新定时器。
6. 不让 TUI 解析条件或直接执行 Hook 动作。

**验证：** `uv run pytest -q tests/test_tui.py -k hook`，期望样式、输入恢复、异步结果和清理测试通过。

## T25：接入 CLI 启动与退出清理

**文件：** `src/dragon_code/cli.py`、`tests/test_cli.py`  
**依赖：** T23、T24

**步骤：**

1. 启动时构造 HookLoader 并只加载一次配置。
2. 把 HookIssue 以脱敏中文警告输出到 stderr。
3. 创建 HookActionExecutor 与 HookEngine 并传入 TUI。
4. 应用退出时兜底触发未执行的 SessionEnd。
5. 在会话、记忆和 MCP 最终清理前 `await hook_engine.close()`。
6. 保证配置缺失或局部无效不阻止 TUI 启动。

**验证：** `uv run pytest -q tests/test_cli.py`，期望启动、警告、一次加载和幂等关闭测试通过。

## T26：添加安全配置示例

**文件：** `.dragon-code/hooks.yaml.example`  
**依赖：** T9、T13

**步骤：**

1. 提供 PostToolUse Shell、PreToolUse 拒绝、Prompt 和异步 HTTP 示例。
2. Shell 示例使用静态脚本并说明从 stdin 读取 JSON。
3. 示例覆盖单条件与 `all_of`，但不使用未支持语法。
4. webhook 和 Authorization 使用明显占位符，不放真实秘密。

**验证：** 在配置加载测试中读取该示例，期望所有示例 Hook 均可解析且无 HookIssue。

## T27：运行 Hook 专项回归

**文件：** 全部 Hook、Permission、Agent、Command、TUI 测试  
**依赖：** T2、T13、T16、T21、T22、T24、T25、T26

**步骤：**

1. 运行所有 `test_hook_*`。
2. 运行权限、Agent、上下文、Command、会话和 TUI 相关测试。
3. 修复失败，不能通过放宽断言掩盖历史或顺序错误。
4. 检查测试结束后没有残留子进程或未关闭任务警告。

**验证：** `uv run pytest -q tests/test_hook_*.py tests/test_permission_*.py tests/test_agent.py tests/test_context_manager.py tests/test_command.py tests/test_tui.py tests/test_cli.py`，期望全部通过。

## T28：运行全量质量检查

**文件：** 全仓库  
**依赖：** T27

**步骤：**

1. 同步锁定依赖。
2. 运行 Ruff 格式检查和静态检查。
3. 编译全部源码与测试。
4. 运行完整 pytest。
5. 修复后从失败命令重新执行，直到取得通过证据。

**验证：** 依次运行：

```text
uv sync --locked
uv run ruff format --check .
uv run ruff check .
uv run python -m compileall -q src tests
uv run pytest -q
```

期望全部成功。

## T29：执行 tmux 真实端到端场景

**文件：** 临时 Hook 配置与测试文件，不提交秘密值  
**依赖：** T28

**步骤：**

1. 在 tmux 中启动 Dragon Code。
2. 配置 PostToolUse 自动动作，让 Agent 写入 Python 文件后留下可观察标记。
3. 输入真实对话请求，确认模型调用 Write/Edit、Hook 自动运行、结果展示且 Agent 最终完成。
4. 配置 PreToolUse 拒绝指定路径，再请求模型修改该路径。
5. 确认文件未变化、UI 显示拒绝、ToolResult 回灌且模型调整。
6. 输入 `/hooks`，确认列表安全且顺序稳定。
7. 退出后检查 Dragon Code、Hook 子进程和后台任务均已清理。

**验证：** 保存 tmux 输出、文件状态和进程检查结果，逐项对照 checklist.md。

## T30：记录验收、交接和学习入口

**文件：** `specs/ch12-hook-system/acceptance-report.md`、`docs/PROJECT_HANDOFF.md`、`docs/learning-notes.md`  
**依赖：** T29

**步骤：**

1. 按 checklist.md 记录每项实际命令和结果，不填写未经执行的证据。
2. 更新交接文档中的 ch12 能力、核心文件、测试和 tmux 结果。
3. 在学习笔记中增加 ch12 核心调用链、关键类型和源码回顾入口。
4. 明确未验证项和环境限制，不伪装为通过。

**验证：** 对照 checklist.md、测试输出和 tmux 记录检查三份文档中的数字与事实一致。

## T31：创建本地 Git 提交

**文件：** 本章相关文件  
**依赖：** T30

**步骤：**

1. 查看 `git status` 和 diff，确认不包含 `.idea/`、`321.txt`、API Key 或无关改动。
2. 只暂存 ch12 实现、测试、Spec 文档和交接资料。
3. 创建一次本地功能提交。
4. 不推送 GitHub，除非用户明确要求“推送”。

**验证：** `git status --short` 与 `git show --stat --oneline HEAD`，期望提交范围正确且用户无关文件仍未暂存。

## 执行顺序

```text
T1 → T2
 ↓
T3 → T4 → T5
 ↓    ↘
T6    T7 → T8 → T9
 ↓              ↓
T10 → T11 → T12 → T13
                    ↓
              T14 → T15 → T16
                    ↓
              T17 → T18 → T19 → T20 → T21
                                      ↓
                         T22 → T23 → T24 → T25
                                      ↓
                              T26 → T27 → T28
                                            ↓
                                      T29 → T30 → T31
```

T2 与 T3–T6 可在 T1 后分别推进，但单人实现时仍按编号执行，便于逐项验证。

## 自检结果

1. **Plan 覆盖**：统一匹配、配置、条件、动作、Engine、11 个接入点、命令、TUI、CLI、测试和验收均有任务。
2. **粒度检查**：实现任务按单一文件或单一行为拆分；全量检查和 tmux 验收作为独立收尾任务。
3. **依赖链**：没有循环依赖，核心类型先于加载器、动作和 Engine，Engine 先于 Agent/TUI 接入。
4. **验证完整性**：每个任务都有可运行命令或可观察结果。
5. **接口一致性**：类型与方法名与 plan.md 保持一致。
6. **安全边界**：任务明确禁止 Shell 直接插值路径，并包含秘密扫描和进程清理。
7. **范围控制**：没有加入热重载、管理 UI、持久 Hook 状态、真实 SubAgent 或通用事件总线。
