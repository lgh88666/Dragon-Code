# Dragon Code 多协议 LLM 终端对话客户端 Plan

## 技术栈

- 语言：Python 3.12+
- TUI：Textual + Rich + Textual CSS
- 配置：PyYAML
- LLM 通信：官方 Anthropic 与 OpenAI Python SDK
- 依赖管理：uv
- 测试与质量：pytest、Textual Pilot、Ruff
- 端到端环境：WSL/Linux + tmux

## 架构概览

项目采用六层结构，保持依赖单向、代码直观。

1. **入口层**  
   加载配置并启动 TUI。启动期错误转换为简洁提示和非零退出码。

2. **配置层**  
   读取并校验 YAML Provider 列表，生成配置对象。Anthropic 和 OpenAI 共用基础字段；
   `thinking` 只在协议支持时生效。

3. **协议适配层**  
   定义统一 Provider 基类、消息类型和流式输出形式。Anthropic 与 OpenAI 各有一个适配器，
   将不同 SDK 的请求与流式事件转换为统一正文增量。思考增量在适配器内部丢弃。

4. **会话层**  
   保存进程内对话历史并协调单轮请求。仅在回复成功后提交完整的 user/assistant 消息对，
   避免失败轮次污染上下文。

5. **终端交互层**  
   Textual App 负责 Provider 选择、对话历史、流式区域、多行输入、计时和状态栏。
   网络流通过 Textual Worker 消费，界面等待期间仍可响应。

6. **展示资源层**  
   保存 System Prompt、ASCII 猫、版本和消息渲染规则，避免协议层接触界面样式。

项目内部命名：

- Python 包：`dragon_code`
- CLI 命令：`dragon-code`
- 配置目录：`.dragon-code/config.yaml`
- TUI 主类：`DragonCodeApp`

一轮请求的数据流：

```text
输入文本
  → 暂存本轮用户消息
  → Provider.stream(已完成历史 + 本轮输入)
  → Textual Worker 消费统一流式事件
  → 动态区域追加纯文本并更新计时
  → 成功：Markdown 定型并把本轮加入历史
  → 失败：展示脱敏错误，不把失败轮次加入历史
  → 恢复输入
```

## 核心数据结构与接口

代码以容易阅读和讲解为优先，不使用非必要的复杂泛型、`Protocol`、`slots` 或不可变容器。
实现中的关键步骤使用中文注释和中文 docstring。

### 配置模型

```python
from dataclasses import dataclass, field


@dataclass
class ProviderConfig:
    """单个模型服务的配置。"""

    name: str
    protocol: str
    api_key: str = field(repr=False)
    model: str
    base_url: str | None = None
    thinking: bool = False


@dataclass
class AppConfig:
    """Dragon Code 的完整配置。"""

    providers: list[ProviderConfig]
```

```python
class ConfigError(Exception):
    """配置文件存在问题时抛出的错误。"""


def load_config(path: str) -> AppConfig:
    """读取并校验 YAML 配置文件。"""
```

`protocol` 只允许 `"anthropic"` 和 `"openai"`，通过普通运行时校验保证。

### 对话消息

```python
@dataclass
class ChatMessage:
    """一条用户或助手消息。"""

    role: str
    content: str
```

System Prompt 不进入会话历史，由协议适配器按各协议格式单独注入。

### Provider 统一接口

```python
class BaseProvider:
    """Anthropic 和 OpenAI 适配器共同继承的基类。"""

    def __init__(self, config: ProviderConfig):
        self.config = config

    @property
    def name(self) -> str:
        return self.config.name

    @property
    def model(self) -> str:
        return self.config.model

    async def stream(self, messages, system_prompt):
        """流式返回正文增量，由子类实现。"""
        raise NotImplementedError
```

```python
def create_provider(config: ProviderConfig) -> BaseProvider:
    """根据 protocol 创建对应的 Provider。"""
```

### 错误类型

```python
class ProviderError(Exception):
    """适合安全展示在界面中的模型调用错误。"""

    def __init__(self, category: str, message: str, retryable: bool = False):
        super().__init__(message)
        self.category = category
        self.message = message
        self.retryable = retryable
```

适配器把 SDK 异常转换成该错误。`message` 必须脱敏，不包含 API Key、请求头或完整 SDK
异常对象。

### 会话历史

```python
class Conversation:
    def __init__(self):
        self._messages: list[ChatMessage] = []

    def get_messages(self) -> list[ChatMessage]:
        """返回当前历史的副本。"""

    def build_request_messages(self, user_text: str) -> list[ChatMessage]:
        """返回“已有历史 + 当前用户输入”，暂不改动历史。"""

    def commit_turn(self, user_text: str, assistant_text: str):
        """回复成功后，再保存本轮用户和助手消息。"""
```

### 单轮事件与协调器

```python
@dataclass
class TurnEvent:
    """ChatSession 发送给 TUI 的事件。"""

    type: str
    text: str = ""
    error: ProviderError | None = None
```

`type` 仅使用以下三个值：

