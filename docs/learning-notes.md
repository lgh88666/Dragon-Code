# Dragon Code 学习笔记

> 用于记录开发 Dragon Code 过程中值得理解、复习和用于面试表达的内容。
>
> 当我说“这条记一下”时，将内容补充到对应章节，不只记录结论，也记录为什么这样设计。

## 使用约定

- 每完成一个模块，开发、测试和 tmux 验收后进行一次核心源码回顾。
- 源码回顾完成后，把重要知识补充到本笔记。
- 优先记录设计思想、调用链、关键代码、踩坑和面试表达，不大段复制源码。
- 不记录 API Key、密码或其他敏感信息。
- 暂时没理解的内容放入“待复习”，后续解决后再移动到对应章节。

## 项目能力路线

```text
ch01 认识 Coding Agent
  ↓
ch02 LLM 对话与终端界面
  ↓
ch03 工具系统
  ↓
ch04 Agent Loop
  ↓
ch05 System Prompt
  ↓
ch06 权限系统
  ↓
ch07 MCP
  ↓
ch08 上下文管理
  ↓
ch09 记忆系统
  ↓
ch10 Slash Command
  ↓
ch11 Skill
  ↓
ch12 Hook
  ↓
ch13 SubAgent
  ↓
ch14 Worktree
  ↓
ch15 Agent Teams
  ↓
ch16 架构回顾
  ↓
ch17 秋招准备
```

## ch02：LLM 对话与终端界面

### 模块解决了什么问题

ch02 打通了“用户输入 → LLM API → 流式回复 → 保存上下文”的完整对话闭环。

当前 Dragon Code 已经是一个多协议终端聊天客户端，但还不能读取文件、修改代码或执行命令。
这些行动能力由 ch03 工具系统提供。

### 核心模块

| 文件 | 职责 |
|---|---|
| `src/dragon_code/cli.py` | 程序入口、配置错误处理、启动 TUI |
| `src/dragon_code/config.py` | 读取并校验 YAML 配置 |
| `src/dragon_code/models.py` | Provider 和消息等内部数据结构 |
| `src/dragon_code/providers/base.py` | 统一 Provider 接口 |
| `src/dragon_code/providers/anthropic.py` | Anthropic 请求与流式响应解析 |
| `src/dragon_code/providers/openai.py` | OpenAI 及兼容端点适配 |
| `src/dragon_code/providers/factory.py` | 根据配置选择协议实现 |
| `src/dragon_code/session.py` | 多轮消息历史管理 |
| `src/dragon_code/tui.py` | 输入、流式显示、计时和界面状态 |
| `src/dragon_code/prompt.py` | System Prompt 和启动 Banner |

### 一次对话的调用链

```text
用户在 TUI 输入消息
  ↓
TUI 将用户消息加入 Conversation
  ↓
Provider Factory 提供当前协议客户端
  ↓
Provider 把内部消息转换为 API 请求
  ↓
Anthropic / OpenAI API 流式返回
  ↓
Provider 解析文本增量
  ↓
TUI 实时更新回复
  ↓
回复结束后保存完整助手消息
  ↓
下一轮请求携带完整历史
```

### 值得记住的设计

#### 1. Provider 抽象

TUI 不应该知道当前使用 Anthropic 还是 OpenAI。

上层只依赖统一 Provider 接口，协议差异留在各自适配器中。这样新增兼容端点时，不需要重写
界面和会话逻辑。

#### 2. 内部消息与 API 消息分离

Dragon Code 内部保存统一消息模型，发送请求时再由不同 Provider 转成协议要求的格式。

这样可以避免协议字段渗透到整个项目。

#### 3. 流式回复使用异步生成器

Provider 不等待完整回复，而是不断产出文本增量。TUI 可以边接收边显示，同时保持事件循环
响应。

#### 4. 会话历史是多轮对话的基础

模型本身不会自动记住上一次 API 请求。每轮都必须把此前消息重新发送给模型。

#### 5. 错误不应该结束会话

鉴权、网络、模型不存在等错误应转换成用户可读信息显示在对话区，程序继续运行。

### 已经踩过的坑

- PowerShell 默认 GBK 不能直接打印部分 Unicode 方块字符；实际终端展示需要 UTF-8。
- WSL 需要同时安装 WSL 2 平台、Ubuntu 发行版和 tmux。
- Textual 异步测试可能受到任务调度时序影响，测试需要等待应用回到明确状态。
- 自动测试能验证图案尺寸和字符，但不能替代用户对视觉设计的确认。

### 面试表达

可以这样介绍 ch02：

