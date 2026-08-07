# Dragon Code MCP 客户端 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|---|---|---|
| 修改 | `pyproject.toml` | 添加 MCP Python SDK v2 依赖 |
| 修改 | `uv.lock` | 锁定新增依赖 |
| 新建 | `src/dragon_code/mcp/__init__.py` | 暴露 MCP 公共入口 |
| 新建 | `src/dragon_code/mcp/config.py` | MCP 配置加载、合并、校验与变量展开 |
| 新建 | `src/dragon_code/mcp/tool.py` | MCP 工具适配、调用和结果转换 |
| 新建 | `src/dragon_code/mcp/manager.py` | 多 Server 连接、发现、缓存和关闭 |
| 修改 | `src/dragon_code/permissions/models.py` | 增加本会话授权选择 |
| 修改 | `src/dragon_code/permissions/engine.py` | MCP 首次询问和会话授权 |
| 修改 | `src/dragon_code/permissions/rules.py` | MCP 工具规则解析、匹配和保存 |
| 修改 | `src/dragon_code/agent.py` | 处理本会话授权选择 |
| 修改 | `src/dragon_code/cli.py` | 异步装配 MCP Manager、Registry 和 TUI |
| 修改 | `src/dragon_code/tui.py` | 注入 Registry，扩展权限菜单和帮助 |
| 修改 | `.dragon-code/config.yaml.example` | 增加 stdio 与 HTTP 配置示例 |
| 修改 | `README.md` | 补充 MCP 使用说明 |
| 新建 | `tests/fixtures/mcp_test_server.py` | 真实本地 stdio MCP 测试 Server |
| 新建 | `tests/test_mcp_config.py` | MCP 配置单元测试 |
| 新建 | `tests/test_mcp_tool.py` | MCP 工具适配单元测试 |
| 新建 | `tests/test_mcp_manager.py` | MCP Manager 单元与本地集成测试 |
| 修改 | `tests/test_permission_engine.py` | MCP 权限顺序测试 |
| 修改 | `tests/test_permission_rules.py` | MCP 规则测试 |
| 修改 | `tests/test_agent.py` | 会话授权测试 |
| 修改 | `tests/test_tui.py` | Registry 注入和四项菜单测试 |

## T1：添加并验证 MCP SDK v2

**文件：** `pyproject.toml`、`uv.lock`

**依赖：** 无

**步骤：**

1. 在项目依赖中添加 `mcp>=2,<3`。
2. 使用 uv 更新锁文件和本地虚拟环境。
3. 在 Python 中导入 `Client`、`StdioServerParameters`、`stdio_client` 和 `streamable_http_client`。
4. 确认安装的是 2.x，而不是教材使用的 1.x。

**验证：** 运行 `uv run python -c "from mcp import Client, StdioServerParameters; from mcp.client.stdio import stdio_client; from mcp.client.streamable_http import streamable_http_client; print('mcp v2 imports ok')"`，期望输出 `mcp v2 imports ok`。

## T2：定义 MCP 配置模型与基础文件读取

**文件：** `src/dragon_code/mcp/config.py`、`src/dragon_code/mcp/__init__.py`

**依赖：** T1

**步骤：**

1. 定义 `McpServerConfig`，包含名称、传输类型以及 stdio/HTTP 对应字段。
2. 定义 `McpConfig`，包含有序 Server 字典和警告列表。
3. 实现单个 YAML 文件的安全读取，只取根节点中的 `mcp_servers`。
4. 文件不存在时返回空配置；用户级文件无法读取或 YAML 非法时记录脱敏警告。
5. 在 `mcp/__init__.py` 暴露配置类型和加载入口。

**验证：** 运行 `uv run python -c "from dragon_code.mcp import McpConfig, McpServerConfig, load_mcp_config; print('ok')"`，期望输出 `ok`。

## T3：实现两层合并、校验与变量展开

**文件：** `src/dragon_code/mcp/config.py`

**依赖：** T2

**步骤：**

1. 读取用户级 `~/.dragon-code/config.yaml` 和传入的项目级配置路径。
2. 先加入用户级 Server，再用项目级同名 Server 完整覆盖。
3. 校验 `type` 只能是 `stdio` 或 `http`。
4. 校验 stdio 的 `command/args/env` 与 HTTP 的 `url/headers` 类型。
5. 只展开 `env` 和 `headers` 值中的 `${VAR}`。
6. 任一引用变量不存在时跳过该 Server，并在警告中包含 Server 名与变量名。
7. 保持 Server 的合并顺序稳定，不展开命令、参数、URL 和名称。

