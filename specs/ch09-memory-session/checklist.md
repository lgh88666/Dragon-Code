# ch09：项目记忆与会话持久化 Checklist

## 状态

- 阶段：已验收（2026-08-11）
- 输入：已批准的 `spec.md`、`plan.md` 与 `task.md`
- 验收原则：先运行或观察，再勾选；自动化证据与 tmux 证据分开记录

## 项目指令

- [x] **三层指令按优先级加载**：项目根、项目 `.dragon-code/`、用户 `~/.dragon-code/` 三份 `DRAGON.md` 均进入自定义指令模块，项目根内容排在最前。（验证：运行 `uv run pytest -q tests/test_instructions.py -k order`；再在隔离项目中启动并询问三份文件中的标记，模型按顺序复述。）(AC1/F1/F7)
- [x] **缺失来源可降级**：只保留项目根 `DRAGON.md` 时程序正常启动，系统提示只包含已有内容。（验证：运行 `uv run pytest -q tests/test_instructions.py -k missing`；隔离目录启动无堆栈。）(AC2/F1/F8)
- [x] **独占行 include 正确展开**：`@include rules/style.md` 被目标正文替换，普通段落中的 `@include` 文本不被误解析。（验证：运行 `uv run pytest -q tests/test_instructions.py -k include`，观察最终加载文本。）(AC3/F2)
- [x] **嵌套深度有上限**：6 层引用只展开允许的 5 层并出现可读警告，其他内容仍可用。（验证：运行 `uv run pytest -q tests/test_instructions.py -k depth`。）(AC4/F3)
- [x] **循环引用不会失控**：A→B→A 被识别，加载结束且产生环路警告；两个非循环分支合法重复引用同一文件不被误判。（验证：运行 `uv run pytest -q tests/test_instructions.py -k cycle`。）(AC5/F4)
- [x] **引用不能逃逸边界**：项目级和用户级 include 均在解析符号链接后检查边界，越界、二进制、非法 UTF-8 和不可读文件被跳过并提示。（验证：运行 `uv run pytest -q tests/test_instructions.py -k "escape or binary or encoding"`。）(AC6/F5/F6/N5)
- [x] **指令加载速度有界**：正常三层小型指令加载耗时低于 200ms。（验证：自动化性能测试或用 `Measure-Command` 连续运行，报告实际最大值。）(N1)

## 会话存档

- [x] **新会话 ID 和目录一致**：ID 符合 `YYYYMMDD-HHMMSS-xxxx`，同一目录同时容纳 `conversation.jsonl` 与 ch08 工具结果。（验证：运行 `uv run pytest -q tests/test_context_state.py tests/test_session_persistence.py -k "session_id or open_new"`；真实启动后检查目录。）(AC7/F9/F10)
- [x] **JSONL 逐条保存完整消息**：完成一轮后每行都是合法 JSON，包含角色、正文、时间戳，首条含模型；工具调用、工具结果和 `hidden_blocks` 往返无丢失。（验证：运行 `uv run pytest -q tests/test_session_persistence.py -k "codec or writer or hidden"`；用 JSON 解析器读取真实会话文件。）(AC8/F11/F12/F14)
- [x] **压缩以边界标记追加**：执行 `/compact` 后旧记录不被重写，文件末尾出现 compact 标记及新历史；恢复时只采用最后边界后的消息。（验证：运行 `uv run pytest -q tests/test_session_persistence.py -k compact`；真实执行 `/compact` 后查看 JSONL。）(AC9/F15/F20)
- [x] **尾部损坏可恢复**：最后一行只有半段 JSON 时，恢复跳过该行并保留此前完整消息。（验证：运行 `uv run pytest -q tests/test_session_persistence.py -k "bad or partial"`。）(AC10/F16/F20)
- [x] **写入并发和刷盘安全**：并发追加不会产生交错半行，每条完成记录 flush+fsync，`close()` 可重复调用。（验证：运行 `uv run pytest -q tests/test_session_persistence.py -k "concurrent or flush or close"`。）(F12/F13/N2)
- [x] **追加性能符合目标**：普通单条 JSONL append 的典型耗时低于 10ms；若当前磁盘环境波动超出目标，报告实际数据而非隐藏。（验证：自动化性能测试记录多次中位数和最大值。）(N1)

