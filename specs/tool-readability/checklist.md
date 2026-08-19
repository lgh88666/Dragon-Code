# Dragon Code 工具交互可读性优化 Checklist

## 工具展示

- [x] 工具开始后动态区立即显示 `● 工具名 关键参数`。（证据：Textual 测试 + tmux 延迟 Bash）
- [x] 工具完成后动态项消失，scrollback 只有一条成功记录。（证据：Textual 测试 + tmux）
- [x] 成功记录包含 `✓`、工具名、关键参数和短摘要。（证据：真实 Read/Bash）
- [x] 失败记录第一行包含 `✗`，第二行包含短原因。（证据：真实不存在文件）
- [x] 完整 ToolResult 仍进入下一轮模型请求。（证据：fake client 请求体测试）
- [x] 两个并发只读工具同时显示，完成后各自只保留一条记录。（证据：Event 控制测试）

## 子 Agent 展示

- [x] 前台子 Agent 内部工具使用相同紧凑格式并带任务标签。（证据：attached 测试 + tmux）
- [x] 后台子 Agent 内部工具不写入主 scrollback。（证据：background 测试 + tmux）
- [x] queued、running、转后台和 completed 状态不显示 task ID。（证据：事件测试 + tmux）
- [x] completed 摘要最多约 80 个终端显示宽度。（证据：长中文摘要测试）
- [x] failed 使用暗红两行并显示 task ID。（证据：失败事件测试）
- [x] cancelled 使用柔和灰，不使用亮黄色。（证据：取消事件测试）

## 视觉与清理

- [x] 工具与任务行只使用低饱和暖橙、柔和灰和暗红。（证据：Rich 样式检查）
- [x] 不再使用 `bold cyan`、`bold magenta`、`bold green` 或亮黄色渲染这些行。（证据：源码和测试检查）
- [x] 回合完成、取消、错误、会话重置和退出后动态工具区为空。（证据：状态清理测试）
- [x] 窄终端下动态区、输入框和状态栏不重叠。（证据：80 列 Textual pilot）
- [x] 最终记录可选择、复制并在 scrollback 回看。（证据：RichLog 选择测试 + tmux 回看）

## 回归

- [x] 主回复流式显示和 Markdown 定型不变。（证据：原回归测试通过）
- [x] Hook、Slash Command 和权限弹窗行为不变。（证据：全量测试 + tmux 权限弹窗）
- [x] `uv sync --locked` 通过。
- [x] `uv run ruff format --check .` 通过。
- [x] `uv run ruff check .` 通过。
- [x] `uv run pytest -q` 全部通过：`530 passed, 2 skipped`。
- [x] 输出和 Git diff 不包含 API Key 或 Authorization。（证据：提交前敏感信息扫描）

## tmux 端到端

- [x] 场景一：真实 Read/Grep 只留下紧凑记录；延迟 Bash 执行中显示动态项，完成后只留单行记录。
- [x] 场景二：定义式前台子 Agent 显示紧凑内部工具和受控完成摘要。
- [x] 场景三：Fork 后台只显示任务状态，不刷内部工具，完成时不显示普通 task ID。
- [x] 场景四：触发不存在文件错误，看到暗红失败行和一条短原因，会话仍可继续。
- [x] 场景五：`/exit` 后终端正常，`DRAGON_CODE_PROCESS_COUNT=0`，tmux 会话已清理。
