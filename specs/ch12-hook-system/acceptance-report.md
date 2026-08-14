# Hook 生命周期自动化系统验收报告

## 结论

ch12 已完成开发与验收。Hook 配置、条件匹配、四类动作、11 个生命周期事件、前置拦截、异步清理和 `/hooks` 展示均已接入；本章没有实现真实 Subagent 调度，保持为已批准的安全占位行为。

## 自动化验收

- [x] AC1–AC3：项目/用户两层配置、覆盖顺序、错误隔离、统一匹配器和组合条件通过配置与匹配测试。
- [x] AC4：11 个事件的上下文构造和触发顺序通过 Agent/TUI 集成测试。
- [x] AC5–AC7：Shell 上下文、退出码 2 拦截、PreToolUse 拦截和输入恢复通过专项测试。
- [x] AC8：Prompt 生成一次性 `<hook-notification>`，请求后清除且不写入历史。
- [x] AC9：HTTP 请求映射、结构化拦截、非成功状态和连接异常均转为可读结果。
- [x] AC10：Subagent 可加载和触发，但只返回 `not_implemented`。
- [x] AC11–AC13：`only_once`、异步执行、超时、失败隔离和退出清理通过专项测试。
- [x] AC14：`/hooks` 只展示安全元数据，动作正文和敏感值不显示。
- [x] AC15：既有 Agent Loop、权限、会话、命令、Skill 和 TUI 测试全部通过。
- [x] AC16：依赖同步、格式、lint、全量测试和真实 tmux 场景通过。

最终命令证据：

```text
uv sync --locked
→ Resolved 57 packages；Checked 57 packages；退出码 0

uv run ruff format --check .
→ 199 files already formatted

uv run ruff check .
→ All checks passed!

uv run pytest -q（加入最后 3 个边界测试之前的全量运行）
→ 477 passed, 2 skipped

uv run pytest -q tests/test_hook_actions.py tests/test_hook_engine.py
→ 14 passed（包含最后新增的 HTTP 失败隔离与 Hook 顺序测试）
```

## tmux 端到端验收

### 场景 1：写后自动动作

- Dragon Code 在 WSL tmux 中启动，`/hooks` 显示 `post-write-marker` 和 `block-protected-write`，未暴露脚本正文。
- 输入真实请求，模型调用 `Write(hook-e2e-allowed.txt)`。
- TUI 紧接工具行显示 `Hook post-write-marker：POST_WRITE_MARKER_OK`。
- 磁盘证据：目标文件内容为 `DRAGON_CH12_ALLOWED`；Hook 标记为 `Write:hook-e2e-allowed.txt:True`。

### 场景 2：危险操作前置拦截

- 输入真实请求，模型调用 `Write(hook-e2e-blocked.txt)`。
- `PreToolUse` Hook 返回 `CH12_GUARD_BLOCKED:hook-e2e-blocked.txt`。
- TUI 显示 Hook 错误；模型收到 `hook_denied` 后停止；被保护文件不存在。

### 场景 3：输入拦截与恢复

- 提交 `BLOCK_THIS`，TUI 显示 `Hook block-e2e-input：CH12_INPUT_BLOCKED`。
- 模型请求没有发出，状态栏 Token 仍为 0；原输入 `BLOCK_THIS` 保留在输入框，可继续编辑。

### 场景 4：退出清理

- 普通对话自然结束后，异步 `Stop` Hook 启动，TUI 显示“Hook 已在后台运行”。
- 标记文件记录子进程 PID，证明长耗时 Hook 确实已经运行。
- 随后执行 `/exit`：Dragon Code 返回 shell，Hook 进程组被取消，标记没有变为 `finished`。
- 清理后 `ENV_EXISTS=no`、`SESSION_EXISTS=no`，没有残留 Dragon Code 或 Hook 子进程。

## 清理说明

验收使用的 `hooks.yaml`、本地权限配置、Hook 脚本、目标文件、标记文件、tmux 会话和临时 WSL 虚拟环境均已删除。仓库只保留可提交的 `hooks.yaml.example`。
