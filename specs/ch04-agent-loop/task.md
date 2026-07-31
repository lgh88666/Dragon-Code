# Dragon Code Agent Loop Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|---|---|---|
| 新建 | `src/dragon_code/agent.py` | Agent Loop、停止条件、取消与模式 |
| 新建 | `src/dragon_code/stream_collector.py` | 单轮 Provider 流式响应双路收集 |
| 新建 | `src/dragon_code/tool_scheduler.py` | 工具分批、并发执行与取消结果 |
| 修改 | `src/dragon_code/models.py` | TokenUsage、ProviderEvent、AgentEvent |
| 修改 | `src/dragon_code/session.py` | 保留 Conversation，移除 ChatSession |
| 修改 | `src/dragon_code/prompt.py` | Plan Mode 和 `/do` 内部提示 |
| 修改 | `src/dragon_code/tui.py` | AgentEvent、进度、用量、命令与 Esc |
| 修改 | `src/dragon_code/providers/base.py` | 更新统一 Provider 事件接口说明 |
| 修改 | `src/dragon_code/providers/anthropic.py` | Anthropic 流式 Token 用量 |
| 修改 | `src/dragon_code/providers/openai.py` | OpenAI 流式 Token 用量与流清理 |
| 修改 | `src/dragon_code/tools/registry.py` | 工具子注册中心 |
| 修改 | `tests/conftest.py` | 多轮 FakeProvider 与用量测试辅助 |
| 新建 | `tests/test_agent.py` | Agent Loop、停止、取消与模式测试 |
| 新建 | `tests/test_stream_collector.py` | 双路收集测试 |
| 新建 | `tests/test_tool_scheduler.py` | 分批、并发与取消测试 |
| 修改 | `tests/test_provider_anthropic.py` | Anthropic usage 测试 |
| 修改 | `tests/test_provider_openai.py` | OpenAI usage-only 分片与关闭测试 |
| 修改 | `tests/test_session.py` | Conversation 测试 |
| 修改 | `tests/test_prompt.py` | Plan Mode Prompt 测试 |
| 修改 | `tests/test_tool_registry.py` | 工具子集测试 |
| 修改 | `tests/test_tui.py` | AgentEvent、命令、进度和取消测试 |

`pyproject.toml` 不修改，本章不增加依赖。

## T1：增加 Token 与 Agent 事件模型

**文件：** `src/dragon_code/models.py`
**依赖：** 无

**步骤：**

1. 新增 `TokenUsage` 数据类，字段为 `input_tokens` 和 `output_tokens`。
2. 实现 `add()`，逐字段累计；任一侧未知时累计值保持 `None`。
3. 实现 `total_tokens` 属性。
4. 给 `ProviderEvent` 增加 `usage` 字段。
5. 用 `AgentEvent` 替换 `TurnEvent`，加入 usage、iteration 和 max_iterations 字段。
6. 为用量合并与事件字段添加简短中文注释。

**验证：**

运行 `uv run python -c "from dragon_code.models import TokenUsage, AgentEvent; assert TokenUsage(2, 3).total_tokens == 5; assert TokenUsage(2, 3).add(TokenUsage(None, 4)).input_tokens is None; print('ok')"`，期望输出 `ok`。

## T2：实现单轮流式收集器

**文件：** `src/dragon_code/stream_collector.py`、`tests/test_stream_collector.py`
**依赖：** T1

**步骤：**

1. 定义 `CollectedResponse`。
2. 定义 `StreamCollector.accept()`，把 text_delta 转成 text AgentEvent。
3. 收集 usage 与 completed 消息。
4. 定义 `finish()`；缺少完整消息时抛出脱敏的响应错误。
5. 测试文本实时转换、完整消息返回、usage 保存和缺少 completed 四种情况。

**验证：**

运行 `uv run pytest tests/test_stream_collector.py -q`，期望全部通过。

## T3：提取 Anthropic 流式用量

