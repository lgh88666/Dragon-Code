# LLM Client 术语统一 Checklist

> 每项通过运行代码或观察行为验证。

## 实现完整性

- [x] 内部公共抽象可通过 `LLMClient`、`LLMError`、`LLMEvent` 和 `create_llm_client` 使用。（验证：运行导入命令，无异常）
- [x] Anthropic 配置创建 `AnthropicClient`，OpenAI 配置创建 `OpenAIClient`。（验证：运行客户端工厂测试）
- [x] Agent 和 StreamCollector 只依赖 LLM Client 术语。（验证：搜索源码并运行对应单元测试）
- [x] 旧类名、旧事件名、旧错误名、旧工厂名和 `dragon_code.providers` 导入均已移除。（验证：`rg` 搜索无命中）
- [x] 不提供旧名称兼容别名。（验证：旧 `dragon_code.providers.base` 导入失败）

## 配置与界面边界

- [x] 原有 YAML `providers:` 与 `ProviderConfig` 无需修改即可加载。（验证：配置测试通过，真实配置正常启动）
- [x] 多 Provider 选择界面的名称、模型和状态栏显示保持不变。（验证：TUI 选择测试通过，实际状态栏显示 DeepSeek V4 Pro）
- [x] `/help` 等现有命令行为没有被本次改名破坏。（验证：TUI 测试通过，tmux 实际显示帮助内容）

## 行为回归

- [x] Anthropic 流式正文、工具调用、Token 用量与错误转换测试通过。（验证：Anthropic 客户端测试通过）
- [x] OpenAI 流式正文、工具调用、Token 用量与错误转换测试通过。（验证：OpenAI 客户端测试通过）
- [x] Agent 多轮工具调用、取消、上限和 Plan Mode 测试通过。（验证：Agent 测试通过）
- [x] TUI 对话、错误恢复、滚动和命令测试通过。（验证：19 项 TUI 测试通过）

## 编译与测试

- [x] `pytest` 全部通过。（验证：101 passed，1 skipped）
- [x] `ruff check .` 无告警。（验证：All checks passed）
- [x] `ruff format --check .` 通过。（验证：66 files already formatted）
- [x] 输出和错误中不出现 API Key。（验证：测试及 tmux 输出均未显示密钥）

## 端到端场景

- [x] 场景一：在 tmux 中启动 Dragon Code，输入普通问题，能收到流式最终回复。（结果：回复“LLM Client 改名测试通过”）
- [x] 场景二：输入需要读取项目文件的真实请求，Agent 正确调用工具并生成最终答复。（结果：显示 `● Read(specs/llm-client-terminology/spec.md)` 并回答正确标题）
- [x] 场景三：输入 `/help`，原有帮助内容仍正常显示。（结果：命令、快捷键和工具列表正常显示）

## 范围检查

- [x] 本次没有引入 Prompt 缓存、system-reminder 或其他 ch05 功能。（验证：变更 diff 仅包含术语迁移和文档）
- [x] 本次没有修改 `ProviderConfig`、YAML 字段和 Provider 选择文案的语义。（验证：源码搜索及实际启动确认）
- [x] 用户已有的 README、IDE 文件、321.txt 与无关 TUI 改动未被覆盖。（验证：git status 仍保留这些原有改动）

## 验收记录

- 日期：2026-08-04
- 单元与集成测试：`101 passed, 1 skipped`
- TUI 测试：`19 passed`
- lint：`ruff check .` 通过
- 格式：`ruff format --check .` 通过
- tmux：普通对话、Read 工具调用、`/help`、`/exit` 均通过，会话已正常关闭
