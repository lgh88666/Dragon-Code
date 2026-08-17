# Dragon Code ch13 SubAgent 子任务分发 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|------|------|------|
| 新建 | `src/dragon_code/subagents/__init__.py` | 导出 ch13 稳定接口 |
| 新建 | `src/dragon_code/subagents/models.py` | Agent 定义、来源、任务状态、事件和启动结果 |
| 新建 | `src/dragon_code/subagents/parser.py` | Markdown + YAML frontmatter 解析 |
| 新建 | `src/dragon_code/subagents/catalog.py` | 项目/用户/内置定义加载和覆盖 |
| 新建 | `src/dragon_code/subagents/filtering.py` | 子 Agent 多层工具过滤 |
| 新建 | `src/dragon_code/subagents/fork.py` | Fork 历史深拷贝、占位结果和标记检测 |
| 新建 | `src/dragon_code/subagents/manager.py` | 三并发 FIFO 任务状态机、通知和取消 |
| 新建 | `src/dragon_code/subagents/host.py` | 隔离子 Agent 构造并复用 `Agent.run()` |
| 新建 | `src/dragon_code/subagents/tools.py` | `Agent` 和四个任务工具 |
| 新建 | `src/dragon_code/subagents/builtin/explore.md` | 只读代码探索角色 |
| 新建 | `src/dragon_code/subagents/builtin/plan.md` | 只读规划角色 |
| 新建 | `src/dragon_code/subagents/builtin/verify.md` | 测试验证角色 |
| 修改 | `src/dragon_code/agent.py` | 来源保护、非交互权限、Fork 快照和任务提醒 |
| 修改 | `src/dragon_code/prompt.py` | 稳定委派约定和任务提醒组合 |
| 修改 | `src/dragon_code/tools/base.py` | 增加主 Agent 专用工具元信息 |
| 修改 | `src/dragon_code/tools/registry.py` | 增加保序过滤 helper |
| 修改 | `src/dragon_code/permissions/engine.py` | 系统工具判断和隔离临时权限实例 |
| 修改 | `src/dragon_code/hooks/engine.py` | 从共享快照创建隔离 HookEngine |
| 修改 | `src/dragon_code/skills/executor.py` | fork Skill 委托统一 Host |
| 修改 | `src/dragon_code/cli.py` | 加载 AgentCatalog，处理启动错误和清理 |
| 修改 | `src/dragon_code/tui.py` | Host/Manager 接线、事件显示、Ctrl+B、状态和清理 |
| 修改 | `src/dragon_code/dragon_code.tcss` | 后台任务状态栏样式 |
| 新建 | `tests/test_subagent_parser.py` | parser 和字段校验测试 |
| 新建 | `tests/test_subagent_catalog.py` | 多来源覆盖和内置失败测试 |
| 新建 | `tests/test_subagent_filtering.py` | 工具过滤和顺序测试 |
| 新建 | `tests/test_subagent_fork.py` | Fork 历史合法性测试 |
| 新建 | `tests/test_subagent_manager.py` | 状态机、并发、排队、移交和通知测试 |
| 新建 | `tests/test_subagent_host.py` | 隔离、模型、权限和 Agent Loop 复用测试 |
| 新建 | `tests/test_subagent_tools.py` | 五个系统工具测试 |
| 修改 | `tests/test_agent.py` | QuerySource、非交互 Ask、动态提醒测试 |
| 修改 | `tests/test_permission_engine.py` | 系统工具与临时账本隔离测试 |
| 修改 | `tests/test_hook_engine.py` | 子 HookEngine 可变状态隔离测试 |
| 修改 | `tests/test_skill_executor.py` | fork Skill 统一后台测试 |
| 修改 | `tests/test_tui.py` | 子任务显示、Ctrl+B、状态和清理测试 |
| 修改 | `tests/test_cli.py` | Agent 定义启动加载和错误测试 |
| 修改 | `tests/test_client_anthropic.py` | Anthropic Fork 请求结构与缓存前缀测试 |
| 修改 | `tests/test_client_openai.py` | OpenAI Fork 请求结构一致性测试 |
| 修改 | `docs/PROJECT_HANDOFF.md` | ch13 状态、证据和下一步 |
| 修改 | `docs/learning-notes.md` | ch13 核心调用链和复习重点 |

