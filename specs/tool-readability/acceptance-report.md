# Dragon Code 工具交互可读性优化验收报告

## 结论

工具与 SubAgent 任务展示已完成降噪：运行中状态只存在于动态区域，结束后写入紧凑的最终记录；成功、失败、取消和任务状态使用接近 Claude Code 的低饱和暖橙、灰色和暗红色。自动化与真实 tmux 场景均通过。

## 自动化证据

- `uv sync --locked`：57 个包锁定检查通过。
- `uv run ruff format --check .`：229 个文件已格式化。
- `uv run ruff check .`：无告警。
- `uv run pytest -q tests/test_tui.py`：`53 passed`。
- `uv run pytest -q`：`530 passed, 2 skipped`。

自动化覆盖动态工具状态、成功单行、失败两行、两个并发工具、前台/后台子 Agent 差异、任务 ID 显隐、摘要长度和清理路径。

## tmux 端到端证据

### 动态工具行与最终记录

真实 DeepSeek 请求执行延迟 Bash。权限等待和命令执行期间动态区显示：

```text
● Bash  python -c "import time; time.sleep(3); print('done')"
```

完成后动态项消失，scrollback 只保留：

```text
✓ Bash  python -c "import time; time.sleep(3); print('done')"  stdout: done
```

### 内置工具与错误

- Read：显示 `✓ Read  pyproject.toml  读取 44 行`。
- Grep：显示 `✓ Grep  BackgroundTaskManager · src  找到 13 处匹配`。
- 不存在文件：显示暗红 `✗ Read ...`，下一行显示 `└ 文件不存在。`，随后会话仍可继续。

### SubAgent

- 定义式前台任务显示任务名和紧凑内部 Read 工具行，普通 queued/running/completed 状态不显示 task ID。
- Fork 后台任务只显示任务状态，不展示内部 Read 工具；完成摘要受长度上限约束。
- Agent 系统工具最终摘要只显示 `子任务已完成` 或 `后台任务已启动`，不会把完整 JSON/子任务结果重复刷入工具行。

### 退出清理

输入 `/exit` 后返回正常命令提示符。清理 tmux 后实测：

```text
DRAGON_CODE_PROCESS_COUNT=0
TMUX_SESSION_GONE
```

## 与批准设计的对应关系

- 未改动 Agent Loop、ToolResult 回灌和工具调度语义。
- 未改动权限弹窗、Slash Command、Hook 与主回复渲染。
- 后台子 Agent 继续隐藏内部过程；前台子 Agent 保留过程可观测性。
- 完整结果仍供模型使用，界面只显示短摘要。
