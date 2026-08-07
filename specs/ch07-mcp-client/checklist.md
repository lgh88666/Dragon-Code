# Dragon Code MCP 客户端 Checklist

> 每一项都通过运行代码或观察真实行为验证；开发完成后记录实际结果和证据。

## 实现完整性

- [x] **两层配置合并**：用户级和项目级的不同 Server 都出现在最终配置中；同名 Server 完整使用项目级对象，不残留用户级字段。（验证：运行 `uv run pytest tests/test_mcp_config.py -q` 的合并用例）(AC1/F1)
- [x] **零配置正常启动**：两层都没有 `mcp_servers` 时返回空 MCP 配置，Dragon Code 仍以六个内置工具启动。（验证：配置单测 + tmux 场景 1）(AC1/F1)
- [x] **Server 字段校验**：非法 type、stdio 缺 command、HTTP 缺 url、args/env/headers 类型错误时，只跳过对应 Server，警告包含 Server 名和原因。（验证：配置参数化单测）(AC2/F2)
- [x] **环境变量成功展开**：env 与 headers 中已定义的 `${VAR}` 被替换为宿主环境值，command、args、url 和名称不展开。（验证：配置单测使用临时环境变量并断言结果）(AC2/F3)
- [x] **缺少环境变量安全跳过**：缺失 `${VAR}` 时整个 Server 被跳过，警告指出变量名，不向 transport 传递空字符串或占位符原文。（验证：配置单测检查 servers、warnings 和 transport 未被调用）(AC2/F3/N4)
- [x] **stdio 连接**：Manager 能启动本地测试 Server、发现工具并调用 echo；关闭后子进程退出。（验证：`uv run pytest tests/test_mcp_manager.py -q -k real_stdio`）(AC3/F4/F6)
- [x] **Streamable HTTP 连接**：HTTP Client 使用配置的 URL 和 headers，工具发现与调用走 Streamable HTTP。（验证：HTTP mock endpoint 记录收到的 Authorization 测试）(AC4/F5/F6)
- [x] **新版协议入口**：代码使用 SDK v2 高层 `Client`，没有自行调用旧版 `session.initialize()` 或实现 JSON-RPC 配对。（验证：代码检索 + Manager 单测）(F6)
- [x] **旧 Server 兼容交给 SDK**：Client 的默认协商模式未被强制限定为新版，旧初始化回退路径未被 Dragon Code 禁用。（验证：Manager Client 构造测试 + SDK 兼容测试桩）(F6)
- [x] **并发启动**：多个慢 Server 的总启动时间接近最慢单个 Server，而不是各耗时相加。（验证：Manager 定时单测）(AC5/F7/N3)
- [x] **启动失败隔离**：正常、失败和超时 Server 同时配置时，正常工具仍被注册；全部失败时 Manager 正常返回空 MCP 工具列表。（验证：Manager 参数化单测）(AC5/F7/N1)
- [x] **完整分页发现**：Server 返回两页工具时，两页工具都被注册，顺序与页面顺序一致。（验证：Manager 分页单测）(F7)
- [x] **统一工具定义**：MCP 工具的名称、描述、参数 Schema 和元信息能通过现有 `ToolDefinition` 导出。（验证：`uv run pytest tests/test_mcp_tool.py -q`）(AC6/F8)
- [x] **命名空间隔离**：工具名为 `mcp__<server>__<tool>`；不同 Server 的同名工具同时存在；非法字符工具被跳过并警告。（验证：适配与 Registry 测试）(AC6/F9)
- [x] **稳定工具顺序**：Server 完成连接的顺序变化时，最终工具仍按配置顺序和远端列表顺序排列。（验证：Manager 使用不同延迟重复运行并比较定义列表）(F7/F9/N10)
- [x] **文本与 JSON 结果**：多个文本块顺序正确，`structured_content` 被格式化为可读 JSON。（验证：工具结果转换单测）(AC7/F10)
- [x] **非文本结果提示**：混合结果保留文本并提示不支持类型；只有图片/音频/资源时返回 `unsupported_content` 结构化错误。（验证：工具结果转换参数化单测）(AC7/F10)
- [x] **远端业务错误保留**：远端 `is_error` 为真时，ToolResult 为失败且仍包含远端可读文本。（验证：假 Caller 返回业务错误）(AC7/F10)
- [x] **调用超时与协议错误**：等待超时、连接断开和 SDK 异常均变成脱敏 ToolResult，不抛出到 Agent Loop。（验证：工具超时/异常单测）(AC8/F10/N2)
- [x] **结果体量控制**：超过 100,000 字符的结果被截断，设置 `truncated=True` 并带截断提示。（验证：超长结果单测）(AC15/N8)
- [x] **MCP 首次必须询问**：没有规则和会话授权时，MCP 工具在四种权限模式下均返回 Ask，read_only_hint 不绕过首次授权。（验证：PermissionEngine 参数化单测）(AC9/F11/N5)
- [x] **允许本次**：选择允许本次后当前调用执行，下一次相同 MCP 工具仍询问。（验证：Agent 审批单测）(AC9/F11)
- [x] **本会话允许**：选择本会话允许后当前调用执行，同一 Agent 后续相同工具不再询问；新 Agent 重新询问。（验证：Agent 会话授权单测）(AC9/F11)
- [x] **永久允许**：选择永久允许后保存完整 MCP 工具名，重新加载规则后相同工具直接 Allow。（验证：权限规则与 Agent 单测）(AC9/F11)
- [x] **deny 优先**：永久 deny 规则命中时不出现审批框；已有会话授权也不能覆盖 deny。（验证：PermissionEngine + Agent 单测）(F11/N5)
- [x] **Plan Mode 排除 MCP**：`/plan` 请求只包含 Read、Glob、Grep；`/do` 后完整 MCP 工具重新进入定义列表。（验证：Agent/TUI 集成测试 + tmux 场景 5）(AC10/F11)
- [x] **连接复用**：连续调用同一 Server 的两个工具时只创建一次 SDK Client和一次 stdio 子进程。（验证：Manager 连接计数测试）(AC11/F12)
- [x] **退出清理**：正常退出时 HTTP Client、MCP Client、生命周期任务和 stdio 子进程全部结束。（验证：Manager 清理测试 + tmux 场景 6）(AC12/F12/N9)
- [x] **关闭超时兜底**：一个 Server 拒绝退出时，Manager 在关闭上限后取消该任务，整体 close 返回且可重复调用。（验证：缩短关闭上限的 Manager 单测）(AC12/F12/N9)

