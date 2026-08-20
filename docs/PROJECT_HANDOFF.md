# Dragon Code 项目交接

> 这是会随章节进度更新的动态交接文档。长期协作规则以根目录 `AGENTS.md` 为准。

## 项目定位

- 项目：Dragon Code
- 仓库：<https://github.com/lgh88666/Dragon-Code>
- 主分支：`master`
- 语言：Python 3.12+
- 界面：Textual TUI
- 依赖管理：uv
- 目标：从零构建类似 Claude Code 的终端 AI 编程助手，用于秋招展示和源码学习。
- 教材中的 MewCode 在本项目中统一对应 Dragon Code。

## 当前状态

- 已完成：ch02–ch13。
- 最近完成模块：GitHub 项目主页 README 专业化重构。
- ch07 实现提交：`9b0d901 feat: add MCP client integration`。
- ch08 实现提交：`97d3cd7 feat: add ch08 context management`。
- ch02–ch13 与工具交互优化已推送到 GitHub `master`；主页美化完成验证后按用户授权继续推送。
- 下一开发章节开始前，继续执行理论学习与四文档审批硬门槛。

## 已有能力

### ch02：多协议 LLM 终端对话

- Anthropic 与 OpenAI/兼容端点。
- YAML Provider 配置与启动选择。
- 流式文本、计时、Markdown 定型和多轮历史。
- Textual TUI、Dragon Banner、错误恢复与安全退出。

### ch03：工具系统

- Read、Write、Edit、Bash、Glob、Grep 六个内置工具。
- 统一 Tool 接口、ToolRegistry、参数 Schema、超时和结构化错误。
- Anthropic/OpenAI 流式工具调用解析与 ToolResult 回灌。

### ch04：Agent Loop

- ReAct 多轮循环，直到模型自然完成或触发停止条件。
- AgentEvent 异步事件流，Agent 与 TUI 解耦。
- 文本实时显示和完整响应收集双路处理。
- 连续只读工具并发、有副作用工具串行。
- `/plan` 与 `/do` 两段式 Plan Mode。

### ch05：系统提示工程化

- 七个稳定系统提示模块与动态环境信息。
- Anthropic 显式提示缓存、OpenAI 稳定前缀。
- system-reminder 动态注入，不污染历史。
- Token 用量和缓存读取/写入统计。

### ch06：权限系统

- 危险命令黑名单、路径沙箱、三级规则、权限模式和 HITL 五层防御。
- default、acceptEdits、plan、bypassPermissions 四种模式。
- 本次允许、永久精确允许和拒绝。
- 权限拒绝作为工具结果返回，Agent Loop 可以调整策略。

### ch07：MCP 客户端

- MCP Python SDK v2。
- stdio 与 Streamable HTTP 两种传输。
- 用户级与项目级 Server 配置合并及 `${VAR}` 展开。
- 启动时并发连接、分页发现、命名隔离和连接复用。
- MCP 工具统一适配成现有 Tool，完整名称为 `mcp__server__tool`。
- 首次、本会话、永久和拒绝四项 MCP 权限。
- 单 Server 失败隔离、结果截断和退出生命周期清理。

### ch08：上下文管理

- 所有内置工具和MCP工具返回完整结果，由ContextManager统一决定是否落盘。
- 单条超过50000字节、同轮剩余合计超过200000字节时保存到会话目录并生成稳定预览。
- Read 支持 `offset`/`limit` 行分页，可按段恢复大型落盘结果。
- 基于最近一次主请求usage和字符增量估算Token，不引入精确tokenizer。
- 接近窗口时使用九部分结构化摘要、固定边界提示和近期原文替换旧历史。
- 主模型和摘要模型使用同协议、Key、base_url的独立Client；本机摘要模型为 `deepseek-v4-flash`。
- `/compact` 手动压缩、自动失败三次熔断、失败保留原历史并继续主请求。

### ch09：项目记忆与会话持久化

