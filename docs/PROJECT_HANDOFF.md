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

- 已完成：ch02–ch10。
- 最近完成模块：ch10 Slash Command 内置命令框架。
- ch07 实现提交：`9b0d901 feat: add MCP client integration`。
- ch08 实现提交：`97d3cd7 feat: add ch08 context management`。
- ch02–ch08 功能代码已经推送到 GitHub；ch09 已完成本地验收，等待用户明确要求后再推送。
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

## 当前核心调用链

```text
CLI 加载 Provider、权限和 MCP 配置
  ↓
McpManager 连接 Server、发现工具并注册到 ToolRegistry
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

## 下一步

推荐顺序：

1. 回顾 ch10 核心源码：输入分流 → Registry → Handler → CommandUI → Textual 交互。
2. 只精读 `command/registry.py`、`command/dispatch.py`、`command/completion.py` 与 `tui.py` 的接线。
3. 如需 100% tmux 清单，先创建可丢弃的会话和记忆，再补做清空恢复、会话删除、记忆删除三项。
4. 学习下一章理论内容，并按 `AGENTS.md` 的四文档流程启动开发。

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