## T1：定义 SubAgent 基础数据模型

**文件：** `src/dragon_code/subagents/models.py`、`src/dragon_code/subagents/__init__.py`

**依赖：** 无

**步骤：**

1. 定义 `AgentDefinitionSource`、`SubAgentKind`、`QuerySource` 和 `TaskStatus`。
2. 定义 `AgentDefinition`、`AgentDefinitionIssue`、`SubAgentLaunchRequest` 和
   `SubAgentResult`。
3. 定义不可变的 `TaskSnapshot`、`SubAgentEvent` 和 `SubAgentLaunchOutcome`。
4. 只从 `__init__.py` 导出其他模块真正需要的公共类型。

**验证：** 运行 `uv run python -c "from dragon_code.subagents import QuerySource, TaskStatus; print(QuerySource.MAIN, TaskStatus.QUEUED)"`，期望正常打印枚举值。

## T2：实现 Agent 定义解析器

**文件：** `src/dragon_code/subagents/parser.py`

**依赖：** T1

**步骤：**

1. 实现 UTF-8、最大文件体量和 YAML frontmatter 分隔校验。
2. 校验 `name`、`description`、Markdown 正文和名称格式。
3. 解析 `tools`、`disallowedTools`、`model`、`maxTurns`、`permissionMode`、
   `background`，拒绝错误类型、重复工具和非法权限模式。
4. 填充简单默认值：模型 `deepseek-v4-flash`、最大轮次沿用全局时使用约定值、默认权限模式。
5. 所有用户可见错误只包含安全路径和可读原因，不带 YAML 堆栈。

**验证：** 运行 `uv run python -m py_compile src/dragon_code/subagents/parser.py`，期望无输出且退出码为 0。

## T3：验证 Agent 定义解析

**文件：** `tests/test_subagent_parser.py`

**依赖：** T2

**步骤：**

1. 覆盖完整合法定义和全部默认值。
2. 覆盖缺名称、缺说明、空正文、坏 YAML、非法名称和超大文件。
3. 覆盖工具列表重复、非法权限模式、错误布尔值和错误轮次类型。
4. 断言解析结果使用 Dragon Code 的真实 `PermissionMode`。

**验证：** 运行 `uv run pytest -q tests/test_subagent_parser.py`，期望全部通过。

## T4：提供三个内置角色

**文件：** `src/dragon_code/subagents/builtin/explore.md`、`src/dragon_code/subagents/builtin/plan.md`、`src/dragon_code/subagents/builtin/verify.md`

**依赖：** T2

**步骤：**

1. `explore` 仅允许 `Read/Glob/Grep`，说明只分析不修改。
2. `plan` 仅允许 `Read/Glob/Grep`，要求输出步骤、风险和验证方案。
3. `verify` 允许 `Read/Glob/Grep/Bash`，允许运行验证但禁止编辑源码。
4. 三者默认模型写为 `deepseek-v4-flash`，正文简洁且不包含动态环境数据。

**验证：** 用 T2 的 parser 逐个读取三个文件，期望名称、说明、工具和正文均有效。

## T5：实现 AgentCatalog 多来源加载

**文件：** `src/dragon_code/subagents/catalog.py`、`src/dragon_code/subagents/__init__.py`

**依赖：** T2、T4

**步骤：**

1. 按 plugin、builtin、user、project 的低到高优先级扫描候选 Markdown。
2. 候选文件和最终定义使用稳定排序，同名由更高优先级覆盖。
3. 用户/项目坏文件记录 `AgentDefinitionIssue` 后继续；内置坏文件抛启动错误。
4. 实现 `get()`、`list_definitions()`、`issues()` 和稳定 `summary_text()`。
5. 接受默认空的 `plugin_roots`，本章不主动寻找不存在的插件目录。

**验证：** 运行一个临时目录脚本加载 Catalog，期望至少发现 `explore/plan/verify` 且顺序稳定。

## T6：验证 Catalog、覆盖和打包资源

**文件：** `tests/test_subagent_catalog.py`

