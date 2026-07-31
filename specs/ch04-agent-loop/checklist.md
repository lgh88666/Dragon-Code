# Dragon Code Agent Loop Checklist

> 每一项都通过运行代码或观察真实行为验证。开发完成后先运行自动化检查，再使用 WSL tmux 执行端到端场景。

## 实现完整性

- [x] Agent 能自主执行多轮“模型请求 → 工具执行 → 结果回写”，直到模型给出无工具调用的最终文本。（验证：运行 `uv run pytest tests/test_agent.py -q -k multi`，观察 Provider 被请求多次且最终事件为 completed。）（AC1）

- [x] 模型第一轮直接返回纯文本时立即自然结束，不产生额外模型请求。（验证：运行 `uv run pytest tests/test_agent.py -q -k natural`，请求次数应为 1。）（AC2）

- [x] 达到 50 次迭代上限时停止，最后一轮工具结果已配对，不产生第 51 次请求。（验证：用测试注入较小上限，运行 `uv run pytest tests/test_agent.py -q -k iteration_limit`。）（AC3）

- [x] 连续三轮全部请求未知工具时停止；中间出现已注册工具会重置计数。（验证：运行 `uv run pytest tests/test_agent.py -q -k unknown`。）（AC4）

- [x] Provider 流出错或未产生完整消息时，当前任务停止并产生 error 事件，下一条对话仍可运行。（验证：运行 `uv run pytest tests/test_agent.py -q -k stream_error`。）（AC5）

- [x] AgentEvent 覆盖 progress、text、tool_start、tool_end、usage、completed、cancelled、limit 和 error。（验证：运行 Agent 事件顺序测试，检查每种结束路径只产生一个终止事件。）（AC6）

- [x] StreamCollector 实时转发文本，同时保存完整助手消息与 Token 用量；缺少 completed 时报告响应错误。（验证：运行 `uv run pytest tests/test_stream_collector.py -q`。）（AC7）

- [x] Anthropic 能从流式事件提取输入和输出 Token，thinking 与工具 JSON 拼接行为保持正常。（验证：运行 `uv run pytest tests/test_provider_anthropic.py -q`。）（F4/F9/F13）

- [x] OpenAI 能读取 choices 为空的 usage-only 分片，缺少 usage 时使用未知值，并在完成、错误和取消时关闭响应流。（验证：运行 `uv run pytest tests/test_provider_openai.py -q`。）（F4/F9/F13）

- [x] `Read A → Glob B → Edit C → Read D` 被分成“Read+Glob 并发、Edit 串行、Read 单独”三个批次。（验证：运行 `uv run pytest tests/test_tool_scheduler.py -q -k partition`。）（AC8）

- [x] 并发批次实际完成顺序不同也不会改变结果返回顺序；单个工具失败不阻止同批其他工具。（验证：运行 `uv run pytest tests/test_tool_scheduler.py -q -k "order or failure"`。）（AC8/N7）

- [x] 每个工具继续受 30 秒超时保护，超时结果回写后 Agent 可以继续下一轮。（验证：运行工具超时测试和 Agent 工具失败继续测试。）（N1/N9）

- [x] 正常多轮、迭代上限、未知工具停止和流错误后，已提交历史不存在悬空工具调用，下一条请求不会因历史格式非法失败。（验证：运行 `uv run pytest tests/test_agent.py -q -k history`，检查每个 ToolCall ID 都有对应 ToolResult。）（AC9）

- [x] 模型响应未完成时取消会丢弃当前部分响应，只保留此前完整迭代。（验证：运行 `uv run pytest tests/test_agent.py -q -k provider_cancel`。）（AC10）

- [x] 工具阶段取消时，已完成调用保留真实结果，未开始调用得到 cancelled，已开始但无法确认的调用得到 cancel_outcome_unknown。（验证：运行 `uv run pytest tests/test_agent.py -q -k tool_cancel`。）（AC11）

- [x] 取消后不再启动 Provider 请求或工具批次，Agent 与 ToolScheduler 的活动任务集合为空。（验证：取消测试结束后断言无 active_provider_task、active_tasks 和未完成测试任务。）（AC10/AC11/N6）

- [x] 每轮产生迭代进度和单轮 usage，本次任务完成时包含累计输入、输出、总 Token；任一必要用量缺失时显示未知。（验证：运行 `uv run pytest tests/test_agent.py tests/test_tui.py -q -k "usage or progress"`。）（AC12）

- [x] `/plan` 与 `/plan 任务` 都能进入持续 Plan Mode；模式中只暴露 Read、Glob、Grep，Write、Edit、Bash 无法执行。（验证：运行 Agent 与 TUI 的 plan_mode 测试，并检查记录的工具定义名称。）（AC13）

