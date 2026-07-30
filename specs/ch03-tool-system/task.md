# Dragon Code 工具系统 Tasks

> 包名：`dragon_code`，Python 3.12+。每个任务都是一个聚焦工作单元，完成后先运行
> 对应验证，再进入下一个任务。

## 文件清单

| 操作 | 文件 | 职责 |
|---|---|---|
| 修改 | `pyproject.toml` | 显式加入 Pydantic v2 |
| 修改 | `uv.lock` | 同步依赖锁定结果 |
| 修改 | `src/dragon_code/models.py` | 工具、消息和事件数据类 |
| 修改 | `src/dragon_code/prompt.py` | 动态 Agent System Prompt |
| 修改 | `src/dragon_code/session.py` | 对话历史与单轮工具闭环 |
| 修改 | `src/dragon_code/tui.py` | 工具行、结果摘要和上限提示 |
| 修改 | `src/dragon_code/providers/base.py` | 统一 ProviderEvent 接口 |
| 修改 | `src/dragon_code/providers/openai.py` | OpenAI 工具协议适配 |
| 修改 | `src/dragon_code/providers/anthropic.py` | Anthropic 工具协议适配 |
| 新建 | `src/dragon_code/tools/__init__.py` | 导出默认工具注册中心 |
| 新建 | `src/dragon_code/tools/base.py` | Tool 基类和公共执行保护 |
| 新建 | `src/dragon_code/tools/path_utils.py` | 工作目录路径检查 |
| 新建 | `src/dragon_code/tools/file_tools.py` | Read、Write、Edit |
| 新建 | `src/dragon_code/tools/search_tools.py` | Glob、Grep |
| 新建 | `src/dragon_code/tools/bash.py` | Bash 命令执行 |
| 新建 | `src/dragon_code/tools/registry.py` | ToolRegistry 与六工具注册 |
| 修改 | `tests/conftest.py` | 支持 ProviderEvent 的假 Provider |
| 修改 | `tests/test_prompt.py` | Agent 工具规则测试 |
| 修改 | `tests/test_provider_openai.py` | OpenAI 工具协议测试 |
| 修改 | `tests/test_provider_anthropic.py` | Anthropic 工具协议测试 |
| 修改 | `tests/test_session.py` | 普通对话和工具闭环测试 |
| 修改 | `tests/test_tui.py` | 工具展示与界面恢复测试 |
| 新建 | `tests/test_tool_base.py` | 数据模型、Schema、校验、超时测试 |
| 新建 | `tests/test_tool_registry.py` | 注册、查找和默认工具集测试 |
| 新建 | `tests/test_file_tools.py` | 文件工具和路径边界测试 |
| 新建 | `tests/test_search_tools.py` | 搜索工具和结果限制测试 |
| 新建 | `tests/test_bash_tool.py` | Bash 输出、失败、超时测试 |
| 修改 | `docs/learning-notes.md` | ch03 源码回顾和学习要点 |

## T1：加入参数校验依赖

**文件：** `pyproject.toml`、`uv.lock`  
**依赖：** 无

**步骤：**

1. 在运行依赖中显式加入 `pydantic>=2,<3`。
2. 使用 uv 更新锁文件。
3. 同步开发环境，确认 Pydantic 可直接导入。

**验证：**

```powershell
uv sync --all-groups
uv run python -c "import pydantic; print(pydantic.VERSION)"
```

期望：同步成功并打印 2.x 版本。

## T2：扩展共享数据模型

**文件：** `src/dragon_code/models.py`、`tests/test_tool_base.py`  
**依赖：** T1

**步骤：**

1. 新增 `ToolDefinition`、`ToolCall`、`ToolResult` 和 `ProviderEvent` 数据类。
2. 扩展 `ChatMessage` 与 `TurnEvent`，所有列表字段使用独立的
   `default_factory`。
3. 实现 `ToolResult.to_model_text()`，输出不转义中文的稳定 JSON。
4. 添加默认值、列表隔离和 JSON 内容测试。

**验证：**

```powershell
uv run pytest tests/test_tool_base.py -q
```

