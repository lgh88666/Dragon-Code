# Dragon Code 三头龙徽章 Banner Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|---|---|---|
| 修改 | `src/dragon_code/prompt.py` | 保存新的三头龙 ASCII 徽章 |
| 修改 | `src/dragon_code/dragon_code.tcss` | 将 Banner 改为深红色 |
| 修改 | `tests/test_prompt.py` | 验证图案尺寸、字符与三个龙头 |
| 修改 | `tests/test_tui.py` | 验证最终界面的 Banner 颜色 |

## T1：更新 Banner 资源测试

**文件：** `tests/test_prompt.py`

**依赖：** 无

**步骤：**

1. 保留图案恰好 5 行、每行不超过 24 字符的检查。
2. 保留所有字符均为 ASCII 的检查。
3. 检查中央龙头的尖顶、双眼和下颌。
4. 检查左右两个朝外龙头。
5. 检查左右展开和下方收拢的环形轮廓。
6. 检查旧正面龙头的标志性嘴部已经消失。
7. 保留应用名、版本、工作目录和就绪提示检查。

**验证：** 实现前运行 `uv run pytest tests/test_prompt.py -q`，预期新的特征测试失败，
证明测试可以识别旧图案。

## T2：替换三头龙字符画

**文件：** `src/dragon_code/prompt.py`

**依赖：** T1

**步骤：**

1. 用已批准的 5 行三头龙图案替换 `DRAGON_BANNER` 内容。
2. 更新常量旁的中文说明。
3. 保持 raw 多行字符串形式。
4. 保持 `render_banner()` 的签名和拼接逻辑不变。

**验证：** 运行 `uv run pytest tests/test_prompt.py -q`，预期全部通过；打印
`render_banner("0.1.0", "D:\\demo")`，目视确认图案对齐。

## T3：修改并验证 Banner 颜色

**文件：** `src/dragon_code/dragon_code.tcss`、`tests/test_tui.py`

**依赖：** T2

**步骤：**

1. 将 `#banner` 的颜色设置为 `#d13b3b`。
2. 保持其余 `#banner` 样式不变。
3. 在 Textual 启动测试中读取 `#banner` 的最终样式。
4. 断言最终颜色等于 `#d13b3b`。

**验证：** 运行 `uv run pytest tests/test_tui.py -q`，预期全部通过。

## T4：执行回归与质量检查

**文件：** 全部源码和测试

**依赖：** T3

**步骤：**

1. 运行 Ruff 格式检查。
2. 运行 Ruff 静态检查。
3. 运行完整 pytest。
4. 运行 Git 空白错误检查。
5. 检查差异，确认没有业务逻辑或依赖的非预期修改。

**验证：**

```text
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
git diff --check
```

所有命令返回退出码 0。

## T5：端到端验收

**文件：** 无

**依赖：** T4

**步骤：**

1. 在 tmux 中启动 Dragon Code。
2. 截取顶部 Banner，确认三头龙图案对齐并显示为红色。
3. 输入一条真实对话请求。
4. 确认聊天功能正常，并逐项核对 `checklist.md`。
5. 若当前环境没有 tmux，记录阻塞证据，并使用 Textual Pilot 和本地启动冒烟测试覆盖可验证项。

**验证：** tmux 截图和真实对话成功；若环境缺少 tmux，明确保留对应未通过项。

## 执行顺序

```text
T1 → T2 → T3 → T4 → T5
```

## 自检结果

- Plan 中的每个改动文件都有对应任务。
- 每个任务都有具体步骤和验证方式。
- 依赖单向且无循环。
- 常量名、颜色值和接口与 `plan.md` 一致。
- 没有加入 Spec 范围外的功能。
