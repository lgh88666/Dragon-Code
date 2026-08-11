# ch09：项目记忆与会话持久化 Tasks

## 状态

- 阶段：已批准（2026-08-11）
- 输入：已批准的 `spec.md` 与 `plan.md`
- 原则：先完成本文件与 `checklist.md` 的审批，再修改任何实现代码
- 教材基线：Vibe Coding ch09 Python 部分

## 文件清单

### 新建源码

| 操作 | 文件 | 职责 |
|---|---|---|
| 新建 | `src/dragon_code/instructions/__init__.py` | 导出项目指令加载接口 |
| 新建 | `src/dragon_code/instructions/loader.py` | 三层 `DRAGON.md` 与安全 `@include` 加载 |
| 新建 | `src/dragon_code/sessions/__init__.py` | 导出会话持久化接口 |
| 新建 | `src/dragon_code/sessions/models.py` | `SessionInfo`、`RestoredSession` 数据结构 |
| 新建 | `src/dragon_code/sessions/codec.py` | `ChatMessage` 与 JSONL 记录双向转换 |
| 新建 | `src/dragon_code/sessions/writer.py` | 追加、压缩边界、刷盘与关闭 |
| 新建 | `src/dragon_code/sessions/reader.py` | 坏行跳过、压缩边界与悬空调用修复 |
| 新建 | `src/dragon_code/sessions/manager.py` | 新建、列出、恢复、清理与当前会话管理 |
| 新建 | `src/dragon_code/memory/__init__.py` | 导出自动记忆接口 |
| 新建 | `src/dragon_code/memory/models.py` | 记忆操作数据结构与合法值 |
| 新建 | `src/dragon_code/memory/prompt.py` | 无工具记忆更新请求与 JSON 输出约束 |
| 新建 | `src/dragon_code/memory/manager.py` | 两级索引、后台更新、原子写入与任务清理 |

### 修改源码

| 操作 | 文件 | 职责变化 |
|---|---|---|
| 修改 | `src/dragon_code/context/state.py` | 新旧会话 ID 校验与统一目录 |
| 修改 | `src/dragon_code/context/manager.py` | 恢复历史超限判断与 ch08 压缩复用 |
| 修改 | `src/dragon_code/session.py` | 初始历史、持久化回调和失败警告 |
| 修改 | `src/dragon_code/prompt.py` | 接入真实项目指令和动态记忆来源说明 |
| 修改 | `src/dragon_code/agent.py` | 注入指令/记忆、自然完成计数、后台记忆与会话切换 |
| 修改 | `src/dragon_code/permissions/__init__.py` | 导出 Read 专用额外根能力 |
| 修改 | `src/dragon_code/permissions/sandbox.py` | 仅 Read 可访问用户记忆目录 |
| 修改 | `src/dragon_code/tools/path_utils.py` | 多个只读根的解析与边界检查 |
| 修改 | `src/dragon_code/tools/file_tools.py` | `ReadTool` 接收额外只读根 |
| 修改 | `src/dragon_code/tools/registry.py` | 注册 Read 时传入用户记忆根 |
| 修改 | `src/dragon_code/tui.py` | `/resume`、搜索选择、恢复 Worker、状态与提示 |
| 修改 | `src/dragon_code/dragon_code.tcss` | 会话选择屏幕和恢复提示样式 |
| 修改 | `src/dragon_code/cli.py` | 组装三个子系统并统一关闭生命周期 |

### 测试与文档

| 操作 | 文件 | 职责 |
|---|---|---|
| 新建 | `tests/test_instructions.py` | 项目指令顺序、include 与安全边界 |
| 新建 | `tests/test_session_persistence.py` | JSONL 编解码、读写、恢复、列表与清理 |
| 新建 | `tests/test_memory.py` | 记忆触发、更新、索引、并发和错误隔离 |
| 修改 | `tests/test_session.py` | Conversation 回调与持久化失败兼容 |
| 修改 | `tests/test_context_state.py` | 新旧会话 ID 和路径兼容 |
| 修改 | `tests/test_context_manager.py` | 恢复后的超限压缩 |
| 修改 | `tests/test_file_tools.py` | 用户记忆 Read 专用额外根 |
| 修改 | `tests/test_permission_sandbox.py` | Read 放宽但其他工具仍受限 |
| 修改 | `tests/test_tool_registry.py` | Read 额外根注册参数 |
| 修改 | `tests/test_prompt.py` | 项目指令和最新记忆注入 |
| 修改 | `tests/test_agent.py` | 自然完成、记忆触发、警告与会话切换 |
| 修改 | `tests/test_tui.py` | `/resume` 状态、筛选、成功切换与失败回滚 |
| 修改 | `tests/test_cli.py` | 启动装配和退出清理 |
| 修改 | `.gitignore` | 忽略项目会话与自动记忆，不忽略手写 `DRAGON.md` |
| 修改 | `README.md` | 说明三层指令、`/resume`、会话和记忆目录 |
| 新建 | `specs/ch09-memory-session/acceptance-report.md` | 开发完成后的实际验收证据 |
| 修改 | `docs/PROJECT_HANDOFF.md` | 记录 ch09 状态、证据和下一步 |
| 修改 | `docs/learning-notes.md` | 验收后记录核心源码回顾要点 |

