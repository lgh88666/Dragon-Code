# ch11：Skill 系统验收报告

## 结论

- ch11 功能实现、自动化回归和真实 Anthropic tmux 主链路通过。
- Checklist：`69/74` 已验证。
- 未完成的 5 项均有明确边界：WSL 原生 Python 子进程、真实 OpenAI 端点、真实 `/commit`、完整跑完 `/review` 摘要、tmux 热更新三段对比。相应核心逻辑已由自动化测试覆盖，本报告不把它们伪装成真实 tmux 证据。

## 自动化证据

- `uv sync --locked`：57 个包检查通过，没有增加意外依赖。
- `uv run ruff format --check .`：180 个文件已格式化。
- `uv run ruff check .`：通过。
- `uv run python -m compileall -q src tests`：通过。
- `uv run pytest -q`：`442 passed, 2 skipped in 16.58s`。
- `uv build`：源码包和 wheel 构建成功。
- wheel 内容检查：`commit`、`review`、`test` 三个内置 `SKILL.md` 均已打包。
- `git diff --check`：通过。

自动化覆盖了解析与格式错误、三级覆盖、稳定摘要、持续激活、白名单并集和拒绝、fork 三种上下文、模型覆盖、JSON 子进程、超时与取消、权限与沙箱、串行调度、命令动态注册、热更新回退、生命周期清理、TUI 管理界面和 ch02–ch10 全量回归。

## tmux 真实证据

真实配置为 Anthropic 协议兼容端点，模型为 `deepseek-v4-pro`。tmux 运行的是项目当前源码，未打印或读取 API Key。

### 通过

- [x] **自然语言自动激活**：请求读取并总结 ch11 Spec，模型先调用 `LoadSkill(name=e2e-summary)`，下一轮调用 `Read(specs/ch11-skill-system/spec.md)`，最后给出三点摘要；无需用户指定 Skill 名。
- [x] **目录型自定义工具**：输入 `/e2e-tool 龙焰测试`，界面显示 inline Skill 和 `skill__e2e_tool__echo(text=龙焰测试)` 工具行。
- [x] **人在回路**：自定义工具首次调用弹出“允许本次 / 永久允许 / 拒绝”菜单；选择允许本次后脚本返回 `龙焰测试`。
- [x] **JSON 回灌**：模型根据脚本标准输出继续回答“回声内容为：龙焰测试”，证明 ToolResult 已进入后续模型请求。
- [x] **fork 实时展示**：`/review` 打开目标选择界面，选择当前 Git 改动后，独立 Skill 连续显示 Glob、Read、工具结果和迭代进度，事件带有真实发生顺序。
- [x] **取消与恢复**：review fork 运行到第 6 轮时按 Esc，显示“当前任务已取消”；随后发送“只回复 OK”，模型正常返回 `OK`。
- [x] **Skill 管理**：`/skill` 列出 commit、review、test 和两个临时项目 Skill，显示来源、模式、上下文、白名单、自定义工具及“不是操作系统级沙箱”提示；按 `R` 可重载。
- [x] **退出清理**：`/exit` 后回到正常命令提示符；检查结果 `dragon_code_processes=0`，tmux 会话随后关闭。
- [x] **临时数据清理**：验收用 `e2e-summary`、`e2e-tool` 文件均已删除，没有进入 Git 范围。

### 真实验收中主动停止的场景

- `/review` 已证明 fork 创建、上下文读取、事件转发和取消清理，但为避免继续消耗大量 Token，没有等待完整审查摘要；最终摘要回流由可控自动化测试验证。
- 没有真实执行 `/commit`，避免在验收过程中让模型提交尚未审阅的代码；参数替换、白名单和 inline 执行由自动化测试及目录型 inline Skill 真机链路分别验证。
- 热更新成功与损坏回退由临时文件自动化测试验证，没有在真实 TUI 中反复破坏项目 Skill。

## 尚未完成的 5 项

- [ ] **WSL 原生 JSON 子进程**：当前 WSL 有 tmux 和 Python，但没有 uv/pip；在线安装 uv 下载超时。Windows JSON 子进程与中文参数已真实通过。
- [ ] **真实 OpenAI 端点**：本机只有 Anthropic 协议配置；OpenAI 请求适配与 Skill 行为由自动化回归覆盖。
- [ ] **真实 `/commit` 场景**：为保护当前未提交开发成果未执行模型提交。
- [ ] **完整 `/review` 摘要回流**：真实 fork 在第 6 轮主动取消；摘要回流由单元与集成测试覆盖。
- [ ] **tmux 热更新三段对比**：解析、成功更新和失败回退均由临时目录测试覆盖。

## 验收中观察到的运行细节

1. Slash Command 的完整主名称第一次 Enter 用于接受补全，第二次 Enter 才执行，符合 ch10 已批准交互。
2. Windows Dragon Code 通过 WSL tmux 驱动时，必须保留稳定的 `cmd.exe` 父进程；这是验收启动方式问题，不是 Skill 逻辑错误。
3. review Skill 面对较大工作树会快速消耗上下文，因此真实验收只观察到足以证明 fork 与事件流的阶段后主动取消。

## 教材 Python 方案对照

### 保持一致

- YAML frontmatter + Markdown SOP、三级加载、两阶段披露、Slash Command 与自动触发、inline/fork、`allowedTools`、`tool.json` 和内置 Skill 样板。

### Dragon Code 的差异

- fork 与自定义工具继续经过 ch06 五层权限，不因 Skill 身份绕过安全检查。
- 自定义 Python 工具放在独立子进程，以 JSON stdin/stdout 通信，不导入主进程。
- `/skill` 使用交互式管理界面，而不是要求用户记忆 list/info/reload 子命令。
- fork 内部事件实时展示，但主会话只接收最终摘要；inline 不允许切换主会话模型。