**文件：** `src/dragon_code/providers/anthropic.py`、`tests/test_provider_anthropic.py`
**依赖：** T1

**步骤：**

1. 在流开始时初始化未知 TokenUsage。
2. 处理 `message_start`，读取输入 Token。
3. 处理 `message_delta`，使用最新输出 Token 覆盖旧值。
4. 在 completed 前产生一个 usage ProviderEvent。
5. 保持 thinking、工具 JSON 拼接和取消传播行为不变。
6. 增加输入、输出用量和缺失用量测试。

**验证：**

运行 `uv run pytest tests/test_provider_anthropic.py -q`，期望全部通过。

## T4：提取 OpenAI 流式用量并关闭响应

**文件：** `src/dragon_code/providers/openai.py`、`tests/test_provider_openai.py`
**依赖：** T1

**步骤：**

1. 在请求中加入流式 usage 选项。
2. 每个分片先读取 usage，再判断 choices 是否为空。
3. 兼容无 usage 分片，保持字段未知。
4. 在 completed 前产生 usage ProviderEvent。
5. 使用 `finally` 保证正常、异常和取消时关闭流。
6. 扩展 FakeStream 记录关闭状态。
7. 测试 choices 为空的 usage-only 分片、缺失用量和异常关闭。

**验证：**

运行 `uv run pytest tests/test_provider_openai.py -q`，期望全部通过。

## T5：实现工具注册中心子集

**文件：** `src/dragon_code/tools/registry.py`、`tests/test_tool_registry.py`
**依赖：** 无

**步骤：**

1. 新增 `subset(names)`。
2. 按原注册顺序选取名称在集合中的工具。
3. 子注册中心复用原工具实例，不重新构造工具。
4. 测试 Read、Glob、Grep 子集的顺序和定义列表。
5. 测试子集中查找 Write 返回空。

**验证：**

运行 `uv run pytest tests/test_tool_registry.py -q`，期望全部通过。

## T6：实现工具调用分批

**文件：** `src/dragon_code/tool_scheduler.py`、`tests/test_tool_scheduler.py`
**依赖：** T1、T5

**步骤：**

1. 定义 `ToolBatch`。
2. 定义 `ToolScheduler` 基础结构。
3. 实现 `partition()`。
4. 连续并发安全工具合并成一个 concurrent 批次。
5. 有副作用、不安全和未知工具各自成为串行批次。
6. 测试 `Read → Glob → Edit → Read` 的批次结构和原始顺序。

**验证：**

运行 `uv run pytest tests/test_tool_scheduler.py -q -k partition`，期望分批测试通过。

## T7：实现批内并发与结果保序

**文件：** `src/dragon_code/tool_scheduler.py`、`tests/test_tool_scheduler.py`
**依赖：** T6

**步骤：**

1. 为批次中的每个工具创建独立异步任务。
2. concurrent 批次同时启动全部任务；串行批次只启动一个任务。
3. 使用统一等待收集任务结果。
4. 单个任务异常转换为该工具的结构化失败结果。
5. 按调用原始下标返回结果。
6. 用不同延迟的假工具证明完成顺序变化但返回顺序不变。

**验证：**

运行 `uv run pytest tests/test_tool_scheduler.py -q -k "execute or order or failure"`，期望全部通过。

## T8：实现工具调度取消结果

**文件：** `src/dragon_code/tool_scheduler.py`、`tests/test_tool_scheduler.py`
**依赖：** T7

**步骤：**

1. 在执行期间登记 active_tasks。
2. 实现 `cancel_active()`，向所有未完成任务发送取消信号。
3. 把已启动但被取消的任务转换为 `cancel_outcome_unknown`。
4. 实现 `make_cancelled_results()`，为未启动调用生成 `cancelled`。
5. 在批次结束后清空 active_tasks。
6. 测试取消结果错误码、结果顺序和活动任务清理。

**验证：**

运行 `uv run pytest tests/test_tool_scheduler.py -q -k cancel`，期望全部通过。

