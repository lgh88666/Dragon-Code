# Dragon Code 权限系统 Plan

## 架构概览

ch06 在现有 `Agent` 与 `ToolScheduler` 之间加入独立的权限层。LLM Client 仍只负责请求模型和解析流式响应，六个工具仍只负责参数校验与实际执行；权限系统在工具真正进入调度器前统一判断是否允许执行。

权限系统拆为六个职责清晰的部分：

1. **权限领域模型**：统一表示权限模式、Allow / Deny / Ask 判断结果、规则、审批请求和用户选择，避免在各模块之间传递容易写错的字符串。
2. **危险命令黑名单**：只检查 Bash 调用，识别 Unix/Linux、PowerShell、CMD 和 WSL 的典型高危命令；命中后直接拒绝。
3. **路径沙箱**：提取 Read、Write、Edit、Glob、Grep 的目标路径，解析真实路径和最近的已存在祖先，判断是否仍位于单一项目根目录内。
4. **规则仓库**：加载用户级、项目级、本地级三层 YAML，按“本地 → 项目 → 用户”顺序匹配 allow / deny 规则，并负责把“永久允许”追加为本地精确规则。
5. **权限引擎**：按“黑名单 → 沙箱 → 规则 → 当前模式”执行判定流水线；安全检查通过但没有最终决定时继续下一层，最终返回 Allow、Deny 或 Ask。
6. **审批协调与 TUI**：Agent 遇到 Ask 时发出审批事件并暂停当前工具调用；TUI 展示三选一确认界面，把用户选择交还 Agent。Agent 不直接操作界面，TUI 也不需要理解权限规则内部实现。

工具调用的主链路如下：

```text
模型产生 ToolCall
        ↓
Agent 按原顺序处理工具批次
        ↓
PermissionEngine.check(...)
        ├─ Deny  → 生成结构化 ToolResult → 回灌模型
        ├─ Ask   → 发审批事件 → 等待 TUI 选择
        │                    ├─ 拒绝 → 结构化 ToolResult
        │                    └─ 允许 → 继续执行
        └─ Allow → 继续执行
                            ↓
            ToolScheduler 保序分批执行
                            ↓
              ToolRegistry → 具体工具
                            ↓
             工具结果按原调用顺序回灌
```

权限检查以现有调度批次为单位接入：连续只读工具仍处于同一个并发批次；有副作用的工具仍各自串行。每个调用先得到权限结论，允许的调用交给原调度器执行，拒绝的调用直接生成结果，最后按模型原始调用顺序合并。这样不会把权限系统与并发执行混成一个大模块。

当前权限模式作为会话状态保存在 Agent 中。TUI 的 Shift+Tab、`/plan` 和 `/do` 只调用 Agent 暴露的模式切换入口；状态栏读取当前模式显示。Plan Mode 仍通过只读工具子注册中心限制模型可见工具，权限矩阵只作为第二道防线。

## 核心数据结构与接口

权限相关类型集中放在权限模块中，不塞进通用的 LLM 数据模型。枚举继承字符串类型，方便写入 YAML 和显示，但业务代码始终比较枚举成员，不散落字符串判断。

### PermissionMode

```python
class PermissionMode(str, Enum):
    DEFAULT = "default"
    ACCEPT_EDITS = "acceptEdits"
    PLAN = "plan"
    BYPASS_PERMISSIONS = "bypassPermissions"
```

表示当前会话采用的权限模式。Agent 保存唯一的当前值，并提供设置指定模式和切换到下一模式的入口。

### PermissionDecision

```python
class PermissionDecision(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    ASK = "ask"
```

这是权限系统对 Agent 暴露的最终三态结果。黑名单、沙箱、规则等单层检查返回 `PermissionResult | None`；`None` 表示本层没有作出最终决定，应继续下一层，而不是额外引入第四种对外状态。

### PermissionResult

```python
@dataclass(frozen=True)
class PermissionResult:
    decision: PermissionDecision
    source: str
    reason: str
    matched_rule: str = ""
```

- `decision`：Allow、Deny 或 Ask。
- `source`：结论来自 `blacklist`、`sandbox`、`local_rule`、`project_rule`、`user_rule` 或 `mode`。
- `reason`：给用户和模型看的简明原因，不包含敏感环境信息。
- `matched_rule`：命中规则时记录原始规则，便于测试和 UI 提示。

