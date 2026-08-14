# Dragon Code ch11 Skill 系统 Spec

## 背景

Dragon Code 已在 ch10 建立集中式 Slash Command 框架，但 `/review` 等 AI 工作流仍以硬编码 Handler 存在。修改提示词需要改源码，用户也无法自行增加可复用工作流。

随着内置工具和 MCP 工具增多，模型同时面对全部工具会降低选择准确率。ch11 将引入 Skill 系统，把“重复提示词 + 操作流程 + 工具子集”封装成可编辑、可复用的技能包。

本章主要参考教材 ch11 的实战提示词与 Python 设计，同时结合 Dragon Code 已有的权限、Agent Loop、System Prompt、ToolRegistry 和 Slash Command 架构做必要适配。

## 目标

- **Skill 标准格式**：用 YAML frontmatter 描述元信息，用 Markdown 正文保存 SOP 指令。
- **三级加载**：按项目级、用户级、内置级顺序发现 Skill，同名时高优先级覆盖低优先级。
- **渐进式披露**：启动时只告诉模型 Skill 名称和描述；需要使用时再加载完整 SOP 和专属工具。
- **显式与自动触发**：Skill 自动注册成 Slash Command，同时允许模型通过 `LoadSkill` 根据用户意图主动激活。
- **持续激活**：激活后的 SOP 通过动态系统提醒进入每轮上下文，不写入普通历史；多个 Skill 可以同时存在，直到 `/clear` 清除。
- **两种执行模式**：inline 复用主对话；fork 使用独立 Agent，过程实时展示，最终只将摘要回流主会话。
- **最小工具集**：inline 与 fork 都落实 `allowedTools` 白名单；多个已激活 Skill 的工具取并集，系统工具始终保留。
- **目录型 Skill**：支持 `SKILL.md`、`tool.json`、`references/`，让 Skill 携带新增工具和实现脚本。
- **安全执行**：自定义 Python 工具通过 JSON 标准输入/输出在独立子进程运行，仍经过 Dragon Code 权限检查；缺少风险声明时按有副作用、不可并发处理。
- **管理与热更新**：提供 `/skill` 的查看、详情和重载能力；执行文件型 Skill 时重新读取源文件，失败则回退上次有效版本。
- **内置样板**：提供 commit、review、test 三个 Skill；现有硬编码 `/review` 由 review Skill 接管。
- **模型覆盖**：fork Skill 可选指定模型；inline Skill 继续使用当前会话模型。

## 相比教材的调整

- fork 子 Agent 不绕过 ch06 权限系统。
- Skill 自定义工具支持可选的 MCP 风格风险注解，并采用保守默认值。
- 自定义工具统一串行，暂不增加 Dragon Code 专属并发字段。
- 明确定义 Python 工具脚本的 JSON 输入输出协议。
- fork 的内部事件实时展示，但完整内部历史不写入主会话。
- inline 不切换模型，避免破坏主会话缓存与多 Skill 模型冲突。
- 教材使用 `/skill list`、`/skill info`、`/skill reload` 子命令；Dragon Code 延续 ch10 的交互式设计，通过零参数 `/skill` 打开管理界面。
- review 从硬编码命令迁移为 Skill 后，继续保留 ch10 已有的 `/r` 别名。

## 功能需求

- **F1 Skill 定义与校验**：支持 YAML frontmatter + Markdown 正文。元信息包含名称、描述、工具白名单、执行模式、可选模型和 fork 上下文策略；名称必须符合小写字母、数字和连字符规则。单个 Skill 格式错误时给出来源明确的错误，不影响其他 Skill 加载。

- **F2 三级发现与覆盖**：按“项目级 → 用户级 → 内置级”扫描 Skill；同名 Skill 只保留优先级最高者，扫描顺序保持稳定。

- **F3 两阶段加载**：启动和 `/skill` 管理界面触发重新加载后，只把有效 Skill 的名称与描述提供给模型；完整 SOP 仅在 Skill 被调用时加载，避免所有 Skill 正文长期占用上下文。

- **F4 自动意图触发**：提供系统级 `LoadSkill` 工具。模型判断用户需求匹配某个 Skill 后，可按名称激活；成功结果只返回简短状态，不重复回传完整 SOP。

- **F5 Slash Command 触发**：每个 Skill 自动注册为 `/<skill-name>` 并出现在帮助和补全菜单中。Skill 命令允许携带自由文本并替换正文中的 `$ARGUMENTS`；原有内置命令继续保持零参数和交互式操作。

