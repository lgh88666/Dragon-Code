# Dragon Code ch13 SubAgent 子任务分发 Checklist

> 每项都必须通过运行命令或观察真实行为验证。自动化测试与 tmux 实测分开记录，不能用
> “理论上可行”代替证据。

## Agent 工具与角色发现

- [ ] 主 Agent 的每次请求都包含 `Agent`、`TaskList`、`TaskGet`、`TaskStop`、
  `SendMessage` 五个工具，名称、顺序和 Schema 在同一会话内不变。（验证：连续抓取两轮
  fake LLM 请求体并逐项比较）(AC1/F1/F2/N1)
- [ ] 增删磁盘上的 Agent 定义文件不会改变已经启动会话的工具描述或 Schema，重启后才重新
  加载。（验证：启动后新增角色文件，再请求一次；重启后再次检查角色摘要）(AC1/F2)
- [ ] `Agent` 工具参数缺失、类型错误和不存在的角色名都返回结构化错误，主 Agent Loop 可以
  继续。（验证：单测分别构造三种非法 ToolCall）(F1/N3)
- [ ] 合法项目级角色能覆盖同名用户级和内置角色，最终定义顺序稳定。（验证：临时三层目录
  放入同名定义，运行 Catalog 单测）(AC2/F3/F4)
- [ ] 损坏的项目级或用户级定义被跳过并产生安全 warning，应用仍能启动。（验证：坏 YAML、
  缺正文各启动一次，观察可读 warning 且无堆栈）(AC2/F3/F4/N7)
- [ ] 损坏的内置角色作为程序错误阻止启动，并给出可读错误。（验证：测试注入坏 builtin root，
  断言非零退出和无未捕获堆栈）(AC2/F4)
- [ ] `explore`、`plan`、`verify` 三个内置角色均可发现；默认模型均为
  `deepseek-v4-flash`，工具范围分别符合只读探索、只读规划和验证命令需求。（验证：Catalog
  单测 + 检查角色摘要）(AC2/F5)
- [x] 三个内置 Markdown 文件包含在构建产物中。（验证：`uv build` 后列出 wheel 内容）(F4/F5)

## 定义式子 Agent

- [ ] 调用 `Agent(role="explore")` 从空白 Conversation 开始，只有角色系统指令和本次任务，
  不继承主历史。（验证：fake LLM 捕获子请求 messages）(AC3/F6)
- [ ] 定义式子 Agent 默认使用 `deepseek-v4-flash`，本次完整模型名覆盖和定义文件模型覆盖均
  生效；模型不可用时只让当前任务失败。（验证：fake client factory 记录配置并注入失败）
  (AC3/F11/N3)
- [ ] 子 Agent 使用现有 ReAct 循环，能连续调用工具，直到返回无 ToolCall 的最终文本才自然
  完成。（验证：fake client 返回“两次工具调用 + 最终文本”）(AC3/F9)
- [ ] 定义式前台任务完成后，`Agent` ToolResult 包含最终文本；主 Conversation 只保存主模型
  的 Agent ToolCall 与 ToolResult，不包含子 Agent 中间消息。（验证：检查父子 Conversation）
  (AC3/F6/N4)
- [ ] 两个同时运行的子 Agent 拥有不同的 Conversation、ContextManager、SkillRuntime、
  HookEngine、Token 和临时权限集合。（验证：并行 Host 单测比较对象和状态）(AC5/F10)
- [ ] 子 Agent 共享真实文件工具、持久权限规则和 Hook 定义快照，且共享部分不造成消息或提醒
  串线。（验证：两个任务操作独立 fake 状态并触发同一 Hook 定义）(AC5/F10/F23)
- [ ] 主 Agent 处于 Plan Mode 时，委派角色也只能使用只读工具，不能通过角色权限模式升级成
  Bash/写文件执行。（验证：Plan Mode 下调用 verify 或自定义高权限角色）(F10/N8)

## Fork 历史与缓存

- [ ] 不传角色名时创建 Fork，并立即返回后台 task ID。（验证：Agent 工具单测检查状态和返回
  JSON）(AC4/F7)
- [ ] Fork 深拷贝父完整历史，修改子消息不会改变父 Conversation。（验证：构造消息后修改
  fork 副本并比较父对象）(AC4/F7/N4)
