# Dragon Code 紧凑翼形 Banner Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|---|---|---|
| 修改 | `src/dragon_code/prompt.py` | 保存图标并生成双色并排 Banner |
| 修改 | `src/dragon_code/tui.py` | 显示 Rich Text Banner |
| 修改 | `src/dragon_code/dragon_code.tcss` | 移除旧红色并设置默认白色 |
| 修改 | `tests/test_prompt.py` | 验证字符、布局、动态文本和样式 |
| 修改 | `tests/test_tui.py` | 验证真实 TUI 展示 |

## T1：更新 Banner 专项测试

**文件：** `tests/test_prompt.py`

**依赖：** 无

**步骤：**

1. 断言图标内容与批准版本完全相同。
2. 断言图标为 4 行，每行显示宽度不超过 9 列。
3. 断言旧三头龙特征不再存在。
4. 断言渲染结果为 Rich `Text`。
5. 断言产品名、版本、说明和工作目录位于正确行。
6. 使用带空格和方括号的目录，断言内容原样保留。
7. 断言结果包含白色、粗体白色和灰色样式。

**验证：** 实现前运行 `uv run pytest tests/test_prompt.py -q`，预期因旧图案和字符串返回值
而失败。

## T2：实现固定图标与双色 Banner

**文件：** `src/dragon_code/prompt.py`

**依赖：** T1

**步骤：**

1. 将 `DRAGON_BANNER` 替换为批准的 4 行 Unicode 图标。
2. 添加简短中文注释。
3. 导入 Rich `Text`。
4. 将 `render_banner()` 的返回类型改为 `Text`。
5. 使用普通列表保存四行右侧信息。
6. 使用 `for` 循环逐行追加图标和对应信息。
7. 对图标、产品名和辅助信息分别应用批准的样式。

**验证：** 运行 `uv run pytest tests/test_prompt.py -q`，全部通过；打印 `.plain` 目视确认。

## T3：接入 TUI 并清理旧颜色

**文件：** `src/dragon_code/tui.py`、`src/dragon_code/dragon_code.tcss`

**依赖：** T2

**步骤：**

1. `Static` 直接接收 `render_banner()` 的结果。
2. 移除 Banner 构造中的 `markup=False`。
3. 将 `#banner` 默认颜色由旧红色改为白色。
4. 不修改 Banner 的尺寸和内边距。
5. 更新 TUI 测试检查新内容。

**验证：** 运行 `uv run pytest tests/test_tui.py -q`，全部通过。

## T4：完整质量检查

**文件：** 全部源码和测试

**依赖：** T3

**步骤：**

1. 运行专项测试。
2. 运行完整 pytest。
3. 运行 Ruff 格式检查。
4. 运行 Ruff 静态检查。
5. 运行 Git 空白错误检查。
6. 检查差异没有无关业务改动，不提交 `.idea/`。

**验证：**

```text
uv run pytest -q
uv run ruff format --check .
uv run ruff check .
git diff --check
```

全部返回退出码 0。

## T5：本地展示与验收

**文件：** `specs/night-dragon-banner/checklist.md`

**依赖：** T4

**步骤：**

1. 在新 PowerShell 窗口运行 `uv run dragon-code`。
2. 让用户直接查看最终图案。
3. 使用 Textual Pilot 验证标准和窄终端。
4. 按 `checklist.md` 记录证据。
5. 本机无 tmux 时保留对应待验项。

**验证：** 应用进程正常运行，用户可以看到新 Banner。

## 执行顺序

```text
T1 → T2 → T3 → T4 → T5
```

## 自检

- 每个 Plan 模块都有任务。
- 每个任务都有验证步骤。
- 任务依赖单向且无循环。
- 接口、常量和样式与 Plan 一致。
- 没有 Spec 范围外的实现。
