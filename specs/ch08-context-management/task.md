# ch08：上下文管理 Task

## 状态

- 阶段：已完成并验收（2026-08-08）。
- 上游文档：`spec.md`、`plan.md` 已批准。
- 硬门槛：`checklist.md` 批准后才能开始实现。

## 执行约定

- 严格按任务编号执行；依赖未完成时不提前修改后续模块。
- 每项先写失败测试或更新现有断言，再实现，再运行该项验证。
- 所有文件修改使用 UTF-8，不写入真实 API Key、Header 或本机配置。
- 每项验证拿到实际输出后才能标记完成。
- 保护现有用户改动，只暂存本章范围文件。

## T0：建立基线

- **文件**：不修改产品文件。
- **依赖**：无。
- **操作**：
  1. 执行 `git status --short --branch`，确认本章文档之外没有未知改动。
  2. 执行当前完整测试，记录 ch08 开始前基线。
  3. 记录 Python、uv、依赖锁和当前工作目录。
- **验证**：
  - `uv run pytest -q` 通过。
  - `uv run ruff check .` 通过。
  - 如果基线失败，先记录并停止功能实现，不把旧失败误认为 ch08 引入。

## T1：扩展 Provider 配置与公共模型

- **文件**：
  - `src/dragon_code/models.py`
  - `src/dragon_code/config.py`
  - `tests/test_config.py`
- **依赖**：T0。
- **操作**：
  1. `ProviderConfig` 增加向后兼容的 `context_window` 和 `summary_model` 字段。
  2. YAML 解析支持正整数 `context_window`；拒绝布尔值、零、负数、浮点数和字符串。
  3. 未配置时按协议解析为 Anthropic 200000、OpenAI 128000。
  4. `summary_model` 允许省略；出现时必须是非空字符串。
  5. 新增 `CompactEvent` 及 AgentEvent 的可选压缩字段，保持旧构造方式可用。
- **验证**：
  - `uv run pytest -q tests/test_config.py`
  - 新测试覆盖两个协议默认值、显式覆盖、summary model、非法值和旧配置。
  - `uv run ruff check src/dragon_code/models.py src/dragon_code/config.py tests/test_config.py`

## T2：建立上下文常量和状态类型

- **文件**：
  - `src/dragon_code/context/__init__.py`
  - `src/dragon_code/context/constants.py`
  - `src/dragon_code/context/state.py`
  - `tests/test_context_state.py`
- **依赖**：T1。
- **操作**：
  1. 写入 Spec 批准的全部固定常量。
  2. 实现安全会话 ID 和 `.dragon-code/sessions/<id>/tool-results/` 路径对象。
  3. 实现调用 ID 到安全文件名的稳定映射，包含可读前缀和哈希。
  4. 实现替换决定、冻结账本和查询方法。
  5. 实现 usage 锚点和自动摘要熔断器。
  6. 实现 `CompactStats` 等只保存数据的类型。
- **验证**：
  - `uv run pytest -q tests/test_context_state.py`
  - 覆盖 Windows 非法字符、`..`、斜杠、同前缀碰撞、唯一会话 ID、账本保留/替换和三次熔断。
  - `uv run ruff check src/dragon_code/context tests/test_context_state.py`

## T3：实现稳定预览和原子落盘

- **文件**：
  - `src/dragon_code/context/manager.py`
  - `tests/test_context_manager.py`
- **依赖**：T2。
- **操作**：
  1. 实现 UTF-8 字节计数。
  2. 实现“前20行且不超过2048字节”的合法 UTF-8 预览。
  3. 预览固定包含原始字节数、保存路径、原始调用 ID 和 Read 重读提示。
  4. 使用同目录临时文件写入，再原子改名到最终文件。
  5. 文件成功后才写替换账本；失败时清理临时文件并保留原内容。
  6. 已有冻结决定时不再 I/O，直接复用原文或稳定预览。
- **验证**：
  - `uv run pytest -q tests/test_context_manager.py -k "preview or offload or ledger"`
  - 覆盖中文多字节边界、20行边界、重复处理 mtime 不变、模拟写入失败后下轮成功。

## T4：实现单条与单轮工具结果处理

- **文件**：
  - `src/dragon_code/context/manager.py`
  - `tests/test_context_manager.py`