- 三层 `DRAGON.md` 项目指令加载和安全 `@include`，含深度、环路、边界与编码保护。
- 会话消息按 JSONL 追加保存，完整保留工具调用、工具结果和隐藏协议块。
- `/resume` 本地会话列表、搜索、坏行跳过、悬空调用截断、原会话续写和失败回滚。
- 新格式会话 45 天过期清理，旧格式数据不展示也不自动删除。
- 用户偏好、纠正反馈、项目知识、参考资料四类自动记忆，项目级和用户级分离。
- `MEMORY.md` 索引注入模型上下文；后台使用当前 LLMClient 更新，不阻塞主对话。

### ch10：Slash Command 内置命令框架

- 12 条内置命令集中注册，统一名称、别名、描述、用法、类型和异步 Handler。
- 普通消息与 `/` 命令在输入入口分流；命令层通过 `CommandUI` 与 Textual 解耦。
- 实时主名称补全、上下选择、最多 8 行、第一次 Enter 填入、第二次执行。
- `/session`、`/memory`、`/permission` 使用交互界面；删除动作有明确确认和安全边界。
- `/review` 使用一次性只读工具集合，不改变长期模式，也不允许 Write/Edit/Bash。
- 教材共同能力保持一致；Dragon Code 额外采用统一空闲保护和交互式管理界面。

### ch11：Skill 系统

- YAML frontmatter + Markdown SOP 的 Skill 格式，支持项目级、用户级和内置级三级覆盖。
- 启动时只向模型提供稳定的名称/描述摘要，需要时通过 `LoadSkill` 或 Slash Command 加载完整 SOP。
- inline Skill 复用主 Agent；fork Skill 使用独立 Agent、独立 Conversation 和可选模型覆盖，只把最终摘要回流主会话。
- `allowedTools` 白名单限制模型可见与可执行工具，多个激活 Skill 取并集，系统工具始终保留。
- 目录型 Skill 可携带 `tool.json` 和 Python 脚本；脚本通过独立子进程和 JSON stdin/stdout 执行。
- Skill 自定义工具仍经过黑名单、路径沙箱、规则、权限模式和人在回路，并统一串行调度。
- `/skill` 提供交互式列表、详情和重载；`/clear`、新建/恢复会话会清除激活状态。
- commit、review、test 三个内置 Skill 随 wheel 发布；原硬编码 review SOP 已移除，`/review` 与 `/r` 由 review Skill 接管。

### ch12：Hook 生命周期自动化系统

- 项目级与用户级 `hooks.yaml` 合并，同名 Hook 由项目级覆盖，错误配置按条隔离。
- 支持精确、glob、正则、取反以及一层 `all_of`/`any_of` 条件；权限规则复用统一匹配器。
- Shell、Prompt、HTTP、Subagent 四类动作已接入；Subagent 本章保持安全占位。
- 11 个生命周期事件贯穿会话、输入、Agent Loop、工具、压缩和通知流程。
- `UserPromptSubmit` 与 `PreToolUse` 支持同步拦截；拒绝转成可恢复事件或 `hook_denied` 工具结果。
- 异步 Hook、`only_once`、超时、输出截断、脱敏和退出清理已实现。
- `/hooks` 仅展示名称、事件、动作类型、来源与控制标记，不泄露命令正文或请求头。
- tmux 已实测写后动作、写前拦截、输入恢复和长耗时 Hook 退出清理。

### ch13：SubAgent 子任务分发

- 主 Agent 新增稳定的 `Agent`、`TaskList`、`TaskGet`、`TaskStop`、`SendMessage` 五个工具。
- 定义式子 Agent 从空白历史和预定义角色启动；内置 `explore`、`plan`、`verify` 默认使用
  `deepseek-v4-flash`。
- Fork 子 Agent 深拷贝父历史，补齐悬空工具结果并继承父模型、系统提示和工具前缀，强制后台。
- BackgroundTaskManager 提供三并发 FIFO、120 秒自动转后台、手动转后台、取消、状态查询、
  一次性完成通知和安全结果截断。
- 子 Agent 复用现有 `Agent.run()`，但隔离 Conversation、上下文、临时权限、Hook 运行状态、
  SkillRuntime 和 Token；共享 LLM/文件工具、持久规则和 Hook 定义快照。