- **F6 持续激活与嵌套**：inline Skill 激活后，其完整 SOP 通过临时系统提醒注入每轮请求，不写入普通或持久化历史。多个 Skill 可以同时激活，`LoadSkill` 始终可见，因此 Skill 可以继续加载其他 Skill。

- **F7 inline 工具限制**：inline Skill 使用主 Agent 和当前模型。存在已激活 Skill 时，可见工具为各 Skill `allowedTools` 的并集，并始终包含系统工具；未列入白名单的工具不能被模型看到或执行。

- **F8 fork 独立执行**：fork Skill 使用独立对话和 Agent，根据 `full`、`recent`、`none` 决定携带多少主会话上下文。子 Agent 的文本、工具调用、权限请求和执行结果实时显示，结束后只把最终摘要回流主会话。

- **F9 fork 模型选择**：fork Skill 未指定模型时继承当前模型；指定模型时使用相同协议和端点创建独立客户端。模型不可用时返回可恢复错误，不启动残缺任务。

- **F10 权限与白名单叠加**：inline 和 fork 调用工具时，同时满足 Skill 白名单与 Dragon Code 五层权限系统。白名单不能绕过黑名单、路径沙箱、规则引擎、权限模式或人在回路。

- **F11 目录型 Skill**：支持包含 `SKILL.md`、可选 `tool.json` 和 `references/` 的目录。`tool.json` 负责声明 Skill 新增工具的名称、描述、参数 Schema、执行脚本及可选 MCP 风格风险注解。执行脚本解析符号链接后的真实路径必须仍位于当前 Skill 目录内。

- **F12 自定义工具执行**：工具参数以 JSON 写入独立 Python 子进程的标准输入，脚本从标准输出返回 JSON 结果。执行具有超时、输出上限、退出码检查和结构化错误，脚本不得在 Dragon Code 主进程中直接导入。

- **F13 保守调度**：未声明风险注解的自定义工具按“非只读、可能破坏”处理；所有 Skill 自定义工具串行执行。只读注解只能影响展示和调度，不能自动绕过权限系统。

- **F14 依赖检查与冲突处理**：Skill 声明的工具不存在、脚本缺失、工具 Schema 非法或名称冲突时，加载阶段立即报告。Skill 名与内置命令冲突时拒绝注册；现有硬编码 `/review` 移除后由内置 review Skill 接管，并保留 `/r` 别名。

- **F15 热更新与回退**：执行文件型 Skill 时重新读取来源文件。重新解析成功则使用新版本；失败时使用上一次有效版本并显示警告。

- **F16 Skill 管理**：提供零参数 `/skill` 交互界面，可列出 Skill、查看来源与元信息、重新扫描加载；用户不需要手写长 Skill 名、子命令或文件路径。

- **F17 生命周期清理**：`/clear`、切换或恢复会话时清除已激活 Skill 和临时工具限制，避免旧 SOP 泄漏到新会话。Skill 定义仍保留，无需重新启动。

- **F18 内置 Skill**：提供 commit、review、test 三个可编辑样板，覆盖 inline、fork、参数替换、工具白名单和典型开发流程。

## 非功能需求

- **N1 缓存稳定**：Skill 摘要按固定顺序进入稳定 System Prompt；完整 SOP 通过动态提醒注入，不污染缓存前缀或持久历史。
- **N2 既有能力不退化**：Agent Loop、上下文压缩、会话恢复、权限系统、MCP、Slash Command、记忆系统和双协议行为继续成立。
- **N3 界面不阻塞**：Skill 扫描、脚本执行和 fork Agent 均使用异步路径；执行期间 TUI 的流式输出、计时、滚动和取消保持响应。
- **N4 历史合法**：inline 激活、fork 摘要回流、错误和取消都不能留下悬空 ToolCall、缺失 ToolResult 或非法角色顺序。
- **N5 失败隔离**：一个 Skill 解析失败、工具脚本失败或 fork Agent 出错，不影响其他 Skill、主 Agent 或后续对话。
- **N6 资源有界**：Skill 文件、`tool.json`、脚本输出、fork 上下文和执行时间均设置合理上限，防止撑爆上下文或界面。
- **N7 取消与清理**：取消 fork 或自定义工具后，尽力终止对应任务和子进程；退出时不残留后台任务、管道或 Python 子进程。
- **N8 安全边界明确**：只加载本地项目级、用户级和内置 Skill，不联网下载或自动安装。自定义脚本属于本地可执行代码，调用前仍经过权限判断，但本章不宣称提供操作系统级沙箱。
- **N9 敏感信息保护**：错误、日志、Skill 详情和脚本结果不得输出 API Key、Authorization、环境变量全集或异常堆栈。
- **N10 确定性**：Skill 与工具扫描顺序固定；相同文件输入应得到相同的覆盖、注册和摘要顺序。
- **N11 跨平台**：路径、UTF-8、Python 子进程和 JSON 管道在 Windows 与 WSL/Linux 下行为一致。
- **N12 跨协议一致**：Anthropic 与 OpenAI/兼容端点下，Skill 发现、激活、工具过滤、fork 事件和结果回流体验一致。
- **N13 可理解性**：优先使用普通类、简单函数和清晰分支；解析、白名单、fork、权限衔接和子进程边界添加简短中文注释。
- **N14 可扩展性**：新增 Skill 主要通过增加目录和 Markdown 完成；新增普通 Skill 不修改 Agent、TUI 或命令框架源码。
- **N15 代码质量**：通过 `ruff format`、`ruff check`、全部自动化测试，并完成真实 tmux 端到端验收。