期望：数据类与 JSON 序列化测试通过。

## T3：实现 Tool 定义与 Schema 生成

**文件：** `src/dragon_code/tools/base.py`、`tests/test_tool_base.py`  
**依赖：** T2

**步骤：**

1. 定义 `Tool` 基类的元信息字段和 `arguments_model`。
2. 实现 `definition()`，使用 Pydantic `model_json_schema()` 生成参数 Schema。
3. 编写最小假工具，验证名称、描述和四类元信息完整导出。

**验证：**

```powershell
uv run pytest tests/test_tool_base.py -q -k "definition or schema"
```

期望：Schema 含参数类型、必填项和字段描述。

## T4：实现 Tool 公共执行保护

**文件：** `src/dragon_code/tools/base.py`、`tests/test_tool_base.py`  
**依赖：** T3

**步骤：**

1. 在 `execute()` 中处理 `arguments=None` 和 Pydantic 参数校验失败。
2. 使用 `asyncio.wait_for()` 包裹具体工具的 `run()`。
3. 将超时、路径错误和未预期异常转换成结构化 `ToolResult`。
4. 保留 `CancelledError`，不把程序取消误报成普通工具错误。

**验证：**

```powershell
uv run pytest tests/test_tool_base.py -q -k "invalid or timeout or exception"
```

期望：所有失败均返回 `success=false`，测试中没有未捕获异常。

## T5：实现工作目录路径检查

**文件：** `src/dragon_code/tools/path_utils.py`、`tests/test_file_tools.py`  
**依赖：** T2

**步骤：**

1. 定义专用路径范围错误。
2. 实现相对路径和绝对路径规范化。
3. 使用解析后的真实路径检查目标是否位于工作目录内。
4. 添加正常路径、`../` 越界和绝对路径越界测试。

**验证：**

```powershell
uv run pytest tests/test_file_tools.py -q -k "path"
```

期望：目录内路径成功，目录外路径被拒绝。

## T6：实现 Read 工具

**文件：** `src/dragon_code/tools/file_tools.py`、`tests/test_file_tools.py`  
**依赖：** T3、T4、T5

**步骤：**

1. 定义带字段描述的 `ReadArguments`。
2. 使用 `asyncio.to_thread()` 读取 UTF-8 普通文件。
3. 添加从 1 开始的行号，并应用 2000 行和 100,000 字符上限。
4. 测试正常读取、不存在文件、目录路径和超长内容。

**验证：**

```powershell
uv run pytest tests/test_file_tools.py -q -k "read"
```

期望：正常内容带行号，错误结构化返回，长内容标记截断。

## T7：实现 Write 工具

**文件：** `src/dragon_code/tools/file_tools.py`、`tests/test_file_tools.py`  
**依赖：** T6

**步骤：**

1. 定义 `WriteArguments` 和完整工具描述。
2. 自动创建工作目录内的父目录，并以 UTF-8 创建或覆盖文件。
3. 返回目标相对路径和写入字符数。
4. 测试创建、嵌套目录、覆盖和路径越界。

**验证：**

```powershell
uv run pytest tests/test_file_tools.py -q -k "write"
```

期望：磁盘内容完全一致，越界目标没有被创建。

## T8：实现 Edit 工具

**文件：** `src/dragon_code/tools/file_tools.py`、`tests/test_file_tools.py`  
**依赖：** T6

**步骤：**

1. 定义 `EditArguments` 和唯一匹配规则说明。
2. 统计 `old_text` 精确匹配数。
3. 仅在匹配一次时替换并写回。
4. 测试匹配一次、零次、多次及路径越界，并验证失败时文件不变。

**验证：**

```powershell
uv run pytest tests/test_file_tools.py -q -k "edit"
```

期望：三种匹配结果可区分，失败场景不修改文件。

## T9：实现 Glob 工具

**文件：** `src/dragon_code/tools/search_tools.py`、`tests/test_search_tools.py`  
**依赖：** T3、T4、T5

**步骤：**

1. 定义 `GlobArguments` 和工具描述。
2. 在工作目录内匹配文件，转换为排序后的相对路径。
3. 限制为 200 个结果并设置截断标记。
4. 测试正常匹配、无结果、越界模式和海量结果。

