# Dragon Code 多协议 LLM 终端对话客户端 Tasks

> 每个任务是一个聚焦的工作单元。实现代码使用直接、易读的写法，并为关键流程添加中文注释。

## 文件清单

| 操作 | 文件 | 职责 |
|---|---|---|
| 新建 | `pyproject.toml` | 项目元数据、依赖、脚本和工具配置 |
| 新建 | `uv.lock` | 锁定依赖版本 |
| 新建 | `.gitignore` | 忽略密钥、虚拟环境和缓存 |
| 新建 | `README.md` | 安装、配置和运行说明 |
| 新建 | `.dragon-code/config.yaml.example` | Provider 配置示例 |
| 新建 | `src/dragon_code/__init__.py` | 包信息和版本 |
| 新建 | `src/dragon_code/__main__.py` | `python -m dragon_code` 入口 |
| 新建 | `src/dragon_code/cli.py` | 配置加载和 TUI 启动 |
| 新建 | `src/dragon_code/config.py` | YAML 加载、校验和 `ConfigError` |
| 新建 | `src/dragon_code/models.py` | 共享数据类 |
| 新建 | `src/dragon_code/prompt.py` | System Prompt 和 Banner |
| 新建 | `src/dragon_code/session.py` | Conversation 和 ChatSession |
| 新建 | `src/dragon_code/tui.py` | Textual 界面和交互 |
| 新建 | `src/dragon_code/dragon_code.tcss` | TUI 布局和样式 |
| 新建 | `src/dragon_code/providers/__init__.py` | Provider 包导出 |
| 新建 | `src/dragon_code/providers/base.py` | Provider 基类和公开错误 |
| 新建 | `src/dragon_code/providers/factory.py` | Provider 工厂 |
| 新建 | `src/dragon_code/providers/anthropic.py` | Anthropic 适配器 |
| 新建 | `src/dragon_code/providers/openai.py` | OpenAI 适配器 |
| 新建 | `tests/conftest.py` | 共享测试夹具和假 Provider |
| 新建 | `tests/test_config.py` | 配置测试 |
| 新建 | `tests/test_session.py` | 会话与单轮协调测试 |
| 新建 | `tests/test_provider_anthropic.py` | Anthropic 适配器测试 |
| 新建 | `tests/test_provider_openai.py` | OpenAI 适配器测试 |
| 新建 | `tests/test_provider_errors.py` | 错误分类和脱敏测试 |
| 新建 | `tests/test_tui.py` | Textual Pilot 界面测试 |

## T1：初始化项目元数据和入口骨架

**文件：** `pyproject.toml`、`src/dragon_code/__init__.py`、`src/dragon_code/__main__.py`

**依赖：** 无

**步骤：**

1. 在 `pyproject.toml` 声明 Python 3.12+、运行依赖和开发依赖。
2. 配置 `dragon-code = "dragon_code.cli:main"` 脚本入口。
3. 配置 Ruff 和 pytest 的源码路径。
4. 在 `__init__.py` 定义版本号。
5. 在 `__main__.py` 转调 `cli.main()`。
6. 使用 uv 创建环境并生成 `uv.lock`。

**验证：** 运行 `uv sync`，期望依赖安装成功且生成 `uv.lock`。

## T2：定义共享数据模型

**文件：** `src/dragon_code/models.py`

**依赖：** T1

**步骤：**

1. 定义 `ProviderConfig`，使用 `field(repr=False)` 隐藏 API Key。
2. 定义 `AppConfig`、`ChatMessage` 和 `TurnEvent`。
3. 为每个类添加简短中文 docstring。
4. 保持字段为简单的字符串、布尔值和列表，不增加高级类型抽象。

**验证：** 运行一段导入命令创建四种对象；打印 `ProviderConfig` 时不得出现 API Key。

## T3：实现配置加载和校验

**文件：** `src/dragon_code/config.py`

**依赖：** T2

**步骤：**

