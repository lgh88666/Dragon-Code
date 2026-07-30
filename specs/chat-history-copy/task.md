# 聊天历史选择与复制 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|---|---|---|
| 修改 | `src/dragon_code/tui.py` | 复制/退出条件分流 |
| 修改 | `tests/test_tui.py` | 自动化验证复制和退出 |
| 修改 | `docs/learning-notes.md` | 核心源码回顾 |
| 新建 | `specs/chat-history-copy/*.md` | Spec 驱动文档和验收记录 |

## T1：调整 Ctrl+C 绑定

**文件：** `src/dragon_code/tui.py`
**依赖：** 无

**步骤：**

1. 把 `Ctrl+C` 从直接安全退出改为调用 `copy_or_quit`。
2. 增加 `ConversationLog`，从 `RichLog` 已渲染行中提取所选纯文本。
3. 新增 `action_copy_or_quit()`。
4. 非空选择调用 Textual 剪贴板；空选择调用原安全退出。
5. 添加中文注释说明兼容原因和分流原因。

**验证：** 运行复制与退出定向测试，两个分支均通过。

## T2：补充自动化测试

**文件：** `tests/test_tui.py`
**依赖：** T1

**步骤：**

1. 保留无选择时 `Ctrl+C` 退出测试。
2. 增加有选择时复制且不退出测试。
3. 验证复制后输入框仍可使用，聊天历史未新增提示。
4. 验证绑定指向新的条件动作。

**验证：** `uv run pytest tests/test_tui.py -q` 全部通过。

## T3：运行回归与静态检查

**文件：** 全项目
**依赖：** T2

**步骤：**

1. 运行完整 pytest。
2. 运行 Ruff lint 和 format check。
3. 运行 Python 编译检查。

**验证：** 所有命令成功退出。

## T4：执行 tmux 端到端验收

**文件：** 无
**依赖：** T3

**步骤：**

1. 在 WSL 的 tmux 中启动 Dragon Code。
2. 产生真实聊天历史并确认可回看。
3. 验证无选择时 `Ctrl+C` 安全退出。
4. 结合 Textual 自动化选择测试验证复制分支，并检查 tmux 的 OSC 52 支持状态。

**验证：** 记录实际命令和结果到 checklist。

## T5：源码回顾和学习笔记

**文件：** `docs/learning-notes.md`
**依赖：** T4

**步骤：**

1. 记录文本选择由 Textual Screen 管理。
2. 记录 OSC 52 的作用。
3. 记录 `Ctrl+C` 条件分流调用链。
4. 记录 Windows Terminal 与 tmux 的边界。

**验证：** 笔记包含核心调用链、关键接口、测试证据和面试表达。

## 执行顺序

```text
T1 → T2 → T3 → T4 → T5
```