**验证：**

```powershell
uv run pytest tests/test_search_tools.py -q -k "glob"
```

期望：结果稳定排序，无匹配成功返回空结果，数量受到限制。

## T10：实现 Grep 工具

**文件：** `src/dragon_code/tools/search_tools.py`、`tests/test_search_tools.py`  
**依赖：** T9

**步骤：**

1. 定义 `GrepArguments`，明确 `pattern` 为正则表达式。
2. 支持搜索单文件或工作目录内子目录。
3. 跳过常见无关目录和非 UTF-8 文件。
4. 返回文件、行号和命中行，限制 200 条且单行最多 500 字符。
5. 测试命中、无命中、非法正则、指定范围和截断。

**验证：**

```powershell
uv run pytest tests/test_search_tools.py -q -k "grep"
```

期望：命中位置正确，非法正则结构化返回，结果限制生效。

## T11：实现 Bash 基础执行

**文件：** `src/dragon_code/tools/bash.py`、`tests/test_bash_tool.py`  
**依赖：** T3、T4

**步骤：**

1. 定义 `BashArguments` 和保守的破坏性元信息。
2. 使用 `asyncio.create_subprocess_shell()`，将 cwd 设置为启动工作目录。
3. 收集 stdout、stderr 和退出码。
4. 测试正常输出、stderr 和非零退出。

**验证：**

```powershell
uv run pytest tests/test_bash_tool.py -q -k "output or nonzero"
```

期望：三个输出字段完整，非零退出返回 `success=false`。

## T12：补充 Bash 超时与输出限制

**文件：** `src/dragon_code/tools/bash.py`、`tests/test_bash_tool.py`  
**依赖：** T11

**步骤：**

1. 超时时终止子进程并等待进程回收。
2. 将超时转换为 `timeout` 结构化结果。
3. 将 stdout 与 stderr 合计限制为 100,000 字符。
4. 添加跨平台的短超时测试和长输出测试。

**验证：**

```powershell
uv run pytest tests/test_bash_tool.py -q -k "timeout or truncate"
```

期望：测试在限定时间内结束，长输出标记截断。

## T13：实现 ToolRegistry 核心行为

**文件：** `src/dragon_code/tools/registry.py`、`tests/test_tool_registry.py`  
**依赖：** T4

**步骤：**

1. 实现注册、重复名拒绝、按名查找和定义列表。
2. 实现未知工具与无效 JSON 的结构化结果。
3. 将合法调用交给对应工具的 `execute()`。
4. 测试注册顺序、重复名、未知名和调用转发。

**验证：**

```powershell
uv run pytest tests/test_tool_registry.py -q -k "register or unknown or execute"
```

期望：注册顺序稳定，任何查找失败都不抛到会话层。

## T14：组装默认六工具注册中心

**文件：** `src/dragon_code/tools/registry.py`、`src/dragon_code/tools/__init__.py`、`tests/test_tool_registry.py`  
**依赖：** T6–T13

**步骤：**

1. 实现接收工作目录的默认注册中心工厂。
2. 按 Read、Write、Edit、Bash、Glob、Grep 顺序实例化。
3. 从包入口导出工厂与注册中心类型。
4. 验证六个名称、Schema 和四类元信息。

**验证：**

```powershell
uv run pytest tests/test_tool_registry.py -q
```

期望：六个工具完整注册且定义可序列化。

### 提交节点 A

完成 T1–T14 且相关测试通过后，提交“工具基础与六个核心工具”这一组改动。

## T15：构建 Agent System Prompt

**文件：** `src/dragon_code/prompt.py`、`tests/test_prompt.py`  
**依赖：** T2

**步骤：**

1. 保留 Banner 代码不变。
2. 将纯文本常量改为接收工作目录的 `build_system_prompt()`。
3. 写明 Agent 身份、操作系统、工作目录、工具结果真实性和单轮限制。
4. 测试提示词不包含 API Key，也不再声称“仅支持文本对话”。

**验证：**