## T9：增加 Plan Mode 与执行提示

**文件：** `src/dragon_code/prompt.py`、`tests/test_prompt.py`
**依赖：** 无

**步骤：**

1. 新增 `PLAN_MODE_PROMPT`。
2. 提示中明确只探索、只规划、不修改、不执行命令。
3. 新增 `DO_PLAN_PROMPT`，要求根据上文计划开始执行。
4. 新增 `build_agent_prompt(base_prompt, mode)`。
5. 测试 default 不追加计划提示，plan 正确追加。

**验证：**

运行 `uv run pytest tests/test_prompt.py -q`，期望全部通过。

## T10：升级 Provider 测试辅助

**文件：** `tests/conftest.py`
**依赖：** T1

**步骤：**

1. 让 FakeProvider 可以按顺序返回多组流事件。
2. 支持 text_delta、usage、tool_call、completed 和 ProviderError。
3. 记录每次请求的 messages、system_prompt 和 tools。
4. 保留现有单轮测试需要的简单构造方式。

**验证：**

运行 `uv run pytest tests/test_provider_anthropic.py tests/test_provider_openai.py tests/test_session.py -q`，期望测试辅助改动不破坏现有用例。

## T11：建立 Agent 与自然完成路径

**文件：** `src/dragon_code/agent.py`、`tests/test_agent.py`
**依赖：** T2、T5、T9、T10

**步骤：**

1. 定义 Agent 构造参数和基础状态。
2. 实现 `run()` 的迭代框架。
3. 第一轮使用“已有历史 + 当前用户消息”请求 Provider。
4. 每轮先产生 progress 事件。
5. 使用 StreamCollector 转发 text 并取得完整响应。
6. 无工具调用时提交用户消息与最终助手消息。
7. 产生 usage 和 completed 事件。
8. 测试直接文本回复只请求一次并正确提交历史。

**验证：**

运行 `uv run pytest tests/test_agent.py -q -k "natural or plain"`，期望全部通过。

## T12：实现多轮工具循环

**文件：** `src/dragon_code/agent.py`、`tests/test_agent.py`
**依赖：** T7、T11

**步骤：**

1. 完整响应包含工具时调用 ToolScheduler.partition()。
2. 每个批次执行前按顺序产生 tool_start。
3. 批次完成后按顺序产生 tool_end。
4. 将 assistant 工具调用和完整 ToolResult 回合提交历史。
5. 使用更新后的完整历史进入下一轮。
6. 最终纯文本回复结束循环。
7. 测试至少两轮工具调用后自然完成。

**验证：**

运行 `uv run pytest tests/test_agent.py -q -k "multi or tool_loop or history"`，期望全部通过。

## T13：实现连续未知工具停止

**文件：** `src/dragon_code/agent.py`、`tests/test_agent.py`
**依赖：** T12

**步骤：**

1. 每轮工具结果完成后判断是否全部为 unknown_tool。
2. 全部未知时计数加一，出现已注册工具时归零。
3. 达到 unknown_tool_limit 后产生 limit 事件。
4. 停止前先提交当前助手调用和未知工具结果。
5. 测试连续三轮停止和中间有效工具重置。

**验证：**

运行 `uv run pytest tests/test_agent.py -q -k unknown`，期望全部通过。

## T14：实现迭代上限

**文件：** `src/dragon_code/agent.py`、`tests/test_agent.py`
**依赖：** T12

**步骤：**

1. 使用构造参数限制最大模型迭代数。
2. 最后一轮仍请求工具时执行并提交工具结果。
3. 产生 limit 事件，不发起下一次请求。
4. 测试注入上限 2 时只产生两次 Provider 请求。
5. 测试历史中的最后一组工具调用拥有对应结果。

**验证：**

运行 `uv run pytest tests/test_agent.py -q -k iteration_limit`，期望全部通过。

## T15：实现 Provider 阶段取消与流错误

