# Dragon Code 权限系统 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|---|---|---|
| 新建 | `src/dragon_code/permissions/__init__.py` | 导出权限系统公开类型 |
| 新建 | `src/dragon_code/permissions/models.py` | 权限模式、结果、规则与审批数据类型 |
| 新建 | `src/dragon_code/permissions/blacklist.py` | 固定跨平台危险命令黑名单 |
| 新建 | `src/dragon_code/permissions/sandbox.py` | 工具路径提取与项目根沙箱 |
| 新建 | `src/dragon_code/permissions/rules.py` | 规则解析、匹配、三级加载和永久保存 |
| 新建 | `src/dragon_code/permissions/engine.py` | 五层权限判断流水线与模式矩阵 |
| 新建 | `src/dragon_code/permissions/approval.py` | Agent 与 TUI 的异步审批协调 |
| 修改 | `src/dragon_code/models.py` | 给 AgentEvent 增加审批请求字段 |
| 修改 | `src/dragon_code/agent.py` | 接入模式、权限预检、审批、拒绝回灌和取消 |
| 修改 | `src/dragon_code/tui.py` | 权限确认框、Shift+Tab、状态栏和审批状态 |
| 修改 | `src/dragon_code/dragon_code.tcss` | 权限确认框自适应样式 |
| 新建 | `tests/test_permission_rules.py` | 规则语法、优先级、加载和保存测试 |
| 新建 | `tests/test_permission_blacklist.py` | 跨平台黑名单和误报测试 |
| 新建 | `tests/test_permission_sandbox.py` | 路径越界、符号链接和新建路径测试 |
| 新建 | `tests/test_permission_engine.py` | 五层短路、模式矩阵和安全默认测试 |
| 新建 | `tests/test_permission_approval.py` | 审批 Future、答复和取消测试 |
| 修改 | `tests/test_agent.py` | 权限回灌、批次保序、HITL 和取消集成测试 |
| 修改 | `tests/test_tui.py` | 确认菜单、模式切换和快捷键测试 |
| 新建 | `.dragon-code/settings.yaml.example` | 权限配置示例 |
| 修改 | `.gitignore` | 忽略项目本地权限设置 |
| 修改 | `README.md` | 记录权限模式、规则与操作方式 |

## T1：建立权限领域模型

**文件：** `src/dragon_code/permissions/models.py`、`src/dragon_code/permissions/__init__.py`

**依赖：** 无

**步骤：**

1. 定义 `PermissionMode`、`PermissionDecision` 和 `ApprovalChoice` 字符串枚举。
2. 定义 `PermissionResult`、`PermissionRule`、`RuleLayer`、`PermissionRequest` 数据类。
3. 为字段添加简短中文注释，保持类型简单，不引入 Pydantic。
4. 从包入口导出后续模块需要的公开类型。

**验证：** 运行 `uv run python -c "from dragon_code.permissions import PermissionMode, PermissionDecision; print(PermissionMode.DEFAULT, PermissionDecision.ASK)"`，期望正常输出且无导入错误。

## T2：解析规则语法并生成精确规则

**文件：** `src/dragon_code/permissions/rules.py`、`tests/test_permission_rules.py`

**依赖：** T1

**步骤：**

1. 解析 `Tool`、`Tool(pattern)` 两种格式，拆出工具名、可选 pattern 和 raw。
2. 只接受六个友好工具名与 allow / deny 两种决定；非法规则返回可跳过的解析错误。
3. 实现从 ToolCall 生成精确规则：Bash 使用完整 command，文件工具使用规范化相对路径。
4. 对 `*`、`?`、`[`、`]` 和反斜杠做字面量转义，防止永久授权扩大范围。
5. 添加合法、非法、无 pattern、含右括号命令和含通配符参数测试。

**验证：** 运行 `uv run pytest tests/test_permission_rules.py -k "parse or exact" -q`，期望相关测试通过。

## T3：实现命令与文件规则匹配

**文件：** `src/dragon_code/permissions/rules.py`、`tests/test_permission_rules.py`

**依赖：** T2

**步骤：**

1. 提取各工具用于匹配的值：Bash command；Read/Write/Edit path；Grep path；Glob pattern。
2. 实现命令 glob：`*` 与 `**` 均可跨任意字符。
3. 实现文件 glob：`*` 不跨 `/`，`**` 可跨目录，Windows 分隔符统一为 `/`。
4. 支持反斜杠转义的字面量通配符。
5. 添加精确命中、不命中、单层/跨层目录和转义测试。

