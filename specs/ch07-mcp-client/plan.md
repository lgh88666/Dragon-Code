# Dragon Code MCP 客户端 Plan

## 技术栈

- Python 3.12+
- MCP Python SDK v2：`mcp>=2,<3`
- MCP 高层客户端：`Client`
- 本地传输：`StdioServerParameters` + `stdio_client`
- 远程传输：Streamable HTTP + SDK 使用的异步 HTTP Client
- 配置：PyYAML
- 异步编排：`asyncio`
- TUI：Textual
- 测试：pytest、pytest-asyncio、tmux

## 架构概览

### MCP 配置层

新建 `dragon_code.mcp.config`，只负责读取用户级和项目级 `mcp_servers`、合并同名 Server、校验字段、展开 `${VAR}`、跳过错误 Server 并返回可读警告。现有 Provider 配置校验保持原样，避免 MCP 配置故障改变模型配置的启动行为。

### MCP 连接管理层

新建 `dragon_code.mcp.manager`，负责并发启动所有 Server、为每个 Server 创建独立连接、使用 SDK v2 `Client` 自动完成新旧协议协商、分页获取完整工具列表、缓存成功连接并在退出时统一关闭。

每个 Server 由一个独立生命周期任务持有，同一个任务负责打开和关闭连接，避免异步上下文在不同任务之间关闭造成资源泄漏。

### 工具适配层

新建 `dragon_code.mcp.tool`，把远端工具包装为现有 `Tool`。它负责命名空间、Schema 透传、只读元信息、调用转发、结果转换、超时和截断。现有 `ToolRegistry` 只负责注册这些工具，不需要理解 MCP 协议。

### 启动装配层

`cli.py` 调整为异步启动流程：

```text
加载 Provider 配置
        ↓
加载 MCP 配置
        ↓
创建六工具注册中心
        ↓
并发连接 MCP Server
        ↓
注册成功发现的 MCP 工具
        ↓
启动 DragonCodeApp
        ↓
退出 TUI 后关闭所有 MCP 连接
```

`DragonCodeApp` 接收已经装配完成的注册中心，不再自行创建固定六工具。

### 权限接入层

MCP 工具继续经过现有 `PermissionEngine`，但权限模块需要局部扩展：MCP 工具无明确规则时强制进入首次确认；新增只保存在内存中的“本会话允许”；deny 规则优先于本会话授权；永久允许保存 MCP 完整工具名；Plan Mode 仍只保留 `Read / Glob / Grep`。

### 保持不变的模块

- Anthropic LLMClient
- OpenAI LLMClient
- StreamCollector
- Conversation
- Agent Loop 主流程
- System Prompt 组装
- TUI 已有的工具事件渲染路径

## 核心数据结构

### `McpServerConfig`

```python
@dataclass
class McpServerConfig:
    name: str
    transport: Literal["stdio", "http"]

    command: str = ""
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)

    url: str = ""
    headers: dict[str, str] = field(default_factory=dict)
```

stdio 使用 `command / args / env`，HTTP 使用 `url / headers`。配置层保证返回的实例已经通过必填字段校验。

### `McpConfig`

```python
@dataclass
class McpConfig:
    servers: dict[str, McpServerConfig]
    warnings: list[str]


def load_mcp_config(
    project_config_path: Path,
    user_config_path: Path | None = None,
) -> McpConfig: ...
```

`warnings` 由 CLI 统一显示，配置层不直接控制 TUI。

### `McpCaller`

```python
class McpCaller(Protocol):
    async def call_tool(
        self,
        name: str,
        arguments: dict,
    ) -> object: ...
```

`McpTool` 只依赖这个最小接口，单元测试可以注入假 Caller 而不启动真实 Server。

### `McpTool`

```python
class McpTool(Tool):
    name: str
    remote_name: str
    server_name: str
    description: str
    input_schema: dict
    read_only: bool
    destructive: bool
    is_concurrency_safe: bool
    category = "mcp"
    caller: McpCaller

    def definition(self) -> ToolDefinition: ...

    async def execute(self, call: ToolCall) -> ToolResult: ...


def adapt_tool(
    server_name: str,
    remote_tool: object,
    caller: McpCaller,
) -> McpTool | None: ...
```

`definition()` 直接使用远端 JSON Schema；`execute()` 检查参数、限制超时、调用远端并转换结果。无法产生合法模型工具名时，`adapt_tool()` 返回 `None`。

### `_ServerRuntime`

```python
@dataclass
class _ServerRuntime:
    name: str
    tools: list[McpTool]
    stop_event: asyncio.Event
    task: asyncio.Task
```