- QuerySource 与 Fork 标记双层禁止嵌套委派；子 Agent 权限 Ask 变成结构化拒绝，不弹 TUI 框。
- fork Skill 已迁移到统一 Host/Manager；本章仍共享工作目录，不提供 Worktree 隔离。
- 自动化证据：`525 passed, 2 skipped`，Ruff 与 build 通过。
- tmux：定义式探索、Fork、TaskGet、SendMessage 续派和 fork Skill 主链路通过；完整并发组合与
  真实权限调整仍在 checklist 中保留为未实测项。
- 完整证据见 `specs/ch13-subagent/acceptance-report.md`。

### ch13 后：工具交互可读性优化

- 工具运行中只在输入框上方动态区域显示一条 `● 工具名 关键参数`，不再提前污染 scrollback。
- 工具完成后成功只保留一行 `✓` 摘要；失败使用暗红 `✗` 与下一行短原因。
- Read、Glob、Grep、Bash 和 SubAgent 系统工具使用语义摘要，不直接展示冗长协议结果。
- 前台子 Agent 内部工具继续可见并带任务标签；后台子 Agent 内部过程保持隐藏。
- 普通任务状态隐藏 task ID，只有查询或失败定位时显示；完成摘要限制约 80 个终端显示宽度。
- 颜色统一为低饱和暖橙、柔和灰和暗红，主对话、命令、Hook 与权限流程不变。
- 自动化证据：`53` 项 TUI 测试通过，全量 `530 passed, 2 skipped`，Ruff 通过。
- tmux 证据：真实 Read/Grep/Bash、前台定义式子 Agent、后台 Fork、失败恢复与退出清理通过。
- 完整证据见 `specs/tool-readability/acceptance-report.md`。

### 项目主页：README 专业化重构

- 使用 Dragon Banner、克制表情和真实技术徽章建立清晰首屏。
- 把 ch02–ch13 能力按工程领域重新分组，并增加 Mermaid 核心架构图。
- 增加快速开始、完整命令表、折叠配置说明、源码导航、开发进度和当前边界。
- 明确 ch14 Git Worktree 尚在学习与规划中，不把未来能力标记为已完成。
- 本地证据：Markdown/链接/敏感信息检查通过，Ruff 通过，全量 `530 passed, 2 skipped`。
- 完整证据见 `specs/github-homepage-refresh/acceptance-report.md`。

## 当前核心调用链

```text
CLI 加载 Provider、权限和 MCP 配置
  ↓
McpManager 连接 Server、发现工具并注册到 ToolRegistry
  ↓
SkillManager 发现三级 Skill，注册 LoadSkill、自定义工具和动态命令
  ↓
Textual TUI 接收用户输入
  ↓
Slash Command 分流器：命令交给 CommandRegistry，普通消息继续进入 Agent
  ↓
Agent 构造 LLMRequest（系统提示、环境、历史、工具定义）
  ↓
AnthropicClient / OpenAIClient 流式返回统一事件
  ↓
Agent 判断是否存在 ToolCall
  ↓
模型可调用 Agent 工具，把定义式或 Fork 子任务交给 SubAgentHost
  ↓
BackgroundTaskManager 管理并发、队列、前后台、取消和一次性完成通知
  ↓
PermissionEngine 检查黑名单、沙箱、规则、模式和用户审批
  ↓
ToolScheduler → ToolRegistry → 内置 Tool 或 McpTool
  ↓
ToolResult 写回 Conversation
  ↓
ContextManager 统一落盘预防、Token估算和可选结构化摘要
  ↓
Agent 进入下一轮，直到最终文本或停止条件
  ↓
SessionWriter 追加完整消息；MemoryManager 在自然完成后按条件后台更新
  ↓
TUI 通过 AgentEvent 实时展示文本、工具行、结果和状态
```

## 核心源码入口