## 集成

- [x] **Registry 统一执行**：`ToolRegistry.execute()` 能按 MCP 完整名称找到 `McpTool` 并返回 ToolResult，未知名称仍返回 `unknown_tool`。（验证：Registry 集成测试）(F8/F9)
- [x] **模型首次请求可见 MCP**：启动成功后，Default Mode 的第一次 LLMRequest 已包含发现到的 MCP 工具定义。（验证：假 LLMClient 捕获 `request.tools`）(AC6/F7/F8)
- [x] **Agent Loop 完整回灌**：模型请求 MCP 工具 → 权限确认 → 执行 → ToolResult 入历史 → 下一轮模型产生最终文本，历史调用 ID 正确配对。（验证：Agent 集成测试）(AC7/AC9)
- [x] **只读 MCP 并发**：完成首次授权后，连续 read_only_hint=True 的 MCP 调用进入并发批；未声明只读的调用仍串行。（验证：ToolScheduler 时序测试）(F8/F11)
- [x] **TUI 无需 MCP 专用分支**：MCP 调用继续显示现有工具行、成功/失败结果摘要并进入 scrollback。（验证：TUI 测试 + tmux capture-pane）(AC16)
- [x] **四项权限菜单**：方向键/Enter 与数字键 1–4 分别得到允许本次、本会话、永久允许、拒绝；默认高亮允许本次；Esc/Ctrl+C 仍取消任务。（验证：`uv run pytest tests/test_tui.py -q`）(AC9)
- [x] **CLI 装配顺序正确**：先连接并注册 MCP 工具，再启动 TUI；TUI 退出或异常时 finally 一定关闭 Manager。（验证：CLI monkeypatch 测试）(F7/F12)
- [x] **跨 LLMClient 一致**：Anthropic 与 OpenAI 的请求都从同一 Registry 获得 MCP 定义，工具调用与结果回灌不增加协议专用 MCP 逻辑。（验证：两种 Client 现有工具请求测试 + 文件 diff）(AC13/N6)
- [x] **原有能力不退化**：六工具、Agent Loop、取消、历史、提示缓存、权限与 TUI 原测试全部通过。（验证：完整 pytest）(AC14/N10)
- [x] **无配置时没有额外告警**：没有 `mcp_servers` 时启动输出不出现连接失败或异常堆栈。（验证：CLI 测试 + tmux 场景 1）(AC14)
- [x] **密钥不泄漏**：配置警告、连接错误、ToolResult、TUI、README、示例配置和测试输出中均无实际 API Key 或 Authorization 值。（验证：敏感字符串检索 + 错误场景输出检查）(AC15/N7)