**依赖：** T5

**步骤：**

1. 验证 project > user > builtin 覆盖和最终按名称排序。
2. 验证项目/用户坏文件跳过并产生 issue。
3. 验证内置坏文件阻止加载。
4. 验证默认空插件来源不产生虚假 issue。
5. 构建 wheel 并确认三个 Markdown 被包含。

**验证：** 运行 `uv run pytest -q tests/test_subagent_catalog.py`，并运行 `uv build` 后检查 wheel 中含 `subagents/builtin/*.md`。

## T7：扩展工具元信息与保序过滤

**文件：** `src/dragon_code/tools/base.py`、`src/dragon_code/tools/registry.py`、`tests/test_tool_base.py`、`tests/test_tool_registry.py`

**依赖：** T1

**步骤：**

1. 给 `Tool` 增加默认 `main_agent_only=False` 元信息，不改变现有工具定义 JSON。
2. 给 `ToolRegistry` 增加按谓词保留工具的 helper，始终维持注册顺序。
3. 保证 `subset/restricted/combined` 的既有行为不改变。
4. 增加默认值、过滤顺序和共享工具实例测试。

**验证：** 运行 `uv run pytest -q tests/test_tool_base.py tests/test_tool_registry.py`，期望全部通过。

## T8：隔离 PermissionEngine 临时账本

**文件：** `src/dragon_code/permissions/engine.py`、`tests/test_permission_engine.py`

**依赖：** T7

**步骤：**

1. 增加 `new_session()`，共享 RuleStore、黑名单和 PathSandbox，创建空的 session allow 集合。
2. 在持久规则判断之后允许合法的主 Agent 系统工具进入执行；已有 deny 规则仍优先。
3. 验证父会话 `allow_for_session()` 不泄漏到新实例。
4. 验证黑名单、沙箱、项目/用户规则和现有四种权限模式无回归。

**验证：** 运行 `uv run pytest -q tests/test_permission_engine.py tests/test_permission_blacklist.py tests/test_permission_sandbox.py`，期望全部通过。

## T9：隔离子 Agent Hook 运行状态

**文件：** `src/dragon_code/hooks/engine.py`、`tests/test_hook_engine.py`

**依赖：** 无

**步骤：**

1. 增加从同一 `HookSnapshot` 创建新会话 HookEngine 的方法。
2. 新实例拥有独立 session id、only-once 集合、提醒、后台任务和结果队列。
3. 验证共享定义快照不会让两个实例的可变状态串线。
4. 验证 `close()` 仍能回收各自后台 Hook task。

**验证：** 运行 `uv run pytest -q tests/test_hook_engine.py`，期望全部通过。

## T10：实现子 Agent 工具过滤

**文件：** `src/dragon_code/subagents/filtering.py`

**依赖：** T1、T7

**步骤：**

1. 定义主 Agent 专用工具集合与后台六工具白名单。
2. 定义式移除 `Agent/Task*/SendMessage/LoadSkill`。
3. 后台额外保留已注册的 `mcp__*` 和 `skill__*` 工具。
4. 依次应用角色黑名单、角色白名单，并保持原注册顺序。
5. Fork 提供保留完整父 registry 的路径，执行安全交给来源保护。

**验证：** 运行 `uv run python -m py_compile src/dragon_code/subagents/filtering.py`，期望通过。

## T11：验证多层工具过滤

**文件：** `tests/test_subagent_filtering.py`

**依赖：** T10

**步骤：**

1. 验证定义式永远看不到五个主 Agent 工具和 `LoadSkill`。
2. 验证后台核心、MCP、Skill 工具保留，其他系统元工具移除。
3. 验证 disallowed 优先于 allowed，空 allowed 不额外收窄。
4. 验证 Fork definitions 顺序与父 registry 完全相同。

**验证：** 运行 `uv run pytest -q tests/test_subagent_filtering.py`，期望全部通过。

## T12：实现 Fork 历史合法化

**文件：** `src/dragon_code/subagents/fork.py`

**依赖：** T1

**步骤：**