| 文件 | 当前职责 |
|---|---|
| `src/dragon_code/cli.py` | 加载配置，装配 Registry、MCP Manager 和 TUI，统一清理 |
| `src/dragon_code/tui.py` | 终端布局、输入、事件消费、权限弹窗和状态展示 |
| `src/dragon_code/command/` | 命令模型、Registry、分发、补全和三类内置 Handler |
| `src/dragon_code/command_screens.py` | 帮助、会话、记忆、权限、审查和确认交互界面 |
| `src/dragon_code/command_widgets.py` | Slash Command 实时候选菜单 |
| `src/dragon_code/skills/parser.py` | SKILL.md 元信息、正文和上限校验 |
| `src/dragon_code/skills/loader.py` | 三级扫描、覆盖、依赖和失败隔离 |
| `src/dragon_code/skills/manager.py` | 稳定定义快照和会话级激活状态 |
| `src/dragon_code/skills/executor.py` | inline/fork 编排、上下文复制和摘要回流 |
| `src/dragon_code/skills/tools.py` | LoadSkill 与自定义 Python 子进程 Tool 适配 |
| `src/dragon_code/agent.py` | Agent Loop、模式、权限等待、工具执行和事件输出 |
| `src/dragon_code/models.py` | 消息、请求、事件、工具调用和用量等统一模型 |
| `src/dragon_code/clients/base.py` | 协议无关 LLMClient 接口 |
| `src/dragon_code/clients/anthropic.py` | Anthropic 请求、缓存和流事件适配 |
| `src/dragon_code/clients/openai.py` | OpenAI/兼容端点请求和流事件适配 |
| `src/dragon_code/stream_collector.py` | 流式实时转发与完整响应收集 |
| `src/dragon_code/tool_scheduler.py` | 工具调用的保序分批和并发调度 |
| `src/dragon_code/tools/registry.py` | 内置工具与 MCP 工具的统一注册和执行入口 |
| `src/dragon_code/permissions/engine.py` | 五层权限判断和 MCP 会话授权 |
| `src/dragon_code/prompt.py` | 模块化系统提示、环境信息、reminder 和 Banner |
| `src/dragon_code/mcp/config.py` | MCP 两层配置、校验和变量展开 |
| `src/dragon_code/mcp/manager.py` | MCP 连接、发现、隔离、缓存和关闭 |
| `src/dragon_code/mcp/tool.py` | 远端 MCP Tool 到 Dragon Code Tool 的适配 |
| `src/dragon_code/context/state.py` | 会话路径、冻结账本、usage锚点和熔断状态 |
| `src/dragon_code/context/summary.py` | 摘要Prompt、解析、近期原文边界和新历史纯函数 |
| `src/dragon_code/context/manager.py` | 工具结果落盘、Token估算、自动/手动压缩协调 |
| `src/dragon_code/instructions/loader.py` | 三层项目指令和安全 include 加载 |
| `src/dragon_code/sessions/manager.py` | 会话创建、列表、恢复、修复和 45 天清理 |
| `src/dragon_code/sessions/writer.py` | JSONL 串行追加、刷盘和压缩边界写入 |
| `src/dragon_code/sessions/reader.py` | JSONL 扫描、坏行跳过和悬空调用截断 |
| `src/dragon_code/memory/manager.py` | 自动记忆调度、模型更新、原子文件写入和索引重建 |

## 最近验证状态

ch11 完成时的证据：

- `uv sync --locked`、format、ruff、compileall 和 wheel 构建全部通过。
- `uv run pytest -q`：`442 passed, 2 skipped`。
- wheel 内含 commit、review、test 三个内置 `SKILL.md`。
- tmux + 真实 Anthropic 兼容 DeepSeek：自然语言 `LoadSkill → Read → 最终摘要` 通过。
- 目录型 Python Tool 弹出权限确认，JSON 回声 `龙焰测试` 成功回灌并形成最终答复。
- `/review` fork 实时展示多轮工具事件；Esc 取消后普通对话返回 `OK`。
- `/skill` 管理界面、reload、`/exit` 和进程清理通过；退出后 `dragon_code_processes=0`。
- WSL 原生子进程和真实 OpenAI 端点因本机环境未验，自动化路径通过。

完整证据见 `specs/ch11-skill-system/acceptance-report.md`。

ch10 完成时的证据：

