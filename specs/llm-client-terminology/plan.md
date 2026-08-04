# LLM Client 术语统一 Plan

## 架构概览

本次改动把“外部模型服务配置”和“内部模型调用对象”分成两层：

```text
config.yaml 中的 providers
          │
          ▼
   ProviderConfig
   （外部服务配置）
          │
          ▼
 create_llm_client()
          │
          ▼
      LLMClient
      ├── AnthropicClient
      └── OpenAIClient
          │
          ▼
 Agent / StreamCollector / TUI
```

YAML 和启动选择界面继续使用 Provider 表示外部服务；Python 内部使用 LLM Client 表示协议客户端。

## 核心数据结构与接口

### LLMClient

```python
class LLMClient:
    def __init__(self, config: ProviderConfig): ...

    @property
    def name(self) -> str: ...

    @property
    def model(self) -> str: ...

    async def stream(
        self,
        messages: list[ChatMessage],
        system_prompt: str,
        tools: list[ToolDefinition],
    ): ...
```

它是 Anthropic 与 OpenAI 客户端共同遵循的基类，接口和现有行为不变。

### LLMError

```python
class LLMError(Exception):
    def __init__(
        self,
        category: str,
        message: str,
        retryable: bool = False,
    ): ...
```

`make_llm_error(error)` 继续负责把 SDK 异常转换为可安全展示的错误。

### LLMEvent

```python
@dataclass
class LLMEvent:
    type: str
    text: str = ""
    tool_call: ToolCall | None = None
    message: ChatMessage | None = None
    usage: TokenUsage | None = None
```

该事件只用于 LLM Client 向 Agent 传递流式数据。`AgentEvent` 仍用于 Agent 向 TUI 传递事件。

### 工厂函数

```python
def create_llm_client(config: ProviderConfig) -> LLMClient: ...
```

根据 `ProviderConfig.protocol` 创建 `AnthropicClient` 或 `OpenAIClient`。

## 模块设计

### clients/base.py

**职责：** 定义 `LLMClient`、`LLMError` 和 `make_llm_error`。

**依赖：** 共享消息模型、工具定义和 `ProviderConfig`。

### clients/anthropic.py

**职责：** `AnthropicClient` 组装 Anthropic 请求并把 SDK 流转换成 `LLMEvent`。

**依赖：** Anthropic SDK、`LLMClient`、共享数据模型。

### clients/openai.py

**职责：** `OpenAIClient` 组装 OpenAI 请求并把 SDK 流转换成 `LLMEvent`。

**依赖：** OpenAI SDK、`LLMClient`、共享数据模型。

### clients/factory.py

**职责：** 根据外部 Provider 配置创建对应的 LLM Client。

### Agent 与 StreamCollector

**职责：** Agent 持有 `client: LLMClient`；`StreamCollector` 消费 `LLMEvent` 并产生 `AgentEvent`。异常统一捕获 `LLMError`。

### TUI

**职责：** 继续让用户选择 Provider 配置，再通过 `create_llm_client` 得到会话客户端。TUI 内部模型客户端变量使用 `client`，界面控件和用户文案中的 Provider 保持不变。

## 模块交互

1. 配置模块读取 `providers` 并生成 `ProviderConfig`。
2. TUI 让用户选择一个 `ProviderConfig`。
3. `create_llm_client` 创建协议对应的客户端。
4. TUI 把客户端交给 Agent。
5. Agent 调用 `LLMClient.stream()`。
6. 客户端产生 `LLMEvent`，StreamCollector 收集完整响应，并把正文转换成 `AgentEvent` 交给 TUI。

## 文件组织

```text
src/dragon_code/
├── clients/
│   ├── __init__.py
│   ├── base.py
│   ├── anthropic.py
│   ├── openai.py
│   └── factory.py
├── agent.py
├── models.py
├── stream_collector.py
└── tui.py

tests/
├── conftest.py
├── test_agent.py
├── test_client_anthropic.py
├── test_client_errors.py
├── test_client_openai.py
├── test_stream_collector.py
└── test_tui.py
```

旧的 `src/dragon_code/providers/` 和对应 `test_provider_*.py` 文件在迁移完成后删除，不保留兼容别名。

## 技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 外部服务配置术语 | 保留 Provider | 与 YAML 含义和用户选择场景一致 |
| 内部调用抽象 | 使用 LLM Client | 与课程 Python 源码一致，职责更明确 |
| 流式事件 | `ProviderEvent` 改为 `LLMEvent` | 事件来源是客户端，不是配置项 |
| 兼容旧导入 | 不提供 | 当前是内部学习项目，彻底统一更容易对照学习 |
| 实现方式 | 仅重命名和移动 | 避免在术语调整中改变稳定行为 |
| TUI 修改 | 精准替换客户端相关代码 | 保留现有 Provider 文案及用户新增的 `/help` 功能 |

## 自检

- spec 中 F1-F6 均有对应模块。
- 模块依赖方向为 TUI/Agent → LLMClient → SDK，无循环依赖。
- `ProviderConfig` 与 `LLMClient` 的边界明确。
- 没有引入 ch05 缓存或 System Prompt 重构。