**验证：** 运行 `uv run pytest tests/test_permission_rules.py -k "match or glob" -q`，期望相关测试通过。

## T4：加载三级权限设置

**文件：** `src/dragon_code/permissions/rules.py`、`tests/test_permission_rules.py`

**依赖：** T2、T3

**步骤：**

1. 按用户级、项目级、本地级三个固定路径读取 YAML。
2. 解析 `permissions.mode`、`allow` 和 `deny`；缺失文件生成空层。
3. YAML 整体非法时只跳过该层；单条规则非法时只跳过该条。
4. 不打印堆栈、密钥或 YAML 中无关内容。
5. 添加三层存在、部分缺失、YAML 非法和规则项非法测试。

**验证：** 运行 `uv run pytest tests/test_permission_rules.py -k "load or invalid" -q`，期望相关测试通过。

## T5：实现三级优先级与默认模式

**文件：** `src/dragon_code/permissions/rules.py`、`tests/test_permission_rules.py`

**依赖：** T4

**步骤：**

1. `RuleStore.match()` 按本地 → 项目 → 用户查找最高优先级命中层。
2. 同一层先检查 deny，再检查 allow。
3. 最高命中层得到 allow 后不再被较远层 deny 覆盖。
4. `default_mode()` 同样按本地 → 项目 → 用户选择合法模式，均无有效值时返回 default。
5. 添加跨层冲突、同层冲突和模式回退测试。

**验证：** 运行 `uv run pytest tests/test_permission_rules.py -k "precedence or mode" -q`，期望相关测试通过。

## T6：保存本地永久授权

**文件：** `src/dragon_code/permissions/rules.py`、`tests/test_permission_rules.py`

**依赖：** T4、T5

**步骤：**

1. 创建缺失的 `.dragon-code` 目录和 `settings.local.yaml`。
2. 把精确规则追加到本地 `permissions.allow`，已存在时不重复。
3. 保留文件内其他 YAML 字段及 deny 列表。
4. 使用同目录临时文件写入后替换，并同步更新内存中的本地规则。
5. 添加创建、去重、保留字段、原子替换后立即匹配测试。

**验证：** 运行 `uv run pytest tests/test_permission_rules.py -k "save or permanent" -q`，期望相关测试通过。

## T7：建立跨平台危险命令规则

**文件：** `src/dragon_code/permissions/blacklist.py`、`tests/test_permission_blacklist.py`

**依赖：** T1

**步骤：**

1. 用带说明的固定规则覆盖 Unix/Linux 根目录递归删除、磁盘写入/格式化和关机重启。
2. 覆盖 PowerShell 的根路径递归删除、磁盘清除/格式化和关机重启。
3. 覆盖 CMD 的根路径删除、format 和 shutdown。
4. 覆盖通过 WSL 包装执行上述 Unix 高危命令的形式。
5. 添加每个平台至少一种命中测试。

**验证：** 运行 `uv run pytest tests/test_permission_blacklist.py -k dangerous -q`，期望相关测试通过。

## T8：处理命令归一化、连接符和误报

**文件：** `src/dragon_code/permissions/blacklist.py`、`tests/test_permission_blacklist.py`

**依赖：** T7

**步骤：**

1. 在扫描前统一大小写、连续空白与换行。
2. 检查由 `;`、`&&`、`||`、管道连接的后续子命令，而非只检查开头。
3. 让命中结果携带固定规则的中文原因，不回显整段敏感命令。
4. 添加普通 `rm -rf build`、`Remove-Item .venv`、`git status`、查看状态等不误报测试。

**验证：** 运行 `uv run pytest tests/test_permission_blacklist.py -q`，期望全部通过。

## T9：提取各工具的沙箱路径

**文件：** `src/dragon_code/permissions/sandbox.py`、`tests/test_permission_sandbox.py`

**依赖：** T1

**步骤：**

1. Read/Write/Edit 提取 `path`，Grep 提取 `path` 或 `.`。
2. Glob 提取第一个通配符前的静态目录；`**/*.py` 映射为项目根。
3. Bash 返回“不适用”，未知工具、缺参数或路径类型错误返回 Deny。
4. 绝对 Glob 与显式 `..` Glob 直接返回 Deny。
5. 添加六工具路径映射和非法参数测试。