> 我先实现了一个协议无关的终端 LLM 客户端。上层 TUI 和会话模块只依赖统一 Provider
> 接口，Anthropic 与 OpenAI 的请求构造和 SSE 流解析由适配器完成。网络和流式处理采用
> 异步方式，保证 Textual 事件循环不被阻塞，同时在单次会话中维护完整多轮上下文。

## ch03：工具系统

### Tool Result 是谁发给谁的

工具不是模型亲自执行的。模型只生成一个结构化工具调用请求，Dragon Code 在本地执行工具，
再把执行结果回传给模型。

从对话关系上看：

```text
Assistant：请求调用工具
  ↓
Dragon Code：在用户侧执行工具
  ↓
User / Tool：把 Tool Result 发回给 Assistant
```

不同协议的表示方式不同：

- Anthropic：`tool_result` 放在 `user` 消息的内容块中。
- OpenAI：工具结果使用专门的 `tool` 角色，并通过工具调用 ID 与请求对应。

因此内部消息模型应该统一表达“工具结果”，再由各 Provider 转换成自己的协议格式。

### 工具描述非常重要

模型不能查看工具的 Python 实现，只能看到工具名称、描述和参数 Schema。模型是否会选择正确
工具、是否会传入正确参数，很大程度取决于工具描述的质量。

一个好的工具描述需要讲清楚：

- 工具能做什么。
- 什么时候应该使用。
- 什么时候不应该使用。
- 每个参数的含义、格式和约束。
- 成功时返回什么。
- 失败时可能返回什么。
- 容易混淆的工具之间有什么区别。

工具描述本质上也是 Prompt Engineering。描述模糊时，即使工具代码完全正确，模型也可能
选错工具或构造错误参数。

### 三个重要的工具元信息

#### `read_only`

表示工具只读取信息，不修改文件或外部状态。

典型工具：

```text
ReadFile
Glob
Grep
```

系统可以据此决定：

- 默认放行，通常不需要用户确认。
- 允许在 Plan Mode 中使用。
- 多个只读操作通常可以并行。
- 失败后通常可以安全重试。

#### `destructive`

表示工具可能修改文件、执行命令或改变外部状态。

典型工具：

```text
WriteFile
EditFile
Bash
```

系统可以据此决定：

- 执行前进入权限检查。
- 必要时询问用户确认。
- Plan Mode 中禁止使用。
- 使用警告样式展示并保留审计信息。
- 不能在失败后盲目自动重试。

`Bash` 比较特殊，同一个工具既能执行 `git status`，也能执行删除文件的命令。初期可以把
它整体标记为破坏性工具，后续权限系统再根据具体命令判断风险。

#### `is_concurrency_safe`

表示工具能否与其他工具同时执行，而不会发生状态冲突或产生不确定结果。

```text
ReadFile / Glob / Grep → 通常为 True
WriteFile / EditFile   → 通常为 False
Bash                   → 初期保守设为 False
```

Agent Loop 可以根据该字段分批调度：

```text
并发安全工具
  → asyncio.gather(...) 同时执行

非并发安全工具
  → 按原始顺序逐个执行
```

例如两个 `EditFile` 同时修改同一个文件时，可能互相覆盖或让唯一匹配失效，因此不能并发。

#### 三者的区别

| 元信息 | 回答的问题 | 主要使用方 |
|---|---|---|
| `read_only` | 工具是否只读取状态？ | 权限系统、Plan Mode、重试策略 |
| `destructive` | 工具是否可能改变状态？ | 权限确认、审计、UI 警告 |
| `is_concurrency_safe` | 工具能否和其他工具一起运行？ | Agent Loop、工具调度器 |

一句话记忆：

> `read_only` 和 `destructive` 决定“需不需要防”，`is_concurrency_safe` 决定“能不能一起跑”。

### ch03 核心源码回顾

#### 文件职责

| 文件 | 职责 |
|---|---|
| `src/dragon_code/models.py` | ToolDefinition、ToolCall、ToolResult、两层事件和统一消息 |
| `src/dragon_code/tools/base.py` | 参数校验、超时和结构化异常的公共入口 |
| `src/dragon_code/tools/file_tools.py` | Read、Write、Edit |
| `src/dragon_code/tools/search_tools.py` | Glob、Grep |
| `src/dragon_code/tools/bash.py` | 异步执行系统命令 |
| `src/dragon_code/tools/registry.py` | 注册、查找并执行六个工具 |
| `src/dragon_code/providers/openai.py` | 拼接 OpenAI tool_calls JSON 分片 |
| `src/dragon_code/providers/anthropic.py` | 解析 tool_use，并保留隐藏 thinking 块 |
| `src/dragon_code/session.py` | 一轮工具执行、结果回灌和一次最终续答 |
| `src/dragon_code/tui.py` | 工具行、结果摘要和单轮上限提示 |

