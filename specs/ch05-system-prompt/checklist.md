# 系统提示工程化 Checklist

> 每一项都通过运行代码、检查请求结构或观察终端行为验证。完成开发后记录实际证据，再勾选结果。

## 实现完整性

- [x] 七个固定系统提示模块按“身份 → 系统约束 → 任务模式 → 动作执行 → 工具使用 → 语气风格 → 文本输出”顺序装配，模块间只有一个空行。（验证：运行 `uv run pytest tests/test_prompt.py -q -k "module or assemble"`，检查模块顺序和分隔符。）(AC1/F1)
- [x] 自定义指令、已激活 Skill、长期记忆三个可选模块为空时被跳过，提供内容时出现在固定模块之后。（验证：运行 `uv run pytest tests/test_prompt.py -q -k "optional"`，观察空模块与测试模块两种结果。）(AC2/F1)
- [x] 新增测试提示模块只需提供名称、优先级和内容，不修改装配主循环。（验证：在单测中挂载一个测试模块并运行装配器，期望按优先级出现。）(AC1/N8)
- [x] 稳定系统提示不包含工作目录、平台日期、Git 状态、模型、当前模式或迭代次数。（验证：连续使用两组不同环境构造提示，断言 `stable` 逐字一致。）(AC5/F3/N1)
- [x] 环境信息包含工作目录、平台、日期、版本、模型和可用的 Git 摘要，并与稳定提示分开保存。（验证：运行 `uv run pytest tests/test_prompt.py -q -k "environment"`，检查 `SystemPrompt.stable` 与 `SystemPrompt.environment`。）(AC3/F2)
- [x] 非 Git 目录、Git 不可用、Git 非零退出或超时时，Git 信息省略或降级且系统提示仍能生成。（验证：运行 `uv run pytest tests/test_prompt.py -q -k "git or gather_environment"`。）(AC13/F2/N4)
- [x] Git 摘要只包含分支、是否修改和修改数量，不包含文件正文、diff、API Key 或敏感环境变量。（验证：检查环境信息测试输出并搜索已知测试密钥不存在。）(N4/N5)
- [x] Plan Mode 第 1、6、11……轮使用完整提醒，其他轮使用精简提醒；默认模式不生成 Plan reminder。（验证：运行 `uv run pytest tests/test_prompt.py tests/test_agent.py -q -k "reminder or plan"`。）(AC9/F7)
- [x] 所有补充提醒都使用 `<system-reminder>` 标签，且提醒正文要求模型遵守而不是直接复述提醒。（验证：检查提醒构造单测和一次 Plan Mode 实际回复。）(AC8/F6)
- [x] Edit 工具定义同时说明“编辑前必须 Read”和“old_text 必须唯一匹配”。（验证：运行 `uv run pytest tests/test_file_tools.py tests/test_tool_registry.py -q`，检查导出的描述。）(AC7/F5)
- [x] Bash 工具定义说明 Read、Glob、Grep 等专用工具优先于 Shell 拼凑。（验证：运行 `uv run pytest tests/test_bash_tool.py tests/test_tool_registry.py -q`，检查导出的描述。）(AC7/F5)
- [x] 稳定系统提示的工具使用模块也包含“优先专用工具”和“编辑前先读”规则。（验证：运行提示单测并在稳定提示文本中断言两条规则。）(AC7/F5)

## Anthropic 协议

- [x] Anthropic 请求只有一个顶层 `system` 字段，该字段包含两个有序文本内容块。（验证：运行 `uv run pytest tests/test_client_anthropic.py -q -k "system or request"`，检查 `system[0]`、`system[1]`。）(AC3/F2)
- [x] `system[0]` 是稳定提示并带 `cache_control: {"type": "ephemeral"}`；`system[1]` 是环境信息且没有缓存标记。（验证：检查 Anthropic 请求体单测。）(AC4/F3)
- [x] Anthropic 工具定义保持固定顺序，稳定 system 断点覆盖工具与稳定提示，最后一个工具不重复添加断点。（验证：连续构造两次请求并比较工具数组与稳定内容逐字一致。）(AC4/AC5/F3/N1)
- [x] Anthropic reminder 只注入请求副本；首轮真实用户文本与 reminder 是独立内容块。（验证：运行 `uv run pytest tests/test_client_anthropic.py -q -k "reminder"`，并比较调用前后的 `ChatMessage`。）(AC8/F6/N3)
- [x] Anthropic 工具续轮中，全部 `tool_result` 内容块位于 reminder 文本块之前，tool use/result 配对不被打断。（验证：运行 `uv run pytest tests/test_client_anthropic.py -q -k "tool_result or reminder"`。）(AC12/F6/N3)
- [x] Anthropic 正确解析缓存创建和缓存读取 Token；字段缺失时均为零。（验证：运行 `uv run pytest tests/test_client_anthropic.py -q -k "usage or cache"`。）(AC6/F4/N6)