## 实现任务

## T1：建立项目指令加载包和三层来源顺序

**文件：** `src/dragon_code/instructions/__init__.py`、`src/dragon_code/instructions/loader.py`、`tests/test_instructions.py`
**依赖：** 无

**步骤：**

1. 定义 `InstructionLoader`，接收项目根和可覆盖的用户目录。
2. 固定按项目根、项目 `.dragon-code/`、用户 `~/.dragon-code/` 的优先级加载 `DRAGON.md`。
3. 跳过不存在或空白的来源，按稳定顺序用空行拼接。
4. 添加来源顺序、缺失文件和空文件测试。

**验证：** 运行 `uv run pytest -q tests/test_instructions.py -k "order or missing or empty"`，期望全部通过，且高优先级内容排在前面。

## T2：实现 `@include` 正常展开和深度限制

**文件：** `src/dragon_code/instructions/loader.py`、`tests/test_instructions.py`
**依赖：** T1

**步骤：**

1. 只把独占一行的 `@include 相对路径` 识别为引用。
2. 相对当前文件目录解析被引用文件，并在原位置展开。
3. 使用当前引用链 `visited` 集合检测环路，返回上一层时移除当前文件。
4. 将最大嵌套深度固定为 5，超过时保留其他可用内容并产生警告。
5. 测试正常嵌套、同文件被两条非循环分支引用、环路和深度超限。

**验证：** 运行 `uv run pytest -q tests/test_instructions.py -k "include or cycle or depth"`，期望展开顺序正确且不会递归失控。

## T3：实现项目指令的路径、编码和二进制安全

**文件：** `src/dragon_code/instructions/loader.py`、`tests/test_instructions.py`
**依赖：** T2

**步骤：**

1. 对项目级引用限制在项目根内，对用户级引用限制在用户 `.dragon-code` 内。
2. 解析符号链接后的真实路径再判断边界。
3. 读取前 512 字节检查 NUL，拒绝二进制文件。
4. 对越界、不可读、非法 UTF-8、二进制和缺失引用返回可读警告，不中断启动。
5. 增加对应安全测试，并确认警告不包含敏感文件内容。

**验证：** 运行 `uv run pytest -q tests/test_instructions.py`，期望所有项目指令测试通过。

## T4：实现新旧会话 ID 与安全路径兼容

**文件：** `src/dragon_code/context/state.py`、`tests/test_context_state.py`
**依赖：** 无

**步骤：**

1. 实现新 ID `YYYYMMDD-HHMMSS-xxxx` 的生成和识别。
2. 保留 ch08 旧 ID 的安全识别，仅用于底层路径兼容。
3. 拒绝路径分隔符、父目录跳转和其他非法 ID。
4. 让 `SessionPaths` 对新旧安全 ID 均能生成相同层级的会话目录。

**验证：** 运行 `uv run pytest -q tests/test_context_state.py`，期望新 ID 唯一且格式正确、旧 ID 可用、恶意 ID 被拒绝。

## T5：定义会话元数据和恢复结果模型

**文件：** `src/dragon_code/sessions/__init__.py`、`src/dragon_code/sessions/models.py`、`tests/test_session_persistence.py`
**依赖：** T4

**步骤：**

1. 定义 `SessionInfo`，保存 ID、标题、更新时间、模型、文件大小和 JSONL 路径。
2. 定义 `RestoredSession`，保存修复后的消息、模型、最后时间、坏行数和悬空截断标记。
3. 从包入口只导出上层真正需要的公开类型。
4. 添加数据结构构造测试。

**验证：** 运行 `uv run pytest -q tests/test_session_persistence.py -k models`，期望字段和值完整。

## T6：实现普通消息与 JSONL 记录双向转换

**文件：** `src/dragon_code/sessions/codec.py`、`tests/test_session_persistence.py`
**依赖：** T5

**步骤：**

