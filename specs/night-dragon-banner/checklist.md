# Dragon Code 三头龙徽章 Banner Checklist

> 每一项通过自动测试或实际启动界面观察验证，并记录实际证据。

## 实现完整性

- [x] **图案已替换（AC1/F1）**
  验证：启动 Dragon Code，顶部展示三头龙徽章，不再显示旧正面龙头。
  证据：`test_old_dragon_features_are_removed` 通过，本地进程已启动。

- [x] **尺寸与字符合规（AC2/F4/N1/N2）**
  验证：单元测试确认图案恰好 5 行、每行不超过 24 字符，并且只包含 ASCII 字符。
  证据：`test_dragon_banner_size_and_ascii` 通过；实测最长行 17 字符。

- [x] **三个龙头可辨认（AC3/F2）**
  验证：目视和单元测试确认中央龙头朝上，左右龙头分别朝外。
  证据：实际输出包含中央 `/^\` 和左右 `<<==<`、`>==>>`。

- [x] **环形轮廓可辨认（AC3/F2）**
  验证：目视确认图案左右展开、下方收拢，形成紧凑徽章轮廓。
  证据：实际输出第五行由 `\____` 向中央收拢并以 `____/` 闭合。

- [x] **Banner 显示为红色（AC4/F3）**
  验证：Textual Pilot 检查 `#banner` 最终颜色为 `#d13b3b`，本地启动目视复核。
  证据：`test_single_provider_layout` 读取最终样式并通过。

- [x] **原有文字不变（AC5/F5）**
  验证：调用 `render_banner("0.1.0", "D:\\demo")`，仍包含应用名、版本、目录和就绪提示。
  证据：`test_render_banner_keeps_existing_text` 及实际打印通过。

- [x] **修改范围正确（F6）**
  验证：Git 差异中没有对话、Provider、输入、流式输出或依赖文件的改动。
  证据：运行代码只修改 `prompt.py` 和 `dragon_code.tcss`。

- [x] **资源集中且有中文说明（N3）**
  验证：图案只在 `DRAGON_BANNER` 中定义，旁边有简短中文注释。
  证据：源码检查通过。

- [x] **不分发官方图片素材（N4）**
  验证：项目只保存 ASCII 字符画，不新增影视图片、矢量文件或其他二进制素材。
  证据：Git 差异无新增二进制文件。

- [x] **标准与窄终端兼容（AC6/N2）**
  验证：Textual Pilot 在标准尺寸和 42×18 窄终端中运行，Banner 不重叠。
  证据：完整测试中的标准布局与窄终端测试通过。

## 自动测试与质量

- [x] `uv run pytest tests/test_prompt.py -q` 返回退出码 0（4 项通过）。
- [x] `uv run pytest tests/test_tui.py -q` 返回退出码 0（9 项通过）。
- [x] `uv run pytest -q` 返回退出码 0（41 项通过）。
- [x] `uv run ruff format --check .` 返回退出码 0（30 个文件已格式化）。
- [x] `uv run ruff check .` 返回退出码 0。
- [x] `git diff --check` 返回退出码 0。

## 端到端场景

### 场景 1：标准终端

- [x] 在项目目录运行 `uv run dragon-code`，应用正常启动（PowerShell 进程 PID 29500）。
- [x] 顶部显示红色、对齐的 5 行三头龙徽章（Pilot 样式和资源测试通过）。
- [x] 应用名称、版本、工作目录、就绪提示和其他界面元素保持正常（布局测试通过）。

### 场景 2：窄终端

- [x] 使用 Textual Pilot 将终端调整到 42×18。
- [x] 三头龙徽章和主要界面元素保持可见，未发生重叠。

### 场景 3：tmux 真实对话

- [ ] 在 tmux 会话中启动 Dragon Code。
- [ ] 使用 `tmux capture-pane -p -S -` 或截图保存顶部 Banner 证据。
- [ ] 输入一条真实对话请求并收到回复，确认聊天功能未受影响。
- [x] 如果本机没有 tmux，记录实际检测结果和待补验项目。
  证据：`Get-Command tmux` 返回 `TMUX_NOT_FOUND`；`wsl --list --verbose` 提示尚未安装 WSL。

## 验收记录格式

```text
- [x] 条目名称
  证据：执行的命令或输入
  实际：观察到的输出、退出码或界面行为
```

未通过项保持未勾选，并记录预期、实际和后续处理方式。
