# 系统提示工程化 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|---|---|---|
| 修改 | `src/dragon_code/models.py` | 增加系统提示、统一请求和缓存用量字段 |
| 修改 | `src/dragon_code/prompt.py` | 模块化提示、环境采集、system-reminder |
| 修改 | `src/dragon_code/clients/base.py` | LLM Client 改为接收统一请求 |
| 修改 | `src/dragon_code/clients/anthropic.py` | system 内容块、显式缓存、提醒注入、缓存用量 |
| 修改 | `src/dragon_code/clients/openai.py` | 稳定 system 前缀、提醒注入、缓存用量 |
| 修改 | `src/dragon_code/agent.py` | 在 Agent Loop 中构造统一请求和按轮提醒 |
| 修改 | `src/dragon_code/tui.py` | 使用新的 Agent 构造参数 |
| 修改 | `src/dragon_code/tools/file_tools.py` | 强化 Edit 工具描述和参数说明 |
| 修改 | `src/dragon_code/tools/bash.py` | 强化 Bash 工具描述和参数说明 |
| 新建 | `scripts/cache_smoke.py` | 安全打印真实端点返回的四类 Token 用量 |
| 修改 | `tests/test_prompt.py` | 提示模块、环境、确定性和提醒节奏测试 |
| 修改 | `tests/test_agent.py` | 统一请求、多轮提醒、历史和 ch04 回归测试 |
| 修改 | `tests/test_client_anthropic.py` | Anthropic system、缓存、提醒和用量测试 |
| 修改 | `tests/test_client_openai.py` | OpenAI system、提醒和用量测试 |
| 修改 | `tests/test_file_tools.py` | Edit 描述强化测试 |
| 修改 | `tests/test_bash_tool.py` | Bash 描述强化测试 |
| 修改 | `tests/conftest.py` | 测试用 Fake LLM Client 适配统一请求 |
| 修改 | `tests/test_tui.py` | TUI 构造和 Fake Client 适配测试 |
| 按需修改 | `tests/test_stream_collector.py` | 验证缓存用量不会破坏流式收集 |

## T1：增加统一提示与请求数据模型

**文件：** `src/dragon_code/models.py`、`tests/test_stream_collector.py`
**依赖：** 无

**步骤：**

1. 增加不可变的 `SystemPrompt`，包含 `stable`、`environment`。
2. 增加 `LLMRequest`，包含消息副本、工具定义、系统提示和可选 reminder。
3. 为 `TokenUsage` 增加默认值为 `0` 的 `cache_write_tokens`、`cache_read_tokens`。
4. 扩展 `TokenUsage.add()`，同时累加缓存字段；保留输入/输出为 `None` 时的旧语义。
5. 增加用量累计测试，确认流式收集仍能保存完整用量。

**验证：** 运行 `uv run pytest tests/test_stream_collector.py -q`，期望全部通过，并能断言缓存读写量被保留。

## T2：实现提示模块与通用装配器

**文件：** `src/dragon_code/prompt.py`、`tests/test_prompt.py`
**依赖：** T1

**步骤：**

1. 定义不可变的 `PromptModule`。
2. 定义七个固定模块及其 `10～70` 优先级。
3. 定义三个可选模块位置及其 `80～100` 优先级。
4. 实现通用装配器：跳过空内容、稳定排序、模块间只保留一个空行。
5. 把原有全局行为规则迁移到对应固定模块中，不把环境和当前模式写入稳定内容。
6. 测试固定顺序、空可选模块和新增测试模块的挂载行为。

**验证：** 运行 `uv run pytest tests/test_prompt.py -q -k "module or assemble or optional"`，期望模块顺序和空模块行为全部通过。

## T3：实现环境信息渲染

**文件：** `src/dragon_code/prompt.py`、`tests/test_prompt.py`
**依赖：** T2

**步骤：**

1. 定义不可变的 `EnvironmentInfo`。
2. 实现环境文本渲染，包含工作目录、平台、日期、版本和模型。
3. Git 字段为空时自动省略对应行。
4. 确保渲染内容不读取 API Key、鉴权头或环境变量。
5. 测试字段齐全和 Git 字段缺失两种情况。

**验证：** 运行 `uv run pytest tests/test_prompt.py -q -k "environment and not git_command"`，期望环境文本字段正确且可降级。

## T4：实现异步 Git 环境采集

**文件：** `src/dragon_code/prompt.py`、`tests/test_prompt.py`
**依赖：** T3

**步骤：**

1. 使用异步子进程执行 Git 状态检查。
2. 为 Git 命令设置 2 秒超时，并在超时时清理子进程。
3. 只解析分支、是否有修改和修改数量，不记录文件名和 diff。
4. 非 Git 目录、Git 不可用、非零退出和超时时返回空 Git 信息。
5. 测试正常仓库、非 Git 目录和超时降级。

**验证：** 运行 `uv run pytest tests/test_prompt.py -q -k "git or gather_environment"`，期望成功与降级场景均通过且无挂起任务。