- **依赖**：T3。
- **操作**：
  1. 接收一轮按模型调用顺序排列的 `ToolResult` 列表。
  2. 第一遍处理超过50000字节的单条结果。
  3. 对剩余结果计算聚合字节数；超过200000时按“大到小、同大小保持原顺序”继续替换。
  4. 只替换使剩余合计达标所需的最少结果。
  5. 返回新的 ToolResult，不修改调用方持有的原对象。
  6. 成功、失败、空内容和已有 truncated 元数据均保持语义一致。
- **验证**：
  - `uv run pytest -q tests/test_context_manager.py -k "single or aggregate or result"`
  - 明确覆盖五条45000字节只替换一条、不同大小顺序、相同大小稳定顺序、落盘失败降级。

## T5：实现摘要纯函数

- **文件**：
  - `src/dragon_code/context/summary.py`
  - `tests/test_context_summary.py`
- **依赖**：T2。
- **操作**：
  1. 稳定序列化 ChatMessage、ToolCall、ToolResult 和隐藏块所需信息。
  2. 构造摘要 System Prompt 和用户内容，首尾禁止工具调用。
  3. Prompt 要求 `<analysis>` 草稿和九部分 `<summary>`。
  4. 解析唯一非空 `<summary>`，拒绝缺失、多个歧义区间和空摘要。
  5. 按消息组选择近期原文，同时满足10000 Token与5条消息。
  6. 将 ToolCall Assistant 与紧随的 Tool Result 视为不可分组。
  7. 构造摘要与固定边界合并的 user 消息，再深拷贝追加近期原文。
- **验证**：
  - `uv run pytest -q tests/test_context_summary.py`
  - 覆盖九部分 Prompt、标签解析、全部历史不足下界、工具配对、顺序和输入不被修改。

## T6：实现完整请求字符量和 Token 估算

- **文件**：
  - `src/dragon_code/context/manager.py`
  - `tests/test_context_manager.py`
- **依赖**：T4、T5。
- **操作**：
  1. 统计 system stable/environment、messages、tools schema 和 reminder 的稳定字符量。
  2. 无锚点时按 `ceil(chars / 3.5)` 全量估算。
  3. 有锚点时只估算正增量。
  4. 当前字符量小于锚点时使旧锚点失效并回退全量估算。
  5. 主请求完成后，以真实 usage 总和和“请求+Assistant输出”字符位置替换锚点。
  6. Tool Result 在主响应后产生，必须进入下一轮新增量。
  7. 摘要 usage 不更新锚点；压缩成功后锚点失效。
- **验证**：
  - `uv run pytest -q tests/test_context_manager.py -k "estimate or anchor or usage"`
  - 覆盖锚点替换不累加、Assistant不重复计算、Tool Result增量、历史缩短回退和未知 usage。

## T7：实现摘要 Client 调用

- **文件**：
  - `src/dragon_code/context/manager.py`
  - `tests/test_context_manager.py`
- **依赖**：T5、T6。
- **操作**：
  1. 使用注入的摘要 `LLMClient` 和现有 `LLMRequest` 发起摘要流。
  2. 摘要请求使用专用 SystemPrompt、单条序列化历史消息、空 tools、无 reminder。
  3. 复用 StreamCollector 收集响应；拒绝工具调用。
  4. 解析摘要并在全部成功后构造新历史。
  5. 跟踪活动摘要任务，支持取消。
  6. 把 Provider 异常转换成安全失败结果，不暴露原始请求或密钥。
- **验证**：
  - `uv run pytest -q tests/test_context_manager.py -k "summary_client or summary_request or cancel"`
  - fake client 断言模型名、tools为空、分析被丢弃、工具调用失败、取消传播。

## T8：实现自动摘要与熔断

- **文件**：
  - `src/dragon_code/context/manager.py`
  - `tests/test_context_manager.py`
- **依赖**：T6、T7。
- **操作**：
  1. `prepare_request` 接收已提交历史、待发送消息、system、同轮 tools 和 reminder。
  2. 先执行历史兜底第1层，再估算完整请求。
  3. 低于 `context_window - 33000` 时直接返回。
  4. 达到阈值且未熔断时触发自动摘要。
  5. 成功返回压缩后的已提交历史和完整请求消息，并清零已有连续失败。
  6. 失败保留原历史、记录失败并允许主请求继续。
  7. 第三次连续失败后停止自动调用；手动路径不受影响。
- **验证**：
  - `uv run pytest -q tests/test_context_manager.py -k "auto or threshold or circuit"`
  - 覆盖阈值前后、三次失败、失败后成功清零、熔断不调用摘要、待发送用户消息原文保留。

