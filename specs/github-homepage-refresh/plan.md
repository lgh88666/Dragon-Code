# Dragon Code GitHub 项目主页美化 Plan

## 架构概览

本次只重构仓库根目录 `README.md`，不改变运行时代码。README 采用“首屏定位 → 能力速览 → 架构 → 快速开始 → 操作与配置 → 源码导航 → 进度与验证”的阅读路径，让面试官先看到工程价值，让使用者随后获得可执行步骤。

## 页面模块

### Hero 首屏

**职责：** 展示 Dragon Code 名称、终端 Dragon Banner、中文价值主张和真实技术徽章。

**设计：** 使用 GitHub 支持的居中 HTML 与 Markdown；表情集中在标题和导航，不进入每条正文。

### 能力速览

**职责：** 把 ch02–ch13 的长列表压缩为四组能力卡片：自主执行、上下文、扩展、安全与协作。

### 系统架构

**职责：** 使用 Mermaid `flowchart` 表达 TUI、Command、Agent、LLMClient、工具调度、权限、MCP、Skill、Hook、记忆和 SubAgent 的关系。

### 快速开始与配置

**职责：** 提供 Python/uv 环境要求、安装、Provider 配置和启动命令；详细 MCP、权限和持久化说明放入折叠块，降低首页长度。

### 操作、源码与进度

**职责：** 用紧凑表格呈现 Slash Command、源码入口和章节进度；明确 ch14 尚未实现。

## 文件组织

```text
Dragon-Code/
├── README.md
├── docs/PROJECT_HANDOFF.md
└── specs/github-homepage-refresh/
    ├── spec.md
    ├── plan.md
    ├── task.md
    ├── checklist.md
    └── acceptance-report.md
```

## 内容数据来源

- 当前版本与 Python 要求：`pyproject.toml`。
- 命令名称与行为：`src/dragon_code/command/builtins.py`。
- 内置 Skill：`src/dragon_code/builtin_skills/`。
- ch02–ch13 能力与证据：`docs/PROJECT_HANDOFF.md` 和各章验收报告。
- 启动方式与配置结构：现有 README、配置模型和示例文件。

## 验证方式

- 检查 Markdown 标题、围栏和 Mermaid 围栏是否成对。
- 提取相对链接并验证对应文件存在。
- 检查 README 不包含真实 Token、个人路径和虚假徽章。
- 运行 Ruff 与全量 pytest，证明纯文档改动没有夹带代码回归。
- 推送后读取 GitHub README 页面，确认远端已更新。

## 技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 视觉方向 | 克制的终端龙主题 | 与产品 Banner 一致，同时保持专业 |
| 徽章 | Python、Textual、MCP、Ruff、章节状态 | 都能由仓库事实验证 |
| 架构图 | GitHub 原生 Mermaid | 无需新增图片资产，后续容易维护 |
| 详细配置 | `<details>` 折叠 | 保留可操作信息但减少首页压迫感 |
| 语言 | 中文为主，保留必要英文术语 | 符合项目与秋招目标 |
| 截图 | 本次不添加 | 当前没有稳定、脱敏且适合长期维护的截图资产 |