**文件：** `src/dragon_code/agent.py`、`tests/test_agent.py`
**依赖：** T3、T4、T11

**步骤：**

1. 每次等待 Provider 下一个事件时登记 active_provider_task。
2. 实现 `request_cancel()` 设置标记并取消当前 Provider 任务。
3. 捕获取消后关闭当前流迭代器。
4. 不提交未产生 completed 的当前响应。
5. 产生 cancelled 事件并清理活动任务。
6. ProviderError 转成 error 事件，保留此前完整迭代。
7. 测试响应中途取消、流错误和后续会话可继续。

**验证：**

运行 `uv run pytest tests/test_agent.py -q -k "provider_cancel or stream_error"`，期望全部通过。

## T16：实现工具阶段取消与历史补齐

**文件：** `src/dragon_code/agent.py`、`tests/test_agent.py`
**依赖：** T8、T12、T15

**步骤：**

1. `request_cancel()` 同时调用 ToolScheduler.cancel_active()。
2. 当前批次保留真实结果或 `cancel_outcome_unknown`。
3. 后续未执行批次生成 `cancelled`。
4. 为所有调用按原始顺序产生 tool_end。
5. 提交完整 assistant 工具调用与全部 ToolResult。
6. 提交后产生 cancelled，不再请求 Provider。
7. 测试三种取消结果、历史配对和 active_tasks 清空。

**验证：**

运行 `uv run pytest tests/test_agent.py -q -k tool_cancel`，期望全部通过。

## T17：实现 Agent 模式状态

**文件：** `src/dragon_code/agent.py`、`tests/test_agent.py`
**依赖：** T5、T9、T12

**步骤：**

1. 实现 `enter_plan_mode()`、`enter_default_mode()` 和 `can_execute_plan()`。
2. Plan Mode 使用 Read、Glob、Grep 子注册中心。
3. Plan Mode 请求使用追加后的系统提示。
4. Plan Mode 自然完成后设置 has_plan。
5. Default Mode 恢复六工具与基础提示。
6. 测试模式跨普通消息保持、工具定义过滤和状态切换。

**验证：**

运行 `uv run pytest tests/test_agent.py -q -k plan_mode`，期望全部通过。

## T18：让 TUI 创建并运行 Agent

**文件：** `src/dragon_code/tui.py`
**依赖：** T17

**步骤：**

1. 将 `self.session` 替换为 `self.agent`。
2. Provider 激活时创建 Conversation、ToolRegistry 和 Agent。
3. 将 `_consume_turn()` 改为消费 `agent.run()`。
4. 保留输入禁用、计时和 Worker 的现有生命周期。
5. 暂时按现有 text、tool、completed、limit、error 分支映射新事件。

**验证：**

运行 `uv run python -m compileall -q src/dragon_code`，期望无编译错误。

## T19：移除 ch03 单轮 ChatSession

**文件：** `src/dragon_code/session.py`、`tests/test_session.py`
**依赖：** T18

**步骤：**

1. 删除 ChatSession 和 ch03 单轮上限常量。
2. 保留 Conversation 的历史副本、请求构造和批量提交方法。
3. 删除旧单轮闭环测试。
4. 保留并补充 Conversation 顺序、复制隔离和批量提交测试。
5. 搜索项目，确认没有 ChatSession 导入。

**验证：**

运行 `uv run pytest tests/test_session.py -q`，并运行 `rg "ChatSession|LIMIT_MESSAGE" src tests`；期望测试通过且搜索无匹配。

## T20：完成 TUI AgentEvent 渲染

**文件：** `src/dragon_code/tui.py`、`tests/test_tui.py`
**依赖：** T18、T19

**步骤：**

1. progress 更新当前迭代与计时文字。
2. text 实时更新动态回复。
3. tool_start 固定前置文本并写工具行。
4. tool_end 按成功、错误、取消和状态未知显示摘要。
5. usage 保存本次任务累计值。
6. completed 显示 Markdown、耗时和 Token。
7. cancelled、limit、error 统一停止计时并恢复输入。
8. 测试各事件的可观测界面结果。