## T9：实现手动强制压缩

- **文件**：
  - `src/dragon_code/context/manager.py`
  - `tests/test_context_manager.py`
- **依赖**：T7、T8。
- **操作**：
  1. 手动入口跳过自动阈值和熔断。
  2. 估算摘要输入是否低于 `context_window - 23000`。
  3. 可发送时复用同一摘要核心路径。
  4. 成功返回新历史和 before/after；失败不修改历史。
  5. 手动成功或失败均不改变自动熔断计数。
- **验证**：
  - `uv run pytest -q tests/test_context_manager.py -k "force or manual"`
  - 覆盖低 Token 仍执行、熔断后执行、过长安全失败和自动计数不变。

## T10：为 Conversation 增加原子替换

- **文件**：
  - `src/dragon_code/session.py`
  - `tests/test_session.py`
- **依赖**：T5。
- **操作**：
  1. 新增整体替换已提交历史的方法。
  2. 输入和内部保存均使用深拷贝，避免 ToolCall/ToolResult 列表共享。
  3. 空列表可以清空历史。
  4. 原有 get/build/commit 行为不变。
- **验证**：
  - `uv run pytest -q tests/test_session.py`
  - 替换后修改输入对象不影响 Conversation，修改返回副本也不影响内部状态。

## T11：移除各工具的提前永久截断

- **文件**：
  - `src/dragon_code/tools/file_tools.py`
  - `src/dragon_code/tools/bash.py`
  - `src/dragon_code/tools/search_tools.py`
  - `src/dragon_code/mcp/tool.py`
  - 对应工具测试文件
- **依赖**：T4。
- **操作**：
  1. Read 返回完整带行号文本并保留总行数元数据。
  2. Read 支持可选 `offset`/`limit` 行分页；默认仍读取完整文件，预览提示按段重读。
  3. Bash 返回完整 stdout/stderr。
  4. Glob/Grep 返回完整结果，保持排序、匹配计数和单行防异常边界。
  5. MCP 转换保留完整文本和结构化内容。
  6. 更新原“截断测试”为“工具完整返回 + ContextManager 统一落盘”。
- **验证**：
  - `uv run pytest -q tests/test_file_tools.py tests/test_bash_tool.py tests/test_search_tools.py tests/test_mcp_tool.py`
  - 构造超过旧上限的结果，工具层内容完整，统一管理器测试证明随后落盘。

## T12：把工具结果处理接入 Agent

- **文件**：
  - `src/dragon_code/agent.py`
  - `tests/test_agent.py`
- **依赖**：T4、T11。
- **操作**：
  1. Agent 接受并持有 ContextManager。
  2. 保持权限检查、批次划分、并发和取消语义。
  3. 收集一轮全部原始 ToolResult 后统一处理。
  4. 处理完成后按模型原始顺序发出 tool_end。
  5. Conversation 保存同一份处理结果。
  6. 落盘失败警告通过安全 AgentEvent 展示，但工具结果仍可回灌。
- **验证**：
  - `uv run pytest -q tests/test_agent.py -k "tool or offload or order or permission or cancel"`
  - 重点断言 TUI 事件与 Conversation 内容一致、并发结果保序、权限拒绝仍是结果。

## T13：把请求准备和自动摘要接入 Agent

- **文件**：
  - `src/dragon_code/agent.py`
  - `src/dragon_code/models.py`
  - `tests/test_agent.py`
- **依赖**：T6、T8、T10、T12。
- **操作**：
  1. 每轮开头只生成一次 active tool definitions。
  2. 区分 Conversation 已提交历史与当前待发送用户消息。
  3. 在 LLMRequest 前调用 prepare_request。
  4. 压缩成功时只替换已提交历史，再追加待发送消息。
  5. 发出自动开始、完成、失败和熔断 CompactEvent。
  6. 主响应完成后记录 usage 锚点；摘要 usage 不参与。
  7. `request_cancel` 同时取消摘要。
  8. 新增 Agent 手动压缩方法并确保不与 run 并发。
- **验证**：
  - `uv run pytest -q tests/test_agent.py -k "compact or usage or pending or definitions or cancel"`
  - Plan Mode definitions、默认 definitions、失败不提交当前用户消息、摘要后继续 Loop 均覆盖。

## T14：接入 TUI 和双 Client

- **文件**：
  - `src/dragon_code/tui.py`
  - `tests/test_tui.py`