## 会话恢复与清理

- [x] **`/resume` 只走本地路由**：IDLE 输入 `/resume` 不请求 LLM，打开会话列表；Esc 取消并返回 IDLE。（验证：运行 `uv run pytest -q tests/test_tui.py -k "resume and route"`；tmux 中实际操作。）(AC11/F17)
- [x] **列表元数据完整**：三个有效会话显示三项，每项有 50 字内标题、相对时间、记录模型和文件大小，按最近时间排序。（验证：运行 `uv run pytest -q tests/test_session_persistence.py tests/test_tui.py -k "list or metadata or resume_screen"`。）(AC12/F18/F19)
- [x] **列表搜索有效**：输入标题或 ID 关键词后只保留匹配项，清空搜索恢复全部。（验证：运行 `uv run pytest -q tests/test_tui.py -k filter`；tmux 中搜索一次。）(AC13/F19)
- [x] **坏行按整行跳过**：文件中间插入非法内容后，其他合法消息仍被加载，并显示/记录跳过数量。（验证：运行 `uv run pytest -q tests/test_session_persistence.py -k bad_line`。）(AC14/F20)
- [x] **悬空工具调用被截断**：末尾 assistant ToolCall 缺少对应 ToolResult 时，从该 assistant 前截断；完整多工具配对不受影响。（验证：运行 `uv run pytest -q tests/test_session_persistence.py -k orphan`，并确认恢复后消息可再次发送给 provider。）(AC15/F21/N3)
- [x] **超限恢复只压缩一次**：超过 ch08 阈值的历史在进入 IDLE 前尝试一次结构化压缩；失败时保留当前旧会话而非半切换。（验证：运行 `uv run pytest -q tests/test_context_manager.py tests/test_tui.py -k "restore and compact"`。）(AC16/F22/N3)
- [x] **跨时段提醒不污染旧文件**：最后消息超过 6 小时时，恢复后的内存历史含时间跨度提醒，恢复动作本身不立即追加旧 JSONL。（验证：运行 `uv run pytest -q tests/test_session_persistence.py -k reminder`，对比恢复前后文件行数。）(AC17/F23)
- [x] **恢复后续写原会话**：恢复后新用户/助手记录进入被选中会话原 JSONL，不写入启动时创建但未选中的会话。（验证：运行 `uv run pytest -q tests/test_session_persistence.py tests/test_tui.py -k "restore and append"`；tmux 恢复后检查文件。）(AC18/F24)
- [x] **恢复切换是原子的**：目标历史读取、修复或压缩任一步失败时，旧 Conversation、ContextManager 和 Writer 仍可用；成功后旧 Writer 被关闭。（验证：运行 `uv run pytest -q tests/test_tui.py -k "restore_session or rollback"`。）(F24/N2/N3)
- [x] **45 天清理边界正确**：46 天前的新格式会话被删除，44 天前保留；单个删除失败不影响其他会话。（验证：运行 `uv run pytest -q tests/test_session_persistence.py -k cleanup`。）(AC19/F25)
- [x] **旧格式数据受保护**：旧 session ID 不显示在 `/resume`，也不被自动清理；底层 ch08 路径仍能安全识别旧 ID。（验证：运行 `uv run pytest -q tests/test_context_state.py tests/test_session_persistence.py -k legacy`。）(AC20/F26/N4)
- [x] **50 个会话扫描速度有界**：列出 50 个本地会话耗时低于 500ms。（验证：自动化性能测试或 `Measure-Command`，记录实际耗时。）(N1)

## 自动记忆

