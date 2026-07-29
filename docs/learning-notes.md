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