1. 定义 `FORK_BOILERPLATE_TAG` 和简短的非交互、禁止嵌套、禁止扩大范围说明。
2. 深拷贝父历史，不复用任何可变消息对象。
3. 复制当前 pending assistant，并给没有结果的 ToolCall 补结构化 placeholder。
4. 追加包含任务指令的 user 消息，确保末尾角色合法。
5. 实现扫描所有 user 文本的 `is_fork_context()` 兜底判断。

**验证：** 运行 `uv run python -m py_compile src/dragon_code/subagents/fork.py`，期望通过。

## T13：验证 Fork 消息序列

**文件：** `tests/test_subagent_fork.py`

**依赖：** T12

**步骤：**

1. 覆盖纯文本历史和含当前多 ToolCall 的历史。
2. 断言每个悬空 ToolCall 恰好有一个 placeholder 结果。
3. 修改 fork 副本后断言父消息保持不变。
4. 验证 Boilerplate 在尾部 user 消息中，且能被扫描函数识别。
5. 验证已有合法工具结果不会重复补齐。

**验证：** 运行 `uv run pytest -q tests/test_subagent_fork.py`，期望全部通过。

## T14：建立任务记录和合法状态机

**文件：** `src/dragon_code/subagents/manager.py`

**依赖：** T1

**步骤：**

1. 实现内部 task/session 记录、`task_<8 hex>` ID 和可选名称唯一性检查。
2. 实现 queued/running/terminal 合法转换，非法转换在内部拒绝。
3. 实现只读 `get()`、`list()` 快照，避免调用者改坏内部状态。
4. 限制保存的结果和错误摘要体量，记录用量、工具数和最近活动。

**验证：** 用小型 fake runner 创建完成和失败任务，期望状态与快照字段正确。

## T15：实现三并发 FIFO 调度

**文件：** `src/dragon_code/subagents/manager.py`

**依赖：** T14

**步骤：**

1. 使用 `deque` 和短临界区 `asyncio.Lock` 保存等待队列。
2. 同时只启动三个 runner，第四个保持 queued 且不执行模型逻辑。
3. 任一任务终止后按提交顺序启动下一项。
4. queued 任务允许直接取消，并从队列移除。

**验证：** 在 fake runner 中用 Event 控制完成顺序，确认前三个运行、第四个排队、释放后第四个启动。

## T16：实现前台等待与无损转后台

**文件：** `src/dragon_code/subagents/manager.py`

**依赖：** T15

**步骤：**

1. 为 attached 任务保存 started、detached 和 done 事件。
2. 120 秒计时只在任务进入 running 后开始。
3. 使用 shield/wait 让超时和 `move_foreground_to_background()` 只解除等待，不取消 runner。
4. 记录 explicit、timeout、manual 三种移交原因，避免重复移交。

**验证：** 使用缩短的测试阈值验证手动和超时移交后同一 runner 继续、执行次数仍为 1。

## T17：实现任务事件、通知、取消和清理

**文件：** `src/dragon_code/subagents/manager.py`

**依赖：** T16

**步骤：**

1. 实现非阻塞事件队列和 `drain_events()`。
2. 后台任务进入终态时生成截断的 `<task-notification>`，前台直接完成不重复通知。
3. 实现 `take_reminders()` 一次取走、不写磁盘。
4. 实现 `stop()`、`reset_session()` 和 `close()`，取消 Agent、runner 与排队任务。
5. 将普通异常转换为 failed 安全摘要，防止异常泄漏到主事件循环。

**验证：** fake runner 完成、失败、取消后检查事件、提醒、终态和 `asyncio.all_tasks()` 中无残留 manager task。

## T18：完整验证任务管理器

**文件：** `tests/test_subagent_manager.py`

**依赖：** T14–T17

**步骤：**

1. 覆盖状态机、ID、名称冲突和快照只读性。
2. 覆盖三并发、FIFO、排队取消和运行取消。
3. 覆盖显式后台、手动移交、超时移交和不重复执行。
4. 覆盖前台无重复通知、后台通知只消费一次和体量截断。
5. 覆盖 reset/close 后无未完成任务。

**验证：** 运行 `uv run pytest -q tests/test_subagent_manager.py`，期望全部通过。

## T19：给 Agent 增加来源与动态提醒入口