1. 定义 `ConfigError`。
2. 读取指定 YAML 文件并捕获文件不存在、不可读和 YAML 语法错误。
3. 校验根节点、providers 非空列表和每个 Provider 的结构。
4. 校验 `name`、`protocol`、`api_key`、`model` 非空。
5. 限定 `protocol` 为 `anthropic` 或 `openai`。
6. 校验 `base_url` 和 `thinking` 的可选类型。
7. 返回 `AppConfig`，错误信息指出具体条目和字段。

**验证：** 使用临时合法配置调用 `load_config()`，期望得到字段正确的 `AppConfig`。

## T4：补齐配置自动测试

**文件：** `tests/test_config.py`

**依赖：** T3

**步骤：**

1. 测试单 Provider 和多 Provider 的合法配置。
2. 测试文件不存在与 YAML 语法错误。
3. 测试 providers 为空、字段缺失、字段为空和非法 protocol。
4. 测试 `thinking` 类型错误。
5. 验证错误信息可读且包含字段位置。
6. 验证配置对象的字符串表示不含密钥。

**验证：** 运行 `uv run pytest tests/test_config.py -q`，期望全部通过。

## T5：添加配置示例和 Git 忽略规则

**文件：** `.dragon-code/config.yaml.example`、`.gitignore`

**依赖：** T3

**步骤：**

1. 添加 Anthropic 配置示例。
2. 添加 OpenAI 和自定义 `base_url` 配置示例。
3. 注释说明 `thinking` 在 OpenAI Chat Completions 下不生效。
4. 忽略 `.dragon-code/config.yaml`、`.venv`、缓存、测试缓存和常见密钥文件。

**验证：** 复制示例到真实配置路径后运行配置加载；运行 `git status --ignored`，确认真实配置被忽略。

## T6：实现 System Prompt 和 Banner

**文件：** `src/dragon_code/prompt.py`

**依赖：** T1

**步骤：**

1. 定义简洁的内置 `SYSTEM_PROMPT`。
2. 定义 ASCII 猫咪图案。
3. 实现 `render_banner(version, cwd)`。
4. 输出必须包含 Dragon Code、版本、工作目录和就绪提示。

**验证：** 调用 `render_banner("0.1.0", "/tmp/demo")`，观察四项信息均存在。

## T7：实现 Provider 基类和安全错误

**文件：** `src/dragon_code/providers/base.py`、`src/dragon_code/providers/__init__.py`

**依赖：** T2

**步骤：**

1. 实现保存配置的 `BaseProvider`。
2. 提供 `name` 和 `model` 属性。
3. 定义 `ProviderError`，包含分类、公开信息和是否可重试。
4. 实现 SDK 异常转公开错误的辅助函数。
5. 对可能包含密钥的异常文本做替换或改写，不原样展示未知异常详情。
6. 保持 `CancelledError` 不被普通异常处理吞掉。

**验证：** 创建 ProviderError 并打印，期望只显示公开信息。

## T8：测试 Provider 错误分类和脱敏

**文件：** `tests/test_provider_errors.py`

**依赖：** T7

**步骤：**

1. 覆盖鉴权、限流、网络、模型不存在、参数错误和未知错误。
2. 验证每类错误的 `category` 与 `retryable`。
3. 构造包含测试密钥的异常，确认公开错误中没有该密钥。
4. 验证未知错误不输出完整异常堆栈或请求信息。

**验证：** 运行 `uv run pytest tests/test_provider_errors.py -q`，期望全部通过。

## T9：实现 Anthropic 请求构造

**文件：** `src/dragon_code/providers/anthropic.py`

**依赖：** T6、T7

**步骤：**

1. 在构造函数中创建 `AsyncAnthropic`，传入密钥和可选 `base_url`。
2. 将统一消息转换为 Anthropic Messages 格式。
3. 注入模型名、System Prompt 和输出上限。
4. 当 `thinking` 为真时加入扩展思考参数，并保证预算小于输出上限。
5. 为关键参数转换添加中文注释。

