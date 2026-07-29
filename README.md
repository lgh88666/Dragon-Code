# Dragon Code

Dragon Code 是一个使用 Python 构建的、Claude Code 风格终端 AI 编程助手。

当前 ch02 已实现：

- Anthropic 与 OpenAI Chat Completions 两种协议
- OpenAI 兼容端点
- 多 Provider 启动选择
- 流式回复、等待动画和响应计时
- 单会话多轮上下文
- 完整 Textual TUI 与 Markdown 定型
- 可恢复、经过脱敏的错误提示

本章尚不包含文件工具、命令执行、MCP、权限和 Agent Loop。

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
- `/exit`：退出
- Ctrl+C：安全退出

等待模型时会显示 `Imagining… (Ns)`；回复流式结束后会重新渲染为 Markdown。

## 开发验证

```bash
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
```

最终验收需在 tmux 中启动 Dragon Code，输入真实对话，并逐项核对
[`checklist.md`](checklist.md)。