- [x] **四类笔记可创建并正确归属**：用户偏好、纠正反馈进入用户级；项目知识、参考资料进入项目级；Markdown frontmatter 含 type/title/created/updated，文件名为 `<type>_<slug>.md`。（验证：运行 `uv run pytest -q tests/test_memory.py -k "create or category or level"`；真实提出“记住我偏好简洁回复”后检查文件。）(AC21/F27/F28/F29/F30)
- [x] **索引随增删改重建**：create/update/delete 后相应 `MEMORY.md` 摘要行同步变化，不残留已删除条目。（验证：运行 `uv run pytest -q tests/test_memory.py -k "update or delete or rebuild"`。）(AC22/F31/F34/F40)
- [x] **记忆索引进入后续请求**：启动时同时加载项目级和用户级索引；后台更新完成后，当前会话下一次请求使用新快照，无需重启。（验证：运行 `uv run pytest -q tests/test_prompt.py tests/test_agent.py tests/test_memory.py -k "memory and index"`；真实下一轮询问保存偏好。）(AC23/F32/F36/F43)
- [x] **模型可按索引读取用户记忆详情**：Read 能读取 `~/.dragon-code/memory/`，但 Write/Edit/Glob/Grep 对该目录仍被沙箱拒绝。（验证：运行 `uv run pytest -q tests/test_file_tools.py tests/test_permission_sandbox.py tests/test_tool_registry.py -k "memory or extra_read"`。）(F33/N5)
- [x] **记忆更新不阻塞主会话**：后台 LLM 尚未返回时，新用户消息可以立即进入 Agent Loop，spinner 和输入状态正常。（验证：运行 `uv run pytest -q tests/test_memory.py tests/test_agent.py -k background`；tmux 使用可控慢响应观察。）(AC24/F37/N8)
- [x] **后台失败静默隔离**：模型错误、非法 JSON 或磁盘错误不进入对话区、不终止会话、不自动重试；内部日志记录原因，后续记忆任务仍能执行。（验证：运行 `uv run pytest -q tests/test_memory.py -k "failure or invalid"`。）(AC25/F38/F39/F42/N6)
- [x] **索引体量受控**：单索引最多 200 行/25KB，合并注入最多 25KB，截断时带 `(index truncated)` 且不切断 UTF-8 字符。（验证：运行 `uv run pytest -q tests/test_memory.py -k limit`。）(AC26/F31/F36)
- [x] **触发规则准确**：前四轮普通自然完成不触发，第五轮触发；出现 `记住/记忆/别忘/remember/memo` 任一关键词立即触发；取消、错误、未知工具或迭代上限不触发。（验证：运行 `uv run pytest -q tests/test_agent.py tests/test_memory.py -k trigger`。）(AC31/F35/F41)
- [x] **记忆更新使用无工具请求**：请求由当前 `LLMClient` 发送但工具定义为空，响应只解析 JSON 操作，不可能后台调用 Bash/文件工具。（验证：运行 `uv run pytest -q tests/test_memory.py -k "prompt or no_tools"`，检查假客户端请求。）(F37/F38/N5)
- [x] **记忆文件更新原子且串行**：并发触发由 `asyncio.Lock` 串行处理，临时文件 replace 后不留下半写文件或孤立临时文件。（验证：运行 `uv run pytest -q tests/test_memory.py -k "lock or atomic or concurrent"`。）(F40/N2)

## 系统集成与非回归

- [x] **系统提示模块位置正确**：项目指令进入自定义指令模块，记忆进入长期记忆模块；空内容跳过，七个固定模块及 system-reminder 语义不变。（验证：运行 `uv run pytest -q tests/test_prompt.py -k "custom or memory or order"`。）(AC27/F43)
- [x] **Conversation 通知覆盖完整**：用户、助手、工具调用/结果和整体历史替换都触发存档；没有回调时与 ch08 行为一致。（验证：运行 `uv run pytest -q tests/test_session.py -k "callback or persistence"`。）(AC28/F13/F15/F44/N4)
- [x] **Agent 与恢复状态互斥**：Agent Loop 中 `/resume` 只提示等待；RESUMING 时不能提交新对话或再次恢复。（验证：运行 `uv run pytest -q tests/test_tui.py -k "resume and state"`；tmux 分别尝试。）(AC29/F46/N8)
- [x] **`/compact` 与后台记忆互不破坏**：两者并行时都能结束，Conversation、JSONL 和 `MEMORY.md` 均为合法完整内容。（验证：运行 `uv run pytest -q tests/test_memory.py tests/test_context_manager.py tests/test_agent.py -k "compact and memory"`；必要时用可控慢客户端复现。）(AC30/F47/N2)
- [x] **保存失败可见但会话继续**：模拟 Writer 失败时 TUI 黄色显示“本轮未能保存”，最终回复仍完成且下一轮可提交；警告不混入 assistant 正文。（验证：运行 `uv run pytest -q tests/test_agent.py tests/test_tui.py -k session_warning`。）(AC32/F44/N6)
- [x] **当前 Provider 保持不变**：恢复记录中的模型只用于列表展示，恢复后仍使用启动时选择的当前 LLMClient。（验证：运行 `uv run pytest -q tests/test_session_persistence.py tests/test_tui.py -k provider`。）(F18/F24)
- [x] **ch02–ch08 能力不退化**：流式、工具调用、权限审批、MCP、Plan Mode、取消和上下文压缩原测试均通过。（验证：运行全量 `uv run pytest -q`。）(N4/N9)
- [x] **本地数据不进入 Git**：`.dragon-code/sessions/` 和 `.dragon-code/memory/` 被忽略，根目录和项目目录的 `DRAGON.md` 可选择提交，用户目录始终位于仓库外。（验证：运行 `git check-ignore -v` 检查两个自动目录，再确认 `git check-ignore .dragon-code/DRAGON.md` 返回未忽略。）(N5)
- [x] **退出清理完整**：退出时 Writer 关闭、记忆和清理任务被取消/等待、MCP 子进程关闭，终端状态恢复。（验证：单测退出路径；tmux `/exit` 后用进程检查确认无残留。）(N2/N8)
- [x] **无新运行依赖**：`pyproject.toml` 与锁文件未因 ch09 引入新包。（验证：查看 diff，并运行 `uv sync --locked`。）(N10)