**文件：** `src/dragon_code/agent.py`、`src/dragon_code/prompt.py`

**依赖：** T1、T12、T17

**步骤：**

1. 给 Agent 增加 `query_source`、`stable_system_override` 和 reminder source 可选参数。
2. 每轮构造 reminder 时合并任务通知，取走后不写入 Conversation。
3. 保存当前轮稳定 system 文本，供 Fork 继承。
4. 在执行工具期间保存当前 assistant 消息，结束后在 finally 中清空。
5. 给稳定系统提示增加简短委派规则，不包含任务状态或动态角色文件内容。

**验证：** 运行现有 `tests/test_prompt.py` 和 Agent 请求体测试，确认主 Agent 默认行为不变且 reminder 不持久。

## T20：实现来源保护和非交互权限

**文件：** `src/dragon_code/agent.py`

**依赖：** T8、T19

**步骤：**

1. 工具执行前检查 `main_agent_only`、`QuerySource` 和 Fork 标记。
2. 拒绝嵌套时生成 `nested_agent_denied` ToolResult，不进入 PermissionEngine。
3. 增加 `interactive_permissions=False` 路径，把 Ask 转成结构化拒绝。
4. 主 Agent 默认仍发送 PermissionRequest，现有审批流程不改变。
5. 确保 cancel、未知工具、Hook 和历史提交路径仍合法。

**验证：** 运行 `uv run pytest -q tests/test_agent.py tests/test_permission_approval.py`，期望现有测试不回归。

## T21：补齐 Agent 的 ch13 单元测试

**文件：** `tests/test_agent.py`

**依赖：** T20

**步骤：**

1. 验证 defined/fork 来源拒绝主 Agent 专用工具。
2. 验证 source 丢失但含 Fork tag 时仍拒绝。
3. 验证非交互 Ask 不产生 PermissionRequest，并把拒绝结果回灌后继续循环。
4. 验证父稳定 system 可被 Fork 捕获、任务提醒只进入请求、不进入历史。
5. 验证 Plan Mode 下委派不能升级成写权限。

**验证：** 运行 `uv run pytest -q tests/test_agent.py`，期望全部通过。

## T22：实现定义式 SubAgentHost 创建

**文件：** `src/dragon_code/subagents/host.py`

**依赖：** T5、T9–T11、T18、T21

**步骤：**

1. 解析角色、完整模型覆盖和命名任务冲突，返回结构化启动失败。
2. 创建空 Conversation、独立 ContextManager、PermissionEngine、SkillRuntime 和 HookEngine。
3. 用角色正文扩展稳定系统指令，按角色最大轮次和权限模式构造子 Agent。
4. 默认前台，角色或调用显式 background 时直接后台。
5. 主 Agent 为 Plan Mode 时强制只读工具和 Plan 权限，禁止角色升级。

**验证：** fake LLMClient 下启动 `explore`，确认历史从首条任务开始、模型和工具集合符合定义。

## T23：实现 Fork 与模型选择

**文件：** `src/dragon_code/subagents/host.py`

**依赖：** T12、T22

**步骤：**

1. 从父 Agent 获取 committed history、pending assistant、稳定 system 和原 registry。
2. 使用 `build_fork_messages()` 创建独立 Conversation。
3. 强制继承父模型，忽略 Fork 模型覆盖，使用完整父工具顺序。
4. 设置 `QuerySource.FORK_SUBAGENT`、非交互权限和强制后台。
5. 模型 client 创建失败时只让当前 task failed。

**验证：** fake 父 Agent 下比较模型名、stable system、工具定义顺序和消息深拷贝，期望完全符合 plan。

## T24：消费现有 Agent.run 并管理子 Session

**文件：** `src/dragon_code/subagents/host.py`

**依赖：** T23

**步骤：**

1. runner 只消费现有 `child_agent.run(prompt)`，不实现第二个 ReAct 循环。
2. 把文本、工具、轮次、用量和终态转换成带任务身份的 `SubAgentEvent`。
3. completed 转成功结果；error/limit 转 failed；cancelled 转 cancelled。
4. 保存命名 `SubAgentSession`，实现 `continue_named()` 复用 Conversation 并创建新 task ID。
5. 每次执行后关闭独立 HookEngine，程序退出时统一清理所有 session。