- [ ] 当前 assistant 中每个尚未完成的 ToolCall 都恰好获得一个 placeholder ToolResult，已有
  结果不会重复补齐。（验证：含多 ToolCall 的 Fork 单测）(AC4/F7/N4)
- [ ] Fork 尾部任务带 `<fork-boilerplate>`，明确禁止提问、交互确认、扩大范围和再次委派；
  该文本不进入主 Conversation/JSONL。（验证：检查父子历史及会话文件）(AC4/F8/N4)
- [ ] Fork 继承父模型、稳定 System Prompt 和工具定义顺序，不接受模型覆盖。（验证：比较父子
  fake 请求）(AC4/F7/F11/N1)
- [ ] 连续两次 Fork 的稳定 System Prompt 和工具定义前缀逐项一致。（验证：Anthropic/OpenAI
  请求体快照比较）(AC17/N1)
- [ ] 端点提供缓存字段时能观察到缓存读取 Token；不提供时按零处理且任务仍完成。（验证：两种
  fake 流用量响应）(AC17/N1/F25)

## 工具过滤与权限

- [ ] 定义式子 Agent 看不到 `Agent`、四个任务工具和 `LoadSkill`。（验证：捕获定义式子请求
  tools）(AC6/F12/F13)
- [ ] 后台角色只获得通过过滤的六个核心工具，以及允许的 `mcp__*`/`skill__*` 工具；结果顺序
  与原注册顺序一致。（验证：混合 registry 过滤单测）(F12)
- [ ] 角色 `disallowedTools` 优先于 `tools` 白名单，空白名单不额外收窄。（验证：三组过滤
  参数单测）(F12)
- [ ] Fork 为缓存保留父工具 Schema，但调用 `Agent` 或任务工具时被 QuerySource 拒绝并返回
  `nested_agent_denied`。（验证：Fork 来源 ToolCall 单测）(AC6/F13)
- [ ] 即使 QuerySource 被错误设置为 main，只要历史包含 Fork Boilerplate，嵌套调用仍被拒绝。
  （验证：丢失来源标记的兜底单测）(AC6/F13)
- [ ] 子 Agent 触发 Ask 时不出现 TUI 审批框，而是收到结构化 `permission_denied` 并可以继续
  调整。（验证：fake 子任务先请求写入、再改为只读并最终完成）(AC7/F14)
- [ ] 子 Agent 不继承父会话“本次/本会话允许”，但用户级、项目级持久 allow/deny 规则继续
  生效。（验证：父 engine 临时允许后创建子 engine，再分别测试临时与持久规则）(AC7/F14)
- [ ] 危险命令黑名单和路径沙箱在 bypass 权限角色下仍不可绕过。（验证：子 Agent 请求测试用
  危险命令和越界路径，观察结构化拒绝）(AC7/F14/N7)
- [ ] 主 Agent 的正常权限弹窗、Plan Mode 和现有权限模式没有退化。（验证：运行 ch06 全部权限
  测试并在 TUI 发起一次普通写操作）(N8)

## 前台、后台和队列

- [ ] 定义式任务默认 attached 前台运行，TUI 实时显示带角色名称的文本、工具调用、结果、
  迭代和用量。（验证：tmux 运行 explore 真实任务）(AC8/F15/F24)
- [ ] `run_in_background=true` 立即返回 task ID，子任务在同一协程实例中继续。（验证：fake
  runner 计数等于 1）(AC8/F16)
- [ ] 前台任务实际运行达到测试阈值后自动转后台，排队时间不计入阈值，已完成轮次不重复执行。
  （验证：缩短阈值的 manager 单测）(AC8/F16)
- [ ] 前台子任务运行时按 `Ctrl+B` 能立即无损转后台；Esc 仍表示取消而不是转后台。（验证：
  Textual pilot + tmux 实测）(AC8/F16)
- [ ] Fork 和 fork Skill 即使显式要求前台也始终后台。（验证：两条启动路径单测）(AC8/F16/F22)
- [ ] 同时提交四个受控任务时前三个 running，第四个 queued；前三个任一结束后第四个按提交顺序
  启动。（验证：Event 控制的 manager 单测）(AC9/F17/F18)
- [ ] queued 任务没有提前调用模型或执行工具，并能被 TaskStop 直接取消。（验证：runner 调用
  计数和状态快照）(AC9/F18/F19)