生命周期任务内部持有 SDK `Client`。该结构不把底层流暴露给其他模块。

### `McpManager`

```python
class McpManager:
    def __init__(self, config: McpConfig): ...

    async def start(self) -> None:
        """并发连接全部 Server 并发现工具。"""

    def tools(self) -> list[McpTool]:
        """按配置顺序返回成功发现的工具。"""

    def warnings(self) -> list[str]:
        """返回配置、连接和工具适配警告。"""

    async def close(self) -> None:
        """在退出上限内关闭所有 Server。"""
```

MCP 包使用以下固定限制：

```python
CONNECT_TIMEOUT_SECONDS = 30.0
CALL_TIMEOUT_SECONDS = 30.0
CLOSE_TIMEOUT_SECONDS = 5.0
MAX_RESULT_CHARS = 100_000
```

### 权限结构扩展

```python
class ApprovalChoice(StrEnum):
    ALLOW_ONCE = "allow_once"
    ALLOW_SESSION = "allow_session"
    ALLOW_ALWAYS = "allow_always"
    DENY_ONCE = "deny_once"
```

```python
class PermissionEngine:
    session_allowed_tools: set[str]

    def allow_for_session(self, tool_name: str) -> None: ...
```

判断顺序为：黑名单与沙箱 → 永久规则 → 本会话 MCP 授权 → MCP 首次询问。因此本会话授权不能覆盖 deny 规则。

### 保持不变的公共结构

- `ToolCall`
- `ToolDefinition`
- `ToolResult`
- `AgentEvent`
- `LLMRequest`
- `ChatMessage`

## 模块设计

### `dragon_code.mcp.config`

**职责：**

- 读取用户级与项目级 `mcp_servers`；
- 按 Server 名完整覆盖合并；
- 校验 `type` 和必填字段；
- 只展开 `env` 与 `headers` 中的 `${VAR}`；
- 缺变量或配置非法时跳过单个 Server；
- 收集脱敏警告。

**依赖：** Python 标准库、PyYAML；不依赖 Agent、ToolRegistry 或 MCP SDK。

### `dragon_code.mcp.tool`

**职责：**

- 转换远端工具定义；
- 构造 `mcp__server__tool`；
- 透传参数 Schema；
- 解析 `read_only_hint`；
- 调用远端工具；
- 转换文本、结构化 JSON、远端错误和不支持内容；
- 对最终结果执行字符上限截断。

**结果规则：**

- 多个文本块按远端顺序拼接；
- `structured_content` 格式化成可读 JSON，追加在文本后；
- 混合结果中的图片、音频和资源链接转为明确提示；
- 只有不支持内容时返回 `unsupported_content`；
- `is_error` 为真时保留远端文本并返回失败结果；
- SDK 异常和超时只返回脱敏错误。

**依赖：** 现有 Tool 模型和 MCP SDK 类型；不依赖 Agent 和 TUI。

### `dragon_code.mcp.manager`

**职责：**

- 创建 stdio 或 Streamable HTTP Client；
- 并发启动 Server；
- 依靠 SDK v2 自动协商新旧协议；
- 分页拉取全部工具；
- 调用适配层；
- 缓存成功连接；
- 记录独立失败；
- 统一关闭。

stdio 使用 `StdioServerParameters` 和 `stdio_client`，只传入配置声明的环境变量。HTTP 使用带 headers 的异步 HTTP Client，再交给 `streamable_http_client`。两种 Client 都由对应 Server 的生命周期任务持有。

虽然 Server 并发连接，最终工具顺序仍按配置顺序和远端工具顺序排列。

### `dragon_code.permissions`

**职责扩展：**

- 允许合法的 `mcp__server__tool` 规则名；
- 永久允许保存完整 MCP 工具名；
- 保存仅当前会话有效的工具名集合；
- MCP 工具无规则、无会话授权时返回 Ask；
- deny 规则在会话授权之前判断；
- 黑名单和文件沙箱继续只处理原有适用工具。

### `dragon_code.agent`

只增加 `ALLOW_SESSION` 处理：通知 PermissionEngine 保存工具名并继续当前调用。Agent Loop、结果回灌、取消和批处理逻辑保持不变。

### `dragon_code.tools.registry`

继续保存内置与 MCP 工具，不增加协议判断。注册顺序为六个内置工具，然后是配置顺序中的 MCP 工具。重复名称由 Manager 提前跳过并告警。

### `dragon_code.cli`

**职责扩展：**