**验证：** 运行一个临时配置脚本，期望项目级同名 Server 胜出、合法变量完成展开、缺变量 Server 被跳过且产生警告。

## T4：补齐 MCP 配置测试

**文件：** `tests/test_mcp_config.py`

**依赖：** T3

**步骤：**

1. 测试两层文件都缺失时返回空 MCP 配置。
2. 测试仅用户级、仅项目级和两层合并。
3. 测试项目级同名配置完整覆盖而不是字段级混合。
4. 测试 stdio 与 HTTP 的合法字段。
5. 测试非法类型、缺必填字段和错误字段类型只跳过对应 Server。
6. 测试 `${VAR}` 成功展开和缺变量跳过。
7. 测试 command、args、url 中的占位文本不被展开。
8. 断言所有警告不包含已展开的敏感值。

**验证：** 运行 `uv run pytest tests/test_mcp_config.py -q`，期望全部通过。

## T5：实现 MCP 工具定义适配

**文件：** `src/dragon_code/mcp/tool.py`

**依赖：** T1

**步骤：**

1. 定义 `McpCaller` 最小协议。
2. 定义 `McpTool`，保存完整名称、远端名称、Server 名、Schema、描述和 Caller。
3. 实现 `adapt_tool()`，构造 `mcp__server__tool`。
4. 只允许模型 API 接受的字母、数字、下划线和连字符。
5. 描述缺失时生成包含 Server 与工具名的兜底描述。
6. Schema 缺失时使用空对象 Schema。
7. 只有远端 `read_only_hint` 明确为真时，才标记只读和并发安全。
8. 覆盖 `definition()`，直接返回远端 Schema，不创建动态 Pydantic 模型。

**验证：** 运行一个最小假远端工具适配脚本，期望名称、描述、Schema 和只读元信息正确。

## T6：实现 MCP 结果转换

**文件：** `src/dragon_code/mcp/tool.py`

**依赖：** T5

**步骤：**

1. 按顺序收集所有文本内容块。
2. 将 `structured_content` 用稳定缩进和中文友好的 JSON 格式化后追加。
3. 将图片、音频、资源链接和嵌入资源转换为“不支持该内容类型”的提示。
4. 混合结果保留可用文本；只有不支持内容时返回 `unsupported_content`。
5. 将远端 `is_error` 映射成失败 `ToolResult`，同时保留远端可读内容。
6. 聚合完成后限制为 100,000 字符，超出时设置 `truncated=True` 并添加截断标记。

**验证：** 用假结果分别覆盖文本、JSON、混合内容、仅非文本、远端错误和超长结果，期望转换结果符合 plan.md。

## T7：实现 MCP 调用超时与脱敏错误

**文件：** `src/dragon_code/mcp/tool.py`

**依赖：** T6

**步骤：**

1. `execute()` 拒绝缺失或无效的参数对象。
2. 使用固定 30 秒上限调用 `caller.call_tool()`。
3. 保留 `CancelledError`，让 Agent 的取消链路继续工作。
4. 将超时转换为 `timeout` 失败结果。
5. 将连接、协议和未知异常转换为不包含原始 headers、环境变量或堆栈的 `mcp_error`。
6. 确保所有结果使用原始 ToolCall ID 和完整 MCP 工具名。

**验证：** 注入立即成功、抛异常和持续等待的假 Caller，期望成功、脱敏错误和超时结果正确。

## T8：补齐 MCP 工具适配测试

**文件：** `tests/test_mcp_tool.py`

**依赖：** T5、T6、T7

**步骤：**

1. 测试合法命名和非法字符跳过。
2. 测试描述与 Schema 兜底。
3. 测试只读标记缺失、假和真三种情况。
4. 测试文本块顺序和结构化 JSON。
5. 测试混合非文本与仅非文本结果。
6. 测试远端业务错误、调用异常和超时。
7. 测试 100,000 字符截断。
8. 测试取消异常继续向上传递。

**验证：** 运行 `uv run pytest tests/test_mcp_tool.py -q`，期望全部通过。

## T9：实现 stdio 与 HTTP Client 构造

**文件：** `src/dragon_code/mcp/manager.py`