**验证：** fake AgentEvent 序列分别完成、失败和取消，确认结果、用量、工具计数和 session 复用正确。

## T25：验证 Host 的隔离和复用

**文件：** `tests/test_subagent_host.py`

**依赖：** T22–T24

**步骤：**

1. 验证两个定义式任务的 Conversation、ContextManager、SkillRuntime、HookEngine 和权限临时账本不同。
2. 验证底层工具对象、持久 RuleStore 和 HookSnapshot 可共享。
3. 验证默认 `deepseek-v4-flash`、完整模型覆盖和 Fork 父模型继承。
4. 验证 Host 只调用 `Agent.run()`，自然完成、超限、错误和取消映射正确。
5. 验证 SendMessage 复用 session、新建 task ID，并拒绝未知、忙碌、重名或取消状态。

**验证：** 运行 `uv run pytest -q tests/test_subagent_host.py`，期望全部通过。

## T26：实现统一 `Agent` 工具

**文件：** `src/dragon_code/subagents/tools.py`

**依赖：** T5、T24

**步骤：**

1. 定义 `AgentArguments`，校验任务、说明、角色、模型、后台和名称。
2. 工具描述包含启动时 Catalog 的稳定角色摘要。
3. role 非空走定义式，role 为空走 Fork；Fork 强制后台。
4. 前台完成返回最终文本；显式/超时/手动后台返回结构化 task ID 和状态。
5. 取消 attached 等待时停止对应子任务，再让主 Agent 按既有取消路径收尾。

**验证：** 用 fake Host 分别验证 defined、fork、后台和错误参数返回。

## T27：实现四个任务工具

**文件：** `src/dragon_code/subagents/tools.py`

**依赖：** T18、T24

**步骤：**

1. `TaskList` 返回稳定排序的摘要、运行数和排队数。
2. `TaskGet` 返回状态、用量、工具数和受控长度结果。
3. `TaskStop` 停止 queued/running，终态调用返回清晰错误。
4. `SendMessage` 按唯一名称调用 Host continuation。
5. 五个工具设置正确的 system、main-only、只读/副作用和并发元信息。

**验证：** 运行参数校验脚本，确认五个 `ToolDefinition` 名称和顺序稳定。

## T28：验证五个系统工具

**文件：** `tests/test_subagent_tools.py`

**依赖：** T26–T27

**步骤：**

1. 覆盖 Agent 前台结果、三种后台回执、Fork 和未知角色。
2. 覆盖 TaskList/Get/Stop/SendMessage 正常路径。
3. 覆盖未知 ID、重复名称、忙碌 session、终态停止和超长结果截断。
4. 连续生成 definitions，断言字节序和内容不随任务状态变化。

**验证：** 运行 `uv run pytest -q tests/test_subagent_tools.py`，期望全部通过。

## T29：接入 CLI 启动加载

**文件：** `src/dragon_code/cli.py`、`tests/test_cli.py`

**依赖：** T5

**步骤：**

1. 在 MCP/Skill 启动准备阶段加载 AgentCatalog。
2. 将项目/用户 issue 以安全 warning 输出。
3. 内置定义错误转换成可读启动错误，无 Python 堆栈。
4. 把 Catalog 传给 DragonCodeApp，不创建虚假 plugin root。

**验证：** 运行 `uv run pytest -q tests/test_cli.py`，期望合法、warning 和致命错误场景全部通过。

## T30：在 TUI 构造稳定工具和 SubAgentHost

**文件：** `src/dragon_code/tui.py`

**依赖：** T25、T28、T29

**步骤：**

1. provider 激活时创建一个会话级 BackgroundTaskManager。
2. 先按固定顺序注册 Agent、TaskList、TaskGet、TaskStop、SendMessage，再创建主 Agent。
3. 创建 SubAgentHost，绑定主 Agent 和五个工具。
4. 主 Agent 注入 manager 作为动态 reminder source。
5. SkillExecutor 注入同一个 Host。

**验证：** TUI 测试启动后抓取主请求工具定义，确认五个工具存在、顺序固定且重复激活不会重复注册。