#### ProviderEvent 与 TurnEvent

这两个事件不是第三方协议，而是 Dragon Code 内部的简单数据包：

```text
模型 SDK
  ↓ ProviderEvent：模型返回了什么
ChatSession
  ↓ TurnEvent：界面应该显示什么
TUI
```

ProviderEvent 屏蔽 Anthropic 与 OpenAI 的流式格式差异。TurnEvent 还包含工具执行结果
和单轮上限，因为这些信息不是模型 Provider 产生的，而是 ChatSession 协调出来的。

#### 完整调用链

```text
用户提问
  ↓
Provider 注入六个工具定义
  ↓
模型返回 ToolCall
  ↓
ToolRegistry 按名称找到 Tool
  ↓
Tool.execute 校验参数、限制超时、包装错误
  ↓
具体工具执行并返回 ToolResult
  ↓
ChatSession 把 Assistant 工具调用与 ToolResult 加入临时历史
  ↓
Provider 发起一次最终续答
  ↓
TUI 流式显示最终答复
```

#### 两种协议的关键差异

OpenAI 使用 `delta.tool_calls[index]` 传输调用，同一个工具的名称和 arguments JSON
可能被拆成多个 chunk，必须按 index 分别拼接。工具结果使用 `role=tool`，并带
`tool_call_id`。

Anthropic 使用 `tool_use` 内容块和 JSON 增量。工具结果位于下一条 `user` 消息的
`tool_result` 内容块中。开启扩展思考时，工具续答还必须原样带回对应的 `thinking`
或 `redacted_thinking` 块，但这些内容绝不能渲染到 TUI。

#### 结构化错误为什么重要

文件不存在、参数缺失、非法 JSON、唯一匹配失败、非零退出和超时都属于 Agent 可以理解
并处理的信息。如果直接抛出 Python 异常，会话会中断；转换成 ToolResult 后，模型可以
在最终答复中说明实际失败原因。

#### 路径保护

文件类工具先用 `Path.resolve()` 得到真实路径，再检查它是否仍位于启动工作目录内。
因此普通 `../` 和指向外部的符号链接都不能绕过边界。Bash 本章没有沙箱，仍被保守标记
为 destructive，权限确认留到后续章节。

#### 单轮上限

ch03 只允许：

```text
第一次模型请求 → 一批工具 → 第二次模型请求 → 停止
```

第二次模型请求如果再次调用工具，ChatSession 不执行、不保存该调用，而是显示本地上限
提示。这能清楚区分“工具系统”和下一章的“Agent Loop”。

### ch03 测试与证据

- 自动化测试覆盖六个工具、路径越界、输出截断、两种协议 JSON 分片、隐藏 thinking、
  多工具顺序、结构化失败和单轮上限。
- Ruff 格式与 lint、Python 编译、依赖锁检查均通过。
- WSL/tmux + 真实 DeepSeek 已验证 Read 成功后续答，耗时 5.3 秒。
- 真实不存在文件返回 `not_found`，随后会话仍可继续。
- 真实 Write 创建并覆盖文件，磁盘内容为 `dragon_ok_2026`。
- 真实 Grep 命中 `src/dragon_code/tools/registry.py:12`。
- 真实 Glob 找到未知文件后，续答阶段的 Read 被单轮上限拦截。

### ch03 踩坑记录

- tmux `send-keys` 会把部分带连字符的文本解释成按键名称，端到端测试数据应使用简单
  字母、数字和下划线，或采用更严格的文字输入方式。
- Windows 默认权限可能不允许测试创建符号链接；普通绝对路径和 `../` 越界测试仍会
  执行，符号链接场景在允许的平台验证。
- Anthropic thinking 不能简单“接收后丢弃”：工具续答要求保留签名内容块，只能做到
  “不展示但原样回灌”。

### ch03 面试表达

> 我为终端编程助手设计了协议无关的工具系统。每个工具通过统一接口提供描述、JSON
> Schema、安全元信息和异步执行入口，公共基类负责参数校验、超时与结构化错误。Provider
> 适配器分别解析 OpenAI tool_calls 和 Anthropic tool_use 的流式 JSON 分片，再转换成
> 统一事件。ChatSession 串行执行首轮工具、按协议回灌 ToolResult，并只允许一次最终续答，
> 因而在实现真实 Agent 能力的同时明确控制了本章与 Agent Loop 的边界。

