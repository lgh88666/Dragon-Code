# 聊天历史选择与复制 Plan

## 架构概览

保留现有 `RichLog` 聊天历史。当前 Textual 6.x 能记录 `RichLog` 的鼠标选择范围，但
无法从 Rich 渲染对象中提取所选文字，因此增加一个很小的 `ConversationLog` 子类，
从 `RichLog` 已渲染的行中提取纯文本。`DragonCodeApp` 接收快捷键后读取当前屏幕的
选择文本：非空时调用 Textual 剪贴板入口；没有选择时调用既有安全退出动作。

## 核心接口

### `ConversationLog.get_selection()`

```python
def get_selection(self, selection: Selection) -> tuple[str, str] | None
```

不改变 `RichLog` 的渲染、滚动或写入行为，只把已经渲染的行组合成纯文本，再按 Textual
提供的选择范围提取内容。

### `DragonCodeApp.action_copy_or_quit()`

```python
def action_copy_or_quit(self) -> None
```

读取当前屏幕选择。存在非空文本时调用 `copy_to_clipboard()` 并返回；否则调用
`action_safe_quit()`。

### Textual 原生接口

```python
selected_text = self.screen.get_selected_text()
self.copy_to_clipboard(selected_text)
```

`get_selected_text()` 汇总当前屏幕选择；`copy_to_clipboard()` 通过 OSC 52 交给终端，
并同步维护 Textual 的内部剪贴板值，便于自动化验证。

## 模块设计

### TUI

**职责：** 保留聊天历史选择能力，处理复制与退出分流。
**对外行为：** `Ctrl+C` 根据是否存在非空选择执行复制或退出。
**依赖：** Textual `Screen` 选择状态和 `App.copy_to_clipboard()`。

### TUI 测试

**职责：** 验证绑定、复制分支、空选择退出分支和复制后继续使用。
**策略：** 自动化测试直接设置一个可观察的屏幕选择，触发 `Ctrl+C`，断言 Textual
内部剪贴板和应用运行状态。

## 模块交互

```text
用户拖选 RichLog 文字
        ↓
Textual Screen 保存选择
        ↓
用户按 Ctrl+C
        ↓
DragonCodeApp.action_copy_or_quit()
        ├── 选择非空 → copy_to_clipboard() → 应用继续运行
        └── 无选择   → action_safe_quit() → 应用安全退出
```

## 文件组织

```text
dragonAgent/
├── src/dragon_code/tui.py
├── tests/test_tui.py
├── docs/learning-notes.md
└── specs/chat-history-copy/
    ├── spec.md
    ├── plan.md
    ├── task.md
    └── checklist.md
```

## 需求覆盖

| 需求 | 归属 |
|---|---|
| F1 | `ConversationLog` 兼容 Textual 原生选择 |
| F2、F3 | `action_copy_or_quit()` 的复制分支 |
| F4 | `action_copy_or_quit()` 的退出分支 |
| F5 | TUI 回归测试和 tmux 验收 |

## 技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 选择实现 | Textual 原生选择 + 极小提取适配 | 保留 `RichLog`，修复当前版本无法提取 Rich 文本的问题 |
| 剪贴板 | Textual `copy_to_clipboard()` | 使用框架提供的 OSC 52，不引入平台依赖 |
| 快捷键 | 一个条件分流动作 | 保留用户熟悉的 `Ctrl+C` 退出语义 |
| 复制提示 | 无提示 | 用户已明确选择静默复制 |
| tmux | 验证现有环境，不改全局配置 | 避免扩大项目权限和配置范围 |