## OpenAI 协议

- [x] OpenAI 请求的第一条 system 消息由“稳定提示 + 两个换行 + 环境信息”组成，稳定提示完整位于前缀。（验证：运行 `uv run pytest tests/test_client_openai.py -q -k "request or system"`。）(AC3/F2/F3)
- [x] OpenAI 请求不包含 Anthropic 专属 `cache_control` 字段。（验证：递归检查 OpenAI 请求体，期望没有 `cache_control`。）(F3/F8)
- [x] OpenAI reminder 只进入临时请求副本，不改变正式消息历史，不打断 assistant tool call 与 tool 结果。（验证：运行 `uv run pytest tests/test_client_openai.py -q -k "reminder or tool_history"`。）(AC8/AC12/F6/N3)
- [x] OpenAI 正确解析 `prompt_tokens_details.cached_tokens`；字段缺失时读取量为零，写入量始终为零。（验证：运行 `uv run pytest tests/test_client_openai.py -q -k "usage or cache"`。）(AC6/F4/N6)

## Agent 与集成

- [x] LLM Client 对外统一接收 `LLMRequest`，Agent 不直接处理 Anthropic/OpenAI 专属字段。（验证：搜索客户端调用并运行 `uv run pytest tests/test_agent.py -q`。）(F8/N8)
- [x] 每次 `Agent.run()` 只构造一次稳定提示并只采集一次环境信息，Loop 内每轮复用同一个 `SystemPrompt`。（验证：在 Agent 单测中记录构造/采集次数及多轮请求内容。）(F2/F3/N1/N4)
- [x] 每轮请求仍携带 system、当前完整历史和当前模式可用的工具定义。（验证：记录 Fake LLM Client 收到的多轮 `LLMRequest`。）(F3/F7)
- [x] reminder 不写入 `Conversation`，不显示在 TUI scrollback，任务完成后再次提问仍能正常请求。（验证：Agent 历史单测 + tmux 连续两次真实提问。）(AC8/AC12/F6/N3)
- [x] Plan Mode 只发送 Read、Glob、Grep 定义；`/do` 恢复六个工具并立即执行已确认计划。（验证：Agent/TUI 单测 + tmux `/plan`、`/do` 场景。）(AC9/F7)
- [x] ch04 的多轮 Agent Loop、保序分批并发、停止条件、取消和流错误恢复不退化。（验证：运行完整 `tests/test_agent.py`、`tests/test_tool_scheduler.py`、`tests/test_stream_collector.py`。）(AC11/N2)
- [x] 统一用量对象和 Agent 任务累计量包含输入、输出、缓存写入、缓存读取四项。（验证：运行 Agent 与 StreamCollector 用量测试。）(AC6/F4)
- [x] TUI 继续显示现有输入/输出 Token 状态，不增加缓存面板，界面布局和 `/help` 不退化。（验证：运行 `uv run pytest tests/test_tui.py -q` 并启动 TUI 观察。）(N2)
- [x] Anthropic 与 OpenAI 使用同一组稳定模块、环境内容和 Plan reminder 节奏，差异只存在于请求序列化和用量字段解析。（验证：对两个 Fake Client 使用同一个 `LLMRequest`，对比语义内容。）(AC10/F8)

## 缓存确定性与真实烟测

