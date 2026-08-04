# Dragon Code ch06 权限系统验收报告

## 结论

权限系统实现完成。自动化测试、格式化和 lint 全部通过；真实 DeepSeek（Anthropic 协议）tmux 场景跑通 Read → Write → HITL → 工具结果回灌 → 最终答复完整链路。

Checklist 共 49 项：

- **完整通过：40 项**
- **自动化通过、真实 tmux 环境未完整覆盖：9 项**
- **功能失败：0 项**

## 自动化证据

- `uv run ruff format --check .`：通过，88 个文件格式正确。
- `uv run ruff check .`：通过，无告警。
- `uv run pytest -q`：`182 passed, 2 skipped`。
- `git diff --check`：通过，无空白错误。
- `git check-ignore -v .dragon-code/settings.local.yaml`：命中 `.gitignore`。

两项 skip 均为当前 Windows 用户无创建符号链接权限：

1. 既有文件工具的符号链接逃逸测试。
2. ch06 PathSandbox 的符号链接逃逸测试。

普通项目路径、新建多级路径、绝对越界和 `../` 越界测试均通过；符号链接防逃逸代码保留，并额外处理 dangling symlink。

## 已通过的核心行为

- [x] 固定危险命令黑名单覆盖 Unix/Linux、PowerShell、CMD 与 WSL 样例。
- [x] bypassPermissions 不能绕过黑名单、沙箱和显式 deny。
- [x] Read/Write/Edit/Glob/Grep 项目根沙箱与路径参数校验。
- [x] 命令规则与文件规则的精确、`*`、`**` 和转义匹配。
- [x] 本地 → 项目 → 用户三级优先级；同层 deny 优先。
- [x] 权限设置缺失、YAML 非法、单条规则非法时安全降级。
- [x] default、acceptEdits、plan、bypassPermissions 四模式矩阵。
- [x] 黑名单 → 沙箱 → 规则 → 模式的短路顺序。
- [x] 允许本次、永久允许、拒绝本次三种审批结果。
- [x] 永久规则原子保存、去重、立即生效和保存失败降级。
- [x] 权限拒绝转换为结构化 ToolResult 并继续 Agent Loop。
- [x] 混合允许/拒绝批次按原 call_id 和顺序回灌。
- [x] 多个合法只读调用保留原有并发执行。
- [x] 审批取消后工具调用与取消结果配对，历史保持合法。
- [x] Anthropic 与 OpenAI Client 继续使用统一 ToolCall/ToolResult 路径。
- [x] Shift+Tab 四模式循环、状态栏模式显示和 Plan Mode 回归。
- [x] 权限确认框支持方向键、Enter、数字 1/2/3、Esc/Ctrl+C 逻辑。
- [x] ch04/ch05 的 Agent Loop、缓存、system-reminder、流式和取消测试无回归。

## tmux 真实场景证据

运行环境：WSL tmux 3.6，通过 WSL 调用项目 Windows 虚拟环境中的 Python 3.12.6；模型为 `deepseek-v4-pro`，Anthropic 协议。

### 场景 1：允许本次——通过

真实请求：读取 `README.md`，再写入 `permission-e2e/allow-once.txt`。

观察结果：

1. `● Read(README.md)` 自动执行并返回内容摘要。
2. `● Write(permission-e2e/allow-once.txt)` 触发权限确认框。
3. 确认框显示工具摘要、Ask 原因和三项选择，默认高亮“允许本次”。
4. 选择 1 后显示 `└─ 已写入 permission-e2e\allow-once.txt`。
5. 文件实际内容为 `Dragon Code ch06 权限测试通过`。
6. 模型收到工具结果并给出最终总结；本轮总计 3309 Token。

### 场景 2：模式切换——通过

tmux 中连续发送 Shift+Tab，状态栏依次显示：

```text
default → acceptEdits → plan → bypassPermissions → default
```

Plan 就绪行显示“仅使用只读工具”；Bypass 就绪行明确“硬防线仍生效”。

### 场景 3：审批取消——核心行为通过

触发 Write 确认后按 Esc，观察到：

```text
└─ 已取消：用户取消了任务，工具尚未执行。
● 当前任务已取消。
```

目标文件不存在，tmux 会话仍存活。相同流程在 Textual pilot 中进一步验证输入恢复、焦点恢复和后续请求成功。

## 环境限制与部分验收

以下 9 项已有自动化证据，但未全部通过真实 tmux 手工矩阵：

1. Windows 当前用户无符号链接权限，真实 symlink 逃逸只在代码路径与条件测试中覆盖。
2. 永久允许已通过临时项目保存/重载测试，未使用真实 API 做“重启后同调用不再询问”。
3. 用户拒绝后模型调整策略已通过 Fake Client 多轮测试，未额外消耗真实 API 重跑。
4. acceptEdits/bypassPermissions 的工具矩阵已自动化验证；tmux 只验证了模式切换显示。
5. `/plan` → `/do` 已通过 Agent 与 TUI 测试，未在本轮真实模型中重复执行。
6. 项目外路径拒绝已通过沙箱与 Agent 测试，未让真实模型读取外部测试文件。
7. 取消后的后续请求已通过 Textual pilot；WSL tmux 控制 Windows Python 时部分键盘控制序列会被桥接吞掉。
8. scrollback 顺序已在真实场景观察并由 TUI 测试覆盖；未单独保存窄屏截图。
9. DeepSeek Anthropic 端点做了真实场景；OpenAI 路径使用 Fake Client 和请求体测试验证。

WSL 原生 Python 为 3.14.4，但缺少 `ensurepip/python3-venv`，无法创建一次性原生虚拟环境。未擅自安装 WSL 系统包。跨终端按键限制已如实记录，不归类为权限业务逻辑失败。

## 清理结果

- 已关闭测试 tmux 会话（最后一次 Ctrl+C 被 WSL 作为进程信号处理，会话随之退出）。
- 已删除本次创建的 `permission-e2e/allow-once.txt` 和空测试目录。
- 未生成永久权限规则，没有遗留 `.dragon-code/settings.local.yaml`。
- 创建 WSL 临时虚拟环境失败时未留下 `/tmp/dragon-code-e2e-venv`。
