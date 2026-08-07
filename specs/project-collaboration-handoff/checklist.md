# Dragon Code 跨设备协作与开发模式 Checklist

> 每项通过读取实际文件或运行命令验证。

## 长期开发模式

- [x] 根目录存在 `AGENTS.md`，新 Agent 能直接发现长期规则。（验证：`Test-Path AGENTS.md` 返回 True）(AC1)
- [x] 明确项目统一称为 Dragon Code，MewCode 自动转换。（验证：搜索 `Dragon Code` 和 `MewCode`）(AC1)
- [x] 明确中文回答、中文注释和简单 Python 风格。（验证：搜索对应规则）(AC1)
- [x] 完整记录 `spec.md → plan.md → task.md → checklist.md` HARD GATE。（验证：搜索四个文件名和“禁止实现”）(AC2)
- [x] 记录默认逐阶段审批和用户显式批量批准规则。（验证：搜索“批量批准”）(AC2)
- [x] 记录一次一个问题、选择题优先、推荐项第一和 2–3 种方案。（验证：搜索需求澄清规则）(AC2)
- [x] 记录教材 Python 为主要参考、已批准设计优先、差异必须解释。（验证：搜索“教材”和“差异”）(AC3)
- [x] 记录 task 验证、完整测试、tmux 真实对话和 checklist 逐项验收。（验证：搜索验证命令与 tmux）(AC4)
- [x] 记录核心源码回顾和 `docs/learning-notes.md` 更新规则。（验证：搜索文件路径）(AC5)
- [x] 记录每章验收后本地 commit、只有明确要求才 push。（验证：搜索 Git 规则）(AC7)

## 项目交接

- [x] `PROJECT_HANDOFF.md` 列出 ch02–ch07 的完成状态和主要能力。（验证：逐章搜索）(AC6)
- [x] 交接文档包含当前核心调用链和关键源码入口。（验证：检查调用链和文件表）(AC6)
- [x] 交接文档记录最近 `226 passed, 2 skipped` 和 ch07 tmux 结果。（验证：搜索测试数字和 MCP）(AC6)
- [x] 交接文档记录下一步 ch08 及 ch06/ch07 学习笔记待整理状态。（验证：检查“下一步”）(AC6)
- [x] 新电脑步骤包含 clone/pull、`uv sync --locked`、本地配置和启动命令。（验证：逐条执行静态检查）(AC8)
- [x] 明确 API Key、本地配置和登录态不通过 Git 同步。（验证：检查安全边界）(AC8/AC9)
- [x] 包含每章验收后的交接更新模板。（验证：检查模板小节）(AC6)

## 一致性与安全

- [x] 六个目标文档均存在且无 TBD/TODO。（验证：文件存在检查 + `rg "TBD|TODO"` 无命中）(AC10)
- [x] `AGENTS.md` 只放稳定规则，`PROJECT_HANDOFF.md` 只放动态状态。（验证：人工对照职责）(AC10)
- [x] 敏感信息扫描无真实 API Key、长 Bearer Token 或用户邮箱。（验证：`rg` 安全扫描）(AC9)
- [x] `git diff --check` 通过。（验证：命令退出码为 0）(AC10)
- [x] `.idea/` 和 `321.txt` 未进入暂存和提交。（验证：`git status --short` 与 `git diff --cached --name-only`）(AC9)

## Git

- [x] 本次文档已创建本地提交。（验证：`3469095 docs: record project workflow and handoff`）(AC7)
- [x] 未自动推送 GitHub。（验证：本地提交完成后等待用户明确指令）(AC7)

## 实际验收记录

- 日期：2026-08-07。
- 文件：六个目标文档全部存在。
- 占位符：稳定规则、交接、spec 和 plan 中无真实 TBD/TODO。
- 安全扫描：无真实 API Key、长 Bearer Token 或用户邮箱。
- Git 检查：`git diff --cached --check` 通过，`.idea/` 和 `321.txt` 未提交。
- 本地提交：`3469095 docs: record project workflow and handoff`。
- 远端状态：未执行 push，等待用户明确授权。