1. 实现 `message_to_record` 与 `record_to_message`。
2. 保存 `role`、`content`、时间戳，并只在首条需要时保存 `model`。
3. 对字段缺失或类型错误抛出明确的解析异常，交给 Reader 按整行跳过。
4. 测试 user、assistant 和空文本消息的往返一致性。

**验证：** 运行 `uv run pytest -q tests/test_session_persistence.py -k "codec and basic"`，期望往返后消息等价。

## T7：完整保存工具字段和 `hidden_blocks`

**文件：** `src/dragon_code/sessions/codec.py`、`tests/test_session_persistence.py`
**依赖：** T6

**步骤：**

1. 序列化和恢复完整 `ToolCall` 字段。
2. 序列化和恢复完整 `ToolResult` 字段及调用 ID 配对。
3. 原样保存并恢复 Anthropic 使用的 `hidden_blocks`。
4. 增加包含 thinking、tool use、成功结果和错误结果的往返测试。

**验证：** 运行 `uv run pytest -q tests/test_session_persistence.py -k "tool or hidden"`，期望协议字段无丢失。

## T8：实现 JSONL 追加写、首条模型和刷盘

**文件：** `src/dragon_code/sessions/writer.py`、`tests/test_session_persistence.py`
**依赖：** T7

**步骤：**

1. `SessionWriter` 以 UTF-8 追加模式打开 `conversation.jsonl`。
2. 使用 `threading.Lock` 保护单条完整 JSON 写入。
3. 第一条消息写模型字段，后续消息不重复写。
4. 每行写完执行 flush 和 fsync；`close()` 支持重复调用。

**验证：** 运行 `uv run pytest -q tests/test_session_persistence.py -k "writer and append"`，期望每行都是独立合法 JSON，且模型只出现一次。

## T9：实现压缩边界追加与 Writer 关闭行为

**文件：** `src/dragon_code/sessions/codec.py`、`src/dragon_code/sessions/writer.py`、`tests/test_session_persistence.py`
**依赖：** T8

**步骤：**

1. 实现 `compact_record` 标记。
2. `replace(messages)` 只追加 compact 标记和新历史，不重写旧文件。
3. 关闭后继续 append/replace 时返回明确错误，不产生半行。
4. 测试两次压缩、空新历史和幂等关闭。

**验证：** 运行 `uv run pytest -q tests/test_session_persistence.py -k "compact or close"`，期望 JSONL 保持追加式且边界清楚。

## T10：让 Conversation 支持持久化回调和失败警告

**文件：** `src/dragon_code/session.py`、`tests/test_session.py`
**依赖：** T8、T9

**步骤：**

1. 构造函数支持初始消息、追加回调和替换回调，默认值保持 ch08 兼容。
2. `commit_messages` 和 `replace_messages` 先更新内存，再调用持久化回调。
3. 捕获回调异常并保存一次性警告，不回滚已经批准的内存历史。
4. 实现 `take_persistence_warning()`，读取后清空。
5. 测试正常回调、恢复历史不重写、持久化失败仍可继续和无回调旧行为。

**验证：** 运行 `uv run pytest -q tests/test_session.py`，期望原测试和新增持久化测试全部通过。

## T11：实现 Reader 的坏行跳过和最后压缩边界

**文件：** `src/dragon_code/sessions/reader.py`、`tests/test_session_persistence.py`
**依赖：** T7、T9

**步骤：**

1. 逐行读取 JSONL，空行和无法解析的坏行计数后跳过。
2. 从最后一个合法 compact 标记之后恢复消息。
3. 从首条可用记录提取模型，从最后条可用记录提取时间。
4. 测试文件中间坏行、尾部半行、多个 compact 标记和完全空文件。

**验证：** 运行 `uv run pytest -q tests/test_session_persistence.py -k "reader and (bad or compact)"`，期望可用历史被保留且坏行数准确。

## T12：修复恢复历史中的悬空工具调用

**文件：** `src/dragon_code/sessions/reader.py`、`tests/test_session_persistence.py`
**依赖：** T11

**步骤：**

1. 检查 assistant 工具调用与后续 tool result 的 ID 配对。
2. 遇到未配结果的工具调用时，从该 assistant 消息前截断恢复历史。
3. 已完整配对的多工具调用保持不变。
4. 设置 `orphan_call_truncated`，供 TUI 显示恢复警告。

**验证：** 运行 `uv run pytest -q tests/test_session_persistence.py -k orphan`，期望不再留下会导致 provider 400 的悬空调用。

## T13：实现新会话创建和统一 ActiveSession