- `"text"`：收到正文增量
- `"completed"`：本轮成功结束
- `"error"`：本轮失败

```python
class ChatSession:
    def __init__(self, provider, conversation, system_prompt):
        self.provider = provider
        self.conversation = conversation
        self.system_prompt = system_prompt

    async def stream_turn(self, user_text):
        """完成一次请求，并逐步产生 TurnEvent。"""
```

### TUI 状态

```python
class SessionState(Enum):
    SELECTING = "selecting"
    IDLE = "idle"
    STREAMING = "streaming"
```

`DragonCodeApp` 只持有活动 `ChatSession`、当前状态、本轮文本缓冲、开始时间和 Textual
Worker，不直接构造协议请求。

## 模块设计

### `dragon_code.config`

**职责：**

- 读取 `.dragon-code/config.yaml`
- 解析并校验 YAML
- 将文件、语法和字段问题转换为 `ConfigError`

**对外接口：** `load_config(path: str) -> AppConfig`

**依赖：** PyYAML、`models`

### `dragon_code.models`

**职责：** 集中保存 `ProviderConfig`、`AppConfig`、`ChatMessage`、`TurnEvent` 等共享数据类。

**依赖：** Python 标准库

### `dragon_code.prompt`

**职责：**

- 保存内置 System Prompt
- 保存 ASCII 猫
- 生成包含应用名、版本和工作目录的 Banner

**对外接口：** `SYSTEM_PROMPT`、`render_banner(version, cwd)`

### `dragon_code.providers.base`

**职责：**

- 定义 `BaseProvider`
- 定义 `ProviderError`
- 将 SDK 异常转换为脱敏的公开错误

`asyncio.CancelledError` 继续向上抛出，其他已知 SDK 异常按鉴权、限流、网络、模型不存在、
参数错误和未知错误分类。

### `dragon_code.providers.anthropic`

**职责：**

- 封装 `AsyncAnthropic`
- 转换 Anthropic Messages 请求
- 注入 System Prompt
- 按配置开启扩展思考
- 返回正文增量并丢弃 thinking 增量
- 支持自定义 `base_url`

**对外类：** `AnthropicProvider(BaseProvider)`

### `dragon_code.providers.openai`

**职责：**

- 封装 `AsyncOpenAI`
- 使用 Chat Completions 流式接口
- 将 System Prompt 放到消息列表开头
- 返回正文增量
- 支持自定义 `base_url`
- 首版不向 Chat Completions 传递 `thinking`

**对外类：** `OpenAIProvider(BaseProvider)`

### `dragon_code.providers.factory`

**职责：** 根据 `ProviderConfig.protocol` 创建适配器。未知协议返回清晰错误，不使用插件或
动态导入机制。

**对外接口：** `create_provider(config) -> BaseProvider`

### `dragon_code.session`

**职责：**

- `Conversation` 保存已成功完成的历史
- `ChatSession` 协调单轮请求
- 累计助手正文
- 成功后提交完整轮次
- 失败时生成错误事件且不污染历史

### `dragon_code.tui`

首版将 TUI 集中放在一个模块中，包含：

- `DragonCodeApp`：主界面与状态控制
- `ProviderSelectScreen`：多 Provider 选择界面
- `MessageInput`：Enter 提交、Alt+Enter 换行
- 少量消息渲染辅助函数

主要职责：

- 组成 Banner、就绪提示、对话区、流式区、输入框和状态栏
- 使用 Textual Worker 消费 `ChatSession.stream_turn()`
- 使用定时器刷新 `Imagining… (Ns)`
- 流式期间禁用提交但保持界面响应
- 完成后写入 Markdown
- 错误时显示脱敏提示
- `/exit` 与 Ctrl+C 安全退出

### `dragon_code.cli`

**职责：**

- 加载固定路径配置
- 处理启动期配置错误
- 启动 `DragonCodeApp`

CLI 不包含业务逻辑。

### 测试模块

自动测试至少覆盖：

- 配置加载和错误校验
- 会话历史
- 两种 Provider 的流式事件转换
- Provider 错误脱敏
- ChatSession 成功和失败
- Textual Pilot 的单 Provider、多 Provider、提交、错误恢复和退出

外部请求使用假客户端，不消耗真实 API；真实 API 仅用于 tmux 端到端验收。

## 模块交互

### 启动流程

```text
python -m dragon_code
    → cli.main()
    → load_config(".dragon-code/config.yaml")
        ├─ 失败：输出可读错误，返回非零退出码
        └─ 成功：DragonCodeApp(config).run()
```

单 Provider 直接创建 Provider 和 ChatSession 并进入空闲状态；多 Provider 显示
`ProviderSelectScreen`，用户选择后再创建 ChatSession。

### 成功对话

```text
MessageInput 提交
    → DragonCodeApp 暂存输入、清空输入框、启动计时与 Worker
    → ChatSession 组装“历史 + 当前输入”
    → Provider.stream()
    → ChatSession 产生 text 事件
    → TUI 实时更新纯文本区域
    → 流正常结束
    → Conversation.commit_turn()
    → ChatSession 产生 completed 事件
    → TUI Markdown 定型、显示总耗时、恢复输入
```

