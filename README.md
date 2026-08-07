# Dragon Code

Dragon Code 是一个使用 Python 构建的、Claude Code 风格终端 AI 编程助手。

当前已完成 ch02–ch07 的核心能力：

- Anthropic 与 OpenAI Chat Completions 两种协议
- OpenAI 兼容端点
- 多 Provider 启动选择
- 流式回复、等待动画和响应计时
- 单会话多轮上下文
- 完整 Textual TUI 与 Markdown 定型
- 可恢复、经过脱敏的错误提示
- Read、Write、Edit、Bash、Glob、Grep 六个工具
- 能持续调用工具直到任务完成的 ReAct Agent Loop
- `/plan` 与 `/do` 两段式 Plan Mode
- 模块化 System Prompt、system-reminder 与提示缓存统计
- 黑名单、路径沙箱、三级规则、权限模式和 HITL 五层权限系统
- stdio 与 Streamable HTTP 两种 MCP 传输
- 启动期 MCP 工具自动发现、命名隔离和连接复用

当前仍不包含 MCP Resources/Prompts、自动重连、网络访问限制、资源配额和审计日志。

## 环境要求

- Python 3.12+
- [uv](https://docs.astral.sh/uv/)
- 最终端到端验收使用 WSL/Linux 与 tmux

## 安装

在项目根目录执行：

```bash
uv sync --locked
```

## 配置

复制配置示例：

```bash
cp .dragon-code/config.yaml.example .dragon-code/config.yaml
```

Windows PowerShell 可使用：

```powershell
Copy-Item .dragon-code/config.yaml.example .dragon-code/config.yaml
```

然后编辑 `.dragon-code/config.yaml`，至少保留一个 Provider 并填写真实 API Key：

```yaml
providers:
  - name: "Anthropic"
    protocol: "anthropic"
    api_key: "你的 API Key"
    model: "你的模型名称"
    thinking: true
```

OpenAI 或兼容端点示例：

```yaml
providers:
  - name: "OpenAI Compatible"
    protocol: "openai"
    api_key: "你的 API Key"
    model: "你的模型名称"
    base_url: "https://你的服务地址/v1"
```

`.dragon-code/config.yaml` 已被 Git 忽略。不要把真实 API Key 写入示例文件、README 或提交记录。

## MCP 配置

MCP Server 写在 `mcp_servers` 中。Dragon Code 会合并用户级
`~/.dragon-code/config.yaml` 与项目级 `.dragon-code/config.yaml`，项目级同名 Server
完整覆盖用户级配置。

本地 stdio Server 示例：

```yaml
mcp_servers:
  local_test:
    type: stdio
    command: uv
    args: [run, python, tests/fixtures/mcp_test_server.py]
```

远程 Streamable HTTP Server 示例：

```yaml
mcp_servers:
  remote_demo:
    type: http
    url: https://example.com/mcp
    headers:
      Authorization: "Bearer ${MCP_HTTP_TOKEN}"
```

只有 `env` 和 `headers` 的值支持 `${VAR}`。变量不存在时只跳过对应 Server，并显示
不包含凭据的警告。单个 Server 连接失败不会影响其他 MCP Server 和六个内置工具。

成功发现的工具以 `mcp__服务名__工具名` 注册。首次调用 MCP 工具时可以选择：允许本次、
本会话允许、永久允许或拒绝。Plan Mode 不会向模型提供 MCP 工具，执行 `/do` 后恢复。

## 运行

```bash
uv run dragon-code
```

也可以使用模块入口：

```bash
uv run python -m dragon_code
```

## 操作

- Enter：提交消息
- Alt+Enter：在输入框中换行
- `/help`：显示帮助
- `/exit`：退出
- `/plan`：进入只读计划模式
- `/do`：执行已经完成的计划
- Shift+Tab：循环切换四种权限模式
- Esc：取消当前 Agent 任务
- Ctrl+C：有选中文字时复制；任务中取消；空闲时退出

等待模型时会显示 `Imagining… (Ns)`；回复流式结束后会重新渲染为 Markdown。

## 权限系统

工具执行前依次经过：危险命令黑名单 → 项目路径沙箱 → 权限规则 → 当前模式 → 用户确认。黑名单不可配置关闭；任何模式都不能绕过黑名单和路径沙箱。

四种模式：

- `default`：只读工具自动允许，写文件和 Bash 需要确认。
- `acceptEdits`：读写文件自动允许，Bash 需要确认。
- `plan`：只向模型提供 Read、Glob、Grep。
- `bypassPermissions`：普通操作自动允许，但黑名单、沙箱和显式 deny 仍生效。

内置工具需要确认时可以选择：允许本次、永久允许此精确调用、拒绝本次。MCP 工具额外支持
“本会话允许”。永久允许写入项目本地文件 `.dragon-code/settings.local.yaml`，该文件已被 Git 忽略。

规则格式为 `工具名(模式)`：

```yaml
permissions:
  mode: default
  allow:
    - Bash(git status)
    - Read(docs/**)
  deny:
    - Read(.env)
    - Write(.git/**)
```

规则来源按优先级排列：

1. 项目本地：`.dragon-code/settings.local.yaml`
2. 项目共享：`.dragon-code/settings.yaml`
3. 用户全局：`~/.dragon-code/settings.yaml`

完整示例见 `.dragon-code/settings.yaml.example`。

## 开发验证

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
```

最终验收需在 tmux 中启动 Dragon Code，输入真实对话，并逐项核对
[`specs/ch07-mcp-client/checklist.md`](specs/ch07-mcp-client/checklist.md)。