- `uv sync --locked`：57 个包检查通过。
- `uv run ruff format --check .`：160 个文件已格式化。
- `uv run ruff check .` 与 `compileall`：通过。
- `uv run pytest -q`：`408 passed, 2 skipped`。
- tmux + 真实 DeepSeek：补全、帮助、状态、权限弹窗、真实工具调用、只读审查、Esc 取消和 `/q` 退出通过。
- `/review` 45 秒执行到第 15 轮，仅观察到只读工具，工作树未变化；取消后回到空闲。
- `/q` 后 `DRAGON_PYTHON_PROCESS_COUNT=0`。
- 真实数据上的清空恢复、会话删除和记忆删除未执行；对应临时目录集成测试通过。

完整证据见 `specs/ch10-slash-command/acceptance-report.md`。

ch09 完成时的证据：

- `uv sync --locked`：57 个包检查通过。
- `uv run ruff format --check .`：141 个文件已格式化。
- `uv run ruff check .`：通过。
- `uv run pytest -q`：`369 passed, 2 skipped`。
- 性能：指令加载平均 0.910ms；会话追加中位数 0.195ms、最大 1.299ms；扫描 50 个会话 12.967ms。
- WSL tmux + 真实 DeepSeek：Read 工具调用完整写入 JSONL，`/resume` 搜索并恢复后能引用前文。
- 明确“记住”后自动生成项目记忆；新会话无需读文件即可回答 `CH09-BLUE-DRAGON`。
- 含坏行和悬空 ToolCall 的会话被跳过/截断后仍可继续对话；`/exit` 后进程数为 0。

完整证据见 `specs/ch09-memory-session/acceptance-report.md`。

ch08 完成时的证据：

- `uv sync --locked`：57个包锁定检查通过。
- `uv run ruff format --check .`：121个文件已格式化。
- `uv run ruff check .`：通过。
- `uv run python -m compileall -q src tests`：通过。
- `uv run pytest -q`：`304 passed, 2 skipped`。
- Windows真实DeepSeek：主模型 `deepseek-v4-pro`，摘要模型 `deepseek-v4-flash`。
- 121911字节结果完整保存在L盘，真实主模型通过Read分页确认尾部标记。
- 自动摘要后当前消息保留且主任务继续；低Token `/compact` 成功。
- 自动连续失败三次熔断和手动绕过由可控自动化测试验证。
- 2026-08-10 已补真实 WSL tmux：113999字节结果落盘、模型按 `offset=5995`/`limit=6` 重读并回答 `DRAGON_5999`。
- 同一 tmux 会话中 `/compact` 成功，压缩后模型仍能引用保存路径和尾部；`/exit` 后无残留 Dragon Code 进程且结果文件保留。

完整证据见 `specs/ch08-context-management/acceptance-report.md`。

ch07 完成时的历史证据：

ch07 完成时的证据：

- `uv sync --locked`：通过。
- `uv run ruff format --check .`：通过。
- `uv run ruff check .`：通过。
- `uv run pytest -q`：`226 passed, 2 skipped`。
- tmux + 真实 DeepSeek：成功调用 `mcp__local_test__echo(text=dragon)`。
- TUI 显示四项 MCP 权限菜单，ToolResult 回灌后模型最终回答包含 `dragon`。
- “本会话允许”后，相同 MCP 工具再次调用不弹窗。
- `/plan` 只制定计划；`/do` 恢复 MCP 并执行 `plan-dragon`。
- 一个无效 Server 与正常 Server 并存时，正常工具仍返回 `isolation-ok`。
- `/exit` 后没有残留 `mcp_test_server.py` 子进程。

完整证据见 `specs/ch07-mcp-client/acceptance-report.md`。

## 学习与回顾状态

