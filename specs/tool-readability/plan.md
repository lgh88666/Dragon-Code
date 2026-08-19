# Dragon Code 工具交互可读性优化 Plan

## 架构概览

保留现有 `RichLog + Static` 布局。在对话区与模型流式文本之间增加一个轻量
`#tool-activity` 动态区域。工具开始时登记活动项并刷新该区域；工具结束时从活动项中移除，
再由统一 helper 生成最终 RichLog 记录。

不修改 AgentEvent、ToolResult 或协议层，仅在 TUI 消费事件时改变展示策略。

## 核心数据结构

### PendingToolDisplay

```python
@dataclass(frozen=True)
class PendingToolDisplay:
    key: str
    call: ToolCall
    agent_label: str = ""
```

- `key`：主工具使用 `main:{call_id}`，子 Agent 使用 `sub:{task_id}:{call_id}`。
- `call`：保留工具名和关键参数，供完成时与 ToolResult 合并。
- `agent_label`：前台子 Agent 的低调来源标签；主工具为空。

`DragonCodeApp.active_tool_displays` 使用普通 `dict` 保存，依赖 Python 字典插入顺序展示并发项。

## 核心接口

- `_start_tool_display(key, call, agent_label="")`：登记活动工具并刷新动态区。
- `_finish_tool_display(key, result)`：移除活动项并写入成功或失败最终记录。
- `_update_tool_activity()`：把所有活动项渲染到 `#tool-activity`。
- `_clear_tool_activity()`：在取消、结束、会话切换和退出时清除残留。
- `format_tool_subject(call)`：生成无颜色的“工具名 + 关键参数”。
- `format_tool_result(result, limit=...)`：生成受控短摘要。

## 渲染规则

### 执行中

```text
● Read  src/dragon_code/agent.py
```

符号和工具名使用低饱和暖橙，参数使用柔和灰。

### 成功

```text
✓ Read  src/dragon_code/agent.py  读取 842 行
```

使用柔和灰，不整行标绿。

### 失败

```text
✗ Bash  uv run pytest
  └ 测试失败，退出码 1
```

两行使用暗红，原因限制长度；完整 ToolResult 不受影响。

### 子 Agent

```text
● permission-study · Read  src/dragon_code/permissions/engine.py
✓ Agent  permission-study  已完成 · 权限系统分为……
```

queued、running、转后台和 completed 不显示 task ID；完成摘要约 80 个终端显示宽度；failed 的
第二行显示 task ID。

## 模块交互

```text
AgentEvent(tool_start)
  → _start_tool_display()
  → #tool-activity 临时渲染

AgentEvent(tool_end)
  → _finish_tool_display()
  → 清除活动项
  → RichLog 写入最终紧凑记录
```

前台 SubAgentEvent 使用 `sub:{task_id}:{call_id}` 进入同一流程。后台内部事件保持忽略。

## 文件组织

```text
src/dragon_code/
├── tui.py                  — 状态、格式化 helper 和事件接线
└── dragon_code.tcss        — tool-activity 动态区域布局和低饱和基础颜色

tests/
└── test_tui.py             — 单行、失败两行、并发动态项、子 Agent 状态和清理测试

specs/tool-readability/
├── spec.md
├── plan.md
├── task.md
└── checklist.md
```

## 技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 历史行更新 | 动态 Static + 完成后写 RichLog | RichLog 不适合原地更新，避免替换主组件 |
| 活动状态 | 普通有序 dict | 简单支持多个并发工具，不引入额外状态机 |
| 配色 | Python 中三个 Rich 颜色常量 | RichLog 分段着色直接、改动局部 |
| 成功表现 | 符号 + 灰色 | 避免亮绿色抢占主回复视觉焦点 |
| task ID | 正常隐藏、失败显示 | 降噪同时保留排错入口 |
| 子 Agent 内部工具 | 前台显示、后台隐藏 | 保留可观察性且避免后台刷屏 |

## 与现有设计的关系

- 保留教材和 Dragon Code 现有的实时工具反馈，但把“立即写历史”改为“动态展示后定型”。
- 不引入 Claude Code 的可折叠组件；当前阶段选择更轻量、便于学习的实现。
- ToolResult 的模型回灌、截断和落盘继续由原逻辑处理，TUI 只读取摘要。
