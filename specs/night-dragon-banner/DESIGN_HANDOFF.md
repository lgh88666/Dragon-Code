# Dragon Code 启动图案设计交接

## 交接目标

记录 Dragon Code 终端启动图案的设计结论，并为后续 mew-spec 文档更新和实现提供交接。
旧的三头龙 ASCII 方案已被用户明确否决，不能继续沿用。

视觉讨论现已结束，用户已经确认采用本文件中的最终图案。当前仍未修改实现代码。

## 最终确认的设计

最终图案为紧凑、无脸、抽象的翼形小图标：

```text
 ▗▄   ▄▖
▐██▙▄▟██▌
▝██▀█▀██▘
  ▘   ▝
```

设计结论：

- 实际尺寸：4 行，最大宽度 9 列。
- 字符范围：使用 Unicode 方块及部分块字符。
- 构图含义：中间为紧凑主体，两侧像一双展开的小翅膀；整体可以让人联想到小龙或翼形精灵，
  但不要求明确描绘龙的头部、身体或五官。
- 表情：保持无脸，不添加眼睛。
- 主体颜色：纯白色 `#FFFFFF`。
- 背景：使用终端原有黑色或深色背景，不增加色块、红色描边或渐变。
- 文字：`Dragon Code` 使用白色；版本、说明和工作目录使用灰色。用户表示这些辅助细节
  可按项目现有排版和合理默认值处理。
- 视觉目标：像 Claude Code 的常驻小图标一样紧凑、有品牌感、适合与版本和目录信息并排，
  但图案本身必须保持原创。

建议的 Banner 排版示意：

```text
 ▗▄   ▄▖   Dragon Code  v0.1.0
▐██▙▄▟██▌  Multi-provider coding agent
▝██▀█▀██▘  D:\project
  ▘   ▝
```

用户最终确认：“反正就这个图案其他的我不管”。该回复应视为图案正式通过，不需要在后续
会话中重新发起视觉方向讨论。

## 项目背景

- 项目名：Dragon Code
- 项目类型：类似 Claude Code 的终端 AI 编程助手
- 实现语言：Python 3.12+
- TUI 框架：Textual
- 当前阶段：ch02，多协议 LLM 终端对话客户端
- 代码风格：写法尽量简单，避免难懂的高级语法，并保留必要的中文注释
- 沟通语言：中文

## 用户的设计偏好

以下内容记录设计探索过程中的历史偏好：

- 主题必须与“龙”有关。
- 图案要小，不能明显占用终端对话空间。
- 需要有较强的视觉辨识度，不能只是勉强能看出是龙。
- 用户曾考虑《驯龙高手》的夜煞造型。
- 用户提供过一张蓝紫色像素小龙参考图，特点是侧身坐姿、展开单翼、长尾。
- 因完整像素小龙缩成 ASCII 后需要较大尺寸，用户放弃了该方向。
- 用户随后接受参考坦格利安三头龙家徽，并同意使用红色。
- 当前实现的紧凑三头龙字符画被用户评价为“太丑了”，已明确否决。
- 用户随后放弃具象龙形，转向类似 Claude Code 常驻标志的紧凑小图标。
- 用户认可最终图标带来的“小龙主体加一双翅膀”的联想，但不要求继续强化龙的具体形象。
- 曾讨论红色、黑红双色和红色描边，最终均未采用；确认使用纯白主体。

参考图片位于：

```text
D:\Users\admin\AppData\Roaming\LarkShell-ka-transsion\sdk_storage\
e4102e53b9039db13462787c0075243d\resources\images\
img_v3_02142_1a6bbc8c-108e-45b4-85b3-34896bed928g.jpg
```

## 当前已否决的图案

```text
       /^\
  <<==<o o>==>>
 /\/\  \^/  /\/\
<    \ /|\ /    >
 \____V_|_V____/
```

否决原因：整体观感不好，不能达到用户期望的设计质量。

注意：已有自动测试只证明它符合尺寸、字符和代码约束，不能证明它美观。新方案不能以
“测试通过”为设计完成标准，必须让用户先看到字符画并明确认可。

## 当前代码状态

相关文件：

```text
src/dragon_code/prompt.py
src/dragon_code/dragon_code.tcss
tests/test_prompt.py
tests/test_tui.py
specs/night-dragon-banner/spec.md
specs/night-dragon-banner/plan.md
specs/night-dragon-banner/task.md
specs/night-dragon-banner/checklist.md
```

当前实现：

- `DRAGON_BANNER` 在 `src/dragon_code/prompt.py` 中集中定义。
- `render_banner(version, cwd)` 将图案和应用信息拼接为字符串。
- `src/dragon_code/tui.py` 通过 `Static(..., id="banner", markup=False)` 展示 Banner。
- `src/dragon_code/dragon_code.tcss` 将整个 `#banner` 设置为深红色 `#d13b3b`。
- 当前图案为 5 行纯 ASCII，最长行不超过 24 列。
- 当前测试总数为 41 项。

当前 Git 状态：

- 分支：`master`
- 远端：`https://github.com/lgh88666/Dragon-Code.git`
- 当前三头龙实现提交：`4d5bc5b feat: 使用红色三头龙启动徽章`
- 该提交已经推送到远端。

## 已确认事项

1. 图案题材：原创抽象翼形符号，不再要求具象龙形。
2. 构图方式：小图标与 `Dragon Code`、版本及目录信息并排。
3. 最大尺寸：图标固定为 4×9。
4. 字符范围：允许并采用 Unicode 方块及部分块字符。
5. 颜色：图标主体为纯白色 `#FFFFFF`。
6. 着色范围：图标和产品名为白色，辅助信息为灰色。
7. 文字 Logo：保留 `Dragon Code`。

## 后续流程

1. 视觉方案已通过，不再重复提供草案或追问颜色、题材和尺寸。
2. 按 mew-spec 顺序更新四份文档：
   `spec.md → plan.md → task.md → checklist.md`。
3. 四份文档获得批准后才能修改实现。
4. 实现时替换 `DRAGON_BANNER`，调整 Banner 的颜色和并排信息布局，并同步测试。
5. 开发后运行单元测试、Ruff、Textual Pilot 和 Windows PowerShell 本地启动检查。
6. 最后按 `checklist.md` 验收；若环境支持，再使用 tmux 做真实终端端到端测试。

## 设计时应避免

- 不要把箭头符号简单拼成龙头。
- 不要为了满足“三头”而牺牲整体轮廓和美感。
- 不要重新启用三头龙、完整像素龙、大型字符画、表情脸或红色描边方向。
- 不要在四份 mew-spec 文档批准前修改实现代码。
- 不要仅凭自动测试宣布视觉设计通过。
- 不要擅自增大图案尺寸。
- 不要修改对话、Provider、流式输出或输入区域等无关功能。
- 不要在输出、测试或日志中展示 API Key。

## 后续会话可直接使用的开场 Prompt

```text
请阅读 specs/night-dragon-banner/DESIGN_HANDOFF.md。

Dragon Code 的终端启动图案已经获得用户确认，不要重新讨论视觉方向。请遵守项目的
mew-spec 流程，先按 spec.md → plan.md → task.md → checklist.md 的顺序更新四份文档，
每次只处理和确认一份文档。四份文档全部批准前不要修改实现代码。
```

## 当前验收限制

本机 Windows 环境没有安装 tmux，WSL 也尚未安装。因此当前只能使用：

- 单元测试
- Ruff
- Textual Pilot
- Windows PowerShell 本地启动

tmux 中的真实对话与截图需要等 WSL/tmux 可用后补验。
