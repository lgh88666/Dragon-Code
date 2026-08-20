# Dragon Code GitHub 项目主页美化 Spec

## 背景

当前 README 能说明安装、配置和已有功能，但仍停留在 ch09，长段落较多，项目亮点、架构和当前完成度不容易快速识别。Dragon Code 已完成 ch02–ch13，需要让秋招面试官和普通开发者在较短时间内理解它是什么、解决什么问题、如何运行，以及它与普通聊天套壳的区别。

## 目标

- **专业首屏**：使用清晰标题、短标语、真实徽章和终端风格 Banner，在首屏建立项目定位。
- **克制趣味**：使用少量龙主题与功能语义表情，增加辨识度，但不把 README 做成表情堆叠。
- **能力速览**：按 Agent 核心、工程上下文、安全扩展和交互体验分组呈现 ch02–ch13 能力。
- **快速上手**：让新用户能顺序完成安装、配置和启动，并明确本地密钥不能提交。
- **架构可读**：用一张 GitHub 可渲染的 Mermaid 图串起 TUI、Agent Loop、LLMClient、工具、权限、MCP、Skill、Hook、记忆与 SubAgent。
- **秋招展示**：突出项目的工程深度、验证证据和源码学习价值，而不仅是“调用模型 API”。

## 功能需求

- F1：README 首屏展示 Dragon Code 名称、简洁中文定位、ASCII Dragon Banner 和少量真实徽章。
- F2：提供项目亮点区，用简短条目解释自主 Agent Loop、多协议、工具系统、权限、MCP、上下文、记忆、Skill、Hook 与 SubAgent。
- F3：提供架构概览图，表达用户请求进入 TUI 后，经 Agent Loop 调用 LLM 与工具基础设施并返回结果的主链路。
- F4：提供可复制的安装、Provider 配置和启动步骤，兼顾 PowerShell 与通用命令。
- F5：提供常用交互命令表，覆盖 `/help`、`/plan`、`/do`、`/compact`、`/resume`、`/skill`、`/hooks` 和退出操作。
- F6：提供章节进度或能力演进区，准确显示 ch02–ch13 已完成，ch14 Worktree 尚在学习/规划阶段。
- F7：保留权限、密钥安全、MCP 配置和开发验证等必要信息，但压缩重复段落并改善导航。
- F8：提供项目结构和核心源码入口，帮助面试官快速定位 Agent、客户端、工具、权限和子 Agent 实现。

## 非功能需求

- N1：不添加无法验证的 GitHub Actions、测试覆盖率、下载量、Star、License 或性能徽章。
- N2：表情只用于标题或关键标签，整体保持克制、统一且适合技术项目。
- N3：README 中不出现真实 API Key、Authorization、个人本地路径或本地配置内容。
- N4：不依赖仓库外部截图和容易失效的第三方图片；徽章仅使用稳定的 shields.io 静态/技术标签。
- N5：移动端和窄屏仍可阅读，避免超宽表格和过长单行。
- N6：所有命令、功能和进度描述必须与当前代码及验收记录一致。

## 不做的事

- 不创建新 Logo、演示 GIF、宣传视频或独立文档站。
- 不修改 Python 实现、TUI 行为、配置格式或项目版本号。
- 不添加尚未实现的 Worktree、Agent Team 等功能说明为“已完成”。
- 不创建 GitHub Actions、Release、Issue 模板、PR 模板或 License 文件。
- 不删除详细设计与验收文档，只在 README 中提供必要入口。

## 验收标准

- AC1：打开 GitHub 项目主页，首屏能在不滚动太多的情况下看见名称、定位、徽章、Banner 和核心价值。
- AC2：README 明确覆盖 ch02–ch13 的主要能力，且没有继续写成“当前只完成 ch02–ch09”。
- AC3：Mermaid 架构图语法完整，节点关系与当前核心调用链一致。
- AC4：全新用户能够根据 README 完成 `uv sync --locked`、复制配置并运行 `uv run dragon-code`。
- AC5：常用命令表与当前 Command/Skill 能力一致，不宣传不存在的命令。
- AC6：README 明确区分已完成功能与规划中的 ch14，不产生误导。
- AC7：Markdown 链接、代码围栏、标题层级和相对路径通过静态检查，无断裂的仓库内链接。
- AC8：敏感信息扫描无真实 Key、Token 或 Authorization 值。