```powershell
uv run pytest tests/test_prompt.py -q
```

期望：工具规则、工作目录和操作系统均出现在提示词中。

## T16：升级 Provider 公共流式接口

**文件：** `src/dragon_code/providers/base.py`、`tests/conftest.py`  
**依赖：** T2

**步骤：**

1. 将 `BaseProvider.stream()` 扩展为接收工具定义。
2. 约定输出 `ProviderEvent`，并更新中文接口注释。
3. 更新 `FakeProvider`，使其可预设完整事件序列并记录收到的工具定义。
4. 保留现有延迟和 ProviderError 模拟能力。

**验证：**

```powershell
uv run python -m compileall -q src/dragon_code/providers tests/conftest.py
uv run pytest tests/test_provider_errors.py -q
```

期望：Provider 与假 Provider 可导入，现有公共错误测试通过。

## T17：实现 OpenAI 工具定义与历史转换

**文件：** `src/dragon_code/providers/openai.py`、`tests/test_provider_openai.py`  
**依赖：** T16

**步骤：**

1. 将统一工具定义转换为 OpenAI function tools。
2. 转换普通消息、Assistant `tool_calls` 和每个 `role=tool` 结果。
3. 保留 system prompt 与完整历史顺序。
4. 测试请求体包含六工具格式及正确的 `tool_call_id`。

**验证：**

```powershell
uv run pytest tests/test_provider_openai.py -q -k "request or message or tool_definition"
```

期望：请求体结构符合 Chat Completions 工具格式。

## T18：实现 OpenAI 流式工具参数拼接

**文件：** `src/dragon_code/providers/openai.py`、`tests/test_provider_openai.py`  
**依赖：** T17

**步骤：**

1. 按 `tool_call.index` 建立临时缓冲区。
2. 拼接调用 ID、函数名和 arguments JSON 片段。
3. 流结束后按 index 产生完整 `tool_call` 事件。
4. 测试单工具、多工具、名称分片和参数分片。

**验证：**

```powershell
uv run pytest tests/test_provider_openai.py -q -k "fragment or multiple"
```

期望：多个调用不混淆，参数字典完整。

## T19：完成 OpenAI 统一完成事件

**文件：** `src/dragon_code/providers/openai.py`、`tests/test_provider_openai.py`  
**依赖：** T18

**步骤：**

1. 正文改为产生 `text_delta` 事件。
2. 流结束产生包含正文和工具调用的 `completed` 事件。
3. 无效 JSON 生成 `arguments=None` 与 `parse_error`。
4. 保留空 choices 忽略和脱敏错误转换。

**验证：**

```powershell
uv run pytest tests/test_provider_openai.py -q
```

期望：文本、工具、完成和错误测试全部通过。

## T20：实现 Anthropic 工具定义与历史转换

**文件：** `src/dragon_code/providers/anthropic.py`、`tests/test_provider_anthropic.py`  
**依赖：** T16

**步骤：**

1. 将统一工具定义转换为 Anthropic `input_schema`。
2. 将 Assistant 调用转换为 `tool_use` 内容块。
3. 将内部 tool 消息转换为 user `tool_result`，失败时设置 `is_error=true`。
4. 测试多结果同一 user 消息和调用 ID 对应关系。

**验证：**

```powershell
uv run pytest tests/test_provider_anthropic.py -q -k "request or message or tool_result"
```

期望：请求历史符合 Anthropic Messages 工具结构。

## T21：实现 Anthropic 流式工具参数拼接

**文件：** `src/dragon_code/providers/anthropic.py`、`tests/test_provider_anthropic.py`  
**依赖：** T20

**步骤：**

1. 在 `content_block_start` 记录 tool_use ID、名称和 index。
2. 在 JSON 增量事件中按 index 拼接参数。
3. 内容块结束时产生完整 `tool_call` 事件。
4. 测试单工具、多工具、分片 JSON 和无效 JSON。

**验证：**

```powershell
uv run pytest tests/test_provider_anthropic.py -q -k "tool_use or fragment or multiple"
```

期望：工具调用完整且互不混淆。