**文件：** `src/dragon_code/sessions/manager.py`、`tests/test_session_persistence.py`
**依赖：** T4、T8、T10、T12

**步骤：**

1. 在 manager 中定义 `ActiveSession`，集中持有 ID、Conversation、Writer 和恢复计数。
2. `open_new(model)` 创建新 ID、会话目录、Writer 与带回调的 Conversation。
3. 确保 ch08 `SessionPaths` 与 JSONL 使用同一个 ID。
4. `close()` 幂等关闭当前 Writer。

**验证：** 运行 `uv run pytest -q tests/test_session_persistence.py -k "open_new or active"`，期望目录和对象使用相同 ID。

## T14：实现会话扫描、标题和列表元数据

**文件：** `src/dragon_code/sessions/reader.py`、`src/dragon_code/sessions/manager.py`、`tests/test_session_persistence.py`
**依赖：** T11、T13

**步骤：**

1. 只扫描新格式 ID 下的 `conversation.jsonl`。
2. 用第一条用户文本生成最多 50 字标题，无用户文本时使用默认标题。
3. 直接从 JSONL 和文件属性计算模型、更新时间与大小，不建立 meta 文件。
4. 按最近更新时间降序返回，并跳过不可读会话。

**验证：** 运行 `uv run pytest -q tests/test_session_persistence.py -k "list or title or metadata"`，期望排序和展示字段正确。

## T15：实现会话恢复和时间跨度提醒

**文件：** `src/dragon_code/sessions/manager.py`、`tests/test_session_persistence.py`
**依赖：** T12、T13、T14

**步骤：**

1. `restore(session_id, model)` 读取并修复历史，再为同一 JSONL 创建追加 Writer。
2. 超过 6 小时时在恢复后的内存历史加入 system-reminder，不立即改写旧 JSONL。
3. 记录中的模型只用于展示，继续对话使用当前启动选择的模型。
4. 恢复后下一条消息继续追加到原会话文件。

**验证：** 运行 `uv run pytest -q tests/test_session_persistence.py -k "restore or reminder"`，期望旧历史不重复写且新消息追加到原文件。

## T16：实现 45 天过期会话清理

**文件：** `src/dragon_code/sessions/manager.py`、`tests/test_session_persistence.py`
**依赖：** T14

**步骤：**

1. `cleanup_expired(45)` 只处理可识别的新格式会话目录。
2. 删除前再次解析绝对路径并确认位于 sessions 根目录下。
3. 保留 45 天内目录、旧格式目录、普通文件和不可确认目标。
4. 返回实际删除的会话 ID，单个删除失败不影响其他会话。

**验证：** 运行 `uv run pytest -q tests/test_session_persistence.py -k cleanup`，期望只删除超过 45 天的新格式会话。

## T17：定义记忆操作模型和无工具更新提示

**文件：** `src/dragon_code/memory/__init__.py`、`src/dragon_code/memory/models.py`、`src/dragon_code/memory/prompt.py`、`tests/test_memory.py`
**依赖：** 无

**步骤：**

1. 定义 `MemoryOperation` 及 create/update/delete、project/user、四种记忆类型的合法值。
2. 构造记忆更新请求，包含当前自然完成回合和两级完整索引。
3. 明确要求只输出 JSON 数组，并设置空工具列表。
4. 测试四类归属提示、无变化时空数组以及请求不携带工具。

**验证：** 运行 `uv run pytest -q tests/test_memory.py -k "prompt or operation"`，期望请求内容完整且工具列表为空。

## T18：实现两级 MEMORY 索引加载与体量控制

**文件：** `src/dragon_code/memory/manager.py`、`tests/test_memory.py`
**依赖：** T17

**步骤：**

1. 从项目 `.dragon-code/memory/MEMORY.md` 和用户 `~/.dragon-code/memory/MEMORY.md` 加载索引。
2. 按项目后用户的已批准顺序拼接，并给来源加清楚标签。
3. 每个索引限制 200 行/25KB，合并注入再限制 25KB，按完整 UTF-8 边界截断。
4. 缺失、不可读和非法编码时返回空或可降级结果，不中断对话。

**验证：** 运行 `uv run pytest -q tests/test_memory.py -k "index or limit"`，期望顺序稳定且不超过上限。

## T19：实现记忆操作解析和安全文件名

**文件：** `src/dragon_code/memory/manager.py`、`tests/test_memory.py`
**依赖：** T17

**步骤：**