## T31：实现 TUI 子任务事件和 Ctrl+B

**文件：** `src/dragon_code/tui.py`、`src/dragon_code/dragon_code.tcss`

**依赖：** T30

**步骤：**

1. 增加 `Ctrl+B` binding，只移交当前 attached 子 Agent。
2. 定时 drain 子任务事件；attached 显示带 Agent 名称的明细，后台只显示状态摘要。
3. 在 scrollback 展示 queued/running/manual/timeout/completed/failed/cancelled。
4. 状态栏增加 running/queued 数量，计数为零时保持简洁。
5. 文件写入型后台任务启动时明确提示共享工作区可能冲突。

**验证：** Textual pilot 测试中注入事件并按 Ctrl+B，确认 manager 收到移交、界面文字和状态栏更新。

## T32：实现会话切换和退出清理

**文件：** `src/dragon_code/tui.py`

**依赖：** T31

**步骤：**

1. `/clear`、新建、恢复会话前调用 manager `reset_session()`。
2. Esc/主取消只停止当前 attached 子任务；已脱离后台任务由 TaskStop 或退出管理。
3. 安全退出时 await manager.close()，再关闭 Hook、session 和 MCP。
4. 清理子任务轮询 timer/Worker，保证重复退出幂等。

**验证：** Textual pilot 中分别切会话和退出，确认 queued/running 均取消且无残留 task。

## T33：验证 TUI 集成

**文件：** `tests/test_tui.py`

**依赖：** T30–T32

**步骤：**

1. 验证前台子 Agent 文本、工具行、结果和 Agent 名称。
2. 验证后台只显示状态摘要，不泄露完整内部历史。
3. 验证 Ctrl+B、120 秒移交事件、running/queued 状态栏。
4. 验证完成通知显示但不自动调用主模型。
5. 验证 clear/resume/quit 清理路径。

**验证：** 运行 `uv run pytest -q tests/test_tui.py`，期望全部通过。

## T34：迁移 fork Skill 到统一 Host

**文件：** `src/dragon_code/skills/executor.py`、`tests/test_skill_executor.py`

**依赖：** T24、T30

**步骤：**

1. 保留 inline Skill 当前激活和提醒逻辑。
2. 删除 fork 分支内手工创建 Conversation/Client/ContextManager/Agent 的代码。
3. 把 Skill context、model、allowed tools、SOP 和 arguments 转成 Skill fork 请求。
4. Skill fork 强制后台，立即返回任务 ID，不自动提交摘要到主 Conversation。
5. 验证 full/recent/none、工具范围、模型和通知仍生效。

**验证：** 运行 `uv run pytest -q tests/test_skill_executor.py tests/test_skill_runtime.py`，期望全部通过。

## T35：验证跨协议请求与缓存前缀

**文件：** `tests/test_client_anthropic.py`、`tests/test_client_openai.py`

**依赖：** T23、T30

**步骤：**

1. Anthropic 请求验证 Fork 的 stable system、工具顺序和父历史前缀。
2. OpenAI 请求验证相同上层消息和工具语义。
3. 两协议验证 placeholder ToolResult 的 call ID 配对。
4. 缓存字段存在时解析读取量，缺失时仍为零且不失败。

**验证：** 运行 `uv run pytest -q tests/test_client_anthropic.py tests/test_client_openai.py`，期望全部通过。

## T36：运行 ch13 定向集成测试

**文件：** 上述全部 ch13 实现与测试文件

**依赖：** T1–T35

**步骤：**

1. 运行所有 `test_subagent_*`。
2. 运行 Agent、权限、Hook、Skill、TUI、CLI 和两个 Client 的受影响测试。
3. 修复失败并重复执行，不能把失败留到全量验收。

**验证：** 运行
`uv run pytest -q tests/test_subagent_parser.py tests/test_subagent_catalog.py tests/test_subagent_filtering.py tests/test_subagent_fork.py tests/test_subagent_manager.py tests/test_subagent_host.py tests/test_subagent_tools.py tests/test_agent.py tests/test_permission_engine.py tests/test_hook_engine.py tests/test_skill_executor.py tests/test_tui.py tests/test_cli.py tests/test_client_anthropic.py tests/test_client_openai.py`，期望全部通过。

