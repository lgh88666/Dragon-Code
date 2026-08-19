# Dragon Code 工具交互可读性优化 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|---|---|---|
| 修改 | `src/dragon_code/tui.py` | 活动工具状态、紧凑渲染和任务行降噪 |
| 修改 | `src/dragon_code/dragon_code.tcss` | 动态工具区域布局 |
| 修改 | `tests/test_tui.py` | 新展示行为自动化测试 |
| 修改 | `docs/PROJECT_HANDOFF.md` | 记录优化结果和证据 |
| 新建 | `specs/tool-readability/acceptance-report.md` | 记录实际验收证据 |

## T1：建立低饱和渲染 helper

**文件：** `src/dragon_code/tui.py`
**依赖：** 无

**步骤：**
1. 定义暖橙、柔和灰、暗红三个颜色常量。
2. 拆分工具名、关键参数和结果摘要格式化。
3. 实现成功单行与失败两行 Rich Renderable。
4. 保留现有截断和上下文落盘提示。

**验证：** 格式化单测断言文本、长度和失败原因正确。

## T2：增加动态工具区域和活动状态

**文件：** `src/dragon_code/tui.py`、`src/dragon_code/dragon_code.tcss`
**依赖：** T1

**步骤：**
1. 在 compose 中增加 `#tool-activity` Static。
2. 增加 `PendingToolDisplay` 和有序活动字典。
3. 实现登记、结束、刷新和清理方法。
4. 支持同时展示多个活动工具。

**验证：** Textual pilot 注入两个工具开始事件，动态区同时显示两项；结束后清空。

## T3：接入主 Agent 工具事件

**文件：** `src/dragon_code/tui.py`
**依赖：** T2

**步骤：**
1. `tool_start` 改为写动态区域。
2. `tool_end` 改为移除动态项并写最终记录。
3. 成功只写一条，失败写状态与原因两行。
4. 回合完成、取消、错误时清理残留活动项。

**验证：** fake Agent Loop 的 scrollback 中每个成功工具仅出现一条最终记录。

## T4：接入前台子 Agent 工具事件

**文件：** `src/dragon_code/tui.py`
**依赖：** T2

**步骤：**
1. attached 子 Agent 使用 task ID + call ID 作为活动键。
2. 动态行和最终行包含低调任务名称标签。
3. 后台子 Agent 内部工具事件继续忽略。
4. 子任务结束、取消和会话重置时清理相关活动项。

**验证：** 分别注入 attached/background 事件，观察只有 attached 内部工具进入界面。

## T5：压缩子 Agent 任务状态行

**文件：** `src/dragon_code/tui.py`
**依赖：** T1

**步骤：**
1. queued、running、转后台、completed 隐藏 task ID。
2. completed 摘要限制约 80 个终端显示宽度（中文约 40 字）。
3. failed 使用暗红两行并显示 task ID；cancelled 使用柔和灰。
4. workspace warning 保持明显但使用低饱和暗红。

**验证：** TUI 测试检查正常状态不含 ID，失败状态含 ID，摘要长度受控。

## T6：补齐回归测试

**文件：** `tests/test_tui.py`
**依赖：** T1–T5

**步骤：**
1. 更新旧工具格式断言。
2. 覆盖执行中动态区、成功单行和失败两行。
3. 覆盖两个并发工具、前台子 Agent 和后台隐藏。
4. 覆盖完成/取消/错误/会话重置后的动态状态清理。

**验证：** `uv run pytest -q tests/test_tui.py` 全部通过。

## T7：全量检查与真实验收

**文件：** 全项目、`specs/tool-readability/checklist.md`
**依赖：** T6

**步骤：**
1. 运行 uv sync、Ruff 和全量 pytest。
2. 在 tmux 启动 Dragon Code，执行真实 Read/Grep 和子 Agent 任务。
3. 对照 checklist 记录真实显示和退出清理。
4. 更新验收报告与交接文档。

**验证：** 所有命令退出码为 0，tmux 中显示符合批准样式。

## T8：创建本地提交

**文件：** 本功能范围文件
**依赖：** T7

**步骤：**
1. 检查 diff 和敏感信息。
2. 只暂存本功能文件，保护 `.idea/`、`321.txt` 和本地 Skill。
3. 创建本地提交，不自动推送。

**验证：** `git show --stat --oneline HEAD` 显示本功能提交。

## 执行顺序

```text
T1 → T2 → T3
       └→ T4
T1 ─────→ T5
T3 + T4 + T5 → T6 → T7 → T8
```