**验证：** 使用假客户端捕获请求参数，确认消息、System Prompt、模型和 thinking 设置正确。

## T10：实现 Anthropic 流式解析并测试

**文件：** `src/dragon_code/providers/anthropic.py`、`tests/test_provider_anthropic.py`

**依赖：** T9

**步骤：**

1. 使用异步流上下文读取 Anthropic 事件。
2. 只产出正文文本事件。
3. 忽略 thinking 事件和无关生命周期事件。
4. 将 SDK 异常转换为 `ProviderError`。
5. 用假事件流验证多个正文分片按顺序产出。
6. 验证 thinking 内容不会出现在输出中。
7. 验证自定义 `base_url` 和错误路径。

**验证：** 运行 `uv run pytest tests/test_provider_anthropic.py -q`，期望全部通过。

## T11：实现 OpenAI 请求与流式解析

**文件：** `src/dragon_code/providers/openai.py`

**依赖：** T6、T7

**步骤：**

1. 在构造函数中创建 `AsyncOpenAI`，传入密钥和可选 `base_url`。
2. 把 System Prompt 放到消息列表首项。
3. 将历史消息转换为 Chat Completions 格式。
4. 使用异步 Chat Completions 流。
5. 只产出非空正文增量。
6. 不传递 Anthropic 风格的 thinking 参数。
7. 将 SDK 异常转换为 `ProviderError`。

**验证：** 使用假客户端消费多个分片，期望按顺序得到正文。

## T12：补齐 OpenAI 适配器测试

**文件：** `tests/test_provider_openai.py`

**依赖：** T11

**步骤：**

1. 验证 System Prompt 位于消息列表首项。
2. 验证完整历史按顺序发送。
3. 验证空增量被忽略、正文增量被保留。
4. 验证 `thinking=True` 时请求中仍不出现 thinking 参数。
5. 验证自定义 `base_url`。
6. 验证 SDK 错误转换为 `ProviderError`。

**验证：** 运行 `uv run pytest tests/test_provider_openai.py -q`，期望全部通过。

## T13：实现 Provider 工厂

**文件：** `src/dragon_code/providers/factory.py`、`src/dragon_code/providers/__init__.py`

**依赖：** T10、T12

**步骤：**

1. 根据 `protocol` 创建 `AnthropicProvider` 或 `OpenAIProvider`。
2. 未知协议返回清晰的 `ValueError`。
3. 从 providers 包导出上层真正需要的类和工厂函数。
4. 在现有 Provider 测试中增加工厂分派断言。

**验证：** 分别传入两种配置，确认返回正确适配器；传入非法协议时得到可读错误。

## T14：实现 Conversation

**文件：** `src/dragon_code/session.py`

**依赖：** T2

**步骤：**

1. 初始化空消息列表。
2. `get_messages()` 返回列表副本。
3. `build_request_messages()` 返回历史加当前用户输入，但不修改内部历史。
4. `commit_turn()` 按 user、assistant 顺序追加成功轮次。
5. 添加中文注释说明“先请求成功，再提交历史”的原因。

**验证：** 构造两轮消息，确认顺序正确且修改返回副本不会影响内部历史。

## T15：实现 ChatSession 单轮协调

**文件：** `src/dragon_code/session.py`

**依赖：** T7、T14

**步骤：**

1. 保存 Provider、Conversation 和 System Prompt。
2. 调用 `build_request_messages()` 生成请求上下文。
3. 逐个接收 Provider 正文增量，累计完整回复并产生 `text` 事件。
4. 流正常结束后提交历史并产生 `completed` 事件。
5. 捕获 `ProviderError` 并产生 `error` 事件。
6. 错误时不提交会话历史。
7. 保持取消异常继续向上抛出。

**验证：** 使用假 Provider 跑一次成功和一次失败，观察事件顺序和历史变化。

## T16：补齐会话和协调器测试

**文件：** `tests/conftest.py`、`tests/test_session.py`