- 严格加载 Provider 配置；
- 宽容加载 MCP 配置；
- 创建默认注册中心；
- 启动 MCP Manager；
- 注册发现的工具；
- 输出脱敏警告；
- 把注册中心注入 TUI；
- 在 `finally` 中关闭 Manager。

同步 `main()` 只负责调用异步入口，确保连接创建、使用和关闭位于同一个事件循环。

### `dragon_code.tui`

**职责扩展：**

- 构造时接收已经装配完成的 `ToolRegistry`；
- 激活 Provider 时把同一注册中心交给 Agent；
- 权限菜单扩展为允许本次、本会话允许、永久允许、拒绝本次；
- `/help` 更新权限说明；
- 继续复用现有工具行和结果行，不新增 MCP 专用 UI。

### LLMClient 与提示系统

Anthropic、OpenAI、StreamCollector 和 Prompt 模块不修改。MCP 工具注册后自然通过 `ToolRegistry.definitions()` 进入 Agent 构造的 `LLMRequest`。

## 模块交互

### 启动流程

```text
1. CLI 读取项目 Provider 配置
2. CLI 读取用户级、项目级 MCP 配置
3. 创建包含六个内置工具的 ToolRegistry
4. McpManager 并发启动所有 Server
5. 每个 Server 创建传输、进入 Client、协商协议、分页列工具并适配
6. Manager 按配置顺序汇总成功工具
7. CLI 把 MCP 工具注册进 ToolRegistry
8. CLI 把完整 ToolRegistry 交给 TUI
9. TUI 选择 LLMClient 后创建 Agent
```

### 工具调用流程

```text
模型返回 ToolCall
      ↓
Agent 交给 ToolScheduler
      ↓
PermissionEngine 检查权限
      ↓
允许后调用 ToolRegistry.execute()
      ↓
找到对应 McpTool
      ↓
McpTool 调用所属 Server 的 SDK Client
      ↓
转换为 Dragon Code ToolResult
      ↓
Agent 产生 tool_end 事件
      ↓
TUI 显示结果摘要
      ↓
ToolResult 写入历史并回灌模型
```

### 首次权限流程

```text
MCP 工具调用
      ↓
永久 deny / allow 是否命中？
      ├─ deny  → 结构化拒绝
      ├─ allow → 直接执行
      └─ 未命中
           ↓
本会话是否允许该工具？
      ├─ 是 → 直接执行
      └─ 否 → TUI 四选一确认
```

### 并发与顺序

`McpTool.is_concurrency_safe` 由远端 `read_only_hint` 决定。连续只读 MCP 调用可进入并发批，未声明只读的调用串行执行；权限确认与最终结果都保持模型原始顺序。

### Plan Mode

Plan Mode 从完整 Registry 取固定 `Read / Glob / Grep` 子集，因此 MCP 工具不会发送给模型。`/do` 后 Agent 恢复完整 Registry。

### 失败流程

远端异常、超时或断开由 `McpTool` 脱敏并转换为失败 `ToolResult`，回灌模型后 Agent Loop 继续。本章不自动重连。

### 退出流程

TUI 退出后，CLI 的 `finally` 通知所有 Server 生命周期任务停止。每个任务在自身内部退出 SDK Client 上下文并关闭 HTTP Client、stdio 管道和子进程；超过整体关闭上限后取消剩余任务。

## 文件组织

```text
dragonAgent/
├── pyproject.toml
├── README.md
├── .dragon-code/
│   └── config.yaml.example
├── src/
│   └── dragon_code/
│       ├── mcp/
│       │   ├── __init__.py
│       │   ├── config.py
│       │   ├── manager.py
│       │   └── tool.py
│       ├── permissions/
│       │   ├── engine.py
│       │   ├── models.py
│       │   └── rules.py
│       ├── agent.py
│       ├── cli.py
│       └── tui.py
├── tests/
│   ├── fixtures/
│   │   └── mcp_test_server.py
│   ├── test_mcp_config.py
│   ├── test_mcp_tool.py
│   ├── test_mcp_manager.py
│   ├── test_permission_engine.py
│   ├── test_permission_rules.py
│   ├── test_agent.py
│   └── test_tui.py
└── specs/
    └── ch07-mcp-client/
        ├── spec.md
        ├── plan.md
        ├── task.md
        └── checklist.md
```

### 新建文件