## T5：实现 system-reminder 与 Plan Mode 节奏

**文件：** `src/dragon_code/prompt.py`、`tests/test_prompt.py`
**依赖：** T2

**步骤：**

1. 实现统一的 `<system-reminder>` 包装函数。
2. 编写 Plan Mode 完整提醒和精简提醒。
3. 实现第 `1、6、11……` 轮完整、其他轮精简的选择逻辑。
4. 保留 `/do` 使用的执行提示，但不把 Plan Mode 内容再拼到稳定系统提示尾部。
5. 测试第 1、2、5、6、11 轮的提醒选择。

**验证：** 运行 `uv run pytest tests/test_prompt.py -q -k "reminder or plan"`，期望提醒均带标签且轮次节奏正确。

## T6：迁移 LLM Client 统一接口

**文件：** `src/dragon_code/clients/base.py`
**依赖：** T1

**步骤：**

1. 把 `LLMClient.stream()` 参数改为单个 `LLMRequest`。
2. 更新类型导入和中文说明。
3. 不改错误脱敏与异常分类逻辑。

**验证：** 运行 `uv run python -m py_compile src/dragon_code/models.py src/dragon_code/clients/base.py`，期望无语法或导入错误。

## T7：实现 Anthropic 的两个 system 内容块与缓存断点

**文件：** `src/dragon_code/clients/anthropic.py`、`tests/test_client_anthropic.py`
**依赖：** T1、T6

**步骤：**

1. 让 `_build_request()` 接收 `LLMRequest`。
2. 构造唯一的 `system` 字段，其值为两个文本内容块。
3. 在 `system[0]` 稳定提示块设置 `cache_control: {"type": "ephemeral"}`。
4. `system[1]` 放环境信息且不设置缓存标记。
5. 工具定义保持注册顺序，不在最后一个工具上重复设置缓存断点。
6. 更新测试收集助手并断言完整请求结构。

**验证：** 运行 `uv run pytest tests/test_client_anthropic.py -q -k "request or system or cache_control"`，期望 system 只有一个字段、内部恰有两个有序内容块。

## T8：实现 Anthropic reminder 临时注入与历史合法性

**文件：** `src/dragon_code/clients/anthropic.py`、`tests/test_client_anthropic.py`
**依赖：** T7

**步骤：**

1. 在 `_build_messages()` 生成的协议副本中注入 reminder。
2. 用户文本和 reminder 使用相互独立的文本内容块，不修改原始 `ChatMessage`。
3. 存在 `tool_result` 时，保证全部 `tool_result` 内容块排在 reminder 文本块之前。
4. 保证 reminder 不插入 assistant `tool_use` 与对应 user `tool_result` 之间。
5. 测试首轮用户请求、工具回灌续轮和无 reminder 三种场景。

**验证：** 运行 `uv run pytest tests/test_client_anthropic.py -q -k "reminder or tool_result"`，期望消息配对合法且原始历史不变。

## T9：解析 Anthropic 缓存用量

**文件：** `src/dragon_code/clients/anthropic.py`、`tests/test_client_anthropic.py`
**依赖：** T7

**步骤：**

1. 从 `message_start.usage` 读取缓存创建与缓存读取字段。
2. 写入统一的 `cache_write_tokens`、`cache_read_tokens`。
3. 字段缺失或为 `None` 时按 `0` 处理。
4. 保持现有输入、输出 Token 解析不变。

**验证：** 运行 `uv run pytest tests/test_client_anthropic.py -q -k "usage or cache"`，期望完整字段和缺失字段场景均通过。

## T10：实现 OpenAI 稳定前缀与 reminder 注入

**文件：** `src/dragon_code/clients/openai.py`、`tests/test_client_openai.py`
**依赖：** T1、T6

**步骤：**

1. 让 `stream()` 和请求构造使用 `LLMRequest`。
2. 用固定的两个换行符连接稳定提示和环境信息，形成请求开头的 system 消息。
3. 不发送任何 Anthropic 专属字段。
4. 把 reminder 作为临时带标签消息放在完整历史之后，不修改原始消息列表。
5. 保证 assistant tool call 与对应 tool 结果的顺序不被 reminder 打断。
6. 更新测试收集助手并断言请求结构和历史副本不变。

**验证：** 运行 `uv run pytest tests/test_client_openai.py -q -k "request or reminder or tool_history"`，期望稳定段始终在环境段之前，工具配对不变。

## T11：解析 OpenAI 缓存用量

**文件：** `src/dragon_code/clients/openai.py`、`tests/test_client_openai.py`
**依赖：** T10

**步骤：**

1. 从 `prompt_tokens_details.cached_tokens` 读取缓存命中量。
2. 设置 `cache_read_tokens`，并保持 `cache_write_tokens` 为 `0`。
3. 兼容对象字段和字段缺失两种响应。
4. 保持现有流关闭和错误恢复逻辑不变。

**验证：** 运行 `uv run pytest tests/test_client_openai.py -q -k "usage or cache or closes"`，期望缓存字段、缺失字段和流清理测试全部通过。

