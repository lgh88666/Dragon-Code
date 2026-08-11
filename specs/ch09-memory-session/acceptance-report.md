# ch09：项目记忆与会话持久化验收报告

## 结论

ch09 已完成实现，并通过自动化测试与真实 DeepSeek、WSL tmux 端到端验收。

- **项目指令**：按项目根、项目 `.dragon-code/`、用户目录三层加载 `DRAGON.md`，支持安全 `@include`。
- **会话持久化**：完整消息按 JSONL 追加保存，支持工具调用配对、压缩边界、坏行跳过和悬空调用截断。
- **会话恢复**：`/resume` 提供列表、搜索和原会话续写；恢复失败时不破坏当前会话。
- **自动记忆**：四类 Markdown 笔记与 `MEMORY.md` 索引在后台更新，项目级和用户级分开保存。
- **生命周期**：45 天清理只处理新格式会话；退出时关闭 Writer、后台记忆、MCP 和清理任务。
- **安全**：会话与自动记忆目录均被 Git 忽略，API Key 和本地配置未进入报告或候选提交。

## 自动化证据

执行日期：2026-08-11；环境：Windows、uv 管理的 Python 环境。

| 命令 | 实际结果 |
|---|---|
| `uv sync --locked` | Resolved 57 packages；Checked 57 packages |
| `uv run ruff format .` | 141 files left unchanged |
| `uv run ruff format --check .` | 141 files already formatted |
| `uv run ruff check .` | All checks passed |
| `uv run pytest -q` | 369 passed, 2 skipped in 21.85s |
| `git diff --check` | 退出码 0；仅出现 LF/CRLF 提示，无空白错误 |
| checklist 未完成项扫描 | 0 项 |

主要自动化覆盖：

- 三层指令优先级、缺失降级、独占行 include、5 层深度、环路、符号链接越界、二进制和非法 UTF-8。
- 新旧会话 ID、消息编解码、工具调用/结果配对、`hidden_blocks`、并发追加、flush/fsync、压缩边界和重复关闭。
- `/resume` 本地路由、列表元数据、搜索、坏行恢复、悬空工具调用截断、超限恢复压缩、原子切换和旧格式保护。
- 45 天清理边界：46 天前删除、44 天前保留，并隔离单个删除失败。
- 四类记忆的创建、更新、删除、索引重建、体量限制、触发节奏、无工具 LLM 请求、后台失败隔离和原子写入。
- ch02–ch08 的流式、工具、权限、MCP、Plan Mode、取消和上下文压缩非回归。

性能实测：

```text
INSTRUCTION_AVG_MS=0.910
APPEND_MEDIAN_MS=0.195
APPEND_MAX_MS=1.299
LIST_50_MS=12.967
LIST_COUNT=50
```

这些结果分别低于指令加载 200ms、典型追加 10ms 和 50 会话扫描 500ms 的目标。

## WSL tmux 真实端到端证据

执行日期：2026-08-11；环境：WSL、tmux、真实 `deepseek-v4-pro`。验收过程没有输出 API Key。

### 1. 完整工具会话存档

在 tmux 中启动 Dragon Code，要求读取 `README.md` 第一行。实际观察：

```text
● Read(README.md)
  └─ 1 | # Dragon Code
final=Dragon Code
elapsed=3.8s
```

生成的新格式会话 `20260811-171247-48cd` 中，JSONL 顺序为：

```text
user（含本会话模型）
assistant ToolCall（含调用 ID）
ToolResult（使用同一调用 ID）
assistant 最终答复
```

这证明真实工具调用、结果回灌与磁盘记录配对一致。

### 2. `/resume` 搜索与继续对话

退出后重新启动并输入 `/resume`，列表显示会话元数据；按会话 ID 搜索并恢复 4 条消息。随后询问前一轮读取到的项目名，模型没有再次调用工具，直接回答 `Dragon Code`。新消息继续追加到原会话文件。

### 3. 自动记忆跨会话生效

在一个会话中输入：

```text
请记住：Dragon Code 项目的验收代号是 CH09-BLUE-DRAGON。
```

后台任务创建项目知识笔记和 `MEMORY.md` 索引。退出并启动全新会话后，在不读取文件的情况下提问，模型正确回答 `CH09-BLUE-DRAGON`。验收专用记忆文件随后已删除，未进入 Git。

### 4. 项目指令与 include

临时项目根 `DRAGON.md` 引用一个规则文件。真实模型能同时回答根规则 `ROOT-DRAGON-09` 和 include 规则 `INCLUDE-DRAGON-09`，证明运行请求收到了加载后的自定义指令。三层优先级和越界分支由隔离自动化测试覆盖，未伪装成 tmux 人工场景。临时文件验收后已删除。

### 5. 异常会话恢复

构造一个含坏 JSON 行和末尾悬空 ToolCall 的隔离会话，真实 `/resume` 显示：

```text
已恢复，共 1 条消息
已跳过 1 行损坏记录
已截断缺少工具结果的末尾记录
```

恢复后继续发消息，模型正常返回 `OK`，未出现 provider 400 或会话崩溃。隔离会话文件验收后已删除。

### 6. 退出清理

执行 `/exit` 后关闭 tmux 验收会话，进程检查结果：

```text
DRAGON_PROCESS_COUNT=0
```

没有残留 Dragon Code 进程。流式期间 `/resume` 互斥、恢复失败回滚、后台记忆取消和 `/compact` 边界恢复由可控自动化测试验证。

## 自动化与人工验收边界

- 真实 tmux 覆盖：工具会话落盘、`/resume` 搜索与续聊、跨会话记忆、项目指令 include、异常恢复、正常退出。
- 自动化覆盖：三层优先级、压缩边界、超限恢复压缩、恢复原子回滚、45 天清理、并发写入、后台失败与取消等难以稳定人工制造的边界。
- 没有把自动化场景描述成 tmux 已实测，也没有把临时验收数据提交到仓库。

## 明确未实现

保持已批准 Spec 边界：不包含向量数据库或 RAG、跨设备/团队同步、会话分支重命名删除导出、自动生成标题、结构化数据库、完整审计系统和跨进程并发写同一会话。