- [x] Plan Mode 完成一次回复后仍保持；继续补充要求时仍使用只读工具，磁盘上不创建计划文件。（验证：连续运行两次 Plan Mode 请求，检查 mode、工具定义和文件系统。）（AC13）

- [x] `/do` 仅在 Plan Mode 已有计划时有效；有效时切回 Default、恢复六工具并自动发送执行提示，无效时不请求 Provider。（验证：运行 `uv run pytest tests/test_tui.py -q -k "do_command or mode"`。）（AC14）

## 集成与界面

- [x] TUI 只消费 AgentEvent，不直接执行工具、解析 Provider 事件或控制循环。（验证：检查 TUI 测试使用 Fake AgentEvent 即可驱动文本、工具、完成和错误展示。）（F3）

- [x] 流式期间动态区实时显示正文，工具调用前的 preamble 被固定到 scrollback，最终文本以 Markdown 定型。（验证：运行 TUI 事件测试，并在 tmux 场景中观察。）（F4/F14）

- [x] progress 事件显示类似 `Agent working… 3/50`，spinner 与总耗时持续刷新。（验证：运行 TUI progress 测试并在慢响应中观察秒数递增。）（AC12/N2）

- [x] 并发批次中的工具行按模型顺序展示，结果也按原始顺序展示，不因完成时间交错。（验证：使用不同延迟的假工具驱动 TUI，读取 RichLog 行顺序。）（N3）

- [x] tool_end 对成功、普通错误、cancelled 和 cancel_outcome_unknown 使用可区分文字与样式。（验证：运行 TUI 工具结果渲染测试。）（F14）

- [x] 运行中按 `Esc` 只取消当前任务，不退出程序；空闲时按 Esc 不改变会话；现有 Ctrl+C 复制或退出行为保持正常。（验证：运行 `uv run pytest tests/test_tui.py -q -k "escape or cancel or copy_or_quit"`。）（AC10/AC11）

- [x] completed、cancelled、limit 和 error 都会停止计时、清空动态区、恢复输入框并重新聚焦。（验证：逐种终止事件运行 TUI 测试。）（F14/N2）

- [x] Plan/Default 当前模式在界面中可见，`/plan` 和 `/do` 切换后立即更新。（验证：运行命令测试并观察状态栏或就绪提示。）（F11/F12）

- [x] 长文件、长命令和大量搜索结果继续按 ch03 规则截断，TUI 只显示摘要和截断提示。（验证：运行 ch03 大结果测试，并在一次真实长输出任务中观察 scrollback。）（N12）

- [x] Anthropic 与 OpenAI/DeepSeek 适配器向 Agent 输出相同类型的事件，TUI 无协议分支。（验证：分别使用两个 Fake Provider 跑同一 Agent/TUI 测试。）（AC15）

## 编译、测试与质量

- [x] `uv run python -m compileall -q src/dragon_code` 无错误。

- [x] `uv run ruff format --check .` 通过。

- [x] `uv run ruff check .` 无告警。

- [x] `uv run pytest tests/test_stream_collector.py tests/test_tool_scheduler.py tests/test_agent.py -q` 全部通过。

- [x] `uv run pytest tests/test_provider_anthropic.py tests/test_provider_openai.py -q` 全部通过。

- [x] `uv run pytest tests/test_tui.py tests/test_session.py -q` 全部通过。

- [x] `uv run pytest -q` 全部通过，ch02、ch03 和聊天复制功能无回归。

- [x] Agent 循环、双路收集、分批并发、取消收尾和模式切换具有简洁中文注释，没有残留 ChatSession 或 ch03 单轮限制分支。（验证：运行 `rg "ChatSession|LIMIT_MESSAGE" src tests` 无匹配，并人工回顾核心文件。）（N14）

- [x] 源码、事件、错误、终端输出和测试输出中不出现配置中的 API Key。（验证：使用不会打印密钥的定向检索和运行输出检查；不得把密钥作为检索命令参数回显。）（N13）

## 端到端场景

### 场景 1：Default Mode 多轮自主任务

- [x] 在 WSL 中进入项目目录，使用 tmux 启动 Dragon Code：

  ```text
  tmux new -s dragon-ch04
  uv run dragon-code
  ```

  输入：

  ```text
  读取 321.txt，判断它的主题；然后在 tmp/ch04-e2e/summary.txt 写入三行摘要；最后重新读取该文件并告诉我第一行。
  ```

  期望观察到：

  - 至少两次模型迭代。
  - Read、Write、Read 等工具自主连续执行。
  - 每轮进度发生变化。
  - 最终答复体现重新读取到的真实第一行。
  - 无需用户中途催促。（AC1/AC12/AC16）