## T12：让 Agent 构造统一请求

**文件：** `src/dragon_code/agent.py`、`tests/conftest.py`、`tests/test_agent.py`
**依赖：** T1、T4、T5、T6

**步骤：**

1. Agent 构造参数改为接收注册中心、工作目录和应用版本，不再接收预先拼好的字符串系统提示。
2. 在每次 `run()` 开始时构造一次 `SystemPrompt`。
3. 每一轮从正式历史与当前工具集构造新的 `LLMRequest`。
4. 更新测试 Fake LLM Client，使其记录完整请求对象。
5. 更新现有 Agent 测试的创建方式，保持停止、错误、取消和工具执行断言不变。

**验证：** 运行 `uv run pytest tests/test_agent.py -q -k "not plan"`，期望默认模式下 ch04 的循环与错误行为继续通过。

## T13：接入 Agent 的 Plan reminder 与缓存用量累计

**文件：** `src/dragon_code/agent.py`、`tests/test_agent.py`
**依赖：** T9、T11、T12

**步骤：**

1. 默认模式将 `LLMRequest.reminder` 设为 `None`。
2. Plan Mode 根据当前迭代次数放入完整或精简 reminder。
3. 保持 Plan Mode 只导出 Read、Glob、Grep。
4. 断言多轮请求的稳定提示完全一致，reminder 随轮次变化。
5. 断言 reminder 不进入 `Conversation`，工具调用与结果仍配对。
6. 让任务用量和会话用量同时累加缓存读写字段。

**验证：** 运行 `uv run pytest tests/test_agent.py -q -k "plan or reminder or usage or history"`，期望注入节奏、历史和四类用量累计正确。

## T14：更新 TUI 与测试 Fake Client

**文件：** `src/dragon_code/tui.py`、`tests/test_tui.py`
**依赖：** T12、T13

**步骤：**

1. TUI 创建 Agent 时传入工作目录和 `__version__`。
2. 移除 TUI 对旧 `build_system_prompt(workdir)` 字符串接口的调用。
3. 更新 TUI 测试中的 Fake LLM Client，使其接收并记录 `LLMRequest`。
4. 保持 `/plan`、`/do`、`/help`、Token 状态栏和取消行为不变。
5. 不在 TUI 中新增缓存命中面板。

**验证：** 运行 `uv run pytest tests/test_tui.py -q`，期望现有 TUI 行为和新 Agent 构造方式全部通过。

## T15：强化工具描述

**文件：** `src/dragon_code/tools/file_tools.py`、`src/dragon_code/tools/bash.py`、`tests/test_file_tools.py`、`tests/test_bash_tool.py`
**依赖：** T2

**步骤：**

1. 在 Edit 工具描述中明确编辑前必须先 Read。
2. 保留并强化 `old_text` 必须唯一匹配的说明。
3. 在 Bash 描述中明确读取、文件查找和内容搜索优先使用 Read、Glob、Grep。
4. 在相关参数字段描述中补充必要限制。
5. 测试导出的工具定义同时包含这些关键规则。

**验证：** 运行 `uv run pytest tests/test_file_tools.py tests/test_bash_tool.py tests/test_tool_registry.py -q`，期望工具行为未改变且描述规则可观察。

## T16：增加缓存烟测脚本

**文件：** `scripts/cache_smoke.py`
**依赖：** T7～T14

**步骤：**

1. 加载现有 Dragon Code 配置并选择指定或第一项 provider 配置。
2. 使用与正式 Agent 相同的提示、工具定义和 LLM Client 请求路径连续发送两次简单请求。
3. 只打印输入、输出、缓存写入和缓存读取 Token，不打印请求正文和 API Key。
4. 端点不返回缓存字段时打印 `0` 和可读说明，不报错。
5. 提供简短命令行用法说明。

**验证：** 运行 `uv run python scripts/cache_smoke.py --help`，期望显示安全用法且不会加载或打印密钥。

## T17：完整回归与代码质量检查

**文件：** 本章所有修改文件
**依赖：** T1～T16

**步骤：**

1. 运行完整单元测试，修复所有回归。
2. 运行 Ruff 格式化检查和 lint。
3. 检查源码和测试中不存在旧的 `build_agent_prompt` 调用。
4. 检查环境、调试与错误输出不会包含 API Key。
5. 确认无悬空 asyncio task 或未关闭流。

**验证：** 依次运行：

```text
uv run pytest -q
uv run ruff format --check .
uv run ruff check .
rg "build_agent_prompt" src tests
```

期望全部测试与 Ruff 检查通过，最后一条搜索无结果。

## 执行顺序

```text
T1 → T2 → T3 → T4
 │    └────→ T5
 └────────→ T6

T6 → T7 → T8 → T9
 └──→ T10 → T11

T4 + T5 + T6 → T12 → T13 → T14
T2 → T15

T7～T15 → T16 → T17
```

其中 Anthropic、OpenAI 和工具描述在依赖完成后可以分开实施，但最终都必须经过 T17 的完整回归。