## 聊天历史选择与复制：核心源码回顾

### 模块目标

- 解决的问题：用户可以从 Dragon Code 历史区拖选并复制代码、命令和回复。
- 用户可观察行为：有选择时 `Ctrl+C` 复制，无选择时 `Ctrl+C` 退出。
- 明确不做：复制按钮、键盘扩展选择、会话持久化和消息组件重写。

### 文件职责

| 文件 | 职责 |
|---|---|
| `src/dragon_code/tui.py` | 提取 RichLog 选择文本，处理复制/退出分流 |
| `tests/test_tui.py` | 模拟真实鼠标拖选并验证剪贴板、继续对话和退出 |

### 核心调用链

```text
鼠标在 ConversationLog 中拖动
  ↓
render_line() 提供每个字符的位置元信息
  ↓
Textual Screen 记录 Selection
  ↓
用户按 Ctrl+C
  ↓
action_copy_or_quit()
  ├─ Selection 非空 → copy_to_clipboard() → OSC 52 → 终端剪贴板
  └─ Selection 为空 → action_safe_quit()
```

### 为什么需要 `ConversationLog`

当前 Textual 6.12 的 `RichLog` 会渲染 Rich/Markdown 对象，但其默认选择逻辑无法从这种
渲染结果中取得文字，而且渲染行没有供鼠标选择使用的位置元信息。因此界面看似支持
选择，实际 `Screen.get_selected_text()` 得到空内容。

`ConversationLog` 仍然继承 `RichLog`，只补两件事：

1. `render_line()` 调用 `apply_offsets()`，让 Textual 能把鼠标坐标换成行列下标，并把
   当前选择范围高亮。
2. `get_selection()` 从已经渲染的行中组合纯文本，再按 `Selection` 提取。

它没有改变消息写入、Markdown 渲染、滚动或工具行逻辑。

### OSC 52 是什么

OSC 52 是终端控制序列。程序不能像桌面 GUI 那样直接操作所有平台的系统剪贴板，
Textual 会把选择内容编码后发送 OSC 52，由 Windows Terminal 等外层终端决定是否写入
系统剪贴板。

tmux 位于应用和外层终端之间。当前环境的 `set-clipboard=external` 允许应用发出的
OSC 52 继续交给外层终端。后台分离的 tmux 没有外层终端客户端，因此可以验证应用没有
退出，却不能在后台读取 Windows 系统剪贴板。

### 重要边界

- `if selected_text:` 同时排除了 `None` 和空字符串，避免空选择阻止退出。
- 复制后不清除选择，所以连续按 `Ctrl+C` 会继续复制；按 `Escape` 或单击其他位置可以
  清除选择。
- 鼠标点击历史区后输入框可能失去焦点；继续对话时重新点击输入框或按 `Tab` 即可。
- Textual 把终端单元格坐标转换为字符下标，因此中文等双宽字符也能正确选择。

### 测试与证据

- 自动化测试真实组合鼠标按下、拖动和松开事件，并精确比较剪贴板文字。
- 内容覆盖用户消息、助手 Markdown、代码块、工具行和错误行。
- 完整测试结果：`70 passed, 1 skipped`。
- WSL/tmux + DeepSeek 验证：选择 `COPY_READY` 后复制不退出，随后正常得到第二轮
  `CONTINUE_OK`；清除选择后 `Ctrl+C` 安全退出。

### 面试表达

> 我修复了 Textual RichLog 在 Rich/Markdown 渲染下无法实际选择文字的问题。通过一个
> 很小的 RichLog 子类为渲染行附加字符位置，并从 Selection 中提取纯文本；同时把
> Ctrl+C 设计成条件动作，有选择就通过 OSC 52 复制，没有选择就安全退出。测试不仅断言
> 剪贴板内容，还在 WSL/tmux 中发送真实鼠标序列验证了复制、继续对话和退出三条路径。

## ch05：系统提示工程化

### 一个 system 字段，两个内容块

Anthropic 请求并不是发送两个同名的 `system` 字段，而是发送一个 `system` 字段，字段值
是内容块列表：

```text
system
├── system[0]：稳定系统提示，带 cache_control
└── system[1]：动态环境信息，不带 cache_control
```

稳定块包含七个固定模块：身份、系统约束、任务模式、动作执行、工具使用、语气风格和文本
输出。环境块包含工作目录、平台、日期、Git 摘要、版本和模型。

### Anthropic 缓存顺序

Anthropic 计算提示前缀的顺序固定为：

```text
tools → system → messages
```

