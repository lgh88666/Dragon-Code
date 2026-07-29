# Dragon Code 夜行小龙 Banner Plan

## 架构与修改范围

本次不新增运行模块，只修改现有 Banner 资源并补充针对性测试。

### `src/dragon_code/prompt.py`

- 将 `CAT_BANNER` 替换为 `DRAGON_BANNER`。
- 保存最终 5 行以内的纯 ASCII 夜行小龙头像。
- `render_banner()` 改用新常量。
- 应用名、版本、工作目录和就绪提示的拼接逻辑保持不变。

### `tests/test_prompt.py`

- 检查猫咪图案已消失。
- 检查龙图案的行数、最大宽度和字符范围。
- 检查版本、工作目录及就绪提示仍存在。

### 不修改的模块

`src/dragon_code/tui.py` 与 `src/dragon_code/dragon_code.tcss` 不修改。TUI 继续调用原来的
`render_banner()`，现有模块交互保持不变。

```text
DRAGON_BANNER
    → render_banner(version, cwd)
    → DragonCodeApp.compose()
    → 顶部 Static 显示
```

## ASCII 图案设计

```text
      /\     /\
  ___/  \___/  \___
 /  \  o     o  /  \
<    \    ^    /    >
 \____\__===__/____/
```

设计说明：

- 第一行表示短龙角。
- 第二行表示圆润且有棱角的头顶。
- 第三行使用倾斜眉线和大眼睛表现可爱与敏捷。
- 第四行表示脸部尖角和小鼻子。
- 第五行表示下颌和略带坏笑的嘴部。
- 图案共 5 行，最长行不超过 24 列。
- 全部使用 ASCII 字符。
- 造型为原创，不包含具体影视角色的标志性细节。

资源旁添加中文注释：

```python
# 原创夜行小龙头像：紧凑、终端友好，不复刻具体影视角色。
DRAGON_BANNER = ...
```

## 文件组织

```text
specs/night-dragon-banner/
├── spec.md
├── plan.md
├── task.md
└── checklist.md

src/dragon_code/
└── prompt.py

tests/
└── test_prompt.py
```

## 测试设计

`test_prompt.py` 验证：

- `DRAGON_BANNER` 恰好为 5 行。
- 每行宽度不超过 24 个字符。
- 所有字符均为 ASCII。
- 图案包含约定的眼睛和龙角特征。
- 原猫咪特征字符串不再存在。
- `render_banner()` 仍包含 Dragon Code、版本、工作目录和就绪提示。
- 图案是 `render_banner()` 输出的首个内容块。

现有 `test_tui.py` 继续验证 Banner 在标准和窄终端中可以显示。

## 技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 图案常量 | `DRAGON_BANNER` | 名称与内容一致，删除猫咪语义 |
| 字符范围 | 纯 ASCII | 各终端字符宽度稳定 |
| 字符串形式 | Python raw 多行字符串 | 反斜杠无需重复转义，图案容易阅读 |
| 渲染入口 | 保留 `render_banner()` | 不影响 TUI 和其他调用方 |
| 测试方式 | 尺寸、字符与关键特征测试 | 约束需求并允许未来微调造型 |
| 新依赖 | 不增加 | 纯文本资源无需依赖 |

## Spec 覆盖检查

- F1–F3：由 `DRAGON_BANNER` 和专项测试覆盖。
- F4：保持 `render_banner()` 接口并测试原有文字。
- F5：不修改 TUI、CSS 或其他运行模块。
- N1–N4：尺寸、ASCII、集中定义及原创设计覆盖。
- N5：完整测试和 Ruff 质量门禁覆盖。
- 所有功能需求和验收标准均有明确实现或验证归属。
