# Dragon Code 紧凑翼形 Banner Plan

## 架构概览

保留现有 TUI 结构，只调整 Banner 资源和渲染结果。`prompt.py` 使用 Rich 的 `Text` 对象
逐行拼接图标和产品信息，`Static` 直接显示这个 Rich renderable。

```text
固定 4 行图标 + 版本 + 工作目录
              ↓
       render_banner()
              ↓
       Rich Text（双色）
              ↓
       #banner Static
```

## 核心数据与接口

### `DRAGON_BANNER`

```python
DRAGON_BANNER: str
```

保存用户批准的 4 行 Unicode 图标。常量只包含图标，不包含产品信息。

### `render_banner`

```python
def render_banner(version: str, cwd: str) -> Text
```

逐行生成 Rich `Text`：

- 图标使用 `white`。
- `Dragon Code` 使用 `bold white`。
- 版本、说明和工作目录使用 `grey70`。
- 工作目录作为普通文本追加，不经过 markup 解析。

## 模块设计

### `src/dragon_code/prompt.py`

**职责：** 保存系统提示词和固定图标，生成带样式的 Banner。

**实现：**

1. 将旧三头龙替换为批准的 4 行 Unicode 图标。
2. 导入 `rich.text.Text`。
3. 将四行右侧信息组织为简单列表。
4. 使用普通循环逐行追加图标、两个空格和对应信息。
5. 最后一行不追加右侧文字。

### `src/dragon_code/tui.py`

**职责：** 显示 `render_banner()` 返回的 Rich `Text`。

**实现：**

- 保持 `Static` 和 `#banner` 不变。
- 移除没有实际作用的 `markup=False`，直接传入 Rich `Text`。
- 不改变其他组件和事件处理。

### `src/dragon_code/dragon_code.tcss`

**职责：** 控制 Banner 的尺寸与间距。

**实现：**

- 移除旧的红色。
- 使用白色作为没有显式样式内容的默认颜色。
- 保持宽度、高度和内边距不变。

### `tests/test_prompt.py`

**职责：** 验证图标、排版、动态信息和样式。

**覆盖：**

- 固定字符与 4×9 尺寸。
- 旧三头龙特征消失。
- `Text.plain` 中三行信息的位置正确。
- 版本和特殊字符工作目录原样保留。
- Rich Text 同时包含白色、粗体白色和灰色样式。

### `tests/test_tui.py`

**职责：** 验证真实 TUI 中 Banner 能正常显示。

**覆盖：**

- `#banner` 的 renderable 包含新图标和产品信息。
- 标准和窄终端布局继续通过。
- Provider、输入框和其他布局检查保持不变。

## 文件组织

```text
src/dragon_code/
├── prompt.py
├── tui.py
└── dragon_code.tcss

tests/
├── test_prompt.py
└── test_tui.py

specs/night-dragon-banner/
├── DESIGN_HANDOFF.md
├── spec.md
├── plan.md
├── task.md
└── checklist.md
```

## 技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 多色文本 | Rich `Text` | Textual 原生接受 Rich renderable |
| 拼接方式 | 普通循环与 `append` | 简单直观，方便初学者阅读 |
| 工作目录 | 作为纯文本追加 | 方括号等字符不会被解析成 markup |
| 图标字符 | 固定 Unicode | 忠实保留已批准设计 |
| 默认颜色 | 白色 | 与图标主体一致，并替代旧红色 |
| 新依赖 | 不增加 | Rich 已由 Textual 提供并已在项目中使用 |

## 模块交互

1. TUI 启动时取得版本号和当前工作目录。
2. `render_banner()` 创建四行带样式的 Rich `Text`。
3. `Static` 显示该对象。
4. TCSS 只负责布局和默认颜色。

## Spec 覆盖

- F1、F2、F7：固定 Unicode 资源与专项测试覆盖。
- F3–F5：`render_banner()` 和 Rich 样式测试覆盖。
- F6：不修改其他 TUI 行为，现有集成测试覆盖。
- N1–N7：字符精确检查、特殊目录测试、窄终端测试和完整质量门禁覆盖。
- 不存在未覆盖需求或循环依赖。