### PermissionRule 与 RuleLayer

```python
@dataclass(frozen=True)
class PermissionRule:
    tool_name: str
    pattern: str | None
    decision: PermissionDecision
    raw: str


@dataclass
class RuleLayer:
    name: str
    path: Path
    allow: list[PermissionRule]
    deny: list[PermissionRule]
    default_mode: PermissionMode | None = None
```

`PermissionRule` 是解析后的单条 `工具名(模式)` 规则。`RuleLayer` 表示用户级、项目级或本地级配置。规则仓库始终按本地、项目、用户保存三个层，层内先检查 deny，再检查 allow。

设置文件统一使用以下简单结构：

```yaml
permissions:
  mode: default
  allow:
    - Bash(git status)
    - Read(README.md)
  deny:
    - Read(.env)
    - Write(.git/**)
```

三份文件路径为：

- 用户级：`~/.dragon-code/settings.yaml`
- 项目级：`<项目根>/.dragon-code/settings.yaml`
- 本地级：`<项目根>/.dragon-code/settings.local.yaml`

### ApprovalChoice 与 PermissionRequest

```python
class ApprovalChoice(str, Enum):
    ALLOW_ONCE = "allow_once"
    ALLOW_ALWAYS = "allow_always"
    DENY_ONCE = "deny_once"


@dataclass(frozen=True)
class PermissionRequest:
    call: ToolCall
    reason: str
    summary: str
    exact_rule: str
```

`PermissionRequest` 是 Agent 发给 TUI 的审批信息。`summary` 只展示工具名和经过长度限制的关键参数；`exact_rule` 是选择永久允许时将写入本地配置的精确规则。

### AgentEvent 扩展

现有 `AgentEvent` 增加一个可选字段：

```python
permission_request: PermissionRequest | None = None
```

当 `type == "permission_request"` 时，TUI 只依赖该字段渲染确认界面。已有 text、tool_start、tool_end、usage、progress、completed、cancelled、limit、error 事件保持不变。

### PermissionEngine

```python
class PermissionEngine:
    def check(
        self,
        call: ToolCall,
        tool: Tool | None,
        mode: PermissionMode,
    ) -> PermissionResult:
        """按五层顺序判断一次工具调用，返回最终三态结果。"""
```

构造时接收项目根、黑名单、路径沙箱和规则仓库。`check()` 本身只做快速同步判断，不执行工具、不操作 TUI，也不修改配置。

### RuleStore

```python
class RuleStore:
    @classmethod
    def load(cls, project_root: Path) -> "RuleStore": ...

    def match(self, call: ToolCall) -> PermissionResult | None: ...

    def default_mode(self) -> PermissionMode: ...

    def save_local_allow(self, exact_rule: str) -> None: ...
```

`load()` 独立读取三层文件，某一层出错只跳过该层的问题内容。`match()` 实现层级与层内优先级。`save_local_allow()` 去重后更新本地级 `permissions.allow`，保留文件里的其他 YAML 字段，并通过临时文件替换避免只写入一半。

### ApprovalController

```python
class ApprovalController:
    def begin(self, call_id: str) -> asyncio.Future[ApprovalChoice]: ...
    def resolve(self, call_id: str, choice: ApprovalChoice) -> None: ...
    def cancel(self) -> None: ...
```

它是 Agent 与 TUI 之间的一次性异步交接点：Agent 先用 `begin()` 创建 Future，再发出审批事件并等待该 Future；TUI 菜单完成后调用 `resolve()`；用户取消任务时 `cancel()` 唤醒等待方，避免竞态、死锁和遗留 Future。控制器不包含任何规则判断。

### Agent 的权限入口

```python
def set_permission_mode(self, mode: PermissionMode) -> None: ...
def cycle_permission_mode(self) -> PermissionMode: ...
def resolve_permission(self, call_id: str, choice: ApprovalChoice) -> None: ...
```

Agent 继续是唯一编排者。模式切换、审批答复和任务取消通过这三个简单入口进入；LLM Client、Conversation 和六个工具不感知 TUI 的存在。

## 模块设计

### `permissions/models.py`

**职责：** 保存权限模式、判断结果、规则、审批请求和审批选项等小型数据类型。

**对外接口：** `PermissionMode`、`PermissionDecision`、`PermissionResult`、`PermissionRule`、`RuleLayer`、`ApprovalChoice`、`PermissionRequest`。