**依赖：** T1、T3

**步骤：**

1. 为 stdio 配置构造 `StdioServerParameters` 和 `stdio_client` transport。
2. 只把配置中的 env 传给 stdio 参数，不复制宿主完整环境。
3. 为 HTTP 配置创建带 headers、重定向和合理超时的异步 HTTP Client。
4. 把 HTTP Client 交给 `streamable_http_client` transport。
5. 两种 transport 最终都交给 SDK v2 `Client`。
6. 将 transport 构造封装为可被测试替换的私有入口。

**验证：** 通过 monkeypatch 捕获构造参数，确认 stdio command/args/env 与 HTTP url/headers 正确传入。

## T10：实现单 Server 生命周期与分页发现

**文件：** `src/dragon_code/mcp/manager.py`

**依赖：** T5、T9

**步骤：**

1. 为每个 Server 创建独立生命周期任务、停止事件和就绪结果。
2. 在该任务内部进入 HTTP Client、transport 和 MCP `Client` 上下文。
3. 进入 Client 后循环调用工具列表接口，直到没有下一页。
4. 逐个调用 `adapt_tool()`，跳过非法工具并记录警告。
5. 同一 Server 返回重复完整名称时只保留第一项并警告。
6. 就绪后保持连接，等待 Manager 的停止事件。
7. 连接或发现失败时在原任务内退出已进入的上下文。

**验证：** 使用分页假 Client 返回两页工具，期望全部工具按页内顺序被发现，任务收到停止事件后退出。

## T11：实现多 Server 并发启动与稳定汇总

**文件：** `src/dragon_code/mcp/manager.py`

**依赖：** T10

**步骤：**

1. 定义 `McpManager` 的配置、运行时、工具和警告状态。
2. 按配置顺序为每个 Server 启动生命周期任务。
3. 并发等待各 Server 在 30 秒内就绪。
4. 单个失败或超时只记录该 Server 的脱敏警告并清理其任务。
5. 成功工具按配置顺序汇总，不能按连接完成顺序排列。
6. 提供 `tools()` 和 `warnings()` 的拷贝，防止调用方修改内部状态。

**验证：** 用快成功、慢成功、失败三个假 Server，期望总耗时体现并发，工具顺序仍按配置，失败只产生一条警告。

## T12：实现 Manager 关闭兜底

**文件：** `src/dragon_code/mcp/manager.py`

**依赖：** T11

**步骤：**

1. `close()` 向所有成功 Server 设置停止事件。
2. 并发等待生命周期任务自行退出 SDK 上下文。
3. 整体等待超过 5 秒后取消剩余任务。
4. 等待取消完成，避免留下未回收任务。
5. `close()` 可重复调用且不会再次关闭已经结束的连接。

**验证：** 使用正常退出和故意卡住的假生命周期任务，期望正常任务被关闭，卡住任务在测试缩短的上限后取消，第二次 close 不报错。

## T13：补齐 Manager 测试

**文件：** `tests/test_mcp_manager.py`

**依赖：** T10、T11、T12

**步骤：**

1. 测试 stdio 和 HTTP 构造参数。
2. 测试 SDK Client 进入后不手工调用旧版 initialize。
3. 测试多页工具发现和命名适配。
4. 测试并发连接与配置顺序汇总。
5. 测试单 Server 连接失败、发现失败和超时隔离。
6. 测试所有 Server 失败时工具列表为空但 start 正常返回。
7. 测试正常关闭、关闭超时、取消和重复关闭。
8. 检查测试结束后没有未完成生命周期任务。

**验证：** 运行 `uv run pytest tests/test_mcp_manager.py -q`，期望全部通过且无 asyncio 任务泄漏警告。

## T14：扩展 MCP 权限规则

**文件：** `src/dragon_code/permissions/rules.py`、`tests/test_permission_rules.py`

**依赖：** 无

**步骤：**

1. 保留六个内置工具现有规则校验。
2. 额外接受符合命名规范的完整 MCP 工具名。
3. MCP 无参数规则按完整工具名匹配。
4. 为 MCP ToolCall 生成永久 allow 时返回完整工具名。
5. 拒绝包含非法字符或缺少 Server/工具部分的 MCP 规则。
6. 增加解析、匹配、保存与重新加载测试。

**验证：** 运行 `uv run pytest tests/test_permission_rules.py -q`，期望原测试和 MCP 新测试全部通过。

