# ch10：Slash Command 内置命令框架验收报告

## 结论

- 功能实现与自动化验收通过。
- Checklist：`68/71` 已验证。
- 剩余 3 项是需要删除本地状态的 tmux 场景（清空后恢复、会话删除、记忆删除）；对应行为已由临时目录集成测试通过，本次没有在真实用户数据上执行破坏性操作。

## 自动化证据

- `uv sync --locked`：57 个锁定包检查通过。
- `uv run ruff format --check .`：160 个文件已格式化。
- `uv run ruff check .`：通过。
- `uv run python -m compileall -q src tests`：通过。
- `uv run pytest -q`：`408 passed, 2 skipped`。
- `git diff --check`：通过。

覆盖内容包括命令注册与冲突检测、大小写和别名、零参数解析、异步 Handler、补全状态机、帮助和状态、Plan/Do、清空、恢复、会话删除、记忆删除和索引重建、权限模式、只读审查、忙碌保护、历史不污染与退出清理。

## tmux 真实证据

### 通过

- [x] 输入 `/` 后显示主命令和描述，窗口最多显示 8 行；完整命令第一次 Enter 只补全，第二次 Enter 执行。
- [x] `/help` 打开注册中心驱动的帮助界面；Esc 可安全关闭。
- [x] `/status` 展示版本、cwd、Provider、模型、权限、会话、Token、工具和记忆计数；连续执行两次均成功。
- [x] `/permission` 展示 `default`、`acceptEdits`、`bypassPermissions`，不包含 Plan Mode。
- [x] 真实 DeepSeek 对话触发 Grep、Read 和 Bash 权限确认；拒绝 Bash 后 Agent Loop 能继续完成。
- [x] `/review` 对当前 Git 改动执行真实只读审查；观察到 Read/Glob 等只读工具，45 秒内工作树状态保持不变。
- [x] `/review` 运行到第 15 轮时按 Esc，界面显示“当前任务已取消”并回到空闲状态。
- [x] `/q` 别名安全退出；退出后 `DRAGON_PYTHON_PROCESS_COUNT=0`。

### 未在真实数据上执行

- [ ] `/clear` 后再 `/resume` 恢复旧会话：自动化集成测试通过，本次未额外制造真实会话数据。
- [ ] `/session` 取消并确认删除测试会话：临时目录测试通过，本次未删除真实会话。
- [ ] `/memory` 取消并确认删除测试记忆：双层临时目录和索引重建测试通过，本机当前状态显示用户/项目记忆均为 0。

## tmux 发现并修复的问题

1. **补全事件交错**：快速键入完整命令时偶尔需要第三次 Enter。修复为在用户真正改变文本前持续抑制补全菜单重开。
2. **帮助弹窗 Esc 崩溃**：全局取消入口调用了帮助弹窗缺失的 `action_cancel()`。补齐统一取消接口并增加回归测试。
3. **快速本地命令竞态**：Handler 可能在 Worker 引用赋值前完成，导致已完成 Worker 被重新写回并永久误判忙碌。清理前让出一次事件循环，并新增连续本地命令测试。

## 教材 Python 方案对照

### 保持一致

- 集中式 Registry、异步 `handler(ui)`、UI Protocol、三类命令、零参数、主名称补全和帮助单一信息源。

### Dragon Code 的差异

- 补全第一次 Enter 只填入、第二次才执行；教材示例更偏直接执行。
- 所有命令统一要求空闲，避免命令与 Agent/恢复/压缩状态交错。
- `/session`、`/memory`、`/permission` 使用交互界面，不要求记忆长 ID 或参数。
- `/review` 使用一次性只读工具集合，不改变长期权限模式，也不设置 Plan 标记。