### 场景 2：持续 Plan Mode 与 `/do`

- [x] 在同一会话输入：

  ```text
  /plan 为 tmp/ch04-e2e/plan-demo.txt 设计一份四行的 Agent Loop 学习卡片，先阅读 ch04 spec，再给出计划，不要执行。
  ```

  第一版计划完成后继续输入：

  ```text
  把学习卡片的最后一行改成“停止条件”，重新整理计划。
  ```

  然后输入：

  ```text
  /do
  ```

  期望观察到：

  - 两次规划请求均保持 Plan Mode。
  - 规划期间只出现 Read、Glob、Grep，不出现 Write、Edit、Bash。
  - `/do` 后切回 Default 并出现写工具。
  - `tmp/ch04-e2e/plan-demo.txt` 内容符合最终计划。
  - 执行完成后继续保持 Default Mode。（AC13/AC14/AC16）

### 场景 3：Esc 取消与恢复

- [x] 输入一个会运行较长时间的真实请求：

  ```text
  执行一个等待 20 秒后才输出 done 的 Python 命令，完成后再读取 README.md。
  ```

  在命令执行期间按 `Esc`，期望观察到：

  - 当前任务停止，不再执行后续读取。
  - 工具结果显示取消或最终状态未知。
  - Dragon Code 不退出，输入框恢复。
  - 随后输入“只回复 123”，能够正常得到答复。
  - tmux 中没有持续刷新的残留 Agent 任务。（AC10/AC11/AC16）

### 场景 4：工具错误后自主调整

- [x] 输入：

  ```text
  读取 does-not-exist-ch04.txt；如果不存在，改为读取 README.md，并告诉我项目标题。
  ```

  期望观察到：

  - 第一次 Read 返回结构化不存在错误。
  - Agent 不崩溃、不结束会话。
  - 模型根据错误自动再次调用 Read。
  - 最终答复来自 README.md 的真实内容。（F2/N9）

### 场景 5：跨协议一致

- [x] 使用有效的 Anthropic 协议配置运行场景 1，记录工具顺序、最终答复、Token 和结束状态。

- [x] 使用有效的 OpenAI/DeepSeek 兼容协议配置再次运行场景 1，期望触发、执行、回写、进度、用量和结束行为与 Anthropic 一致。（AC15）

### 场景 6：scrollback 与清理

- [x] 完成以上场景后在 tmux 中回滚，确认多轮文本、工具行、结果摘要、取消提示和最终答复按真实顺序存在；退出 Dragon Code 后终端状态正常。（AC16）

- [x] 验收结束后仅清理本次场景创建的 `tmp/ch04-e2e/` 测试目录，确认项目其他文件未被删除或覆盖。（验证：先确认目录绝对路径位于项目内，再执行清理。）

## 验收记录（2026-07-31）

### 自动化证据

- `uv run pytest -q`：`101 passed, 1 skipped`。
- `uv run ruff check .`：无告警。
- `uv run ruff format --check .`：62 个文件均已格式化。
- `uv run python -m compileall -q src/dragon_code`：通过。
- 旧架构符号检查：源码与测试中没有 `ChatSession`、`TurnEvent` 或 ch03 的 `LIMIT_MESSAGE`。
- 密钥定向扫描：配置目录以外的源码、测试和规格文档中，实际 API Key 命中数为 0。

### tmux 端到端证据

- Anthropic/DeepSeek 场景 1：自动完成读取 `321.txt`、写入三行摘要、重新读取和最终回答；磁盘检查为 3 行，首行为“1. 该文件是一句简短的赞美之词。”。
- Plan Mode：两次规划期间就绪提示持续显示“仅使用只读工具”，磁盘上没有提前创建目标文件；`/do` 后恢复 Default，生成 4 行学习卡片，最后一行为五种停止条件。
- Esc 取消：Bash 等待命令运行期间取消，界面显示 `cancel_outcome_unknown` 对应的“状态未知”结果和“当前任务已取消”；随后输入“只回复 123”得到正常回复。
- 工具错误调整：读取不存在文件失败后，Agent 自动改读 `README.md`，最终给出真实项目标题。
- OpenAI/DeepSeek 兼容协议：自动完成 `Read → Write → Read → 最终答复`，显示输入、输出和累计 Token；测试后配置已恢复为 Anthropic。
- 真实 Anthropic 流暴露了 SDK 高级 `input_json` 事件不带 `index` 的兼容问题；修复并加入线上事件形状回归测试后，真实多轮工具调用通过。
- 两个 tmux 会话均通过 `/exit` 正常结束，无残留会话；验收创建的 `tmp/ch04-e2e/` 已在确认绝对路径后清理。