## T22：保留 Anthropic 隐藏思考块

**文件：** `src/dragon_code/providers/anthropic.py`、`tests/test_provider_anthropic.py`  
**依赖：** T21

**步骤：**

1. 捕获 `thinking` 与 `redacted_thinking` 的完整内容块。
2. 只将其写入 Assistant `hidden_blocks`，不产生文本事件。
3. 在工具续答请求中把隐藏块原样放回 Assistant 消息开头。
4. 流结束产生完整 `completed` 事件并保留现有 thinking 配置测试。

**验证：**

```powershell
uv run pytest tests/test_provider_anthropic.py -q
```

期望：TUI 可见事件中无思考文本，续答请求保留完整隐藏块。

### 提交节点 B

完成 T15–T22 且 Provider 测试通过后，提交“跨协议工具调用解析”这一组改动。

## T23：扩展 Conversation 消息提交

**文件：** `src/dragon_code/session.py`、`tests/test_session.py`  
**依赖：** T2

**步骤：**

1. 保留返回历史副本和临时用户消息构建。
2. 增加一次提交多条统一消息的入口。
3. 测试普通消息、工具调用、工具结果和隐藏块的顺序。
4. 确认外部修改返回列表不会污染内部历史。

**验证：**

```powershell
uv run pytest tests/test_session.py -q -k "conversation"
```

期望：统一历史顺序正确，副本隔离有效。

## T24：迁移普通文本会话流程

**文件：** `src/dragon_code/session.py`、`tests/test_session.py`  
**依赖：** T14、T16、T23

**步骤：**

1. 给 `ChatSession` 注入 `ToolRegistry`。
2. 消费 `text_delta` 与 `completed` ProviderEvent。
3. 无工具调用时保持 ch02 的流式文本和历史行为。
4. ProviderError 时发送 error 事件且不提交本轮。

**验证：**

```powershell
uv run pytest tests/test_session.py -q -k "plain or failure or second_turn"
```

期望：原有普通对话行为没有回归。

## T25：执行首轮多工具调用

**文件：** `src/dragon_code/session.py`、`tests/test_session.py`  
**依赖：** T24

**步骤：**

1. 收集首轮完整 Assistant 消息中的所有工具调用。
2. 按出现顺序发送 `tool_call`、执行注册中心并发送 `tool_result`。
3. 单个失败时继续执行剩余调用。
4. 测试三个调用的事件顺序和结果 ID 对应关系。

**验证：**

```powershell
uv run pytest tests/test_session.py -q -k "multiple_tools or tool_failure"
```

期望：所有工具串行执行，失败不打断同批次。

## T26：实现工具结果回灌与最终续答

**文件：** `src/dragon_code/session.py`、`tests/test_session.py`  
**依赖：** T25

**步骤：**

1. 构造用户消息、Assistant 工具调用消息和 tool 结果消息。
2. 使用同一工具定义发起一次续答。
3. 流式转发最终文字并在成功后统一提交完整历史。
4. 验证第二次 Provider 请求收到全部调用和结果。

**验证：**

```powershell
uv run pytest tests/test_session.py -q -k "followup or tool_history"
```

期望：最终文本来自第二次请求，历史顺序符合 Plan。

## T27：实现单轮上限

**文件：** `src/dragon_code/session.py`、`tests/test_session.py`  
**依赖：** T26

**步骤：**

1. 检测续答阶段再次返回工具调用。
2. 不执行这些调用，也不把它们写入历史。
3. 发送 `limit` 事件并保存本地 Assistant 结束文本。
4. 测试注册中心执行次数始终只有首轮一次。

**验证：**

```powershell
uv run pytest tests/test_session.py -q -k "limit"
```

期望：第二轮工具调用未执行，当前轮正常结束。

### 提交节点 C

完成 T23–T27 且会话测试通过后，提交“单轮工具闭环”这一组改动。

## T28：实现 TUI 工具展示格式

**文件：** `src/dragon_code/tui.py`、`tests/test_tui.py`  
**依赖：** T2

**步骤：**

