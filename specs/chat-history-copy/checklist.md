# 聊天历史选择与复制 Checklist

> 每项均通过运行或观察验证；开发完成后记录实际证据。

## 实现完整性

- [x] 聊天历史保留鼠标选择能力。（验证：选择用户消息、助手回复、代码和工具行。）
- [x] 有非空选择时，`Ctrl+C` 复制所选文字且应用继续运行。（验证：自动化测试剪贴板值
  和运行状态。）
- [x] 复制后不显示通知、不追加聊天记录。（验证：对比复制前后历史行数。）
- [x] 无选择时，`Ctrl+C` 安全退出。（验证：自动化测试和 tmux 实测。）
- [x] 复制后仍可输入并继续使用。（验证：复制后提交下一条消息。）

## 集成

- [x] `Ctrl+C` 绑定指向复制/退出分流动作。（验证：检查应用绑定并触发两个分支。）
- [x] 流式、Markdown、工具行与错误行展示未受影响。（验证：现有 TUI 和 session 测试。）
- [x] 剪贴板只包含用户实际选择的文本。（验证：精确比较选择值。）

## 编译与测试

- [x] `uv run pytest tests/test_tui.py -q` 通过。
- [x] `uv run pytest -q` 通过。
- [x] `uv run ruff check .` 通过。
- [x] `uv run ruff format --check .` 通过。
- [x] `uv run python -m compileall -q src tests` 通过。

## 端到端场景

- [x] 场景 1：Windows 测试环境选择历史文字 → `Ctrl+C` → 剪贴板完全一致 → 应用继续
  运行。
- [x] 场景 2：复制后继续输入一轮对话 → 正常回复，历史区没有复制通知。
- [x] 场景 3：WSL + tmux 启动 Dragon Code → 无选择按 `Ctrl+C` → 安全退出且终端正常。
- [x] 场景 4：检查 tmux/Windows Terminal 的 OSC 52 支持 → 不修改用户全局配置并记录
  实际结果。

## 源码回顾

- [x] 学习笔记说明 Screen 选择、OSC 52、条件分流及跨终端边界。

## 验收报告

### 通过（18/18）

- TUI 定向测试：`12 passed in 2.42s`。
- 完整测试：`70 passed, 1 skipped in 4.32s`；跳过项为 Windows 无符号链接权限的既有
  测试，不属于本功能。
- Ruff lint：`All checks passed!`。
- Ruff format：`52 files already formatted`。
- Python 编译：成功退出，无输出。
- 自动化鼠标场景：向 `ConversationLog` 发送按下、拖动、松开事件，中文内容被精确选择；
  `Ctrl+C` 后 `app.clipboard` 与选择内容完全一致，应用保持运行，历史行数不变。
- 内容覆盖：用户消息、助手 Markdown、代码块、工具行和错误行均可从选择中提取。

### tmux 端到端

- 环境：WSL Ubuntu、tmux 3.6，`set-clipboard=external`。
- 启动：在独立会话 `dragon-copy-e2e` 中运行 Dragon Code。
- 第一轮真实 DeepSeek 对话：请求 `Reply exactly COPY_READY`，实际回复 `COPY_READY`，
  耗时 1.5 秒。
- 复制分支：发送真实 SGR 鼠标拖选序列选择 `COPY_READY`，再发送 `Ctrl+C`；tmux 会话
  仍存在，证明没有误走退出分支。
- 继续对话：清除选择、重新聚焦输入框，请求 `Reply exactly CONTINUE_OK`，实际回复
  `CONTINUE_OK`，耗时 1.3 秒。
- 退出分支：无选择时发送 `Ctrl+C`，tmux 会话正常结束。
- 剪贴板边界：分离的后台 tmux 没有连接 Windows Terminal 客户端，不能从该进程读取
  Windows 系统剪贴板；精确内容由 Textual 自动化剪贴板断言验证。未修改用户 tmux 配置。
