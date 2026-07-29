# Dragon Code 紧凑翼形 Banner Checklist

> 所有条目必须通过运行或观察验证，并记录实际证据。

## 实现完整性

- [x] **固定图标正确（AC1/F1/F2/N1）**
  验证：逐字符比较运行时图标和交接文档中的批准图标。
  证据：`test_dragon_banner_matches_approved_icon` 通过，UTF-8 实际打印一致。

- [x] **并排信息正确（AC2/F3/F5）**
  验证：第一行显示产品名和真实版本，第二行显示英文说明，第三行显示真实工作目录。
  证据：`test_render_banner_has_approved_layout` 通过，实际打印三行从同一列开始。

- [x] **双色样式正确（AC3/F4）**
  验证：图标和产品名为白色，版本、说明和工作目录为灰色。
  证据：Rich Text 样式测试确认包含 `white`、`bold white` 和 `grey70`。

- [x] **旧图案与红色已移除（AC4/F7）**
  验证：源码、渲染文本和样式中不再包含旧三头龙特征与 `#d13b3b`。
  证据：专项测试通过，TCSS 已改为白色默认样式。

- [x] **特殊目录安全（AC6/N5）**
  验证：使用 `D:\My [Demo] Project` 渲染，目录原样显示且不触发 markup 错误。
  证据：`test_render_banner_keeps_special_directory_characters` 通过。

- [x] **原功能不变（AC7/F6）**
  验证：就绪提示、Provider 信息、输入框和会话相关测试继续通过。
  证据：完整 42 项测试全部通过。

- [x] **实现简单且无新依赖（N4）**
  验证：使用普通循环和 Rich `Text`；依赖文件没有变化。
  证据：源码和 Git 差异检查通过。

- [x] **密钥安全（N7）**
  验证：Banner 和测试输出不包含 `api_key` 或实际密钥。
  证据：渲染输出仅包含产品信息、版本和工作目录。

## 自动测试与质量

- [x] `uv run pytest tests/test_prompt.py -q` 返回退出码 0（5 项通过）。
- [x] `uv run pytest tests/test_tui.py -q` 返回退出码 0（9 项通过）。
- [x] `uv run pytest -q` 返回退出码 0（42 项通过）。
- [x] `uv run ruff format --check .` 返回退出码 0（31 个文件已格式化）。
- [x] `uv run ruff check .` 返回退出码 0。
- [x] `git diff --check` 返回退出码 0。

## 端到端场景

### 标准终端

- [x] `uv run dragon-code` 正常启动（PowerShell 进程 PID 15416）。
- [ ] 顶部实际展示以下并排 Banner：

  ```text
   ▗▄   ▄▖   Dragon Code  v0.1.0
  ▐██▙▄▟██▌  Multi-provider coding agent
  ▝██▀█▀██▘  D:\project
    ▘   ▝
  ```

- [x] 图标和文字颜色符合设计，其他界面元素保持正常（Rich 样式与 TUI 测试通过）。

### 窄终端

- [x] Textual Pilot 在约 42×18 尺寸下正常启动。
- [x] Banner 不与对话区或输入区重叠，长目录按终端能力安全换行或裁切。

### tmux

- [x] 在 tmux 中启动并截图。
  证据：Ubuntu WSL 2 中使用 tmux 3.6 启动 Dragon Code，`capture-pane` 成功捕获完整 Banner。
- [x] 输入真实对话请求并收到回复。
  证据：输入“请用一句话介绍 Dragon Code。”，DeepSeek V4 Pro 在 3.1 秒内返回完整回复。
- [x] WSL/tmux 环境可用。
  证据：Ubuntu 运行于 WSL 2，项目目录可访问，tmux 版本为 3.6。

## 验收记录

未通过项保持未勾选，并写明预期、实际和后续处理。