- 工具与 SubAgent 可读性优化已经验收；可在下次回顾中对照讲解“动态状态”和“最终 scrollback”分层。
- ch11 已完成开发与验收；下一步安排一次只讲核心链路的源码回顾。
- ch10 已补充一份聚焦 Registry、分流、UI Protocol、补全和只读审查的学习笔记；下一步可进行核心源码回顾。
- `docs/learning-notes.md` 已系统整理 ch02、ch03、聊天历史复制、ch05，并补充 ch09 核心源码回顾入口。
- ch06 已进行过对话式核心回顾，但尚未整理成独立的完整学习笔记章节。
- ch07、ch08 功能已经开发和验收，完整源码学习笔记仍可按需补充。
- ch09 已完成开发与验收，下一步安排一次聚焦核心调用链的源码回顾。
- 后续回顾只聚焦核心调用链、关键类型、边界、测试和面试表达，不逐文件啃完所有源码。
- 用户说“记一下”时，应立即把对应知识补入 `docs/learning-notes.md`。

## 不通过 Git 同步的内容

以下内容必须在新电脑重新配置，不能提交到仓库：

- `.dragon-code/config.yaml` 中的 Provider API Key。
- `.dragon-code/settings.local.yaml` 中的本地权限选择。
- `.env` 和任何真实 Token。
- 用户级 `~/.dragon-code/config.yaml` 与 `~/.dragon-code/settings.yaml`。
- 本机安装的 MCP Server、命令路径和环境变量。
- 飞书账号登录态和浏览器会话。
- Codex 本地应用偏好、未上传附件和未进入 Git 的聊天内容。

## 新电脑继续开发

### 1. 获取代码

首次克隆：

```powershell
git clone https://github.com/lgh88666/Dragon-Code.git
cd Dragon-Code
```

已经克隆过：

```powershell
git pull origin master
```

### 2. 安装依赖

```powershell
uv sync --locked
```

### 3. 重建本地配置

```powershell
Copy-Item .dragon-code/config.yaml.example .dragon-code/config.yaml
```

然后只在本地填写 Provider API Key、模型、base_url 和需要的 MCP Server。确认该文件仍被 `.gitignore` 忽略。

### 4. 启动验证

```powershell
uv run dragon-code
```

也可以使用：

```powershell
uv run python -m dragon_code
```

### 5. 在新 Codex 聊天中恢复上下文

打开仓库根目录后，发送：

```text
请先阅读 AGENTS.md 和 docs/PROJECT_HANDOFF.md，再查看 git status。
继续 Dragon Code 项目，严格遵守仓库记录的 Spec 开发模式。
```

即使原聊天没有同步，新 Agent 也应从仓库恢复长期规则和当前状态。

## 全部章节完成后的待优化事项

### Skill 激活状态缺少自动退出

- **当前现状**：inline Skill 一旦通过 Slash Command 或 `LoadSkill` 激活，就会保留在
  `SkillRuntime` 中。此后每次模型请求都会继续注入该 Skill 的完整 SOP reminder，直到
  用户执行 `/clear`、新建或恢复会话，或者重启 Dragon Code。
- **主要影响**：任务已经完成后，旧 Skill 仍可能影响模型行为、限制可用工具，并在后续
  请求中持续消耗动态 reminder token。
- **待讨论方案**：全部章节开发完成后，统一评估“inline Skill 自然完成后自动退出”、
  “增加显式停用命令（如 `/skill stop`）”以及“允许用户查看和选择性停用 Active Skills”。
- **暂不修改原因**：当前行为符合 ch11 已批准的“多个 Skill 持续激活”设计；现在只登记
  为待处理点，避免在后续章节开发期间临时改变 Skill 生命周期语义。

## 下一步

推荐顺序：

1. 回顾 ch13 核心源码：Agent 工具 → Host → Manager → child `Agent.run()` → 通知回流。
2. 如需补齐 100% tmux 清单，执行四任务并发/排队/Ctrl+B/TaskStop 和真实权限调整场景。
3. 学习 ch14 Worktree 理论内容，并按 `AGENTS.md` 的四文档流程启动开发。

## 每章验收后的更新模板

每章完成时更新本文件：

```markdown
### chXX：模块名
- 新增能力：
- 明确不做：
- 核心文件：
- 自动化证据：
- tmux 证据：
- 核心源码回顾状态：
- 学习笔记状态：
- 实现提交：
- 下一步：
```

同时执行：

1. 更新该章 checklist 和 acceptance report。
2. 更新本交接文档。
3. 创建本地 Git commit。
4. 等用户明确要求后再 push。