## 不做的事

- **Skill 市场与远程分发**：不搜索、下载、安装或更新网络上的 Skill。
- **版本与签名体系**：不做 Skill 版本解析、依赖锁定、数字签名和可信发布者验证。
- **操作系统级沙箱**：不使用容器、虚拟机或受限账户隔离自定义脚本；只提供现有权限判断、超时和子进程隔离。
- **自动安装依赖**：Skill 缺少 Python 包或外部程序时返回清晰错误，不自动执行 `pip install`、`uv add` 等操作。
- **多语言自定义工具**：本章只规定 Python 脚本执行协议，不为 JavaScript、Go、Shell 分别设计运行器。
- **文件监听器**：不常驻监听目录变化；执行时重读文件，或通过 `/skill` 管理界面手动重新扫描。
- **后台 Skill**：不支持定时、守护进程式或退出后继续运行的 Skill。
- **Skill Pipeline**：不在 frontmatter 中设计自动流水线、`canDelegateTo` 或声明式 Skill 编排。
- **完整 SubAgent 管理**：允许 Skill 嵌套，但不实现父子 Agent 树、深度限制、后台 Agent 和独立任务面板；这些留给 ch13。
- **跨会话保持激活**：只持久化普通会话消息，不恢复 `activeSkills`；恢复会话后需要重新激活。
- **独立 Provider 选择**：fork 的 `model` 只覆盖当前 Provider 的模型名，不切换协议、API Key 或服务商。
- **自定义工具并发优化**：所有 Skill 自定义工具串行执行。
- **Skill 编辑器**：不在 TUI 中创建或编辑 Skill；用户直接修改 Markdown、JSON 和 Python 文件。
- **自动质量评分**：不自动评价、排序或推荐第三方 Skill。
- **完全兼容所有厂商格式**：主要遵循教材结构，并吸收 Agent Skills/MCP 的常用字段；不保证任意第三方 Skill 可以不经调整直接运行。

## 验收标准

