# Dragon Code 跨设备协作与开发模式 Plan

## 架构概览

采用“稳定规则 + 动态状态”两层文档结构：

```text
新电脑 / 新聊天
  ↓
AGENTS.md                   稳定规则：怎么协作、怎么开发
  ↓
docs/PROJECT_HANDOFF.md     动态状态：做到哪里、接下来做什么
  ↓
README.md + specs/ + docs/learning-notes.md
  ↓
继续学习或进入下一章 Spec 流程
```

`AGENTS.md` 是执行入口，规则变化较少；`PROJECT_HANDOFF.md` 是交接入口，每章验收后更新。章节细节继续由 `specs/` 保存，知识总结继续由 `docs/learning-notes.md` 保存。

## 文档结构

### AGENTS.md

包含以下固定模块：

1. 项目身份与语言。
2. 代码可读性要求。
3. Spec 驱动 HARD GATE。
4. 澄清与审批规则。
5. 教材参考和冲突优先级。
6. 开发、验证和 tmux 验收。
7. 核心源码回顾与学习笔记。
8. Git、安全和用户文件保护。
9. 新会话恢复入口。

### docs/PROJECT_HANDOFF.md

包含以下动态模块：

1. 项目定位和仓库信息。
2. 当前开发状态。
3. ch02–ch07 已完成功能。
4. 当前核心调用链和关键文件。
5. 最近自动化与 tmux 证据。
6. 本地配置和密钥边界。
7. 新电脑接续步骤。
8. 下一步和待回顾内容。
9. 每章完成后的更新模板。

## 文档交互

```text
用户提出新章节
  ↓
Agent 读取 AGENTS.md
  ↓
Agent 读取 PROJECT_HANDOFF.md 和现有代码
  ↓
四文档 Spec 流程
  ↓
开发 + 自动化验证 + tmux 验收
  ↓
更新 checklist / acceptance report
  ↓
更新 PROJECT_HANDOFF.md
  ↓
本地 Git commit
  ↓ 用户明确要求
Git push
```

## 文件组织

```text
dragonAgent/
├── AGENTS.md
├── README.md
├── docs/
│   ├── PROJECT_HANDOFF.md
│   └── learning-notes.md
└── specs/
    └── project-collaboration-handoff/
        ├── spec.md
        ├── plan.md
        ├── task.md
        └── checklist.md
```

## 规则优先级

1. 用户当前明确指令。
2. 当前功能已经批准的 Spec。
3. 根目录 `AGENTS.md`。
4. `docs/PROJECT_HANDOFF.md` 中的动态状态。
5. 教材和 Vibe Coding Python 参考。
6. Agent 自行推断。

若教材与已批准设计不同，不静默改回教材版本，而是保留当前设计并说明差异。

## 更新策略

- `AGENTS.md`：只有长期协作规则改变时更新。
- `PROJECT_HANDOFF.md`：每章验收后更新能力、测试、核心文件和下一步。
- `learning-notes.md`：源码回顾或用户说“记一下”时更新。
- `specs/`：每个功能独立目录，保存完整审批与验收依据。

## 技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 长期指令位置 | 根目录 `AGENTS.md` | 新 Agent 最容易发现，并与源码一起版本控制 |
| 动态状态位置 | `docs/PROJECT_HANDOFF.md` | 与稳定规则分离，适合频繁更新 |
| 开发模式记录 | 在 AGENTS 中写完整 HARD GATE | 不能依赖聊天记忆或某一章 Spec |
| 教材冲突 | 已批准设计优先，差异解释 | 保持项目连续性，同时便于用户对照学习 |
| 源码学习 | 核心链路 + 学习笔记 | 平衡学习深度与项目进度 |
| Git 推送 | 本地提交自动，推送需授权 | 支持回滚，同时避免未授权外部变更 |
| 密钥同步 | 新电脑手动安全配置 | 防止敏感信息进入 Git 历史 |

## Spec 覆盖

- F1–F7、F9–F11 由 `AGENTS.md` 承载。
- F8、F12 由 `PROJECT_HANDOFF.md` 承载。
- N1–N6 通过文件职责、结构检查和敏感信息扫描验证。
