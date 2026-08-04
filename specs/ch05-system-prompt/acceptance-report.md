# 系统提示工程化验收报告

## 结果

- 通过：51 / 52 项
- 未完全观测：1 项
- 自动化测试：115 passed，1 skipped
- Ruff 格式：通过
- Ruff lint：通过

## 自动化证据

```text
uv run pytest -q
115 passed, 1 skipped

uv run ruff format --check .
71 files already formatted

uv run ruff check .
All checks passed!

rg "build_agent_prompt" src tests
无匹配
```

跳过项是 Windows 当前权限不允许创建符号链接的既有文件工具边界测试，不是 ch05 失败。

## tmux 端到端证据

### 默认模式读取与总结

真实请求读取 `specs/ch05-system-prompt/spec.md`：

```text
● Read(specs/ch05-system-prompt/spec.md)
```

模型随后正确概括模块化提示、稳定缓存和 system-reminder 三项目标，界面没有显示内部提醒。

### 历史合法性

工具任务结束后继续询问上一轮文档标题，模型正常回答：

```text
系统提示工程化 Spec
```

没有出现消息结构相关 400。

### Plan Mode 与 /do

Plan Mode 中只观察到两个只读调用：

```text
● Glob(*e2e*)
● Glob(ch05*)
```

输入 `/do` 后恢复完整工具集并自动执行：

```text
● Write(ch05_e2e_temp.txt)
● Read(ch05_e2e_temp.txt)
```

文件内容验证为 `Dragon Code ch05 E2E OK`，随后已删除该临时文件。

### 默认模式多轮工具任务

真实执行：

```text
Read(spec.md) → Write(ch05_e2e_summary.txt) → 最终答复
```

摘要文件内容与 Spec 一致，验收后已删除临时文件。

### 取消与恢复

慢 Bash 执行中发送 Escape 对应控制码后：

```text
└─ 状态未知：已请求取消工具，但无法确认底层操作是否已经完成。
● 当前任务已取消。
```

随后继续提问，模型正常返回 `OK`，证明取消后的历史与界面状态可继续使用。

## 缓存证据

普通烟测时，前缀已被此前 TUI 请求缓存：

```text
第 1 次：缓存读取=1280
第 2 次：缓存读取=1280
```

使用新的固定 `--cache-tag` 后：

```text
第 1 次：输入=1358，缓存写入=0，缓存读取=0
第 2 次：输入=78，缓存写入=0，缓存读取=1280
```

这证明第二次请求复用了 1280 个稳定前缀 Token。当前 DeepSeek Anthropic 兼容端点没有返回
`cache_creation_input_tokens`，因此 checklist 中“真实观察缓存写入字段”一项保持未勾选；
缓存写入字段的解析逻辑已由 Anthropic 单元测试覆盖。

## 未完全观测

- [ ] 使用会返回 `cache_creation_input_tokens` 的官方 Anthropic 或完整兼容端点，观察首次请求的缓存写入 Token。

这是当前端点的可观测字段限制，不影响缓存读取、稳定前缀复用和缺字段降级行为。