- [x] 同一工具集和固定模块连续构造两次时，工具定义与稳定提示逐字节一致。（验证：单测对序列化结果直接比较。）(AC5/F3/N1)
- [x] 修改日期、工作目录、Git 状态或对话历史不会改变稳定提示与工具定义。（验证：单测改变动态字段后再次比较稳定前缀。）(AC5/F3/N1)
- [x] 缓存烟测脚本只打印四类 Token 用量和必要说明，不打印 API Key、系统提示全文或消息正文。（验证：运行 `uv run python scripts/cache_smoke.py --help`，并通读脚本输出路径。）(N5)
- [ ] 对支持 Anthropic Prompt Cache 且达到最低缓存 Token 数的端点连续请求两次：首次出现缓存写入量，后续出现缓存读取量。（验证：运行 `uv run python scripts/cache_smoke.py`，记录两次实际用量。）(AC4/F3)
- [x] 如果当前兼容端点不返回缓存字段，脚本显示缓存值为零并给出“端点可能不支持或未达到门槛”的说明，程序不崩溃。（验证：在当前 DeepSeek 兼容配置下运行烟测。）(AC6/N6)

## 编译、测试与安全

- [x] `uv run pytest -q` 全部通过。（验证：记录实际通过/跳过/失败数量。）(AC14/N7)
- [x] `uv run ruff format --check .` 通过。（验证：命令退出码为 0。）(AC14/N7)
- [x] `uv run ruff check .` 无告警。（验证：命令退出码为 0。）(AC14/N7)
- [x] `rg "build_agent_prompt" src tests` 无结果，旧的模式拼接入口已移除。（验证：搜索命令无匹配。）(F6/F7)
- [x] 配置密钥不会出现在对象 repr、测试输出、TUI、缓存烟测或异常信息中。（验证：使用已知测试密钥运行相关测试并搜索捕获输出。）(AC14/N5)
- [x] 环境采集超时、客户端流结束和任务取消后无未关闭流、子进程或 asyncio task。（验证：相关清理单测通过，测试结束无 pending task 警告。）(N2/N4)

## tmux 端到端场景

- [x] 场景 1——默认模式真实对话：在 tmux 启动 Dragon Code，要求“读取 `specs/ch05-system-prompt/spec.md` 并概括目标”；观察 Agent 调用 Read、得到结果并给出与文件内容一致的答复，TUI 不显示 system-reminder。（验证：保存 tmux pane 输出。）(AC8/AC11)
- [x] 场景 2——多轮工具任务回归：要求“读取某个小文件，再根据内容创建摘要文件”；观察 Agent Loop 自动读后写、无需中途催促，最终文件存在且内容正确。（验证：tmux 输出 + 检查临时文件，测试后清理临时文件。）(AC11/N2)
- [x] 场景 3——Plan Mode：输入 `/plan` 后给出一个需要修改文件的任务；观察只调用 Read/Glob/Grep 并给出计划，再输入 `/do`，观察恢复 Edit/Write/Bash 并按计划执行。（验证：tmux 输出、工具行与结果摘要。）(AC9/F7)
- [x] 场景 4——历史可继续：完成含工具结果和 reminder 的任务后再提出一条普通问题；观察第二次请求成功，无消息结构相关 400，前一轮提醒未出现在 scrollback。（验证：tmux 连续两轮输出。）(AC12/N3)
- [x] 场景 5——缓存观测：在同一配置下运行缓存烟测或连续两个稳定请求；记录缓存写入/读取字段的实际结果，并注明端点是否支持及是否达到最低门槛。（验证：真实命令输出，不以“应该命中”代替证据。）(AC4/AC6)
- [x] 场景 6——取消回归：运行一个会触发多轮或较慢工具的任务，按 Esc 或流式态 Ctrl+C；观察任务取消、界面回到空闲且下一条消息仍可发送。（验证：tmux 输出与后续正常对话。）(AC11/N2/N3)

## 核心源码回顾准备

- [x] 开发完成后向用户回顾 `prompt.py`：模块装配、环境采集、reminder 节奏。（验证：结合真实源码逐段讲解。）
- [x] 回顾 `models.py` 与 `agent.py`：`SystemPrompt`、`LLMRequest` 如何进入每一轮 Agent Loop。（验证：画出一条简洁请求链路。）
- [x] 回顾两个 LLM Client：同一份统一请求如何变成 Anthropic 与 OpenAI 的不同格式。（验证：展示删去密钥和正文后的请求结构对比。）
- [x] 把“system 是一个字段、内部两个内容块”“缓存顺序 tools → system → messages”等值得记忆的内容补充到项目学习笔记。（验证：检查笔记文档新增条目。）