**依赖：** 只依赖标准库和现有 `ToolCall`，不依赖 TUI、Agent 或具体工具。

### `permissions/blacklist.py`

**职责：** 对 Bash 的完整命令文本执行不可配置的危险模式扫描。扫描前统一大小写和空白，再检查命令本身以及由 `;`、`&&`、`||`、管道等连接的子命令，避免只检查开头。内置规则按平台意图分组并配中文说明。

**对外接口：** `DangerousCommandGuard.check(command)`，未命中返回 `None`，命中返回 Deny 结果。

**依赖：** 权限领域模型与 Python 正则表达式；不读取 YAML。

**范围：** 覆盖典型的根目录递归删除、磁盘格式化/清除、系统关机重启等 Unix/Linux、PowerShell、CMD 和 WSL 形式；普通项目目录清理、查看命令与常规 Git 命令不能仅因包含相似单词而被拒绝。

### `permissions/sandbox.py`

**职责：** 从工具调用中提取需要保护的路径，并验证真实目标位于项目根内。

**路径映射：**

- Read / Write / Edit：使用 `path`。
- Grep：使用 `path`，缺省为 `.`。
- Glob：取 glob 模式中第一个通配符前的静态目录部分；没有静态目录时使用 `.`。绝对模式或静态部分含 `..` 时拒绝。
- Bash：不适用，返回 `None` 继续下一层。

**对外接口：** `PathSandbox.check(call, tool)`，安全或不适用时返回 `None`，越界或无法可靠解析时返回 Deny 结果。

**安全细节：** 已存在目标使用真实路径；不存在目标向上查找最近的已存在祖先并解析其符号链接，再把尚不存在的相对尾部接回判断。Windows 比较时处理盘符大小写；所有平台最终都使用“是否能相对于项目根表示”判断边界，不做字符串前缀比较。

**依赖：** 权限模型、`pathlib` 和工具元信息。现有工具内部的 `resolve_workspace_path()` 保留，作为执行时的第二道防线。

### `permissions/rules.py`

**职责：** 解析 `工具名(模式)`、实现命令/文件两套 glob 语义、加载三级设置、匹配规则并写入永久精确授权。

**对外接口：** `parse_rule()`、`RuleStore.load()`、`RuleStore.match()`、`RuleStore.default_mode()`、`RuleStore.save_local_allow()`。

**匹配细节：**

- 命令规则匹配 Bash 的完整 `command`；`*` 和 `**` 都可跨任意字符。
- 文件规则匹配转换为 `/` 分隔符的项目相对路径；`*` 不跨 `/`，`**` 可以跨目录。
- 反斜杠可以转义通配符。永久允许会转义当前参数里的通配符，因此 `Bash(rg *.py)` 不会被错误保存成更宽的 `Bash(rg *)` 权限。
- 从本地层开始检查；当前层只要有匹配，先返回 deny，否则返回 allow，不再查看更远层。
- 单条非法规则只跳过自身；整个 YAML 无法解析时跳过该层，其余层继续工作。

**保存细节：** 本地文件不存在时创建；存在时保留其他 YAML 字段，对 allow 列表去重，并先写同目录临时文件再替换正式文件。

### `permissions/engine.py`

**职责：** 实现唯一的五层判定顺序，并把工具元信息映射到四种模式矩阵。

**对外接口：** `PermissionEngine.check(call, tool, mode)`。

**判断顺序：**

1. 未知工具或关键参数无法解析：从严 Deny。
2. Bash 黑名单：命中即 Deny，未命中继续。
3. 文件路径沙箱：越界即 Deny，安全或不适用继续。
4. 三级规则：命中 allow 或 deny 即返回，未命中继续。
5. 模式兜底：根据 `read_only`、`category` 和当前模式返回 Allow 或 Ask。

该模块不执行工具，也不负责把 Ask 转换为用户选择。

### `permissions/approval.py`

**职责：** 保存当前唯一待决审批的 Future，让 Agent 可以异步等待、TUI 可以稍后回答、取消任务可以立即唤醒等待方。

**对外接口：** `ApprovalController.begin()`、`resolve()`、`cancel()`。

**约束：** 同一时间只允许一个待审批调用；重复答复、过期调用 ID 和已经取消后的答复直接忽略，避免 Future 被重复完成。