- [ ] 每个任务快照包含 ID、名称、类型、时间、状态、用量、工具数、最近活动、结果或安全错误
  摘要。（验证：TaskGet 对 completed/failed/cancelled 各检查一次）(AC9/F17)
- [ ] 任务状态只沿合法方向变化，普通异常只使当前任务 failed，不终止 Textual/asyncio 主循环。
  （验证：非法状态单测 + 注入 runner 异常后继续创建下一任务）(AC9/N3)

## 四个任务工具与通知

- [ ] `TaskList` 返回稳定的任务摘要、running 数和 queued 数。（验证：创建混合状态任务后调用）
  (AC10/F19)
- [ ] `TaskGet` 能按 ID 返回结果、状态、用量和工具数；未知 ID 返回结构化错误。（验证：成功和
  未知 ID 各调用一次）(AC10/F19)
- [ ] `TaskStop` 能取消 running/queued，终态任务和未知 ID 返回清晰错误。（验证：四种状态逐项
  调用）(AC10/F19/F21)
- [ ] `SendMessage` 按唯一名称向 completed session 续派，复用原 Conversation 但创建新 task
  ID；未知、重名、忙碌、取消 session 均返回结构化错误。（验证：Host/工具单测）(AC10/F19)
- [ ] 后台任务完成、失败或取消后，TUI 只显示安全摘要和任务 ID，不显示密钥、堆栈或完整内部
  对话。（验证：注入含敏感占位文本的错误并检查渲染）(AC11/F20/N7)
- [ ] 后台终态通知进入下一次主请求的 `<task-notification>`，只消费一次，不写 Conversation
  或 JSONL。（验证：连续构造两次主请求并检查会话文件）(AC11/F20/N4)
- [ ] 后台任务完成不会自动发起主模型请求，只有用户下一次正常输入才携带提醒。（验证：fake
  client 请求计数在任务完成时不增长）(AC11/F20)
- [ ] 通知、TaskGet 和内存结果超过上限时带截断标记，不撑爆 TUI 或请求上下文。（验证：写入
  超长 fake 结果）(F17/F20/N5)

## Skill 与 Hook 集成

- [ ] inline Skill 仍按 ch11 原路径激活并每轮注入 SOP。（验证：运行原 SkillRuntime 测试）
  (N8)
- [ ] fork Skill 不再自行创建 Agent，而是立即返回统一 task ID，并能通过 TaskGet 获取结果。
  （验证：mock Host 断言只调用统一 launch）(AC13/F22)
- [ ] fork Skill 的 full/recent/none 历史范围、允许工具、模型和 SOP 仍生效。（验证：三种 context
  测试）(AC13/F22)
- [ ] 子 Agent 的用户提交、模型停止、工具前后 Hook 正常触发。（验证：子任务触发记录型 Hook，
  检查执行顺序）(AC14/F23)
- [ ] 一个 Hook 失败只影响对应动作或子任务状态；ch12 Subagent Hook 动作仍明确报告安全占位，
  不创建新任务。（验证：Hook 集成测试）(AC14/F23/N3)

## TUI、取消和资源清理

- [ ] attached 前台子任务明细进入 scrollback，转后台后的内部文本不再逐条显示，只显示状态
  摘要。（验证：tmux 回滚检查）(AC15/F24)
- [ ] 后台启动、queued、手动/自动移交、completed、failed、cancelled 都有可区分状态行。
  （验证：Textual pilot 逐类注入事件）(AC15/F24)
- [ ] 状态栏正确显示 running/queued 数量，任务变化后及时刷新，计数为零时界面保持简洁。
  （验证：启动/完成/取消任务时观察）(AC15/F24)
- [ ] 启动可能写文件的并行后台角色时，UI 明确说明共享工作区和潜在冲突，不声称存在 Worktree
  隔离。（验证：启动两个测试写入角色，观察警告）(AC18/N6)
- [ ] 取消当前 attached 子任务后，父 Agent 工具调用得到合法取消结果，主 Conversation 无悬空
  ToolCall 且可以继续提问。（验证：取消后发送普通对话）(AC12/F21/N4)
- [ ] `/clear`、新会话和 `/resume` 会取消并清空当前会话后台任务，不把任务状态带入新会话。
  （验证：每种切换各运行一次 manager/TUI 测试）(AC12/F21)