- **AC1 Skill 解析**：有效 frontmatter 与 Markdown 能生成完整 Skill；缺少名称/描述、非法名称、错误模式或损坏 YAML 返回带文件来源的错误。（F1）
- **AC2 失败隔离**：同一目录中一个 Skill 损坏时，其余有效 Skill 仍能加载和使用。（F1、N5）
- **AC3 三级优先级**：项目级、用户级、内置级存在同名 Skill 时只采用项目级；删除项目级后自动落到用户级，顺序稳定。（F2）
- **AC4 第一阶段摘要**：模型请求只包含有效 Skill 的名称和描述，不包含未激活 Skill 的完整 SOP；多轮之间摘要逐字节稳定。（F3、N1）
- **AC5 自动激活**：用户使用自然语言提出匹配任务时，模型能调用 `LoadSkill`；下一轮看到完整 SOP，而 ToolResult 只含简短激活结果。（F4）
- **AC6 显式命令**：加载 commit Skill 后，`/commit` 出现在帮助和补全菜单；`/commit 自定义要求` 能把自由文本替换进 `$ARGUMENTS`。（F5）
- **AC7 内置命令不变**：`/resume abc` 等原有零参数命令仍提示不接收参数，原有交互式选择行为不退化。（F5、N2）
- **AC8 持续与多 Skill 激活**：激活两个 inline Skill 后，后续每轮都能看到两份 SOP；普通历史和 JSONL 中不出现重复 SOP。（F6）
- **AC9 inline 白名单**：激活 Skill 后，请求中只出现其 `allowedTools` 与系统工具；模型伪造调用白名单外工具时也不能执行。（F7、F10）
- **AC10 白名单并集**：多个 inline Skill 同时激活时，可见工具是各自白名单并集，且 `LoadSkill` 始终保留。（F6、F7）
- **AC11 inline 模型**：inline Skill 始终复用当前主 Agent、对话历史和模型，不因 frontmatter 的 `model` 字段切换主模型。（F7、F9）
- **AC12 fork 上下文**：分别使用 `full`、`recent`、`none` 运行 fork Skill，子 Agent 获得对应范围的上下文，不共享可变 Conversation 对象。（F8）
- **AC13 fork 展示与回流**：子 Agent 的文本、工具调用、结果和权限请求实时显示；结束后主历史只记录 Skill 触发和最终摘要，不包含完整子对话。（F8、N4）
- **AC14 fork 模型覆盖**：有效模型名能用于 fork；未填写时继承当前模型；无效模型返回可恢复错误，主会话仍能继续。（F9）
- **AC15 权限不绕过**：fork 和自定义工具分别触发危险命令、项目外路径及 Ask 情形时，仍经过黑名单、沙箱、规则、模式与用户确认。（F10）
- **AC16 目录型 Skill**：包含 `SKILL.md`、`tool.json`、`references/` 的 Skill 能加载并把新增工具注册进当前工具中心，逃出 Skill 目录的脚本路径被拒绝。（F11）
- **AC17 脚本执行协议**：自定义工具正确接收标准输入 JSON 并返回标准输出 JSON；参数错误、非零退出、非法 JSON、超时和过长输出均变成结构化 ToolResult。（F12）
- **AC18 保守元信息**：未填写 annotations 的自定义工具按非只读、可能破坏、不可并发处理；有效 MCP 风格注解能被解析，但不能绕过权限。（F13）
- **AC19 串行执行**：模型一次请求两个 Skill 自定义工具时按原顺序串行执行，结果顺序稳定。（F13）
- **AC20 依赖与冲突检查**：不存在的 `allowedTools`、缺失脚本、非法 Schema、重复工具名及内置命令重名均在加载时给出清晰错误。（F14）
- **AC21 热更新回退**：修改 Skill 文件后下一次执行使用新内容；随后故意破坏 frontmatter 时显示警告并继续使用上一次有效版本。（F15）
- **AC22 Skill 管理**：`/skill` 可交互查看列表、来源和详情并执行 reload；用户无需输入完整路径或长名称。（F16）
- **AC23 生命周期**：`/clear`、恢复其他会话和切换会话后，原有 active Skills、SOP 与临时白名单全部清除，Skill 定义仍可重新使用。（F17）
- **AC24 内置样板**：commit、review、test 均可加载和执行；review 使用 fork，commit/test 使用教材指定的 inline 流程；源码中不再存在硬编码 `/review` 提示，`/r` 仍能触发 review Skill。（F18）
- **AC25 缓存与上下文**：未激活时只有稳定 Skill 摘要进入缓存前缀；激活后的 SOP 通过动态提醒注入，不持久化、不破坏工具结果配对。（N1、N4）
- **AC26 取消与清理**：执行 fork 或自定义脚本时按 Esc/Ctrl+C 能回到空闲态，子任务和子进程被清理，随后可继续对话。（N3、N7）
- **AC27 安全与体量**：错误和 UI 不泄露 Key、环境变量全集或堆栈；大型 Skill、脚本输出和 fork 上下文受上限控制。（N6、N8、N9）
- **AC28 跨平台与协议**：Windows/WSL 下 JSON 管道和路径行为一致；Anthropic 与 OpenAI/兼容端点下显式调用、自动激活和 fork 回流一致。（N11、N12）
- **AC29 全量回归**：`uv sync --locked`、格式、lint、编译和全部 pytest 通过，ch02–ch10 原测试无回归。（N2、N15）
- **AC30 真实端到端**：在 tmux 中启动 Dragon Code，使用临时项目 Skill 完成“自然语言自动激活 → 读取文件 → 最终答复”，再执行一次 `/review` fork 和一个目录型自定义工具；逐项记录工具行、权限、回流、清理及最终回复证据。（N15）
