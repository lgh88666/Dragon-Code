# ch08：上下文管理验收报告

## 结论

ch08 两层上下文管理已完成实现，并通过自动化、真实 DeepSeek 与 WSL tmux 端到端验收。

- 轻量预防：单条工具结果超过50000 UTF-8字节时完整落盘；同轮剩余结果合计超过200000字节时稳定选择最少结果落盘。
- 重量兜底：普通请求接近窗口时使用专用摘要模型生成九部分结构化摘要，保留近期原文并继续当前任务。
- 手动控制：`/compact` 可在低Token历史执行；自动摘要连续失败3次后熔断，手动路径仍可用。
- 恢复闭环：Read 支持 `offset`/`limit` 行分页，真实主模型能按段重读落盘结果尾部。
- 安全：真实配置、API Key、Header和会话结果均未进入Git候选文件。

## 自动化证据

执行日期：2026-08-08；环境：Windows、Python 3.13.12、uv 0.12.2；项目与虚拟环境位于 L 盘。

| 命令 | 实际结果 |
|---|---|
| `uv sync --locked` | Resolved 57 packages；Checked 57 packages |
| `uv run ruff format --check . --exclude .pytest_tmp` | 121 files already formatted |
| `uv run ruff check . --exclude .pytest_tmp` | All checks passed |
| `uv run python -m compileall -q src tests` | 退出码0 |
| `uv run pytest -q --basetemp .pytest_tmp_ch08` | 304 passed, 2 skipped in 15.84s |
| `git diff --check` | 退出码0；只有Git的LF/CRLF提示，无空白错误 |
| 配置示例解析 | Anthropic 200000、OpenAI 128000；两个 `summary_model` 字段成功加载 |
| `git check-ignore` | `.dragon-code/sessions/`命中忽略规则；配置示例未被忽略 |
| 敏感模式扫描 | 未发现32位十六进制 `sk-` Key或长 `github_pat_` Token |

主要自动化覆盖：

- 配置默认值、非法值、双Client构造和旧配置兼容。
- Windows路径安全、会话ID、稳定文件名、原子落盘、UTF-8边界和失败重试。
- 49999/50000/50001字节边界、五个45000字节聚合、稳定排序和冻结账本。
- Read/Bash/Glob/Grep/MCP完整结果，以及Read分页重读。
- 完整请求字符估算、usage锚点替换、Assistant去重、工具结果增量和压缩后失效。
- 摘要请求无工具、九部分Prompt、标签解析、近期原文双下界和工具调用配对。
- 自动压缩成功/失败、当前用户原文、三次熔断、手动绕过和取消传播。
- Agent权限、调度、Plan Mode、TUI命令、帮助、状态文案和输入恢复回归。

## 真实 DeepSeek 验收

本机未安装WSL，因此没有伪造tmux证据；使用Windows进程中的真实 Dragon Code 核心链路执行等价验收。真实配置只读取非敏感字段，报告不记录API Key。

实际输出：

```text
main_model=deepseek-v4-pro
summary_model=deepseek-v4-flash
offloaded=true
saved_bytes=121911
saved_under_l_drive=true
reread_tool_called=true
reread_tail_confirmed=true
auto_before=20335
auto_after=20570
pending_preserved=true
main_continued=true
manual_compact=true
manual_before=39
manual_after=206
```

对应结论：

1. 121911字节多行结果完整保存到 `L:\Python_projects\Dragon-Code\.dragon-code\sessions\...\tool-results\`。
2. `deepseek-v4-pro` 主模型主动调用 Read，并使用 `offset=2950`、`limit=100` 读取尾部，正确回答 `tail-marker-dragon`。
3. 自动摘要实际使用 `deepseek-v4-flash`，请求工具列表为空；当前待发送用户消息逐字保留。
4. 自动摘要完成后，主模型继续并返回 `e2e-main-ok`。
5. 只有39个估算Token的短历史仍执行手动摘要。
6. 连续三次失败熔断与手动绕过使用可控fake验证，未伪装成真实端点故障。
7. 验收结束后未发现Dragon Code残留进程；121911和60011字节两次验收文件仍保留在L盘会话目录。

本次自动触发场景用超大工具定义制造窗口压力，历史本身很短，因此摘要后估算由20335变为20570，并不代表长历史压缩率。该场景验证的是触发、模型选择、消息保真和继续执行；近期原文裁剪与实际缩短由确定性单元测试覆盖。

## WSL tmux 补充验收

执行日期：2026-08-10；环境：WSL Ubuntu、tmux 3.6、Linux Python 3.14.4、真实 `deepseek-v4-pro`。WSL 使用 `/tmp` 中的独立运行依赖读取同一份源码和本地配置，没有把 API Key 写入命令、报告或 Git。

实际观察：

```text
tmux_session=dragon-ch08
main_model=deepseek-v4-pro
permission=allow_once
source_lines=6000
source_last_line=DRAGON_5999
offloaded=true
saved_bytes=113999
saved_lines=6000
saved_path=.dragon-code/sessions/1786348387-74e526f1/tool-results/tool-call_00_YdOLSLLOjro8W5o6Daif0531-0adf94b399df.txt
reread_offset=5995
reread_limit=6
reread_last_line=DRAGON_5999
manual_compact_before=2569
manual_compact_after=3222
post_compact_context_preserved=true
dragon_process_after_exit=0
session_result_after_exit=true
```

对应结论：

1. 在 tmux 中启动真实 Dragon Code，TUI 正常显示 Dragon Banner、模型、Token 和权限确认界面。
2. Bash 调用只选择“允许本次”，随后 Read 完整读取 6000 行文件；113999 字节结果被统一落盘，TUI 只显示预览、原始字节数、行数和保存路径。
3. 真实模型读取预览后主动调用 Read，参数为 `offset=5995`、`limit=6`，从落盘结果恢复尾部并回答 `DRAGON_5999`。
4. 在同一会话执行 `/compact`，TUI 显示 `上下文压缩完成：2569 → 3222 Token`。该短历史场景因九部分摘要开销而变大，符合“手动压缩不受阈值限制”的设计；随后模型仍能回答保存路径和最后一行，证明会话可继续。
5. `/exit` 后 tmux pane 回到 Bash，没有残留 `python3 -m dragon_code` 进程；会话目录及113999字节结果仍存在。验收生成的项目根目录临时输入文件已删除。

自动摘要模型选择、自动压缩后继续主任务由上面的真实 DeepSeek 核心链路证据覆盖；三次失败熔断与手动绕过继续由可控自动化测试覆盖，没有伪装成 tmux 人工场景。

## 设计调整记录

- 审批文档原聚合示例“三个80000字节只落盘一个”与单条超过50000字节规则冲突。用户选择A后，统一改为“五个45000字节只落盘一个”。
- 真实验收发现整体重读大结果会再次触发落盘。为完成“可恢复”目标，Read 增加向后兼容的 `offset`/`limit` 行分页，Spec、Plan、Task和Checklist已同步。
- 2026-08-08 的原验收机器没有WSL/tmux，因此当时明确记录为Windows等价链路；2026-08-10 已在另一台机器补齐真实 WSL tmux 证据。

## 明确未实现

保持Spec批准边界：不包含精确tokenizer、`prompt_too_long`紧急重试、摘要输入分组丢弃重试、跨进程Conversation恢复、会话目录自动清理和ch10通用命令注册表。