**依赖：** T15

**步骤：**

1. 在 conftest 中提供成功、失败和慢速假 Provider。
2. 测试 Conversation 返回副本。
3. 测试成功事件顺序为多个 `text` 后一个 `completed`。
4. 测试成功后历史包含完整 user/assistant 消息。
5. 测试失败时产生 `error`，历史保持不变。
6. 测试第二轮请求携带第一轮完整历史。

**验证：** 运行 `uv run pytest tests/test_session.py -q`，期望全部通过。

## T17：搭建 TUI 静态布局

**文件：** `src/dragon_code/tui.py`、`src/dragon_code/dragon_code.tcss`

**依赖：** T5、T6、T13、T15

**步骤：**

1. 定义 `SessionState` 和 `DragonCodeApp`。
2. 组成 Banner、就绪提示、对话区、动态流式区、输入框和状态栏。
3. 将 Banner 放在 TUI 内，而不是启动前打印。
4. 用 TCSS 设置边框、滚动、宽度和状态栏对齐。
5. 单 Provider 时创建 Provider 和 ChatSession。
6. 状态栏显示 Provider 名称与模型。

**验证：** 使用单 Provider 假配置运行 Textual Pilot，确认所有布局节点存在且状态为 IDLE。

## T18：实现多 Provider 选择

**文件：** `src/dragon_code/tui.py`

**依赖：** T17

**步骤：**

1. 定义 `ProviderSelectScreen`。
2. 用 `OptionList` 展示每个 Provider 的名称和模型。
3. 支持方向键移动和 Enter 选定。
4. 选定后创建对应 ChatSession，关闭选择界面。
5. 更新状态栏并进入 IDLE。

**验证：** Pilot 启动双 Provider 配置，选择第二项后确认名称和模型正确。

## T19：实现多行输入和提交规则

**文件：** `src/dragon_code/tui.py`

**依赖：** T17

**步骤：**

1. 定义 `MessageInput`，在代码旁用中文注释解释按键规则。
2. Enter 发送自定义提交消息。
3. Alt+Enter 在当前光标位置插入换行。
4. 空白输入不提交。
5. 提交后清空输入框。
6. STREAMING 状态忽略新的提交。

**验证：** Pilot 模拟 Alt+Enter 和 Enter，确认多行内容正确且只提交一次。

## T20：接入异步流式 Worker

**文件：** `src/dragon_code/tui.py`

**依赖：** T19

**步骤：**

1. 提交时把用户输入写入对话区。
2. 记录本轮开始时间并切换到 STREAMING。
3. 用 Textual Worker 消费 `ChatSession.stream_turn()`。
4. 收到 `text` 事件时累计文本并更新动态纯文本区域。
5. Worker 运行期间禁止重复提交，但不阻塞主界面。

**验证：** 使用慢速假 Provider，确认文本分片逐步出现且计时区域仍可刷新。

## T21：实现计时和 Markdown 定型

**文件：** `src/dragon_code/tui.py`

**依赖：** T20

**步骤：**

1. 使用单调时钟记录开始时间。
2. 使用 Textual Timer 定期刷新 `Imagining… (Ns)`。
3. 首个文本到达前和流式期间都保持计时。
4. 收到 `completed` 后停止定时器。
5. 清空动态区，把完整回复用 Rich Markdown 写入历史区。
6. 显示本轮总耗时并恢复 IDLE。

**验证：** 假 Provider 延迟返回，确认开始前有计时、结束后有总耗时和 Markdown。

## T22：实现错误恢复和安全退出

**文件：** `src/dragon_code/tui.py`

**依赖：** T20、T21

**步骤：**

1. 收到 `error` 事件时显示红色公开错误。
2. 停止计时、清空动态区并恢复 IDLE。
3. 保持输入框可继续下一轮。
4. IDLE 状态识别 `/exit`。
5. 配置高优先级 Ctrl+C 退出动作。
6. 退出时停止 Timer 并取消活动 Worker。