### 失败对话

```text
SDK 异常
    → ProviderError（分类并脱敏）
    → ChatSession 产生 error 事件
    → 不提交 Conversation
    → TUI 显示错误、停止计时、恢复输入
```

失败轮次的用户输入保留在界面，但不加入后续模型上下文。

### 流式期间

Textual Worker 等待网络数据，主事件循环继续处理滚动、计时刷新、窗口变化和 Ctrl+C。
输入框可见，但提交动作被禁用。

### 退出

```text
/exit 或 Ctrl+C
    → 停止计时器
    → 取消当前 Worker
    → 关闭 Textual App
    → 恢复终端状态
```

`/exit` 仅在空闲状态处理；Ctrl+C 始终有效。

### 依赖方向

```text
cli
 ├── config
 └── tui
      ├── session
      │    ├── models
      │    └── providers
      │         ├── base
      │         ├── anthropic
      │         └── openai
      └── prompt
```

底层模块不导入 TUI 或 CLI，不形成循环依赖。

## 文件组织

```text
dragonAgent/
├── pyproject.toml
├── uv.lock
├── README.md
├── .gitignore
├── spec.md
├── plan.md
├── task.md
├── checklist.md
├── .dragon-code/
│   └── config.yaml.example
├── src/
│   └── dragon_code/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── config.py
│       ├── models.py
│       ├── prompt.py
│       ├── session.py
│       ├── tui.py
│       ├── dragon_code.tcss
│       └── providers/
│           ├── __init__.py
│           ├── base.py
│           ├── factory.py
│           ├── anthropic.py
│           └── openai.py
└── tests/
    ├── conftest.py
    ├── test_config.py
    ├── test_session.py
    ├── test_provider_anthropic.py
    ├── test_provider_openai.py
    ├── test_provider_errors.py
    └── test_tui.py
```

`.dragon-code/config.yaml` 保存真实配置并被 `.gitignore` 忽略；仓库只提交
`config.yaml.example`。

## 技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 语言 | Python 3.12+ | 项目既定，异步和标准库能力足够 |
| 依赖管理 | uv + `uv.lock` | 安装快且演示环境可复现 |
| TUI | Textual + Rich | 支持异步 Worker、Widget、键盘事件、Markdown 和响应式布局 |
| TUI 组织 | 一个 `tui.py` + TCSS | 首版容易阅读 |
| 异步任务 | Textual Worker | 生命周期与界面绑定，退出清理清晰 |
| Anthropic | 官方 Messages 流 | SDK 负责 HTTP、SSE 和响应类型 |
| OpenAI | 官方 Chat Completions 流 | 对兼容端点覆盖更广 |
| 扩展思考 | Anthropic 开启，OpenAI 首版忽略 | 两种协议能力不同 |
| 协议抽象 | 简单 `BaseProvider` | 比高级类型抽象更易读 |
| 会话提交 | 成功后原子追加一轮 | 失败不污染上下文 |
| 流式渲染 | 流式纯文本，完成后 Markdown | 避免不完整 Markdown 抖动 |
| 密钥保护 | Git 忽略、隐藏打印、错误脱敏 | 满足 N5 |
| 自动测试 | pytest + Pilot + 假 SDK | 快速、稳定且不消耗 API |
| 代码质量 | Ruff | 配置简单，兼顾格式和检查 |
| E2E | WSL/Linux + tmux | 满足真实终端验收要求 |
| 可读性 | 中文注释、直接控制流 | 便于学习、复盘和面试讲解 |

## Spec 覆盖检查

| Spec | 设计归属 |
|---|---|
| F1 | `config.py`、`models.py`、CLI 错误处理 |
| F2 | `ProviderSelectScreen` |
| F3 | Provider 基类、Factory、协议适配器 |
| F4 | ChatSession、System Prompt、请求构造 |
| F5 | Provider 流式解析和 thinking 过滤 |
| F6 | Conversation 成功轮次提交 |
| F7 | DragonCodeApp 与 TCSS |
| F8 | 动态纯文本区与 Rich Markdown |
| F9 | MessageInput 与状态控制 |
| F10 | `/exit`、Ctrl+C、Worker 清理 |
| F11 | ProviderError、错误事件和 TUI 样式 |
| F12 | 单调时钟和 Textual Timer |
| N1–N2 | Textual Worker、Timer、事件循环 |
| N3 | ChatSession 与统一 Provider |
| N4 | ConfigError |
| N5 | Git 忽略、隐藏字段、错误脱敏 |
| N6 | Textual 响应式布局 |
| N7 | Textual 生命周期和退出动作 |

检查结论：

- F1–F12 均有明确归属。
- 模块依赖单向，无循环依赖。
- 公开接口均有真实调用方。
- 技术决策与 Spec 无冲突。
- 自动测试与 tmux 端到端测试均有明确入口。
