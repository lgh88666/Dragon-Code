# Dragon Code 夜行小龙 Banner Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|---|---|---|
| 修改 | `src/dragon_code/prompt.py` | 用原创夜行小龙替换猫咪图案 |
| 新建 | `tests/test_prompt.py` | 验证图案尺寸、字符和 Banner 文字 |

## T1：新增 Banner 约束测试

**文件：** `tests/test_prompt.py`

**依赖：** 无

**步骤：**

1. 导入 `DRAGON_BANNER` 和 `render_banner()`。
2. 验证图案恰好为 5 行。
3. 验证每行不超过 24 个字符。
4. 验证全部字符均为 ASCII。
5. 验证图案包含两只眼睛、短角和脸部轮廓所需的字符特征。
6. 验证原猫咪特征字符串不再出现。
7. 验证渲染结果仍包含应用名、版本、工作目录和就绪提示。
8. 验证渲染结果以龙图案开头。

**验证：** 修改实现前运行 `uv run pytest tests/test_prompt.py -q`，预期因
`DRAGON_BANNER` 尚未定义而失败，证明测试能捕捉旧实现。

## T2：替换 ASCII Banner

**文件：** `src/dragon_code/prompt.py`

**依赖：** T1

**步骤：**

1. 删除 `CAT_BANNER`。
2. 添加已批准的 5 行 `DRAGON_BANNER` raw 多行字符串。
3. 在常量旁添加原创性和终端兼容性的中文注释。
4. 修改 `render_banner()`，让其使用 `DRAGON_BANNER`。
5. 保持其余 Banner 文字和函数签名不变。

**验证：** 运行 `uv run pytest tests/test_prompt.py -q`，预期全部通过；打印
`render_banner("0.1.0", "/tmp/demo")`，目视确认图案对齐。

## T3：执行回归与质量检查

**文件：** 全部源码和测试

**依赖：** T2

**步骤：**

1. 运行 Ruff 格式检查。
2. 运行 Ruff 静态检查。
3. 运行完整 pytest。
4. 确认 Git 差异中没有 TUI、CSS 或依赖文件的非预期修改。

**验证：**

```text
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
git diff --check
```

所有命令返回退出码 0。

## 执行顺序

```text
T1 → T2 → T3
```

## 自检结果

- Plan 中的两个改动文件均有对应任务。
- 每个任务包含具体步骤和验证方式。
- 任务依赖单向且无循环。
- 接口和常量名称与 `plan.md` 一致。
- 没有加入 Spec 范围外的实现。