**验证：** 假 Provider 首次失败、第二次成功；确认应用未退出且第二轮可用。分别验证 `/exit` 和 Ctrl+C。

## T23：测试 TUI 布局、选择和输入

**文件：** `tests/test_tui.py`

**依赖：** T18、T19

**步骤：**

1. 测试单 Provider 直接进入 IDLE。
2. 测试 Banner、工作目录、就绪提示、输入框和状态栏。
3. 测试多 Provider 选择第二项。
4. 测试 Enter 提交和 Alt+Enter 换行。
5. 测试流式期间拒绝重复提交。

**验证：** 运行 `uv run pytest tests/test_tui.py -q`，期望本组测试通过。

## T24：测试 TUI 流式、错误和退出

**文件：** `tests/test_tui.py`

**依赖：** T21、T22、T23

**步骤：**

1. 测试分片按顺序显示。
2. 测试完成后 Markdown 写入历史区。
3. 测试计时提示和总耗时。
4. 测试错误样式与错误后恢复输入。
5. 测试 `/exit` 和 Ctrl+C。
6. 测试窄终端尺寸下主要 Widget 仍可见。

**验证：** 运行 `uv run pytest tests/test_tui.py -q`，期望全部通过。

## T25：实现 CLI 装配

**文件：** `src/dragon_code/cli.py`

**依赖：** T3、T22

**步骤：**

1. 从固定路径 `.dragon-code/config.yaml` 加载配置。
2. 捕获 `ConfigError`，只打印可读信息并返回非零退出码。
3. 配置合法时启动 `DragonCodeApp`。
4. 不打印 AppConfig、ProviderConfig 或 API Key。
5. 确保 `dragon-code` 和 `python -m dragon_code` 使用同一入口。

**验证：** 缺少配置时运行入口，确认有简洁错误和非零退出码；放入合法配置后确认进入 TUI。

## T26：编写使用说明

**文件：** `README.md`

**依赖：** T5、T25

**步骤：**

1. 说明 Dragon Code 当前 ch02 能力与本章边界。
2. 说明 Python、uv、WSL/Linux 和 tmux 前置条件。
3. 说明复制配置示例、填写 Provider 和运行程序的步骤。
4. 说明 Enter、Alt+Enter、`/exit` 和 Ctrl+C。
5. 提醒真实配置与 API Key 不得提交。

**验证：** 按 README 从空环境步骤执行到程序启动，命令与路径均正确。

## T27：运行完整自动质量门禁

**文件：** 全部实现与测试文件

**依赖：** T1–T26

**步骤：**

1. 运行 Ruff 格式检查。
2. 运行 Ruff 静态检查。
3. 运行完整 pytest。
4. 运行 `python -m dragon_code` 启动冒烟测试。
5. 检查 Git 状态，确认真实配置和密钥未被跟踪。

**验证：**

```text
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
```

三条命令均返回退出码 0；启动冒烟测试进入 TUI。

## 执行顺序

```text
T1
├─ T2 ─ T3 ─ T4 ─ T5
├─ T6
└─ T7 ─ T8

T6 + T7 ─ T9 ─ T10
T6 + T7 ─ T11 ─ T12
T10 + T12 ─ T13

T2 ─ T14
T7 + T14 ─ T15 ─ T16

T5 + T6 + T13 + T15 ─ T17
T17 ─┬─ T18
     └─ T19 ─ T20 ─ T21 ─ T22

T18 + T19 ─ T23
T21 + T22 + T23 ─ T24
T3 + T22 ─ T25 ─ T26

T1–T26 ─ T27
```

## 自检结果

- Plan 中每个模块至少对应一个实现任务。
- 每个任务都有具体文件、依赖、步骤和验证方式。
- 依赖链无循环，可按所列顺序执行。
- 接口名称与 `plan.md` 保持一致。
- 自动测试不调用真实 API。
- tmux 真实对话验收留在 `checklist.md` 阶段执行。