**验证：** 运行 `uv run pytest tests/test_permission_sandbox.py -k extract -q`，期望相关测试通过。

## T10：实现真实路径边界与符号链接防逃逸

**文件：** `src/dragon_code/permissions/sandbox.py`、`tests/test_permission_sandbox.py`

**依赖：** T9

**步骤：**

1. 解析项目根与已有目标的真实路径，再用 `relative_to()` 判断边界。
2. 对不存在目标向上查找最近的已存在祖先，解析符号链接后接回剩余路径。
3. 允许项目内已有路径和多级新建路径；拒绝绝对越界、`../` 和链接逃逸。
4. Windows 环境处理盘符大小写；无法创建符号链接的测试按平台条件跳过。
5. 添加已有、新建、越界和符号链接测试。

**验证：** 运行 `uv run pytest tests/test_permission_sandbox.py -q`，期望全部通过或仅平台不支持的符号链接用例跳过。

## T11：实现权限引擎硬防线与规则短路

**文件：** `src/dragon_code/permissions/engine.py`、`tests/test_permission_engine.py`

**依赖：** T5、T8、T10

**步骤：**

1. 构造 `PermissionEngine`，注入项目根、黑名单、沙箱和 RuleStore。
2. 未知工具或关键参数不合法时从严 Deny。
3. 依次执行黑名单、沙箱、规则；任一明确结果立即返回。
4. 确保黑名单和沙箱只产生 Deny 或继续，不提前产生 Allow。
5. 用测试替身记录调用顺序，验证短路后后续层未运行。

**验证：** 运行 `uv run pytest tests/test_permission_engine.py -k "pipeline or short" -q`，期望相关测试通过。

## T12：实现四模式权限矩阵

**文件：** `src/dragon_code/permissions/engine.py`、`tests/test_permission_engine.py`

**依赖：** T11

**步骤：**

1. 根据 Tool 的 `read_only` 与 `category` 区分只读、文件写和 Bash。
2. 实现 default、acceptEdits、plan、bypassPermissions 四行矩阵。
3. 保证 bypassPermissions 只影响最终模式兜底，不能跳过前置三层。
4. 类别不明工具从严 Ask 或 Deny，不静默 Allow。
5. 参数化测试四种模式和三类工具的全部组合。

**验证：** 运行 `uv run pytest tests/test_permission_engine.py -q`，期望全部通过。

## T13：实现异步审批控制器

**文件：** `src/dragon_code/permissions/approval.py`、`tests/test_permission_approval.py`

**依赖：** T1

**步骤：**

1. `begin()` 在发事件前创建并记录当前调用 ID 与 Future。
2. `resolve()` 只完成 ID 匹配且尚未结束的 Future。
3. `cancel()` 取消当前 Future 并清空引用。
4. 重复 begin、重复答复和过期 ID 不导致崩溃或重复完成。
5. 添加正常答复、取消、错误 ID 和重复答复测试。

**验证：** 运行 `uv run pytest tests/test_permission_approval.py -q`，期望全部通过且无挂起任务警告。

## T14：扩展 AgentEvent 审批事件

**文件：** `src/dragon_code/models.py`、`tests/test_agent.py`

**依赖：** T1

**步骤：**

1. 给 `AgentEvent` 增加可选 `permission_request` 字段。
2. 保持所有现有事件构造代码兼容，不改变默认值。
3. 增加一个最小事件构造测试。

**验证：** 运行 `uv run pytest tests/test_agent.py -k permission_event -q`，期望测试通过。

## T15：统一 Agent 的权限模式状态

**文件：** `src/dragon_code/agent.py`、`tests/test_agent.py`

**依赖：** T12、T13、T14

**步骤：**

1. Agent 构造时接收 PermissionEngine、ApprovalController 和初始模式。
2. 用 `PermissionMode` 替换散落的 default / plan 字符串比较。
3. 实现设置模式和按固定顺序循环模式。
4. `/plan`、`/do` 继续复用 enter/can_execute 接口，并正确维护 `has_plan`。
5. 添加初始模式、循环顺序和 Plan 状态测试。

**验证：** 运行 `uv run pytest tests/test_agent.py -k "permission_mode or plan_mode" -q`，期望相关测试通过。