## T15：实现 MCP 首次询问与会话授权

**文件：** `src/dragon_code/permissions/engine.py`、`tests/test_permission_engine.py`

**依赖：** T14

**步骤：**

1. 在 PermissionEngine 中初始化会话允许工具名集合。
2. 提供只接受合法 MCP 完整名称的 `allow_for_session()`。
3. 保持黑名单、沙箱和永久规则在会话授权之前判断。
4. 无永久规则时，已获会话授权的 MCP 工具返回 Allow。
5. 未获授权的 MCP 工具无论当前权限模式为何都返回 Ask。
6. MCP 的只读标记不改变首次 Ask。
7. 增加 deny 优先、永久 allow、会话 allow、首次 Ask 和四模式测试。

**验证：** 运行 `uv run pytest tests/test_permission_engine.py -q`，期望原测试和 MCP 权限测试全部通过。

## T16：接入 Agent 的本会话授权选择

**文件：** `src/dragon_code/permissions/models.py`、`src/dragon_code/agent.py`、`tests/test_agent.py`

**依赖：** T15

**步骤：**

1. 在 `ApprovalChoice` 增加 `ALLOW_SESSION`。
2. Agent 收到该选择后，把当前 MCP 工具名写入 PermissionEngine 会话集合。
3. 当前调用继续执行，不写入本地 YAML。
4. 同一 Agent 后续调用相同 MCP 工具不再产生权限请求。
5. 新 Agent 使用新 PermissionEngine，不继承旧会话授权。
6. deny 规则场景不得出现审批框或被会话授权覆盖。

**验证：** 运行 `uv run pytest tests/test_agent.py -q`，期望会话授权、永久授权、拒绝和取消测试全部通过。

## T17：让 TUI 接收完整 Registry

**文件：** `src/dragon_code/tui.py`、`tests/test_tui.py`

**依赖：** 无

**步骤：**

1. `DragonCodeApp` 构造时接收 `ToolRegistry`。
2. 保存该实例，不在 `_activate_provider()` 中重新创建默认六工具。
3. 创建 Agent 时注入相同 Registry。
4. 更新 TUI 测试的构造辅助函数，明确传入测试 Registry。
5. 增加包含假 MCP 工具的 Registry 注入测试。

**验证：** 运行相关 TUI 测试，确认 Agent Registry 中包含传入的假 MCP 工具，且不会被默认 Registry 覆盖。

## T18：扩展四项权限菜单与帮助

**文件：** `src/dragon_code/tui.py`、`tests/test_tui.py`

**依赖：** T16、T17

**步骤：**

1. 权限 Modal 增加“本会话允许”选项。
2. 数字键改为 1 允许本次、2 本会话、3 永久允许、4 拒绝。
3. 方向键与 Enter 按四项列表映射正确选择。
4. Esc 和 Ctrl+C 继续取消整个任务。
5. `/help` 更新四项权限说明，并说明 Default Mode 可包含 MCP 工具。
6. 增加四个数字键、列表选择、默认高亮和取消测试。

**验证：** 运行 `uv run pytest tests/test_tui.py -q`，期望全部通过。

## T19：实现 CLI 异步装配与统一清理

**文件：** `src/dragon_code/cli.py`

**依赖：** T4、T11、T12、T17

**步骤：**

1. 保留同步 `main()` 和现有 ConfigError 可读退出行为。
2. 新增异步启动入口，创建默认 Registry 和 McpManager。
3. 打印配置与连接警告，但不得打印 env/header 的值。
4. 启动 Manager 后把所有 MCP 工具注册进 Registry。
5. 创建 `DragonCodeApp(config, registry)` 并使用 Textual 异步运行入口。
6. 用 `try/finally` 保证 TUI 退出或异常时都调用 Manager.close()。
7. 没有 MCP 配置或所有 Server 失败时仍使用六工具 Registry 启动。

**验证：** 用 monkeypatch 替换 Manager 与 App，断言启动顺序、Registry 注入、警告输出和 finally 清理均正确。

## T20：添加真实本地 stdio MCP Server

**文件：** `tests/fixtures/mcp_test_server.py`

**依赖：** T1

**步骤：**

1. 使用 MCP SDK v2 创建可通过 stdio 运行的测试 Server。
2. 提供一个只读 `echo` 工具，返回输入文本。
3. 提供一个结构化 JSON 工具，返回固定对象。
4. 工具描述和参数类型写清楚，方便真实模型选择。
5. 文件直接运行时以 stdio transport 启动，不读取真实密钥或网络。

