# LLM Client 术语统一 Tasks

## 文件清单

| 操作 | 文件 | 职责 |
|---|---|---|
| 新建 | `src/dragon_code/clients/__init__.py` | 导出 LLM Client 公共接口 |
| 新建 | `src/dragon_code/clients/base.py` | `LLMClient`、`LLMError`、错误转换 |
| 新建 | `src/dragon_code/clients/anthropic.py` | Anthropic 协议客户端 |
| 新建 | `src/dragon_code/clients/openai.py` | OpenAI 协议客户端 |
| 新建 | `src/dragon_code/clients/factory.py` | LLM Client 工厂 |
| 删除 | `src/dragon_code/providers/` 下 5 个旧模块 | 移除旧抽象及旧导入路径 |
| 修改 | `src/dragon_code/models.py` | `ProviderEvent` 改为 `LLMEvent` |
| 修改 | `src/dragon_code/agent.py` | 改为依赖 `LLMClient` 与 `LLMError` |
| 修改 | `src/dragon_code/stream_collector.py` | 改为消费 `LLMEvent` |
| 修改 | `src/dragon_code/tui.py` | 客户端工厂、类型和内部变量改名 |
| 修改 | `tests/conftest.py`、`tests/test_agent.py`、`tests/test_stream_collector.py`、`tests/test_tui.py` | 更新公共测试夹具和引用 |
| 新建/删除 | `tests/test_client_*.py`、`tests/test_provider_*.py` | 迁移协议客户端与错误测试名称 |

## T1：建立 clients 基础模块

**文件：** `src/dragon_code/clients/base.py`、`src/dragon_code/clients/__init__.py`

**依赖：** 无

**步骤：**

1. 把公共基类改名为 `LLMClient`。
2. 把安全错误改名为 `LLMError`。
3. 把错误转换函数改名为 `make_llm_error`。
4. 更新中文注释与导出列表。

**验证：** 导入三个公共名称，确认无导入错误。

## T2：迁移两个协议客户端

**文件：** `src/dragon_code/clients/anthropic.py`、`src/dragon_code/clients/openai.py`

**依赖：** T1

**步骤：**

1. 复制现有协议适配逻辑到新模块。
2. 类名改为 `AnthropicClient` 和 `OpenAIClient`。
3. 改为继承 `LLMClient`，使用 `make_llm_error`。
4. 流式输出事件改为 `LLMEvent`，不改协议行为。

**验证：** 分别运行 Anthropic 和 OpenAI 客户端测试。

## T3：建立客户端工厂

**文件：** `src/dragon_code/clients/factory.py`

**依赖：** T2

**步骤：**

1. 定义 `create_llm_client(config)`。
2. 按协议返回相应客户端。
3. 保留针对 Provider 配置协议的可读错误。

**验证：** 工厂测试确认两种协议返回正确类型，非法协议仍报错。

## T4：迁移共享事件与收集器

**文件：** `src/dragon_code/models.py`、`src/dragon_code/stream_collector.py`

**依赖：** T1

**步骤：**

1. `ProviderEvent` 改为 `LLMEvent`。
2. StreamCollector 的输入类型和注释改用 LLM Client 术语。
3. 无完整响应时抛出 `LLMError`。

**验证：** 运行 `tests/test_stream_collector.py`。

## T5：迁移 Agent

**文件：** `src/dragon_code/agent.py`

**依赖：** T3、T4

**步骤：**

1. 构造参数和实例属性从 `provider` 改为 `client`。
2. 主循环调用 `self.client.stream()`。
3. 错误捕获改为 `LLMError`。

**验证：** 运行 `tests/test_agent.py`，确认多轮 Loop、取消和 Plan Mode 行为不变。

## T6：精准迁移 TUI

**文件：** `src/dragon_code/tui.py`

**依赖：** T3、T5

**步骤：**

1. 客户端工厂类型改为 `create_llm_client`。
2. 会话内部客户端属性改为 `client`。
3. 保留 `providers` 配置列表、Provider 选择文案和状态栏控件。
4. 不修改现有 `/help` 命令实现。

**验证：** 运行 `tests/test_tui.py`，确认选择、对话、错误恢复、命令和取消行为不变。

## T7：迁移测试命名与夹具

**文件：** `tests/` 中受影响文件

**依赖：** T2-T6

**步骤：**

1. `FakeProvider` 等模拟客户端改为 LLM Client 术语。
2. `ProviderEvent` 和 `ProviderError` 引用改为新名称。
3. 三个 `test_provider_*.py` 迁移为 `test_client_*.py`。
4. 测试局部变量使用 `client`；表示配置服务时继续使用 `provider`。

**验证：** 运行完整 `pytest`。

## T8：删除旧模块并扫描残留

**文件：** `src/dragon_code/providers/`、全项目 Python 文件

**依赖：** T7

**步骤：**

1. 删除旧 providers 代码目录。
2. 搜索旧类名、事件名、错误名、工厂名和旧导入路径。
3. 仅允许服务配置语境继续出现 Provider。

**验证：** 使用 `rg` 搜索旧代码术语，期望无命中。

## T9：质量检查与端到端验收

**文件：** 全项目、`checklist.md`

**依赖：** T8

**步骤：**

1. 运行格式、lint 和完整测试。
2. 在 tmux 中启动 Dragon Code。
3. 输入普通对话和真实工具任务。
4. 对照 checklist 记录实际证据。

**验证：** 所有必选 checklist 条目通过；如受外部 API 条件限制，明确记录实际阻塞证据。

## 执行顺序

```text
T1 → T2 → T3
 │         │
 └→ T4 ───┴→ T5 → T6 → T7 → T8 → T9
```

## 自检

- plan.md 中每个模块都有实现任务。
- 每个任务都包含具体验证方式。
- 依赖链无循环。
- 没有任务涉及 ch05 功能或改写 `/help`。