- **依赖**：T1、T9、T13。
- **操作**：
  1. 激活 Provider 时创建主 Client 和摘要 Client。
  2. 用工作目录、context window 和摘要 Client 创建 ContextManager。
  3. 现有命令判断增加 `/compact`，不创建命令注册表。
  4. 空闲时启动手动压缩 worker；运行中保持输入禁用。
  5. 使用统一格式化函数显示自动/手动开始、成功、失败和熔断。
  6. `/help` 增加 `/compact`。
  7. Escape 可取消摘要并恢复可输入状态。
- **验证**：
  - `uv run pytest -q tests/test_tui.py -k "compact or help or cancel or provider"`
  - fake client_factory 断言主/摘要模型；命令不写入 Conversation；失败后仍可继续对话。

## T15：配置示例和运行目录忽略

- **文件**：
  - `.dragon-code/config.yaml.example`
  - `.gitignore`
  - `tests/test_config.py`
- **依赖**：T1、T2。
- **操作**：
  1. 示例展示 `context_window` 和 `summary_model`，用注释说明可选默认行为。
  2. 不写入真实模型密钥。
  3. `.gitignore` 忽略 `.dragon-code/sessions/`，但不影响示例配置跟踪。
- **验证**：
  - `uv run python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.dragon-code/config.yaml.example').read_text(encoding='utf-8'))"`
  - `git check-ignore .dragon-code/sessions/demo/tool-results/demo`
  - `git check-ignore .dragon-code/config.yaml.example` 不应把已跟踪示例误处理为运行产物。

## T16：完整自动化回归

- **文件**：本章全部实现与测试文件。
- **依赖**：T1–T15。
- **操作**：
  1. 补齐边界测试：中文、多工具、MCP、失败、取消、Plan Mode、缓存稳定和Windows路径。
  2. 运行格式化、lint、编译和完整测试。
  3. 检查测试中没有真实网络依赖。
- **验证**：
  - `uv sync --locked`
  - `uv run ruff format --check .`
  - `uv run ruff check .`
  - `uv run python -m compileall -q src tests`
  - `uv run pytest -q`

## T17：tmux 真实端到端验收

- **文件**：不修改密钥配置；验收证据稍后写入报告。
- **依赖**：T16。
- **操作**：
  1. 使用测试项目和真实 DeepSeek 启动 Dragon Code。
  2. 触发超过50KB的工具结果，确认TUI只显示预览、磁盘保存完整内容。
  3. 要求模型 Read 预览给出的路径，确认能重读。
  4. 临时使用较小 `context_window` 触发自动摘要，观察摘要 Client 使用 `deepseek-v4-flash` 且没有工具调用。
  5. 观察自动压缩开始/完成、before/after Token，并确认原任务继续。
  6. 在低 Token 会话运行 `/compact`，确认仍执行。
  7. 构造摘要失败三次，观察熔断后自动路径停止、手动仍可执行。
  8. `/exit` 后检查进程清理和会话目录保留。
- **验证**：
  - tmux pane 输出与文件系统证据逐项对应 checklist。
  - 不在报告中记录真实 API Key、Header 或完整敏感工具结果。

## T18：验收报告、交接与提交

- **文件**：
  - `specs/ch08-context-management/checklist.md`
  - `specs/ch08-context-management/acceptance-report.md`
  - `docs/PROJECT_HANDOFF.md`
- **依赖**：T17 且 checklist 全部通过。
- **操作**：
  1. 勾选每项 checklist，并为每项写实际证据。
  2. 记录自动化命令的真实结果和 tmux 场景。
  3. 更新交接文档的已完成能力、核心文件、证据和下一章。
  4. 检查 `git diff --check` 和 `git status`。
  5. 只暂存 ch08 范围文件，创建本地提交；未经用户明确要求不 push。
- **验证**：
  - checklist 无未完成项。
  - acceptance report 不使用“应该通过”等无证据措辞。
  - `git show --stat --oneline HEAD` 只包含本章文件。

## 依赖总览

```text
T0
 ↓
T1
 ↓
T2
 ├─→ T3 → T4 ───────────→ T11 → T12
 └─→ T5 → T6 → T7 → T8 → T9
             └──────────→ T13 ← T10 ← T5
                              ↑
                             T12
                              ↓
                             T14
T1 + T2 ────────────────────→ T15
T1–T15 → T16 → T17 → T18
```