1. 添加工具关键参数格式化函数。
2. 添加成功、失败和截断结果摘要函数。
3. 限制命令和摘要显示长度。
4. 测试六个工具的工具行以及成功、失败样式。

**验证：**

```powershell
uv run pytest tests/test_tui.py -q -k "tool_line or tool_summary"
```

期望：工具行格式稳定，摘要不包含完整长输出。

## T29：消费工具与上限事件

**文件：** `src/dragon_code/tui.py`、`tests/test_tui.py`  
**依赖：** T27、T28

**步骤：**

1. `_consume_turn()` 处理 `tool_call`、`tool_result` 和 `limit`。
2. 首个工具调用到达时，把已有前置文本写入 RichLog 并清空流式区。
3. 工具行和结果摘要写入 scrollback。
4. 完成或达到上限后恢复输入框与计时器。

**验证：**

```powershell
uv run pytest tests/test_tui.py -q -k "tool or limit or recover"
```

期望：工具记录可回看，结束后应用回到 IDLE。

## T30：连接默认注册中心与动态 Prompt

**文件：** `src/dragon_code/tui.py`、`tests/test_tui.py`  
**依赖：** T14、T15、T29

**步骤：**

1. 激活 Provider 时使用启动 cwd 创建默认注册中心。
2. 使用同一 cwd 构建 System Prompt。
3. 将 Provider、Conversation、Prompt 和 Registry 注入 ChatSession。
4. 测试单 Provider 和多 Provider 启动流程。

**验证：**

```powershell
uv run pytest tests/test_tui.py -q
```

期望：原有布局、输入、退出和错误恢复测试以及新增工具测试全部通过。

### 提交节点 D

完成 T28–T30 且 TUI 测试通过后，提交“工具调用终端展示”这一组改动。

## T31：运行跨模块回归测试

**文件：** 本章所有实现和测试文件  
**依赖：** T1–T30

**步骤：**

1. 运行完整 pytest。
2. 修复因统一消息和事件接口引起的 ch02 回归。
3. 确认配置、Provider 工厂、Banner 和退出行为保持不变。

**验证：**

```powershell
uv run pytest -q
```

期望：全部测试通过，无跳过的 ch03 核心测试。

## T32：运行格式与静态检查

**文件：** 本章所有 Python 文件  
**依赖：** T31

**步骤：**

1. 使用 Ruff 格式化本章改动。
2. 运行格式检查和 lint。
3. 重新运行完整测试，防止格式化造成意外改动。

**验证：**

```powershell
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
```

期望：三条命令全部以退出码 0 完成。

## T33：完成源码回顾与学习笔记

**文件：** `docs/learning-notes.md`  
**依赖：** T32

**步骤：**

1. 按文件回顾 Tool、Registry、ProviderEvent、TurnEvent 和 ChatSession 核心调用链。
2. 记录两种协议的工具请求与 ToolResult 方向。
3. 记录流式 JSON 拼接、结构化错误、路径保护和单轮上限。
4. 补充测试证据、踩坑和一段可用于秋招面试的表达。

**验证：**

```powershell
rg -n "ProviderEvent|TurnEvent|ToolRegistry|单轮上限|面试表达" docs/learning-notes.md
```

期望：五个主题均能在 ch03 笔记中找到。

### 提交节点 E

完成 T31–T33 后提交“ch03 回归验证与学习笔记”。进入 checklist 验收前确认工作区
只包含本章文件和用户原有的 `.idea/` 未跟踪目录。

## 执行顺序

```text
T1 → T2
T2 → T3 → T4
T2 → T5
T4 + T5 → T6 → T7 → T8
T4 + T5 → T9 → T10
T4 → T11 → T12
T4 + T6–T12 → T13 → T14

T2 → T15
T2 → T16 → T17 → T18 → T19
          └→ T20 → T21 → T22
T2 → T23
T14 + T16 + T23 → T24 → T25 → T26 → T27
T14 + T15 + T27 → T28 → T29 → T30
T1–T30 → T31 → T32 → T33
```

OpenAI 与 Anthropic 两组适配任务可以并行设计，但开发时仍按表中顺序逐项验证，便于
定位回归。