### `agent.py`

**职责变化：** Agent 持有 `PermissionEngine`、`ApprovalController` 和当前 `PermissionMode`。现有 ReAct Loop、LLM 流收集与历史提交逻辑不变；只在 `_execute_tools()` 中加入权限预检。

**批次处理：**

1. 沿用 `ToolScheduler.partition()` 得到原批次。
2. 按原顺序为批内每个调用发出 `tool_start` 并执行权限检查。
3. Deny 立即生成带来源的结构化 `ToolResult`；Ask 发出 `permission_request` 并等待选择。
4. 允许的调用仍交给 `ToolScheduler.execute_batch()`；拒绝结果与执行结果按原索引合并。
5. 任务取消时为未执行调用补取消结果，保持历史合法。

选择“永久允许”时，Agent 先保存精确本地规则，再执行当前调用；保存失败时不扩大权限，当前调用降级为“仅允许本次”，同时向界面给出非致命提示。

### `models.py`

**职责变化：** 仅给现有 `AgentEvent` 增加可选的 `permission_request` 字段。工具调用、工具结果、聊天历史和 LLM 请求格式不改变。

### `tui.py`

**职责变化：** 新增权限确认 Modal、Shift+Tab 模式切换和状态栏模式展示。

**审批界面：** `PermissionApprovalScreen` 显示工具摘要、Ask 原因和三项 OptionList；支持方向键、Enter、数字 1/2/3、Esc 和 Ctrl+C。选择完成后调用 Agent 的审批答复入口；取消则调用现有任务取消入口。

**状态管理：** 增加 `APPROVING` 界面状态。此状态仍属于正在执行当前任务，计时、滚动和取消有效，但不能提交新消息或切换权限模式。审批关闭后恢复 `STREAMING`；任务结束后恢复 `IDLE`。

**模式切换：** Shift+Tab 仅在 `IDLE` 生效。切换后更新 Agent、就绪提示和状态栏左侧；`/plan` 与 `/do` 复用同一模式设置入口，不维护第二份模式状态。

### `dragon_code.tcss`

**职责变化：** 为权限确认框、工具摘要、原因文本和三项选择增加自适应样式。窄屏使用百分比宽度和最大宽度，不依赖固定终端尺寸。

### `tool_scheduler.py` 与六个工具

**职责变化：** 调度器的分批、并发、取消和保序接口保持不变。六个工具的实际执行逻辑保持不变；仅在测试发现元信息不准确时修正元信息，不把权限规则写入工具内部。

### LLM Client 与请求协议

**职责变化：** 无。权限允许、询问或拒绝都发生在模型已经产生协议无关 `ToolCall` 之后；拒绝仍使用现有协议无关 `ToolResult`，由 Anthropic/OpenAI Client 按原路径序列化。

## 模块交互

### 启动与模式初始化

```text
CLI 加载模型配置
        ↓
TUI 选择并创建 LLM Client
        ↓
RuleStore.load(项目根)
        ├─ 用户级 settings.yaml
        ├─ 项目级 settings.yaml
        └─ 本地级 settings.local.yaml
        ↓
创建 PermissionEngine + ApprovalController
        ↓
按本地 → 项目 → 用户取得初始 PermissionMode
        ↓
创建 Agent，并在状态栏显示当前模式
```

权限配置与模型 Provider 配置分开加载。模型配置错误仍属于启动失败；权限设置错误则按 Spec 安全降级，不阻止 Dragon Code 启动。

### 一次工具调用的权限链路

```text
Agent 收到 ToolCall
        ↓
从 ToolRegistry 查找工具及元信息
        ↓
PermissionEngine.check(call, tool, mode)
        ├─ 黑名单命中 ────────────────→ Deny
        ├─ 沙箱越界/路径不确定 ───────→ Deny
        ├─ 最高优先级规则命中 allow ─→ Allow
        ├─ 最高优先级规则命中 deny ──→ Deny
        └─ 规则未命中 ─→ 模式矩阵 ───→ Allow / Ask
```

- **Allow**：调用进入原有 `ToolScheduler`。
- **Deny**：不执行工具，生成 `error_code="permission_denied"` 的 `ToolResult`；未知工具保留 `unknown_tool` 错误码，以兼容现有连续未知工具停止条件。拒绝来源和命中规则放入结果 metadata。
- **Ask**：Agent 构造 `PermissionRequest` 并发出 `permission_request` 事件，然后等待 `ApprovalController`。