1. 从纯 JSON 或被 Markdown 代码围栏包裹的文本解析操作数组。
2. 严格校验 action、level、memory_type、必要字段和字段类型。
3. create 文件名生成 `<type>_<slug>.md`，update/delete 只接受安全的 `.md` 基名。
4. 拒绝绝对路径、目录分隔符、`..` 和索引文件自身。

**验证：** 运行 `uv run pytest -q tests/test_memory.py -k "parse or filename or traversal"`，期望非法操作被跳过且不越界。

## T20：实现记忆 Markdown 与原子增删改

**文件：** `src/dragon_code/memory/manager.py`、`tests/test_memory.py`
**依赖：** T18、T19

**步骤：**

1. create 写入包含 type、title、created、updated 的 frontmatter 和正文。
2. update 保留 created，更新 title/content/updated；delete 只删除目标记忆文件。
3. 使用同目录临时文件加 replace 原子替换，不留下半文件。
4. 操作完成后根据现存笔记重建对应 `MEMORY.md`。
5. 测试 create/update/delete、文件不存在、部分非法操作和索引一致性。

**验证：** 运行 `uv run pytest -q tests/test_memory.py -k "create or update or delete or atomic"`，期望笔记和索引同步。

## T21：实现记忆触发规则和后台任务生命周期

**文件：** `src/dragon_code/memory/manager.py`、`tests/test_memory.py`
**依赖：** T20

**步骤：**

1. 每 5 个自然完成回合触发一次更新。
2. 用户文本含 `记住`、`记忆`、`别忘`、`remember`、`memo` 时立即触发。
3. `schedule_update` 创建后台任务并立即返回，避免阻塞最终答复。
4. 用 `asyncio.Lock` 串行保护记忆修改，同步磁盘操作放入 `asyncio.to_thread()`。
5. `close()` 取消并等待未完成任务，清空任务集合。

**验证：** 运行 `uv run pytest -q tests/test_memory.py -k "trigger or background or lock or close"`，期望触发准确、调用不阻塞且退出无残留任务。

## T22：实现记忆 LLM 收集、失败隔离和快照更新

**文件：** `src/dragon_code/memory/manager.py`、`tests/test_memory.py`
**依赖：** T20、T21

**步骤：**

1. 使用当前 `LLMClient` 流式收集记忆操作文本，不执行任何工具。
2. 把模型错误、JSON 解析错误和磁盘错误限制在后台任务内部，不重试、不发对话错误。
3. 每批操作成功后重新加载并原子替换内存索引快照。
4. 测试成功更新、模型出错、无效 JSON、磁盘失败和后续任务仍可运行。

**验证：** 运行 `uv run pytest -q tests/test_memory.py`，期望全部记忆测试通过且失败不会冒泡到 Agent Loop。

## T23：为 Read 增加用户记忆专用只读根

**文件：** `src/dragon_code/tools/path_utils.py`、`src/dragon_code/tools/file_tools.py`、`tests/test_file_tools.py`
**依赖：** T18

**步骤：**

1. `ReadTool` 接收可选 `extra_read_roots`。
2. 路径解析时先解析符号链接，再判断位于项目根或任一额外只读根。
3. 允许模型按索引读取用户记忆详情，不改变读文件的行分页和体量限制。
4. 测试项目文件、用户记忆文件、越界文件和符号链接逃逸。

**验证：** 运行 `uv run pytest -q tests/test_file_tools.py -k "read and root"`，期望只允许两个批准的读取范围。

## T24：保持 Write/Edit/Glob/Grep 的原沙箱边界

**文件：** `src/dragon_code/permissions/__init__.py`、`src/dragon_code/permissions/sandbox.py`、`src/dragon_code/tools/registry.py`、`tests/test_permission_sandbox.py`、`tests/test_tool_registry.py`
**依赖：** T23

**步骤：**

1. PathSandbox 仅在工具名为 Read 时考虑额外只读根。
2. Write、Edit、Glob、Grep 和 Bash 保持 ch06 的原项目边界与权限逻辑。
3. Registry 只把用户记忆根传给 ReadTool 和 Read 权限检查。
4. 测试 Read 用户记忆成功，同路径的 Write/Edit/Glob/Grep 仍拒绝。

**验证：** 运行 `uv run pytest -q tests/test_permission_sandbox.py tests/test_tool_registry.py`，期望原权限回归和新增 Read 例外全部通过。

## T25：将项目指令和最新记忆接入系统提示

**文件：** `src/dragon_code/prompt.py`、`src/dragon_code/agent.py`、`tests/test_prompt.py`、`tests/test_agent.py`
**依赖：** T3、T18、T22

**步骤：**