**验证：** 使用官方 Client 通过 stdio 连接该脚本，列出工具并调用 `echo`，期望收到原始输入。

## T21：增加真实 stdio Manager 集成测试

**文件：** `tests/test_mcp_manager.py`、`tests/fixtures/mcp_test_server.py`

**依赖：** T13、T20

**步骤：**

1. 用当前 Python 解释器配置测试 Server 的 stdio command/args。
2. 通过真实 Manager 启动、发现工具并检查完整名称。
3. 调用适配后的 echo 工具并检查 ToolResult。
4. 关闭 Manager 后确认生命周期任务结束。
5. 在 Windows 上不依赖 Bash、Node 或外部网络。

**验证：** 运行 `uv run pytest tests/test_mcp_manager.py -q -k real_stdio`，期望真实 stdio 场景通过。

## T22：更新配置示例与 README

**文件：** `.dragon-code/config.yaml.example`、`README.md`

**依赖：** T3、T19、T20

**步骤：**

1. 在示例配置加入一个 stdio Server 和一个 Streamable HTTP Server。
2. env 与 headers 只使用 `${VAR}`，不写真实凭据。
3. README 说明用户级与项目级合并和完整覆盖语义。
4. README 说明 `mcp__server__tool`、首次权限确认和四项选择。
5. README 删除“当前不包含 MCP”的旧描述。
6. README 说明缺变量、Server 失败和 Plan Mode 的行为。
7. README 给出真实本地测试 Server 的启动配置示例。

**验证：** 运行敏感字符串检索，期望示例与 README 不包含真实 Token；人工对照配置模型确认字段名称一致。

## T23：执行格式化、静态检查和完整回归

**文件：** 所有本章修改文件

**依赖：** T8、T13、T16、T18、T19、T21、T22

**步骤：**

1. 对项目执行 Ruff 格式化。
2. 执行 Ruff lint 并修复所有新增告警。
3. 运行完整 pytest。
4. 运行配置、工具、权限、Agent、TUI 的重点测试。
5. 检查 Anthropic/OpenAI Client、StreamCollector、Session 和 Prompt 文件没有被修改。
6. 检查未提交内容中不存在 API Key、Authorization 值和测试秘密。

**验证：** `uv run ruff format --check .`、`uv run ruff check .`、`uv run pytest -q` 全部通过。

## T24：执行 tmux 真实对话验收

**文件：** `specs/ch07-mcp-client/checklist.md`（验收阶段更新勾选和证据）

**依赖：** T23、已批准的 checklist.md

**步骤：**

1. 在 WSL/tmux 中使用真实 Provider 配置和本地 stdio MCP Server 启动 Dragon Code。
2. 输入要求模型调用 `mcp__local_test__echo` 的真实对话请求。
3. 观察模型收到 MCP 工具定义并发起调用。
4. 选择“允许本次”，观察工具结果回灌和模型最终答复。
5. 再次调用并验证“本会话允许”与后续免询问。
6. 进入 `/plan`，确认模型看不到 MCP 工具；`/do` 后恢复。
7. 配置一个无效 Server，确认失败隔离且内置工具仍可用。
8. 退出 Dragon Code，确认 tmux 中无残留测试 Server 进程。
9. 对照 checklist.md 逐项记录实际证据。

**验证：** tmux capture-pane 中可观察到用户请求、MCP 工具行、权限选择、结果摘要和最终回复；退出后进程检查无残留。

## 执行顺序

```text
T1
├─→ T2 → T3 → T4 ───────────────────────────┐
├─→ T5 → T6 → T7 → T8 ────────────────┐     │
├─→ T9 → T10 → T11 → T12 → T13 ───────┼─→ T19
└─→ T20 ───────────────────────→ T21 ──┘     │
                                              │
T14 → T15 → T16 ────────────────┐             │
                                ├─→ T18       │
T17 ────────────────────────────┘             │
                                              │
T3 + T19 + T20 → T22                          │
                                              │
T8 + T13 + T16 + T18 + T19 + T21 + T22 → T23
                                              ↓
                                            T24
```

T14–T18 可与 MCP 配置、工具和 Manager 的实现并行；开发时仍按任务依赖验证后再合并。