### HITL 审批时序

```text
Agent                              TUI
  │                                 │
  ├─ ApprovalController.begin()     │
  ├─ yield permission_request ─────→│ 打开 PermissionApprovalScreen
  │ 等待 Future                     │ 用户选择 1 / 2 / 3
  │                                 │
  │←──── resolve(call_id, choice) ──┤
  │                                 │
  ├─ 允许本次：执行                 │ 关闭确认框，恢复 STREAMING
  ├─ 永久允许：保存精确规则后执行   │
  └─ 拒绝本次：生成拒绝 ToolResult  │
```

若用户按 Esc 或 Ctrl+C，TUI 关闭确认框并调用 `Agent.request_cancel()`；Agent 同时取消审批 Future、活动工具和后续批次，为尚未执行的调用补取消结果，合法提交已经形成的工具调用/结果对，最后发出 `cancelled` 事件。

### 多工具批次与结果保序

Agent 沿用 `ToolScheduler.partition()` 的批次边界。每批先按顺序完成权限判断和必要审批，再执行允许的调用：

```text
原批次：[Read A, Read B, Read C]
权限： [Allow, Deny, Allow]
执行： [Read A,         Read C]  ← 两个允许项仍并发
合并： [结果 A, 拒绝 B, 结果 C]  ← 按原下标回灌
```

有副作用调用原本就是单元素串行批次，因此多个 Ask 自然按模型顺序逐个出现。只读并发批中的沙箱 Deny 不会阻止其他合法只读调用执行。

### 模式切换与 Plan Mode

- Shift+Tab 仅在 TUI 空闲时调用 `Agent.cycle_permission_mode()`。
- 进入 plan 时，下一次 `run()` 继续使用 Read / Glob / Grep 子注册中心，并使用 ch05 的计划提醒。
- 从 plan 切到其他模式时清除旧的“计划可执行”标志，避免在错误模式下执行旧计划。
- `/plan` 调用统一的 `set_permission_mode(PLAN)`。
- `/do` 仅在计划已经完成时调用 `set_permission_mode(DEFAULT)`，然后沿用现有内置提示触发执行。
- 正在流式、执行工具或等待审批时，Shift+Tab 不生效，避免一个工具批次中途改变规则矩阵。

### 永久允许保存

选择永久允许后，Agent 使用当前调用生成精确规则：Bash 保存完整命令；文件工具保存规范化的项目相对路径；特殊通配字符先转义。`RuleStore` 将规则原子写入本地级 `permissions.allow`，更新内存中的本地规则后再执行当前调用，因此之后相同调用立即生效，无需重启。

如果保存失败，当前调用仅按“允许本次”执行，并通过非致命状态事件提示“永久规则保存失败”；不会假装已经永久授权，也不会中断 Agent Loop。

## 文件组织

```text
dragonAgent/
├── .dragon-code/
│   ├── config.yaml.example              — 现有模型配置示例，不修改语义
│   └── settings.yaml.example            — 新增权限规则与默认模式示例
├── src/dragon_code/
│   ├── permissions/
│   │   ├── __init__.py                  — 导出权限系统公开类型
│   │   ├── models.py                    — 模式、结果、规则、审批数据类型
│   │   ├── blacklist.py                 — 固定危险命令黑名单
│   │   ├── sandbox.py                   — 路径提取、真实路径与边界判断
│   │   ├── rules.py                     — 规则解析、三级加载、匹配和保存
│   │   ├── engine.py                    — 五层权限判断流水线
│   │   └── approval.py                  — 异步审批 Future 协调
│   ├── agent.py                         — 接入权限预检、模式和审批等待
│   ├── models.py                        — AgentEvent 增加审批请求字段
│   ├── tui.py                           — 确认框、Shift+Tab、状态管理
│   └── dragon_code.tcss                 — 权限确认界面样式
├── tests/
│   ├── test_permission_blacklist.py     — 跨平台黑名单与误报测试
│   ├── test_permission_sandbox.py       — 越界、符号链接和新建路径测试
│   ├── test_permission_rules.py         — 解析、glob、优先级和保存测试
│   ├── test_permission_engine.py        — 五层短路和四模式矩阵测试
│   ├── test_permission_approval.py      — resolve、取消和重复答复测试
│   ├── test_agent.py                    — 权限回灌、保序、取消和并发集成
│   └── test_tui.py                      — 模式切换、确认菜单和快捷键测试
├── README.md                            — 权限模式、规则文件和快捷键说明
└── .gitignore                           — 忽略 settings.local.yaml
```

