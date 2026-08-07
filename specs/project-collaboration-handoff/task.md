# Dragon Code 跨设备协作与开发模式 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|---|---|---|
| 新建 | `AGENTS.md` | 长期协作规则与开发模式 |
| 新建 | `docs/PROJECT_HANDOFF.md` | 当前项目状态与跨设备交接 |
| 新建 | `specs/project-collaboration-handoff/spec.md` | 行为需求与验收标准 |
| 新建 | `specs/project-collaboration-handoff/plan.md` | 两层文档架构与更新策略 |
| 新建 | `specs/project-collaboration-handoff/task.md` | 实现任务与验证顺序 |
| 新建 | `specs/project-collaboration-handoff/checklist.md` | 可观测验收项 |

## T1：建立长期协作指令

**文件：** `AGENTS.md`

**依赖：** 已批准的 spec.md、plan.md

**步骤：**

1. 写明 Dragon Code 名称、中文交流和简单 Python 风格。
2. 完整写入四文档 HARD GATE 和审批规则。
3. 写入一次一个问题、选择题优先和方案比较。
4. 写入教材参考、冲突优先级和差异解释要求。
5. 写入开发验证、tmux、checklist 和证据优先规则。
6. 写入核心源码回顾、学习笔记、Git 和安全要求。

**验证：** 使用 `rg` 搜索 HARD GATE、四份文档、tmux、教材、学习笔记、commit 和 push，期望全部有明确规则。

## T2：建立动态项目交接

**文件：** `docs/PROJECT_HANDOFF.md`

**依赖：** T1

**步骤：**

1. 记录项目定位、仓库、技术栈和当前阶段。
2. 按 ch02–ch07 列出已经完成的用户能力。
3. 画出当前 TUI、Agent、LLM Client、Tool、Permission 和 MCP 调用链。
4. 列出核心文件和最近验证结果。
5. 记录不会同步的密钥、本地配置和飞书登录态。
6. 给出新电脑拉取、安装、配置、启动和继续聊天步骤。
7. 标记学习笔记状态和下一步 ch08。
8. 提供每章验收后的更新模板。

**验证：** 对照 README、Git 日志和 ch07 验收报告，确认章节、命令、测试结果和下一步一致。

## T3：执行一致性与安全检查

**文件：** 本次所有 Markdown 文件

**依赖：** T1、T2

**步骤：**

1. 扫描 TBD、TODO 和空章节。
2. 检查 `AGENTS.md` 与 `PROJECT_HANDOFF.md` 没有职责冲突。
3. 检查没有真实 API Key、Authorization 和本地配置内容。
4. 检查所有本地链接和命令与仓库一致。
5. 确认 `.idea/` 和 `321.txt` 未被纳入改动。

**验证：** 运行文档检索、敏感字符串扫描和 `git diff --check`，期望全部通过。

## T4：验收并记录结果

**文件：** `specs/project-collaboration-handoff/checklist.md`

**依赖：** T3

**步骤：**

1. 按 checklist 逐项读取实际文档。
2. 检查新 Agent 的阅读顺序能够恢复开发模式。
3. 确认新电脑步骤不依赖当前电脑绝对路径。
4. 将通过项勾选并记录命令证据。

**验证：** checklist 无未勾选项，且每项都有文件内容或命令输出作为证据。

## T5：创建本地提交

**文件：** 本次六个新文档

**依赖：** T4

**步骤：**

1. 只暂存本次新增文档。
2. 再次检查暂存区不包含 `.idea/`、`321.txt` 或密钥。
3. 创建本地 Git 提交。
4. 不执行 push，等待用户明确要求。

**验证：** `git log -1 --oneline` 显示本次提交；`git status --short` 只保留用户原有未跟踪文件。

## 执行顺序

```text
T1 → T2 → T3 → T4 → T5
```