## 编译与测试

- [x] `uv sync --locked` 成功，安装 MCP SDK v2。（验证：命令退出码为 0，导入 `mcp.Client` 成功）
- [x] `uv run python -m dragon_code` 在合法配置下能启动。（验证：tmux 启动后出现 Dragon Code Banner）
- [x] `uv run ruff format --check .` 通过。（验证：命令退出码为 0）
- [x] `uv run ruff check .` 无告警。（验证：命令退出码为 0）
- [x] `uv run pytest tests/test_mcp_config.py -q` 全部通过。（验证：命令退出码为 0）
- [x] `uv run pytest tests/test_mcp_tool.py -q` 全部通过。（验证：命令退出码为 0）
- [x] `uv run pytest tests/test_mcp_manager.py -q` 全部通过且无任务泄漏警告。（验证：命令退出码为 0）
- [x] `uv run pytest tests/test_permission_engine.py tests/test_permission_rules.py tests/test_agent.py tests/test_tui.py -q` 全部通过。（验证：命令退出码为 0）
- [x] `uv run pytest -q` 完整回归通过。（验证：命令退出码为 0）
- [x] Anthropic/OpenAI Client、StreamCollector、Session、Prompt 与六个内置工具实现没有为 MCP 增加专用分支。（验证：核对 git diff 文件范围）

## 端到端场景（tmux 实跑）

- [x] **场景 1：没有 MCP 配置**——移除两层 `mcp_servers` → 在 tmux 启动 Dragon Code → 正常进入 TUI → `/help` 和六个内置工具可用，启动输出无 MCP 异常。（AC1/AC14）
- [x] **场景 2：真实 stdio 工具调用**——配置 `tests/fixtures/mcp_test_server.py` → 启动后请求“调用本地 echo 工具返回 dragon” → 出现 `mcp__local_test__echo` 工具行和权限菜单 → 选择允许本次 → 工具结果回灌 → 模型最终回复包含 dragon。（AC3/AC6/AC7/AC16）
- [x] **场景 3：本会话授权**——第一次 echo 选择本会话允许 → 同一会话第二次调用 echo 不再弹窗 → 重启 Dragon Code 后再次调用重新弹窗。（AC9）
- [x] **场景 4：失败隔离**——同时配置本地测试 Server 和不存在的 stdio command → 启动警告指出故障 Server → 本地 echo 与六个内置工具仍可使用。（AC2/AC5）
- [x] **场景 5：Plan Mode**——进入 `/plan` 请求使用 echo → 模型不产生 MCP 调用 → `/do` 回到默认模式后 MCP 工具重新可调用。（AC10）
- [x] **场景 6：退出清理**——stdio Server 连接期间输入 `/exit` → Dragon Code 安全退出 → 进程检查中不存在测试 Server 子进程，终端状态正常。（AC12）
- [x] **场景 7：错误后继续会话**——让 MCP 调用返回业务错误或断开连接 → UI 显示可区分错误 → Agent 不崩溃 → 随后发送普通对话仍能获得回复。（AC7/AC8）
- [x] **场景 8：scrollback 与结果体量**——调用产生长结果的 MCP 工具 → 工具行和截断摘要进入 scrollback → 上下滚动正常，TUI 不冻结。（AC15/AC16）

## Spec 对齐检查

- [x] AC1–AC16 每一条至少对应一个以上 checklist 条目。（验证：逐项比对 spec.md 的验收标准编号）
- [x] F1–F12 均有实现检查或集成检查。（验证：逐项比对 spec.md 的功能需求编号）
- [x] 所有 checklist 条目都能通过命令输出、测试结果、TUI 行为或进程状态观察，不依赖逐行阅读实现。（验证：人工复核本文件）
