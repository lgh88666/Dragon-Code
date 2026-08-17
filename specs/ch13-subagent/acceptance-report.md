# Dragon Code ch13 SubAgent 验收报告

## 结论

ch13 的实现、构建、静态检查和全量自动化回归均已通过。真实 TUI 已跑通定义式
SubAgent、Fork 后台任务、TaskGet、SendMessage 续派和 fork Skill 主链路。

并发 `3 running + 1 queued`、`Ctrl+B` 手动转后台以及子 Agent 权限拒绝后的调整，当前由
自动化测试覆盖；本次没有把它们冒充成 tmux 实测。

## 自动化证据

- `uv sync --locked`：退出码 0。
- `uv run ruff format --check .`：224 个文件格式正确。
- `uv run ruff check .`：`All checks passed!`。
- `uv run pytest -q`：`525 passed, 2 skipped in 30.21s`。
- `uv build`：构建成功，wheel 内包含 `explore.md`、`plan.md`、`verify.md`。

自动化覆盖的关键行为：

- Agent 定义解析、稳定排序、三级覆盖、坏定义隔离和内置定义致命错误。
- 定义式空白历史、Fork 深拷贝、悬空 ToolCall 占位结果和缓存稳定前缀。
- 五个稳定系统工具、结构化参数错误、TaskList/TaskGet/TaskStop/SendMessage。
- 三并发 FIFO、排队不提前执行、运行/排队取消、120 秒自动转后台和手动转后台。
- 子 Agent 来源保护、Fork 标记兜底、非交互权限拒绝和 Plan Mode 只读边界。
- 后台通知只注入下一次请求一次，不写入 Conversation；结果截断和敏感值脱敏。
- fork Skill 复用统一 Host/Manager；原 inline Skill、权限、Hook、TUI 和协议测试无回归。

## tmux 证据

### 通过

- [x] 定义式前台探索：真实 DeepSeek 请求调用 `Agent(role="explore")`，子 Agent 流式运行并
  完成；修复了子 Agent 的 `completed` 事件早于 Manager 终态导致的 TUI 状态竞争。
- [x] Fork 后台和查询：Fork 立即返回 `task_50615b3f`，TaskGet 后显示 completed，结果为
  `DRAGON_FORK_OK`，缓存读取量为 7040 tokens。
- [x] 命名任务续派：`contfix` 首个任务 `task_da590634` 返回 `FIRST_OK`；SendMessage 创建新
  任务 `task_be093869` 并返回 `SECOND_OK`。这次实测发现并修复了续派提示未追加的问题。
- [x] fork Skill 主链路：`/review` 通过统一后台任务 `task_afce0bd4` 完成并产生状态摘要。
- [x] 普通安全退出：独立会话执行 `/exit` 后，没有残留 Dragon Code 进程。

### 本次未做完整 tmux 组合场景

- [ ] 同时启动四个真实长任务，完整观察 `3 running + 1 queued`、Ctrl+B、TaskStop 的组合。
- [ ] 真实子 Agent 触发 Ask 后不弹审批框、收到拒绝并自行调整。该路径已有 fake LLM 集成
  测试，但未用真实模型刻意触发。
- [ ] 带 running 和 queued 任务时直接退出并逐项核对模型流、Hook task 和子进程。本次只验证
  了普通退出；Manager 的 running/queued 清理已有自动化测试。

## 实测发现并修复的问题

1. **终态事件竞争**：子 Agent 先吐出 `completed`，Manager 仍是 running，TUI 按终态渲染时
   发生 KeyError。修复为 Manager 屏蔽子 Agent 原始终态，仅在自身完成状态转换后发布终态。
2. **SendMessage 重复旧任务**：Fork 首次提示已在复制历史中，但续派提示没有追加。修复为
   显式区分“提示已在历史”与“需要追加新提示”，并增加回归测试。
3. **极早取消竞争**：runner 尚未进入主体时取消，任务可能停在 running。修复为取消路径始终
   完成合法终态转换。

## 已知边界

- 本章共享同一工作目录，不提供 Worktree 文件隔离；可能写文件的后台任务会显示冲突警告。
- 后台任务不跨会话持久化，切换会话和退出会清理任务。
- Fork 和 fork Skill 强制后台；子 Agent 不允许再次创建或管理子 Agent。
- `deepseek-v4-flash` 是三个内置定义式角色的默认模型；Fork 继承父模型。