1. Agent 构造时接收启动期加载的 `custom_instructions` 和可选 `MemoryManager`。
2. 每次普通 `run()` 开始读取最新 `current_index()`，注入长期记忆模块。
3. 项目指令保持会话内稳定；记忆更新后下一次任务使用新快照。
4. 更新 prompt 中“可选模块尚无真实来源”的过时说明。
5. 测试模块优先级、空内容跳过和更新前后提示变化。

**验证：** 运行 `uv run pytest -q tests/test_prompt.py tests/test_agent.py -k "instruction or memory or prompt"`，期望系统提示内容和顺序正确。

## T26：在自然完成后调度自动记忆

**文件：** `src/dragon_code/agent.py`、`tests/test_agent.py`
**依赖：** T21、T25

**步骤：**

1. 每次 run 开始记录本轮历史起点和用户文本。
2. 只有模型无工具调用自然完成时才增加 `completed_turns`。
3. 传给 MemoryManager 的是本轮深拷贝快照，避免后续 `/compact` 修改它。
4. 错误、取消、迭代上限和未知工具停止均不触发记忆。
5. 测试第 5 轮、关键词、普通非第 5 轮和四种非自然停止。

**验证：** 运行 `uv run pytest -q tests/test_agent.py -k "memory or completed_turn"`，期望调度次数与触发规则一致。

## T27：把会话持久化警告送入 Agent 事件流

**文件：** `src/dragon_code/agent.py`、`tests/test_agent.py`
**依赖：** T10、T26

**步骤：**

1. 每次提交或替换历史后读取 Conversation 的一次性警告。
2. 通过独立 `session_warning` AgentEvent 向 TUI 发送“本轮未能保存”。
3. 警告不改变本轮自然完成结果，也不停止后续会话。
4. 测试写入失败后仍收到最终文本、只出现一次警告且下一轮可继续。

**验证：** 运行 `uv run pytest -q tests/test_agent.py -k session_warning`，期望事件顺序和恢复能力正确。

## T28：实现 Agent 会话替换和恢复计数重建

**文件：** `src/dragon_code/agent.py`、`tests/test_agent.py`
**依赖：** T15、T26

**步骤：**

1. `replace_session` 同时替换 Conversation 和 ContextManager。
2. 按恢复历史中的 user 消息数重算 `completed_turns`。
3. 清除旧会话的 Plan Mode 暂存计划，模式回到安全的普通状态。
4. 保持当前 LLMClient、ToolRegistry、权限和 MCP 连接不变。

**验证：** 运行 `uv run pytest -q tests/test_agent.py -k replace_session`，期望新会话历史生效且旧状态不串入。

## T29：复用 ch08 判断和压缩恢复后的超限历史

**文件：** `src/dragon_code/context/manager.py`、`tests/test_context_manager.py`
**依赖：** T15

**步骤：**

1. 提供恢复历史的 token 窗口判断入口，继续使用 ch08 估算逻辑。
2. 超限时只尝试一次现有结构化压缩，成功后返回新历史。
3. 压缩失败时向上层返回清楚错误，不破坏当前旧会话。
4. 测试未超限、超限成功和超限失败。

**验证：** 运行 `uv run pytest -q tests/test_context_manager.py -k restore`，期望三种分支均可观测且无历史半切换。

## T30：实现 `/resume` 搜索选择屏幕

**文件：** `src/dragon_code/tui.py`、`src/dragon_code/dragon_code.tcss`、`tests/test_tui.py`
**依赖：** T14

**步骤：**

1. 新增 `SessionResumeScreen`，展示标题、相对时间、模型和大小。
2. 支持输入关键字按标题或 ID 过滤，方向键选择，Enter 确认，Esc 取消。
3. 列表为空或扫描失败时给出可读提示并返回 IDLE。
4. 使用 Textual 样式保持窄终端可读。

**验证：** 运行 `uv run pytest -q tests/test_tui.py -k "resume_screen or filter"`，期望筛选、确认和取消行为正确。

## T31：接入 `/resume` 状态机和异步扫描

**文件：** `src/dragon_code/tui.py`、`tests/test_tui.py`
**依赖：** T30

**步骤：**

1. 仅在 IDLE 接受 `/resume`，进入新增 `RESUMING` 状态。
2. 使用 `asyncio.to_thread()` 扫描会话，期间禁用新提交但保持界面响应。
3. 在 STREAMING、APPROVING 或另一次恢复中输入时给出状态提示，不启动第二个 Worker。
4. 更新 `/help` 展示 `/resume`。