因此把显式缓存断点放在稳定的 `system[0]` 末尾，就会同时覆盖全部工具定义和稳定系统
提示；位于断点之后的环境、补充提醒和对话历史不会进入这段稳定缓存。

缓存能否命中有三个条件：

1. 工具定义和稳定提示的内容、顺序逐字一致。
2. 稳定前缀达到当前模型规定的最小 Token 门槛。
3. 请求发生在缓存 TTL 内，且端点真正支持并暴露缓存字段。

### system-reminder 为什么不写入历史

Plan Mode 等运行时约束会随 Agent Loop 轮次变化。如果把它拼进稳定系统提示，会让缓存
前缀不断变化；如果写入 Conversation，又会污染后续对话。

Dragon Code 把 reminder 独立放在 `LLMRequest` 中，只在 LLM Client 序列化本轮请求时
注入带 `<system-reminder>` 标签的临时内容。Anthropic 的 `tool_result` 必须排在 reminder
之前，避免破坏 tool use/result 配对。

Plan Mode 第 `1、6、11……` 轮使用完整提醒，其他轮使用精简提醒；默认模式不注入。

### 统一请求的作用

```text
Agent
  ↓ LLMRequest(messages, tools, system, reminder)
LLM Client
  ├── Anthropic：system 内容块 + 显式缓存
  └── OpenAI：稳定 system 前缀 + 自动缓存字段解析
```

Agent 不需要知道 `cache_control` 或 `prompt_tokens_details`。协议字段只存在于具体
LLM Client 中，统一用量对象最终暴露输入、输出、缓存写入、缓存读取四项。

### 测试与证据

- 自动化测试：`115 passed, 1 skipped`。
- Ruff 格式与 lint 全部通过。
- tmux 真实 DeepSeek：模型按要求优先调用 Read，并正确总结 ch05 Spec。
- Plan Mode 真实调用只出现 Glob；`/do` 后自动完成 Write → Read 验证。
- 取消慢 Bash 后历史保持合法，下一条消息正常返回 `OK`。
- 使用全新缓存标记烟测：第一次输入 1358、缓存读取 0；第二次输入 78、缓存读取 1280。
  当前 DeepSeek 兼容端点没有暴露缓存写入字段，但第二次读取量证明稳定前缀已被复用。

### 踩坑记录

- 在 WSL tmux 中运行 Windows `uv.exe` 时，tmux 的 `Escape` 名称没有被转发为 Textual
  识别的取消键，发送等价控制码 `C-[` 后取消成功。这是测试链路的按键表示差异，不是
  Agent 取消逻辑失败。
- 真正的缓存烟测可能一开始就读到之前 TUI 请求创建的缓存；为观察新前缀，烟测脚本提供
  固定 `--cache-tag`，两次测试请求使用同一个新标记，正式 Agent 不使用该标记。

### 面试表达

> 我把系统提示重构成稳定模块、动态环境和临时提醒三层。Agent 只构造协议无关的
> LLMRequest，Anthropic Client 用一个 system 字段内的两个内容块设置显式缓存断点，
> OpenAI Client 保持稳定前缀。Plan Mode 约束通过不持久化的 system-reminder 按轮注入，
> 既不污染历史，也不会破坏工具结果配对。最后通过真实缓存读取 Token 验证了前缀复用。

## 每章源码回顾模板

### chXX：[模块名称]

#### 模块目标

- 解决什么问题：
- 用户可观察到什么：
- 明确不做什么：

#### 文件职责

| 文件 | 职责 |
|---|---|
| `path` | 说明 |

#### 核心调用链

```text
输入
  ↓
模块 A
  ↓
模块 B
  ↓
输出
```

#### 核心类型和函数

- 类型：
- 函数：
- 关键字段：

#### 重要设计决策

1. 选择：
   - 原因：
   - 替代方案：
   - 取舍：

#### 错误与边界

- 正常情况：
- 参数错误：
- 超时：
- 外部依赖失败：
- 数据过大：

#### 测试与证据

- 单元测试：
- 集成测试：
- tmux 真实场景：

#### 踩坑记录

- 问题：
- 原因：
- 修复：
- 如何避免再次发生：

#### 面试表达

> 用一段自己的话说明该模块。

#### 待复习

- [ ] 问题

## 待复习

- [ ] Function Calling 中工具定义、工具请求和工具结果分别由谁产生？
- [ ] Anthropic 与 OpenAI 的流式工具调用事件有什么区别？
- [ ] Agent Loop 应该设置哪些停止条件？
- [ ] 如何避免工具输出撑爆上下文？
- [ ] 权限系统为什么需要多层防御，而不是只检查危险命令？