- [ ] 退出 Dragon Code 后 queued/running task、模型流、工具协程、Hook task 和子进程均已关闭，
  终端状态正常。（验证：tmux 退出 + 自动化检查未完成 asyncio task）(AC12/F21/N5)

## 跨协议与回归

- [ ] Anthropic 下定义式、Fork、placeholder 配对、任务通知、取消和用量流程通过。（验证：协议
  fake 流测试）(AC16/F25)
- [ ] OpenAI/兼容端点下同一流程具有一致的上层 ToolCall、ToolResult 和任务状态。（验证：协议
  fake 流测试）(AC16/F25)
- [x] `uv sync --locked` 成功。（验证：运行命令，退出码 0）
- [x] `uv run ruff format --check .` 通过。（验证：224 个文件格式正确）
- [x] `uv run ruff check .` 通过。（验证：`All checks passed!`）
- [x] `uv run pytest -q` 全部通过，ch02–ch12 现有能力无回归。（验证：
  `525 passed, 2 skipped`）
  (AC16/N8)
- [ ] 运行期间对话区、状态、错误、测试输出和 Git diff 中均不出现 API Key、Authorization、
  本地环境变量全集或真实密钥。（验证：检查输出并使用安全关键词搜索）(N7)

## tmux 端到端场景

- [x] **场景 1：定义式前台探索**——启动 Dragon Code，要求主模型把真实代码探索任务委派给
  `explore`；看到角色名称、只读工具、迭代和最终文本；父对话未出现子中间历史。
  （验证：tmux 截图/文本证据）(AC3/AC8/AC15)
- [ ] **场景 2：Fork 后台和通知**——提交依赖当前对话背景的任务，模型创建 Fork；立即返回
  task ID；后台完成后出现摘要；下一次提问时模型知道通知，但完成瞬间没有自动回复。
  （验证：请求计数 + tmux 状态行）(AC4/AC11/AC17)
- [x] **场景 3：任务查询和续派**——使用自然语言让模型调用 TaskList、TaskGet，再对已完成命名
  任务调用 SendMessage；续派任务使用新 ID 且能引用原子会话内容。（验证：工具行和结果）
  (AC10)
- [ ] **场景 4：并发、排队和取消**——启动四个可控长任务，观察 3 running + 1 queued；取消
  queued，再对 attached 任务按 Ctrl+B，最后 TaskStop 取消后台任务。（验证：状态栏、scrollback
  和 TaskGet）(AC8/AC9/AC12/AC15)
- [ ] **场景 5：权限调整**——让子 Agent 尝试需要 Ask 的写入或 Bash；没有弹子任务权限框，
  模型看到拒绝后改用安全方案；主会话仍可继续。（验证：工具错误行与最终回复）(AC7)
- [ ] **场景 6：fork Skill**——运行一个现有 fork Skill；立即得到统一 task ID，后台完成后通过
  TaskGet 取得结果，主 Conversation 没有被子中间消息污染。（验证：tmux + 会话 JSONL）
  (AC13)
- [ ] **场景 7：安全退出**——有 running 和 queued 任务时退出；终端恢复，任务、模型流和子进程
  均不残留。（验证：退出后检查 tmux pane 和进程）(AC12)

## 验收报告要求

完成开发后，在本文件对应条目中勾选，并额外给出：

```markdown
## 验收报告

### 自动化通过（N/M）
- [x] 条目 — 证据：命令与实际输出

### tmux 通过（N/M）
- [x] 场景 — 证据：实际工具行、状态或截图

### 未通过
- [ ] 条目 — 预期、实际、原因、修复或后续计划
```

## 自检结果

- **Spec 对齐**：AC1–AC19 均至少对应一个检查项。
- **功能覆盖**：F1–F25 的可观察行为均已列入。
- **非功能覆盖**：缓存、响应性、失败隔离、历史合法性、资源、安全、兼容和可读性均有验证。
- **可观测性**：每项都写明运行命令、请求快照、状态变化或 TUI 行为。
- **实现解耦**：检查重点是请求、结果、状态和用户行为；重命名内部 helper 不会让条目失效。
- **端到端**：包含七个 tmux 场景，覆盖定义式、Fork、任务工具、并发、权限、Skill 和清理。
- **占位符扫描**：没有 TBD、TODO 或未定义验收方式。
