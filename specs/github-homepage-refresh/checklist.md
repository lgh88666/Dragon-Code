# Dragon Code GitHub 项目主页美化 Checklist

## 首屏与视觉

- [x] 首屏显示 Dragon Code 名称、定位、Dragon Banner 和真实技术徽章。（验证：阅读 README 首屏）
- [x] 表情使用克制且语义一致，没有每行堆叠表情。（验证：人工检查）
- [x] 没有虚假的 CI、覆盖率、License、下载量或 Star 徽章。（验证：检查徽章 URL 和标签）

## 内容完整性

- [x] 能力速览覆盖 ch02–ch13 的核心能力。（验证：对照交接文档）
- [x] Mermaid 图覆盖 TUI、Agent、LLMClient、工具、权限、MCP、Skill、Hook、记忆与 SubAgent。（验证：检查图节点）
- [x] 安装、配置和启动步骤可以直接复制执行。（验证：检查命令与配置示例）
- [x] 命令表与当前 CommandRegistry 和内置 Skill 一致。（验证：对照源码）
- [x] ch14 明确标记为学习/规划中，没有宣传为已实现。（验证：查看进度区）
- [x] 核心源码导航指向真实文件或目录。（验证：本地链接检查）

## 安全与质量

- [x] README 不包含真实 API Key、Authorization 值、个人路径或本地配置。（验证：敏感信息扫描 0 命中）
- [x] Markdown 代码围栏成对，标题层级合理。（验证：32 个围栏，静态检查通过）
- [x] 所有仓库内相对链接对应目标存在。（验证：2 个本地链接全部存在）
- [x] `uv run ruff format --check .` 通过：234 个文件已格式化。
- [x] `uv run ruff check .` 通过。
- [x] `uv run pytest -q` 通过：`530 passed, 2 skipped`。

## GitHub 端到端

- [x] 只提交 README 和本功能 Spec/交接文件，没有提交 `.idea/`、`321.txt` 或本地 Skill。（验证：提交清单）
- [x] 主页提交 `c66a47a` 已推送到 `origin/master`。（验证：`git ls-remote`）
- [x] GitHub 项目主页已包含新标题、徽章、架构与快速开始内容。（验证：远端提交内容 + GitHub 页面 HTTP 200）