现有 `clients/`、`tool_scheduler.py` 和六个工具文件不新增权限分支。`tools/path_utils.py` 的执行时边界检查保留，不由权限模块替换。

## 技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 权限接入位置 | Agent 与 ToolScheduler 之间 | 此处已有协议无关 ToolCall，又尚未执行工具；可统一防护且不污染 LLM Client 和具体工具 |
| 权限层未命中 | 返回 `None` 继续下一层 | 对外保持 Allow / Deny / Ask 三态，避免把“安全检查通过”误当成最终授权 |
| 模式表示 | `PermissionMode` 字符串枚举 | YAML 值清晰，代码比较安全，也便于状态栏显示 |
| 黑名单实现 | 固定、分组的预编译正则 | 符合不可配置要求，依赖少，能覆盖跨平台典型高危命令；明确它只是启发式防线 |
| Bash 路径限制 | 不做静态路径沙箱 | 任意 shell 语法无法可靠解析；使用黑名单、规则、模式和 HITL 约束 |
| 文件边界判断 | `pathlib` 真实路径 + `relative_to` | 能处理 `..`、符号链接、Windows 盘符等问题，避免有漏洞的字符串前缀比较 |
| 新建路径判断 | 解析最近的已存在祖先 | 目标尚不存在时仍能识别父目录符号链接逃逸，同时允许项目内创建多级目录 |
| 规则层优先级 | 本地 → 项目 → 用户；层内 deny 优先 | 体现越靠近项目越具体，同时允许本地层显式覆盖较远层；同层冲突从严 |
| 永久授权粒度 | 转义特殊字符的精确规则 | 满足“不自动泛化”，避免命令自带 `*` 时意外变成宽泛授权 |
| 配置失败策略 | 每层独立加载、问题项跳过、默认 default | 权限配置不应让应用崩溃，也不能因解析失败扩大权限 |
| 审批通信 | 单待决 `asyncio.Future` 控制器 | 代码简单，Agent 可暂停而 TUI 不阻塞，取消时能主动唤醒并清理 |
| TUI 审批形式 | Textual ModalScreen + OptionList | 与现有 Provider 选择交互一致，天然支持键盘选择且便于测试 |
| 多调用执行 | 复用原分批，按原索引合并权限/执行结果 | 保留只读并发与有副作用串行，不让完成顺序破坏回灌顺序 |
| bypassPermissions | 只跳过模式层的 Ask | 黑名单、沙箱和显式 deny 仍然有效，符合“放行日常操作但不移除硬边界” |
| Plan Mode | 工具可见性限制 + 权限模式双保险 | 模型通常不会产生写调用，即使异常产生也不会静默执行 |
| 跨协议支持 | 不修改 LLM Client | 两协议已共享 ToolCall / ToolResult，权限放在其上层自然保持一致 |

## Spec 覆盖检查

| Spec 需求 | 设计归属 |
|---|---|
| F1 危险命令黑名单 | `permissions/blacklist.py` + PermissionEngine 第 2 步 |
| F2 路径沙箱 | `permissions/sandbox.py` + 工具执行时二次边界检查 |
| F3 权限规则匹配 | `permissions/rules.py` 的解析与两套 glob 匹配 |
| F4 三级配置加载 | RuleStore 三层加载、优先级、模式选择和安全降级 |
| F5 权限模式兜底 | PermissionMode + PermissionEngine 模式矩阵 |
| F6 五层判定流水线 | PermissionEngine 唯一顺序 + Agent 批次接入 |
| F7 运行时模式切换 | Agent 统一模式入口 + TUI Shift+Tab / 状态栏 |
| F8 人在回路审批 | ApprovalController + PermissionApprovalScreen |
| F9 拒绝结果回灌 | Agent 结构化 ToolResult、原索引合并和历史提交 |
| F10 安全默认 | 未知工具/参数/路径从严 + 配置安全降级 |
| F11 跨协议一致 | 权限位于 LLM Client 上层，共用 ToolCall / ToolResult |