**验证：** 运行 `uv run pytest -q tests/test_tui.py -k "resume and state"`，期望互斥和状态恢复正确。

## T32：实现恢复、压缩和原子会话切换

**文件：** `src/dragon_code/tui.py`、`tests/test_tui.py`
**依赖：** T15、T28、T29、T31

**步骤：**

1. 在 Worker 中通过 `to_thread()` 读取并修复目标会话。
2. 为目标 ID 创建新 ContextManager，超限时先执行一次压缩。
3. 所有新对象准备成功后再调用 `Agent.replace_session` 并替换 ActiveSession。
4. 成功后关闭旧 Writer；任何失败都关闭新 Writer、保留旧会话和旧 Writer。
5. 显示坏行数、悬空截断和时间跨度提醒摘要，返回 IDLE。

**验证：** 运行 `uv run pytest -q tests/test_tui.py -k "restore_session or rollback"`，期望成功切换与失败回滚均无半状态。

## T33：在 TUI 展示持久化警告并保持可继续

**文件：** `src/dragon_code/tui.py`、`src/dragon_code/dragon_code.tcss`、`tests/test_tui.py`
**依赖：** T27

**步骤：**

1. 消费 `session_warning` 事件并以黄色可区分样式写入 scrollback。
2. 不把警告混进 assistant 正文，不改变输入框解锁逻辑。
3. 测试警告后状态回到 IDLE，下一条消息仍可提交。

**验证：** 运行 `uv run pytest -q tests/test_tui.py -k session_warning`，期望提示可见且会话不中断。

## T34：在 CLI 组装项目指令、会话和记忆服务

**文件：** `src/dragon_code/cli.py`、`tests/test_cli.py`
**依赖：** T3、T13、T16、T22、T24、T25、T32

**步骤：**

1. 启动时加载项目指令和两级记忆索引，失败时降级并显示可读警告。
2. 初始化 SessionManager，并后台执行 45 天清理。
3. Provider 选定后新建 ActiveSession，用相同 ID 创建 ContextManager 和 Agent。
4. 将用户记忆目录作为 Read 专用额外根传入 ToolRegistry。
5. 将 SessionManager 和 MemoryManager 传给 TUI 所需入口。

**验证：** 运行 `uv run pytest -q tests/test_cli.py -k "instruction or session or memory or startup"`，期望服务按顺序装配且 ID 一致。

## T35：实现退出时的统一清理

**文件：** `src/dragon_code/cli.py`、`src/dragon_code/tui.py`、`tests/test_cli.py`、`tests/test_tui.py`
**依赖：** T21、T34

**步骤：**

1. 退出时先取消当前 Agent/恢复 Worker。
2. 幂等关闭当前 SessionWriter。
3. 取消并等待 MemoryManager 和会话清理任务。
4. 继续执行 ch07 MCP 关闭和 Textual 终端恢复。
5. 测试普通退出、记忆任务进行中退出和恢复进行中退出。

**验证：** 运行 `uv run pytest -q tests/test_cli.py tests/test_tui.py -k "close or shutdown or exit"`，期望无挂起 task、未关闭文件或子进程。

## T36：更新忽略规则和用户文档

**文件：** `.gitignore`、`README.md`
**依赖：** T34

**步骤：**

1. 忽略项目 `.dragon-code/sessions/` 和 `.dragon-code/memory/` 自动数据。
2. 确认项目根及 `.dragon-code/DRAGON.md` 没有被忽略，可由用户选择提交。
3. 文档说明三层 `DRAGON.md`、安全 include、`/resume`、45 天清理和两级自动记忆。
4. 明确用户级记忆位于项目外，密钥和本地配置仍不得提交。

**验证：** 运行 `git check-ignore -v .dragon-code/sessions/example/conversation.jsonl .dragon-code/memory/MEMORY.md`，期望二者被忽略；运行 `git check-ignore .dragon-code/DRAGON.md`，期望返回未忽略。

## T37：执行 ch09 定向回归测试

**文件：** `tests/` 下本章涉及的全部测试
**依赖：** T1–T36

**步骤：**

1. 运行项目指令、会话、记忆、Context、Agent、权限、工具、TUI 和 CLI 定向测试。
2. 修复发现的问题，并重跑失败测试直到通过。
3. 确认测试使用临时目录和假 LLMClient，不访问真实用户目录和网络。

**验证：** 运行 `uv run pytest -q tests/test_instructions.py tests/test_session_persistence.py tests/test_memory.py tests/test_session.py tests/test_context_state.py tests/test_context_manager.py tests/test_file_tools.py tests/test_permission_sandbox.py tests/test_tool_registry.py tests/test_prompt.py tests/test_agent.py tests/test_tui.py tests/test_cli.py`，期望全部通过。

