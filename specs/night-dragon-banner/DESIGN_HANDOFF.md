# Dragon Code 启动图案设计交接

## 交接目标

在新的聊天中专门讨论并设计 Dragon Code 的终端启动图案。当前三头龙 ASCII 方案已被用户
明确否决，不能视为最终设计，也不要直接在它的基础上继续微调。

新聊天应先完成视觉方案讨论和用户确认，再修改代码。

## 项目背景

- 项目名：Dragon Code
- 项目类型：类似 Claude Code 的终端 AI 编程助手
- 实现语言：Python 3.12+
- TUI 框架：Textual
- 当前阶段：ch02，多协议 LLM 终端对话客户端
- 代码风格：写法尽量简单，避免难懂的高级语法，并保留必要的中文注释
- 沟通语言：中文

## 用户的设计偏好

用户希望启动图案：

- 主题必须与“龙”有关。
- 图案要小，不能明显占用终端对话空间。
- 需要有较强的视觉辨识度，不能只是勉强能看出是龙。
- 用户曾考虑《驯龙高手》的夜煞造型。
- 用户提供过一张蓝紫色像素小龙参考图，特点是侧身坐姿、展开单翼、长尾。
- 因完整像素小龙缩成 ASCII 后需要较大尺寸，用户放弃了该方向。
- 用户随后接受参考坦格利安三头龙家徽，并同意使用红色。
- 当前实现的紧凑三头龙字符画被用户评价为“太丑了”，已明确否决。

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

## 新设计需要重新确认的事项

新聊天应一次只讨论一个问题，至少确认以下内容：

1. 图案题材：坦格利安三头龙、原创单头龙、龙蛋、龙眼、龙爪或其他符号。
2. 构图方式：头像、侧影、徽章、文字 Logo 或图形与文字组合。
3. 最大尺寸：是否继续限制为 5×24，或允许增加到 6–8 行。
4. 字符范围：仅 ASCII，还是允许 Unicode 方框、半格和 Braille 字符。
5. 颜色：纯红、红黑双色、蓝紫色或跟随终端主题。
6. 是否只给龙图案着色，还是整个 Banner 文字一起着色。
7. 是否需要同时保留 `Dragon Code` 的文字 Logo。

## 建议的设计流程

1. 先只讨论视觉方向，不修改代码。
2. 提供 3 个差异明显的字符画草案。
3. 每个草案直接使用等宽代码块展示，并标注实际行数和最大宽度。
4. 用户选中一个草案后，再进行 1–2 轮细节调整。
5. 用户明确说“图案通过”后，重新更新四份文档：
   `spec.md → plan.md → task.md → checklist.md`。
6. 四份文档获得批准后才能修改实现。
7. 开发后运行单元测试、Ruff、Textual Pilot 和本地启动检查。
8. 最后按 `checklist.md` 验收；若环境支持，再使用 tmux 做真实端到端测试。

## 设计时应避免

- 不要把箭头符号简单拼成龙头。
- 不要为了满足“三头”而牺牲整体轮廓和美感。
- 不要在用户认可草案前写实现代码。
- 不要仅凭自动测试宣布视觉设计通过。
- 不要擅自增大图案尺寸。
- 不要修改对话、Provider、流式输出或输入区域等无关功能。
- 不要在输出、测试或日志中展示 API Key。

## 新聊天可直接使用的开场 Prompt

```text
请阅读 specs/night-dragon-banner/DESIGN_HANDOFF.md。

这次只讨论 Dragon Code 的终端启动图案设计，暂时不要修改代码。请遵守项目的
mew-spec 流程，一次只问一个问题。先根据交接文档中的偏好和约束，给我 3 个差异明显、
可以直接在终端显示的字符画草案，并标注每个草案的行数和最大宽度。当前代码里的三头龙
方案已经被我否决，不要继续沿用。
```

## 当前验收限制

本机 Windows 环境没有安装 tmux，WSL 也尚未安装。因此当前只能使用：

- 单元测试
- Ruff
- Textual Pilot
- Windows PowerShell 本地启动

tmux 中的真实对话与截图需要等 WSL/tmux 可用后补验。