## T37：运行格式、静态检查和全量回归

**文件：** 全项目

**依赖：** T36

**步骤：**

1. 同步锁定依赖。
2. 格式化新增和修改代码。
3. 运行 Ruff 格式检查与 lint。
4. 运行完整 pytest，确认 ch02–ch12 无回归。

**验证：** 依次运行：

```bash
uv sync --locked
uv run ruff format .
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
```

期望全部命令退出码为 0。

## T38：执行 tmux 端到端验收

**文件：** `specs/ch13-subagent/checklist.md`

**依赖：** T37、checklist.md 已批准

**步骤：**

1. 在 tmux 中从真实项目目录启动 Dragon Code。
2. 运行定义式 `explore` 前台任务并观察工具、文本和最终结果。
3. 运行 Fork 后台任务，使用 TaskList/TaskGet 查询，再用 SendMessage 续派。
4. 启动长任务，验证 Ctrl+B、排队和 TaskStop。
5. 执行 fork Skill，验证统一 task ID、完成通知和退出清理。
6. 对照 checklist 逐项记录真实证据，失败则修复后重跑。

**验证：** checklist 的自动化项和真实 TUI 项全部取得实际证据；不能把单元测试结果描述成 tmux 实测。

## T39：更新交接、学习笔记并提交

**文件：** `docs/PROJECT_HANDOFF.md`、`docs/learning-notes.md`

**依赖：** T38

**步骤：**

1. 在交接文档记录 ch13 已完成功能、测试命令、tmux 证据、已知限制和下一章入口。
2. 在学习笔记记录 Agent 工具、定义式/Fork、QuerySource、placeholder、任务状态机、
   attached 转后台和隔离边界。
3. 只暂存 ch13 范围文件，保护 `.idea/`、`321.txt`、本地 Skill 和其他用户文件。
4. 创建一次本地 Git 提交；只有用户明确要求时才 push。

**验证：** `git status --short` 只显示预期未提交的用户文件；`git show --stat --oneline HEAD` 显示完整 ch13 提交。

## 执行顺序

```text
T1 → T2 → T3
      ├→ T4 → T5 → T6
      └──────────────┐

T7 → T8             │
 └→ T10 → T11       │
T9                  │
T12 → T13           │
T14 → T15 → T16 → T17 → T18
                           │
T19 → T20 → T21            │
        └──────────────────┼→ T22 → T23 → T24 → T25
                           │                      │
                           └──────────────────────┼→ T26 → T27 → T28
                                                  │
T5 ─────────────────────────────────────────────→ T29
                                                  │
T25 + T28 + T29 ────────────────────────────────→ T30 → T31 → T32 → T33
                                                   └────────────→ T34
T23 + T30 ─────────────────────────────────────────────────────→ T35
T1–T35 → T36 → T37 → T38 → T39
```

可并行关系：

- T7–T11、T12–T13、T14–T18 可以在数据模型稳定后并行推进。
- T29 可与 Host/Manager 的后半段并行，但 T30 必须等待 T25、T28、T29。
- T33、T34、T35 可在各自依赖满足后并行，最后统一进入 T36。

## 自检结果

- **Plan 覆盖**：plan.md 中的 Catalog、Host、Manager、Fork、过滤、权限、工具、TUI、Skill、
  协议和清理均至少有一个实现任务和一个验证任务。
- **Spec 覆盖**：F1–F25 分别落在 T1–T35；AC 的综合行为在 T36–T38 验证。
- **依赖链**：不存在循环依赖，主链可以从 T1 执行到 T39。
- **验证完整性**：每个任务均有具体命令或可观察结果。
- **粒度检查**：任务按单个类型、函数组或测试场景拆分；较大的 Manager、Host、TUI 分成多步。
- **类型一致性**：类型名、接口名和文件组织与已批准 plan.md 一致。
- **范围检查**：没有加入 Worktree、团队系统、任务持久化、真实插件或通用 Runtime。
- **占位符扫描**：没有 TBD、TODO 或“类似某任务”的模糊步骤。