| 文件 | 职责 |
|---|---|
| `src/dragon_code/mcp/__init__.py` | 暴露 MCP 配置、Manager 和 Tool 公共入口 |
| `src/dragon_code/mcp/config.py` | 两层配置加载、合并、校验和环境变量展开 |
| `src/dragon_code/mcp/tool.py` | 工具定义适配、调用和结果转换 |
| `src/dragon_code/mcp/manager.py` | 多 Server 并发连接、发现、缓存和关闭 |
| `tests/test_mcp_config.py` | 配置合并、校验、变量展开和错误隔离 |
| `tests/test_mcp_tool.py` | 命名、Schema、结果、超时和错误测试 |
| `tests/test_mcp_manager.py` | 连接、分页、失败隔离和退出测试 |
| `tests/fixtures/mcp_test_server.py` | tmux 验收使用的真实本地 stdio MCP Server |

### 修改文件

| 文件 | 改动 |
|---|---|
| `pyproject.toml` | 添加 MCP Python SDK v2 依赖 |
| `.dragon-code/config.yaml.example` | 增加 stdio 与 Streamable HTTP 配置示例 |
| `README.md` | 补充 MCP 配置、权限与启动行为说明 |
| `src/dragon_code/permissions/models.py` | 增加“本会话允许” |
| `src/dragon_code/permissions/engine.py` | MCP 首次询问和会话授权 |
| `src/dragon_code/permissions/rules.py` | MCP 工具规则与永久保存 |
| `src/dragon_code/agent.py` | 处理“本会话允许” |
| `src/dragon_code/cli.py` | 异步装配与退出清理 |
| `src/dragon_code/tui.py` | Registry 注入和四项权限菜单 |
| `tests/test_permission_engine.py` | MCP 权限顺序测试 |
| `tests/test_permission_rules.py` | MCP 规则测试 |
| `tests/test_agent.py` | 会话授权测试 |
| `tests/test_tui.py` | 菜单与 Registry 注入测试 |

### 明确不修改

- `src/dragon_code/clients/anthropic.py`
- `src/dragon_code/clients/openai.py`
- `src/dragon_code/stream_collector.py`
- `src/dragon_code/session.py`
- `src/dragon_code/prompt.py`
- 六个内置工具实现

## 技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| MCP SDK | `mcp>=2,<3` | v2 支持当前协议并兼容旧协议 |
| SDK 层级 | 高层 `Client` | 不自行维护 Session 与握手 |
| 协议兼容 | SDK 自动探测 | 新协议发现失败时回退旧初始化 |
| HTTP headers | 自建异步 HTTP Client | SDK v2 的 headers 属于 HTTP Client 配置 |
| stdio 环境 | 只传显式变量 | 避免泄漏宿主全部环境 |
| 配置加载 | MCP 与 Provider 分离 | MCP 可降级，Provider 继续严格校验 |
| 缺少变量 | 跳过 Server | 不发送空凭据或原始占位符 |
| 连接时机 | TUI 前完成 | 首次模型请求即可看到稳定工具集 |
| 并发连接 | 每个 Server 一个生命周期任务 | 并发启动并在原任务内关闭上下文 |
| 工具列表 | 完整处理分页 | 不遗漏后续页面工具 |
| 工具顺序 | 配置顺序 + 远端顺序 | 稳定请求前缀和测试结果 |
| 参数 Schema | 直接透传 | 避免运行时创建 Pydantic 类型 |
| 工具命名 | `mcp__server__tool` | 隔离冲突并保留来源 |
| 只读标记 | 只影响并发 | 不信任外部声明绕过首次授权 |
| 默认权限 | 无授权时始终 Ask | 所有模式均保留首次确认 |
| 会话授权 | 内存工具名集合 | 关闭应用后自然清空 |
| 永久授权 | 保存完整工具名 | 对任意 MCP Schema 保持简单稳定 |
| Plan Mode | 固定内置只读子集 | 自然排除 MCP 工具 |
| 结果 | 文本、JSON、类型提示 | 保留模型可利用信息并明确边界 |
| 结果上限 | 100,000 字符 | 与现有 Read/Bash 量级一致 |
| 调用失败 | 结构化 ToolResult | Agent Loop 可继续调整 |
| 自动重连 | 不实现 | 避免连接状态机和重复调用风险 |
| 测试 | 假 Client 单测 + 本地真实 stdio Server E2E | 稳定覆盖边界并验证真实链路 |

## Spec 覆盖检查

| Spec | 架构归属 |
|---|---|
| F1–F3 | `mcp.config` |
| F4–F7 | `mcp.manager` |
| F8–F10 | `mcp.tool` + `ToolRegistry` |
| F11 | `permissions` + `agent` + `tui` |
| F12 | `mcp.manager` + `cli` |

所有功能需求均有明确模块归属；依赖方向为 `mcp.config → mcp.manager → mcp.tool → tools/models`，Agent 与 TUI 只依赖现有 Tool 抽象，不形成循环依赖。
