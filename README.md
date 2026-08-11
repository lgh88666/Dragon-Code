# Dragon Code

Dragon Code 是一个使用 Python 构建的、Claude Code 风格终端 AI 编程助手。

当前已完成 ch02–ch09 的核心能力：

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
- 工具大结果自动落盘、稳定预览和按路径重读
- 对话窗口逼近上限时自动生成结构化摘要
- `/compact` 手动压缩与连续三次自动失败熔断
- 三层 `DRAGON.md` 项目指令与安全 `@include`
- JSONL 会话存档、`/resume` 搜索恢复和 45 天清理
- 项目级与用户级自动记忆索引

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
    context_window: 128000
    summary_model: "你的轻量摘要模型名称"
```

`context_window` 可省略；Anthropic 默认 200000，OpenAI 及兼容端点默认
128000。`summary_model` 可省略，省略时复用主模型。DeepSeek 兼容端点可将其配置为
`deepseek-v4-flash`；摘要 Client 复用相同协议、API Key 和 `base_url`，但不会携带工具。

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
- `/compact`：立即压缩当前对话上下文
- `/resume`：搜索并恢复当前项目的历史会话
- Shift+Tab：循环切换四种权限模式
- Esc：取消当前 Agent 任务
- Ctrl+C：有选中文字时复制；任务中取消；空闲时退出

等待模型时会显示 `Imagining… (Ns)`；回复流式结束后会重新渲染为 Markdown。

单个工具结果超过 50000 UTF-8 字节，或同轮未替换结果合计超过 200000 字节时，
完整内容会保存在 `.dragon-code/sessions/<session_id>/tool-results/`，对话只保留预览和
Read 重读路径。该目录退出后保留，并已被 Git 忽略。
Read 支持可选的 `offset`（起始行）和 `limit`（最多行数），可按预览提示分段读取
大型结果，避免整体重读后再次超过阈值。

普通请求逼近模型窗口时会自动压缩较早历史并保留近期原文。自动摘要连续失败三次后
进入熔断，但仍会继续主请求；用户可以随时在空闲状态使用 `/compact` 手动重试。

## 项目指令、会话与记忆

Dragon Code 启动时按以下优先级加载手写项目指令：

1. 项目根 `DRAGON.md`
2. 项目 `.dragon-code/DRAGON.md`
3. 用户 `~/.dragon-code/DRAGON.md`

高优先级内容排在前面。指令文件可用独占一行的 `@include 相对路径` 引用其他 UTF-8
Markdown；嵌套最多 5 层，并会拦截循环引用、二进制文件和越过所属根目录的路径。
手写 `DRAGON.md` 不会被 Git 自动忽略，是否提交由项目维护者决定。

每次启动先创建新会话，完整逻辑消息追加到
`.dragon-code/sessions/<session_id>/conversation.jsonl`。输入 `/resume` 可按标题或会话 ID
搜索并恢复；损坏的单行会被跳过，缺少 ToolResult 的末尾 ToolCall 会被安全截断。只有新格式
会话参与列表和自动清理，超过 45 天的会话会在启动后后台清理。

自动记忆分为用户偏好、纠正反馈、项目知识和参考资料。项目记忆位于
`.dragon-code/memory/`，用户记忆位于 `~/.dragon-code/memory/`。模型只在自然完成后的每
5 轮，或用户明确说“记住/别忘/remember/memo”时后台整理；失败不会中断主对话。
项目会话和自动记忆已被 Git 忽略，用户级目录本身位于仓库外。

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
[`specs/ch09-memory-session/checklist.md`](specs/ch09-memory-session/checklist.md)。
