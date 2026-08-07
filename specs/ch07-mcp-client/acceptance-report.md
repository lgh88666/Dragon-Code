# Dragon Code ch07 MCP 客户端验收报告

验收日期：2026-08-07

## 结论

- 通过：61/61
- 未通过：0
- ch07 规定的 MCP 工具接入、权限、生命周期和 TUI 行为均已完成。

## 自动化证据

- `uv sync --locked`：成功，MCP Python SDK v2 依赖可用。
- `uv run ruff format --check .`：通过，102 个文件已格式化。
- `uv run ruff check .`：通过，无告警。
- `uv run pytest -q`：226 passed，2 skipped。
- 真实 stdio 集成测试：发现 `echo`、`project_info`，调用 `echo` 成功，关闭后生命周期任务清空。
- HTTP 传输测试：配置的 URL 与 Authorization header 原样传入 Streamable HTTP transport。
- CLI 生命周期测试：Manager 先启动再创建 TUI；TUI 正常退出或异常时均执行 `close()`。

## tmux 端到端证据

### 1. 无 MCP 配置

- Dragon Code 正常显示 Banner 并进入 TUI。
- `/help` 只显示 Read、Write、Edit、Bash、Glob、Grep 六个内置工具。
- 启动过程没有 MCP 连接异常，`/exit` 正常退出。

### 2. 真实 stdio MCP 调用

- 模型主动生成 `mcp__local_test__echo(text=dragon)`。
- TUI 显示四项权限菜单。
- 选择“允许本次”后，工具结果为 `dragon` 和结构化结果 `{"result": "dragon"}`。
- ToolResult 回灌后，模型生成了包含 `dragon` 的最终答复。

### 3. 本会话授权

- 第二次调用选择“本会话允许该 MCP 工具”。
- 第三次调用 `mcp__local_test__echo(text=session-two)` 直接执行，没有再次弹出权限菜单。

### 4. Plan Mode

- `/plan` 阶段只生成计划，没有执行 MCP 工具。
- `/do` 后恢复完整工具集，成功执行 `mcp__local_test__echo(text=plan-dragon)`。

### 5. Server 故障隔离

- 同时配置不存在的 `broken_test` 和正常的 `local_test`。
- Dragon Code 仍正常进入 TUI。
- 正常 Server 的 `echo` 成功返回 `isolation-ok`。

### 6. 退出清理

- 输入 `/exit` 后 tmux 会话结束。
- Windows 进程检查没有发现残留的 `mcp_test_server.py` 子进程。
- 验收用的临时用户级 MCP 配置已删除。

## 说明

- 兼容端点、超长结果、远端业务错误、超时、权限优先级等不适合反复消耗真实模型调用的边界，已由单元和集成测试覆盖。
- 实际 DeepSeek provider 对 MCP 工具定义、调用、ToolResult 回灌和 Agent Loop 的整条链路已在 tmux 中跑通。