## 编译、格式与测试

- [x] `uv sync --locked` 成功，锁文件一致。
- [x] `uv run ruff format --check .` 通过。
- [x] `uv run ruff check .` 无告警。
- [x] `uv run pytest -q` 全量通过，并在验收报告记录实际通过/跳过数量。
- [x] 项目指令、会话、记忆相关测试全部使用临时目录和假 LLMClient，不访问真实用户记忆、不调用真实网络。（验证：检查测试夹具与测试运行输出。）(N5/N7)
- [x] 运行输出、日志、JSONL、记忆、验收报告和 Git diff 均不含 API Key、Authorization、密码或本地配置正文。（验证：在本章变更和生成测试目录中做敏感字段检索，人工复核命中。）(N5)

## tmux 端到端场景

- [x] **场景 1：指令加载**——在隔离项目准备三层 `DRAGON.md` 和合法 include，tmux 启动 Dragon Code，询问约定内容，模型回答体现高优先级项目规则；越界 include 只产生警告，程序继续运行。(AC1–AC6)
- [x] **场景 2：完整存档**——发出一条会触发 Read 的真实请求，观察 Agent 调用工具并最终回复；检查 JSONL 中 user、assistant ToolCall、ToolResult、assistant 最终消息按序完整配对。(AC7–AC8/AC28)
- [x] **场景 3：压缩与恢复**——执行 `/compact` 后 `/exit`，重新启动并输入 `/resume`；搜索并选择刚才会话，追问前文，模型正确引用恢复内容，新记录追加到原 JSONL。(AC9/AC11–AC18)
- [x] **场景 4：自动记忆跨会话生效**——明确说“记住我偏好简洁回复”，等待后台任务完成；检查合法笔记和索引，启动新会话后模型遵守该偏好。(AC21–AC24/AC31)
- [x] **场景 5：异常恢复**——在隔离副本中加入尾部坏行和悬空 ToolCall，使用 `/resume` 恢复；程序跳过/截断并提示，随后可继续正常对话。(AC10/AC14–AC15)
- [x] **场景 6：状态和退出**——流式时尝试 `/resume`，恢复时尝试提交消息，均被互斥保护；最终 `/exit` 后终端正常且没有 Dragon Code、MCP、记忆任务或打开文件残留。(AC29/N2/N8)

## 验收覆盖自检

- [x] AC1–AC6 已由“项目指令”及场景 1 覆盖。
- [x] AC7–AC10 已由“会话存档”及场景 2/3/5 覆盖。
- [x] AC11–AC20 已由“会话恢复与清理”及场景 3/5 覆盖。
- [x] AC21–AC26 已由“自动记忆”及场景 4 覆盖。
- [x] AC27–AC32 已由“系统集成与非回归”及场景 2/4/6 覆盖。
- [x] 所有条目都能通过命令输出、文件内容、TUI 行为或进程状态观察，无需以逐行审查实现代替行为验收。