## T16：把权限结论转换为结构化结果

**文件：** `src/dragon_code/agent.py`、`tests/test_agent.py`

**依赖：** T15

**步骤：**

1. 为单个 ToolCall 调用 PermissionEngine。
2. Deny 转为 `permission_denied` ToolResult，并在 metadata 写入 source 与 matched_rule。
3. 未知工具保留 `unknown_tool` 错误码和原调用 ID。
4. Allow 返回可执行标记，不在此处直接运行工具。
5. 添加黑名单、沙箱、规则 deny 和未知工具结果测试。

**验证：** 运行 `uv run pytest tests/test_agent.py -k "permission_denied or unknown_tool" -q`，期望相关测试通过。

## T17：接入批次权限预检和结果合并

**文件：** `src/dragon_code/agent.py`、`tests/test_agent.py`

**依赖：** T16

**步骤：**

1. 在现有 `_execute_tools()` 的每个 ToolBatch 内按原顺序做权限预检。
2. 允许调用交给原 `execute_batch()`；拒绝调用不执行。
3. 按原下标合并执行结果和拒绝结果，再发 `tool_end`。
4. 验证多个只读允许项仍并发、其中一个拒绝不影响其他项。
5. 验证有副作用批次仍串行且整体结果保序。

**验证：** 运行 `uv run pytest tests/test_agent.py -k "permission_batch or permission_order" -q`，期望相关测试通过。

## T18：接入 HITL 三种审批结果

**文件：** `src/dragon_code/agent.py`、`tests/test_agent.py`

**依赖：** T6、T13、T17

**步骤：**

1. Ask 时先 `begin()`，再发出包含摘要与精确规则的 `permission_request` 事件。
2. 允许本次直接执行；拒绝本次生成结构化拒绝结果。
3. 永久允许先保存、刷新本地规则，再执行当前调用。
4. 保存失败时按允许本次继续，并发出不终止任务的 warning 事件。
5. 添加三种选择和保存失败测试。

**验证：** 运行 `uv run pytest tests/test_agent.py -k "approval or permanent_allow" -q`，期望相关测试通过。

## T19：处理审批取消和历史合法性

**文件：** `src/dragon_code/agent.py`、`tests/test_agent.py`

**依赖：** T18

**步骤：**

1. `request_cancel()` 同时取消网络、调度器和 ApprovalController。
2. 审批 Future 取消后停止后续审批和迭代。
3. 为当前及剩余未执行调用生成取消结果并按 ID 配对。
4. 提交完整 assistant 工具调用与 tool results 后再发 cancelled 事件。
5. 添加审批中取消、部分调用完成后取消和取消后继续新会话测试。

**验证：** 运行 `uv run pytest tests/test_agent.py -k "cancel_permission or history_after_permission" -q`，期望相关测试通过且无 400 形态的悬空历史。

## T20：实现权限确认 Modal

**文件：** `src/dragon_code/tui.py`、`tests/test_tui.py`

**依赖：** T1

**步骤：**

1. 新建 `PermissionApprovalScreen`，显示工具摘要、原因和三项 OptionList。
2. 默认高亮允许本次，支持上下方向键和 Enter。
3. 数字键 1/2/3 分别返回三种 ApprovalChoice。
4. Esc 与 Ctrl+C 返回取消，不直接退出应用。
5. 添加默认项、方向键、数字键和取消测试。

**验证：** 运行 `uv run pytest tests/test_tui.py -k permission_screen -q`，期望相关测试通过。

## T21：消费审批事件并维护 APPROVING 状态

**文件：** `src/dragon_code/tui.py`、`tests/test_tui.py`

**依赖：** T18、T19、T20

**步骤：**

1. `SessionState` 增加 APPROVING。
2. 收到 `permission_request` 时切换状态并打开确认框。
3. 正常选择调用 `Agent.resolve_permission()` 并恢复 STREAMING。
4. 取消选择调用 `Agent.request_cancel()`，等待 cancelled 事件统一收尾。
5. 处理 permission warning，在对话区显示黄色非致命提示。
6. 添加审批时不能提交新消息、计时继续和取消后恢复 IDLE 测试。

**验证：** 运行 `uv run pytest tests/test_tui.py -k "approving or permission_warning" -q`，期望相关测试通过。

## T22：接入 Shift+Tab、状态栏和 Plan 命令

