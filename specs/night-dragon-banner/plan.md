# Dragon Code 三头龙徽章 Banner Plan

## 架构概览

本次沿用现有 Banner 渲染链，不新增模块和依赖。字符画继续由 `prompt.py` 集中保存，
颜色继续由 Textual CSS 控制。

```text
DRAGON_BANNER
    → render_banner(version, cwd)
    → DragonCodeApp.compose()
    → #banner Static
    → dragon_code.tcss 设置红色
```

## 核心接口

### `DRAGON_BANNER`

类型为普通字符串，保存恰好 5 行的纯 ASCII 三头龙徽章。

### `render_banner(version: str, cwd: str) -> str`

接口和返回类型保持不变。将字符画、应用名称、版本、工作目录和就绪提示拼成完整文本。

## 模块设计

### `src/dragon_code/prompt.py`

**职责：** 保存系统提示词、三头龙字符画，并生成 Banner 文本。

**改动：**

- 替换现有 `DRAGON_BANNER` 内容。
- 使用对称构图：中央龙头朝上，左右龙头分别朝外。
- 左右展开部分表示双翼，下方轮廓向中央收拢，模拟环形徽章。
- 更新常量旁的中文说明。
- `render_banner()` 保持不变。

### `src/dragon_code/dragon_code.tcss`

**职责：** 控制 TUI 组件样式。

**改动：**

- 将 `#banner` 的颜色从主题强调色改为固定的深红色 `#d13b3b`。
- 尺寸、内边距和其他样式保持不变。

### `tests/test_prompt.py`

**职责：** 验证图案内容和 Banner 文本。

**改动：**

- 保留 5 行、24 列、纯 ASCII 检查。
- 将旧正面龙头特征检查改成三头龙特征检查。
- 检查旧图案的眼睛和嘴部特征已经消失。
- 保留应用名称、版本、目录和就绪提示检查。

### `tests/test_tui.py`

**职责：** 验证 Banner 在真实 Textual 应用中的样式和布局。

**改动：**

- 在现有启动测试中检查 `#banner` 的最终颜色为 `#d13b3b`。
- 继续复用标准与窄终端布局测试。

## ASCII 图案设计

```text
       /^\
  <<==<o o>==>>
 /\/\  \^/  /\/\
<    \ /|\ /    >
 \____V_|_V____/
```

设计说明：

- 第一、二行构成朝上的中央龙头。
- 第二行两端的箭头状轮廓表示向左和向右的龙头。
- 第三、四行使用展开的翼形轮廓连接三个龙头。
- 第五行向中央收拢，体现环形徽章的下半部分。
- 图案恰好 5 行，最长行不超过 24 列，全部使用 ASCII 字符。

## 文件组织

```text
specs/night-dragon-banner/
├── spec.md
├── plan.md
├── task.md
└── checklist.md

src/dragon_code/
├── prompt.py
└── dragon_code.tcss

tests/
├── test_prompt.py
└── test_tui.py
```

## 技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 构图 | 对称三头龙徽章 | 5 行内仍能明确表达三个朝向 |
| 字符范围 | 纯 ASCII | 各终端字符宽度稳定 |
| 字符串形式 | Python raw 多行字符串 | 反斜杠不需要重复转义，容易阅读 |
| 颜色实现 | Textual CSS 固定深红色 | 实现简单，不改变 Python 渲染接口 |
| 渲染入口 | 保留 `render_banner()` | 避免影响 TUI 和其他调用方 |
| 测试方式 | 资源测试 + Textual Pilot | 同时验证字符画约束和最终界面样式 |
| 新依赖 | 不增加 | 纯文本和 CSS 已满足需求 |

## Spec 覆盖检查

- F1、F2、F4：由新 `DRAGON_BANNER` 和专项测试覆盖。
- F3：由 `#banner` CSS 和 Textual Pilot 测试覆盖。
- F5：保持 `render_banner()` 接口及原文字测试。
- F6：不修改对话、Provider 和输入输出模块。
- N1–N5：由尺寸、ASCII、布局、依赖和完整质量门禁覆盖。
- 所有功能需求和验收标准都有明确实现或验证归属。