## T38：执行全量格式、静态检查和测试

**文件：** 全仓库
**依赖：** T37

**步骤：**

1. 同步锁定依赖，不新增 ch09 依赖。
2. 格式化本章改动并检查格式。
3. 运行 Ruff 静态检查和全量 pytest。
4. 记录实际测试数量和跳过数量，不能用预期代替证据。

**验证：** 依次运行 `uv sync --locked`、`uv run ruff format .`、`uv run ruff format --check .`、`uv run ruff check .`、`uv run pytest -q`，期望全部成功。

## T39：使用 tmux 做真实端到端验收

**文件：** `specs/ch09-memory-session/checklist.md`
**依赖：** T38

**步骤：**

1. 在 WSL tmux 中启动 Dragon Code，确认新会话生成新格式 ID 和 JSONL。
2. 完成真实多轮对话和至少一次工具调用，退出后检查完整消息、工具配对和 hidden blocks 可恢复。
3. 重启后用 `/resume` 搜索并恢复，继续提问验证前文；同时观察时间/模型/大小展示。
4. 使用临时测试目录验证三层 `DRAGON.md` 与 include，并让模型回答其中明确规则。
5. 触发“记住”关键词，等待后台更新，再发下一轮验证 MEMORY 索引生效。
6. 构造坏行、悬空调用和超限历史的可控副本，验证恢复修复、压缩和失败回滚。
7. 对照 checklist 逐项记录真实证据；自动化才能验证的条目标注为自动化证据。

**验证：** tmux 中 `/exit` 后无 Dragon Code、MCP 或后台记忆残留进程；实际行为覆盖 checklist 端到端场景。

## T40：完成验收报告、交接和学习回顾入口

**文件：** `specs/ch09-memory-session/acceptance-report.md`、`docs/PROJECT_HANDOFF.md`、`docs/learning-notes.md`
**依赖：** T39

**步骤：**

1. 按 checklist 写入每项实际结果、命令输出摘要和 tmux 观察证据。
2. 更新交接文档：ch09 状态、核心调用链、测试数量、已知限制和下一章入口。
3. 在学习笔记中只记录本章核心源码回顾提纲，不逐文件复制源码。
4. 仅暂存 ch09 范围文件，保护 `.idea/`、`321.txt` 和其他用户改动。
5. checklist 全通过后按项目规则创建本地提交；除非用户明确说“推送”，不 push。

**验证：** 运行 `git status --short`，期望本章文件范围清楚且 `.idea/`、`321.txt` 仍未被暂存；验收报告无“待补”“应该”等无证据结论。

## 执行顺序

```text
项目指令：T1 → T2 → T3

会话底座：T4 → T5 → T6 → T7 → T8 → T9 → T10
                              └→ T11 → T12 → T13 → T14 → T15 → T16

自动记忆：T17 → T18 → T19 → T20 → T21 → T22

安全读取：T18 → T23 → T24

核心接入：T3 + T22 → T25 → T26 → T27 → T28
恢复压缩：T15 → T29
界面恢复：T14 → T30 → T31 → T32
警告展示：T27 → T33

启动收尾：T24 + T25 + T32 → T34 → T35 → T36

验证：T1–T36 → T37 → T38 → T39 → T40
```

可在不修改同一文件时并行的组：项目指令 T1–T3、会话底座 T4–T16、自动记忆 T17–T22。进入 Agent、TUI 与 CLI 接入后按依赖顺序串行，避免共享状态改动互相覆盖。

## 自检

- **Plan 覆盖：** instructions、sessions、memory、Context、Read 沙箱、Agent、TUI、CLI、文档与验收均有任务归属。
- **Spec 覆盖：** F1–F8 对应 T1–T3/T25/T34；F9–F26 对应 T4–T16/T29–T35；F27–F42 对应 T17–T26；F43–F47 对应 T10/T25–T35。
- **依赖链：** 无循环依赖；先完成底层编解码/管理器，再接 Agent/TUI/CLI。
- **验证完整性：** T1–T38 均有命令级验证；T39 有真实 tmux 场景；T40 检查证据、交接和 Git 范围。
- **类型一致性：** 接口名称与已批准 `plan.md` 一致；`ActiveSession` 位于 `sessions/manager.py`，避免导入环。
- **占位符扫描：** 无 TBD、TODO 或未决技术选项。
- **范围检查：** 未加入向量数据库、RAG、团队同步、通用 slash 框架或新的依赖。