**文件：** `src/dragon_code/tui.py`、`tests/test_tui.py`

**依赖：** T15、T21

**步骤：**

1. 激活会话时加载 RuleStore、PermissionEngine 与初始模式并交给 Agent。
2. 添加 Shift+Tab 绑定，仅在 IDLE 循环切换四种模式。
3. 状态栏左侧显示权限模式，不再显示 provider 名；右侧模型和 Token 保持不变。
4. `/plan` 与 `/do` 使用统一模式入口；更新 ready 提示和 `/help` 文本。
5. 流式或审批中按 Shift+Tab 不改变模式。
6. 添加初始配置模式、循环切换、状态显示和 Plan 回归测试。

**验证：** 运行 `uv run pytest tests/test_tui.py -k "mode or shift_tab or plan" -q`，期望相关测试通过。

## T23：添加权限确认界面样式

**文件：** `src/dragon_code/dragon_code.tcss`、`tests/test_tui.py`

**依赖：** T20

**步骤：**

1. 为 Modal 背景、确认框、标题、摘要、原因和选项列表添加样式。
2. 使用百分比宽度、最大宽度和自动高度，保证窄屏可用。
3. 保留现有 Banner、对话区、输入框与状态栏布局。
4. 启动 Textual pilot，确认 CSS 能加载且无选择器错误。

**验证：** 运行 `uv run pytest tests/test_tui.py -k "mount or permission_screen" -q`，期望应用挂载与确认框测试通过。

## T24：补充权限配置示例与用户说明

**文件：** `.dragon-code/settings.yaml.example`、`.gitignore`、`README.md`

**依赖：** T5、T22

**步骤：**

1. 示例文件展示 mode、allow、deny、精确规则和 glob 规则。
2. `.gitignore` 增加 `.dragon-code/settings.local.yaml`，不忽略可共享项目设置。
3. README 说明五层顺序、四种模式、Shift+Tab、`/plan`、`/do` 和三层文件路径。
4. 明确 bypassPermissions 仍不能绕过黑名单、沙箱和显式规则。

**验证：** 运行 `rg -n "Shift\+Tab|bypassPermissions|settings.local.yaml|Bash\(git" README.md .dragon-code/settings.yaml.example .gitignore`，期望三类说明都能找到。

## T25：执行跨协议与既有能力回归

**文件：** `tests/test_agent.py`、现有 `tests/test_client_anthropic.py`、`tests/test_client_openai.py`、`tests/test_prompt.py`、`tests/test_tool_scheduler.py`

**依赖：** T19、T22

**步骤：**

1. 添加同一组协议无关 ToolCall 在两种 Fake Client 下经过权限层的测试。
2. 验证拒绝 ToolResult 仍可由两种 Client 转成合法请求消息。
3. 运行 Agent Loop、Plan Mode、缓存/system-reminder、流式收集和调度器原测试。
4. 修复新增权限层引起的兼容问题，但不改 LLM Client 的权限无关语义。

**验证：** 运行 `uv run pytest tests/test_agent.py tests/test_client_anthropic.py tests/test_client_openai.py tests/test_prompt.py tests/test_tool_scheduler.py -q`，期望全部通过。

## T26：运行完整静态检查与测试

**文件：** 全项目

**依赖：** T1–T25

**步骤：**

1. 运行 Ruff 格式化并检查格式。
2. 运行 Ruff lint。
3. 运行全部 pytest。
4. 确认测试输出无未捕获异常、挂起 task、密钥或真实配置内容。

**验证：** 依次运行 `uv run ruff format .`、`uv run ruff check .`、`uv run pytest -q`，期望全部成功。

## 执行顺序

```text
T1
├─ T2 → T3 → T4 → T5 → T6 ───────────┐
├─ T7 → T8 ────────────────────────────┤
├─ T9 → T10 ───────────────────────────┤
└─ T13 ────────────────────────────────┤
                                      ↓
                         T11 → T12 → T14 → T15
                                              ↓
                         T16 → T17 → T18 → T19
                                              ↓
                         T20 → T21 → T22 → T23
                                              ↓
                                  T24 → T25 → T26
```

T20 的纯界面骨架可在 T19 之前编写，但集成验证 T21 必须等待 Agent 审批事件完成。开发时仍按上图主顺序执行，减少同时修改 `agent.py` 与 `tui.py` 带来的排查难度。