**验证：**

运行 `uv run pytest tests/test_tui.py -q -k "event or progress or usage or cancelled"`，期望全部通过。

## T21：接入 `/plan` 和 `/do`

**文件：** `src/dragon_code/tui.py`、`tests/test_tui.py`
**依赖：** T17、T20

**步骤：**

1. 精确识别 `/plan` 与 `/plan 任务内容`。
2. `/plan` 无参数时切换模式但不启动 Worker。
3. `/plan 任务` 使用去掉命令前缀的任务文本启动 Agent。
4. Plan Mode 状态显示在状态栏或就绪提示。
5. `/do` 校验 `can_execute_plan()`。
6. 有计划时切换 Default 并使用 DO_PLAN_PROMPT 启动 Agent。
7. 无计划或模式不正确时显示提示且不请求模型。
8. 测试持续 Plan Mode、计划修改、`/do` 和错误边界。

**验证：**

运行 `uv run pytest tests/test_tui.py -q -k "plan or do_command or mode"`，期望全部通过。

## T22：接入 Esc 取消

**文件：** `src/dragon_code/tui.py`、`tests/test_tui.py`
**依赖：** T16、T20

**步骤：**

1. 增加高优先级 Esc binding。
2. 只在 STREAMING 状态调用 `agent.request_cancel()`。
3. Esc 不直接取消 TUI Worker，也不退出程序。
4. cancelled 事件到达后恢复输入框和焦点。
5. 空闲状态按 Esc 不改变会话。
6. 应用退出时仍强制取消 Worker，避免残留。
7. 测试运行中取消、空闲 Esc 和退出清理。

**验证：**

运行 `uv run pytest tests/test_tui.py -q -k "escape or cancel or quit"`，期望全部通过。

## T23：补齐跨模块与回归测试

**文件：** `tests/test_agent.py`、`tests/test_tui.py`、现有 Provider 与工具测试
**依赖：** T1-T22

**步骤：**

1. 增加事件顺序断言：progress → text/tool → usage → completed/limit。
2. 增加并发批次 scrollback 顺序断言。
3. 增加工具失败后 Agent 继续下一轮测试。
4. 增加 Plan Mode 幻觉 Write 时不会执行的测试。
5. 增加取消后下一条正常消息成功的测试。
6. 确认 ch02/ch03 配置、工具和复制功能测试仍保留。

**验证：**

运行 `uv run pytest -q`，期望全部测试通过。

## T24：格式、静态检查与源码清理

**文件：** 本章全部新增和修改的 Python 文件
**依赖：** T23

**步骤：**

1. 删除未使用导入和旧 ChatSession 分支。
2. 检查 Agent 循环、双路收集、分批并发、取消和模式切换均有中文注释。
3. 运行格式化。
4. 运行 lint。
5. 重新运行全部测试。
6. 检索代码和测试输出，确认没有 API Key 明文。

**验证：**

依次运行：

```text
uv run ruff format .
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
```

期望全部命令通过。

## 执行顺序

```text
T1 ─┬→ T2
    ├→ T3
    ├→ T4
    └→ T10

T5 → T6 → T7 → T8
T9 ───────────┐
T2 + T5 + T9 + T10 → T11
T7 + T11 → T12 ─┬→ T13
                ├→ T14
T3 + T4 + T11 ──┴→ T15
T8 + T12 + T15 → T16
T5 + T9 + T12 → T17
T17 → T18 → T19 → T20
T17 + T20 → T21
T16 + T20 → T22
T1-T22 → T23 → T24
```

建议提交检查点：

```text
T1-T5     基础事件、用量、收集器与工具子集
T6-T9     调度器与模式提示
T10-T17   Agent Loop、停止、取消与模式
T18-T22   TUI 接入
T23-T24   回归与质量检查
```
