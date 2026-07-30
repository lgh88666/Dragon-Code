# Dragon Code 工具系统 Checklist

> 每项都通过运行代码或观察行为验证。开发完成后先执行验证，再根据实际结果勾选；
> 不以“代码看起来正确”代替证据。

## 工具抽象与注册中心

- [ ] 默认注册中心列出且仅列出 Read、Write、Edit、Bash、Glob、Grep 六个工具，顺序
  稳定。（验证：运行注册中心测试，观察导出名称列表。）`AC1/F1/F2`
- [ ] 每个工具定义均包含名称、详细描述、参数 Schema、category、read_only、
  destructive、is_concurrency_safe。（验证：序列化六个定义并逐字段断言。）`AC1/F1`
- [ ] 重复注册同名工具得到可读启动期错误，按名查找合法工具成功。（验证：分别注册
  两个同名假工具和查找 Read。）`AC1/F2`
- [ ] 请求未知工具时返回 `unknown_tool` 结构化结果，不产生未捕获异常。（验证：执行
  一个不存在的工具名并检查 JSON 结果。）`AC1/F2/F11`
- [ ] ToolResult 可稳定转换为包含 success、content、error、metadata、truncated 的
  JSON 文本，中文不被转义成不可读序列。（验证：运行数据模型测试并打印示例。）
  `F7/F11`

## 六个核心工具

- [ ] Read 读取 UTF-8 文件并返回从 1 开始的行号。（验证：读取三行临时文件，观察
  `1`、`2`、`3` 对应内容。）`AC2/F3`
- [ ] Read 读取不存在文件、目录或非 UTF-8 文件时返回可区分的结构化错误。（验证：
  三种输入分别执行，确认程序不抛堆栈。）`AC2/F3/F11`
- [ ] Write 能创建新文件并自动创建不存在的父目录。（验证：写入嵌套临时路径后检查
  磁盘内容。）`AC3/F3`
- [ ] Write 能覆盖已有文件且最终内容与请求完全一致。（验证：对同一文件写入两次并
  读取比较。）`AC3/F3`
- [ ] Edit 在原文唯一匹配时完成一次替换。（验证：构造唯一片段，执行后读取文件。）
  `AC4/F3`
- [ ] Edit 匹配零次或多次时文件保持不变，错误结果包含实际匹配数。（验证：保存执行
  前内容，两种失败后分别比较。）`AC4/F3/F11`
- [ ] Bash 正常命令返回 stdout、stderr 和退出码 0。（验证：执行同时写标准输出和
  标准错误的跨平台测试命令。）`AC5/F3`
- [ ] Bash 非零退出返回 success=false，并保留 stdout、stderr 和退出码。（验证：
  执行主动非零退出命令。）`AC5/F3/F11`
- [ ] Bash 超时后终止子进程并返回 `timeout`，测试不会挂死。（验证：把工具超时设为
  很短并执行更长命令，记录总耗时。）`AC5/N1`
- [ ] Glob 使用 `**/*.py` 能找到预期 Python 文件，只返回文件并按相对路径排序。
  （验证：在临时目录建立混合文件和目录后执行。）`AC6/F3`
- [ ] Glob 无匹配时成功返回空结果，不误报工具异常。（验证：使用不可能匹配的模式。）
  `AC6/F3`
- [ ] Grep 正则搜索返回文件、行号和命中行。（验证：建立已知内容文件并搜索唯一
  关键字。）`AC6/F3`
- [ ] Grep 支持指定单文件或子目录，并跳过常见无关目录和非 UTF-8 文件。（验证：
  在包含 `.git` 和二进制文件的临时树中搜索。）`AC6/F3`
- [ ] Grep 无命中成功返回空结果，非法正则返回结构化参数错误。（验证：两种模式分别
  执行。）`AC6/F3/F11`

## 路径与执行边界

- [ ] Read、Write、Edit、Glob、Grep 均可处理工作目录内的相对路径和绝对路径。
  （验证：用两种路径形式执行同一组工具。）`AC7/F4`
- [ ] 使用 `../` 或绝对路径访问工作目录之外时，五个文件类工具全部拒绝执行。
  （验证：逐工具触发并检查 error_code。）`AC7/F4`
- [ ] 通过工作目录内符号链接指向外部路径时仍被拒绝。（验证：平台允许创建符号链接
  时运行边界测试；不允许时记录平台限制并由真实路径单测覆盖。）`AC7/F4`
- [ ] 越界 Write/Edit 不创建或修改外部目标。（验证：执行前后比较外部文件与目录。）
  `AC7/F4`
- [ ] Bash 从 Dragon Code 启动工作目录执行，但不被文件路径规则拦截。（验证：命令
  打印当前目录并与启动目录比较。）`F3/F4`

## OpenAI 与 DeepSeek 协议

- [ ] 请求体包含六个 OpenAI function tool 定义，每个 parameters 均为有效 JSON
  Schema。（验证：捕获假客户端请求体并逐项检查。）`AC8/F5/F9`
- [ ] 普通消息、Assistant tool_calls 和 role=tool 结果按正确顺序发送，tool_call_id
  一一对应。（验证：构造一段工具历史并捕获请求体。）`AC8/F8/F9`
- [ ] 文本流被转换为 text_delta，流结束产生包含完整正文的 completed 事件。（验证：
  输入多个文本 chunk 并收集统一事件。）`F6/F9`
- [ ] 单个工具的 ID、名称和 JSON 参数被拆成多个 chunk 时能正确拼接。（验证：模拟
  分片流并比较最终 ToolCall。）`AC9/F6`
- [ ] 同一回复中的多个 tool_call index 不会互相混淆。（验证：交错发送两个调用的
  JSON 片段。）`AC9/F6`
- [ ] 无效 JSON 不抛异常，而是产生 arguments=None 并最终得到 invalid_json
  ToolResult。（验证：发送缺少闭合括号的参数片段。）`AC9/AC15/F11`

## Anthropic 协议

- [ ] 请求体包含六个 Anthropic 工具定义及 input_schema。（验证：捕获假客户端请求
  体并逐项检查。）`AC8/F5/F9`
- [ ] Assistant tool_use 与下一条 user/tool_result 正确关联，失败结果带
  `is_error=true`。（验证：构造成功和失败结果并捕获请求体。）`AC8/F8/F9`
- [ ] content block 与 input_json 分片能组装出单个和多个 ToolCall。（验证：模拟
  官方 SDK 事件顺序并收集统一事件。）`AC9/F6`
- [ ] thinking 与 redacted_thinking 不产生任何 TUI 可见文本。（验证：流中加入两种
  隐藏块，确认只收到正文事件。）`AC9/F6`
- [ ] Anthropic 工具续答请求原样保留上一条 Assistant 的隐藏思考块，并位于 tool_use
  之前。（验证：捕获续答请求体并与原始内容块深度比较。）`AC9/F6/F9`
- [ ] Anthropic 与 OpenAI 对同一统一消息历史产生各自合法的工具结果格式。（验证：
  使用同一组 ToolCall/ToolResult 运行两种适配测试。）`AC13/F9/N5`

## 单轮工具闭环

- [ ] 没有工具调用的普通对话仍保持逐字流式输出并保存用户/助手历史。（验证：运行
  原有 ch02 会话测试。）`F8/N5`
- [ ] 首轮一个工具调用会产生 tool_call → tool_result → 最终文本 → completed 的可观测
  事件顺序。（验证：使用假 Provider 跑完整会话并记录事件类型。）`AC10/F7/F8`
- [ ] 首轮多个工具按模型返回顺序串行执行，结果 ID 与调用 ID 对应。（验证：使用记录
  执行顺序的三个假工具。）`AC10/F7`
- [ ] 同批次一个工具失败时，后续工具继续执行，所有结果一起回灌。（验证：让第二个
  假工具失败，检查第三个仍被调用。）`AC10/F7/F11`
- [ ] 完整工具历史依次保存用户提问、Assistant 工具调用、tool 结果、最终 Assistant
  答复。（验证：完成工具轮后读取 Conversation。）`AC11/F8`
- [ ] 续答阶段再次请求工具时注册中心不再执行，界面收到 limit 事件。（验证：假
  Provider 两次都返回工具，检查执行计数。）`AC12/F8`
- [ ] 未执行的第二轮工具调用不写入历史，历史以本地单轮上限文本结束。（验证：读取
  Conversation 并再次构造两种协议请求。）`AC12/F8`
- [ ] Provider 鉴权、网络或模型错误后当前轮不提交，输入仍可继续。（验证：失败一次
  后让假 Provider 成功回复。）`AC15/F11`

## TUI 展示与响应性

- [ ] 每次调用显示 `● 工具名(关键参数)`，Read/Write/Edit 显示路径，Bash 显示命令，
  Glob/Grep 显示模式。（验证：Textual 测试中发送六种 TurnEvent。）`AC14/F10`
- [ ] 成功结果使用成功样式，失败结果使用红色错误样式，单轮上限使用黄色提示。
  （验证：检查 RichLog 渲染内容与样式。）`AC14/F10/F11`
- [ ] 工具结果只显示摘要，完整文件或长命令输出不会铺满对话区。（验证：发送超过
  摘要上限的 ToolResult。）`AC14/N3`
- [ ] 模型在工具调用前产生的前置文本被写入 scrollback，最终续答使用新的流式区域。
  （验证：模拟“正文 → 工具 → 续答正文”。）`AC14/F10`
- [ ] 工具行、结果摘要和最终答复都能滚动回看。（验证：Textual 自动化测试 +
  tmux `capture-pane -S -`。）`AC14/F10`
- [ ] 工具执行和第二次网络请求期间计时持续更新，界面不冻结。（验证：使用延迟假
  工具和延迟 Provider，观察 timer 多次变化。）`AC16/N1/N2`
- [ ] 完成、失败和达到上限后三种路径都恢复输入框并回到 IDLE。（验证：三种 Textual
  场景分别等待状态恢复。）`AC15/N2`

## 结果限制与安全

- [ ] Read 超过 2000 行或 100,000 字符时截断并设置 truncated=true。（验证：生成大
  文件执行 Read。）`AC16/N3`
- [ ] Bash stdout 与 stderr 合计超限时截断且保留退出码。（验证：运行长输出命令。）
  `AC16/N3`
- [ ] Glob 超过 200 个路径、Grep 超过 200 个命中时截断并明确说明。（验证：生成批量
  测试文件。）`AC16/N3`
- [ ] TUI 摘要、ProviderError 和 ToolResult 中均不出现配置中的 API Key。（验证：
  使用唯一测试密钥运行错误路径并搜索所有捕获输出。）`AC17/N6`
- [ ] 六个工具描述不包含密钥或本机敏感配置，并清楚区分使用场景。（验证：打印工具
  定义并人工审阅一次。）`AC8/N6`

## 编译、测试与质量

- [ ] 依赖锁文件与 pyproject 一致。（验证：运行 `uv lock --check`。）`AC18/N7`
- [ ] Python 模块均可编译导入。（验证：运行
  `uv run python -m compileall -q src tests`。）`AC18/N7`
- [ ] 全部自动化测试通过。（验证：运行 `uv run pytest -q`。）`AC18/N9`
- [ ] Ruff 格式检查通过。（验证：运行 `uv run ruff format --check .`。）`AC18/N8`
- [ ] Ruff lint 无告警。（验证：运行 `uv run ruff check .`。）`AC18/N8`
- [ ] ch03 学习笔记包含核心调用链、两种协议差异、错误边界、测试证据、踩坑和面试
  表达。（验证：回顾 `docs/learning-notes.md` 的 ch03 章节。）`AC18/N8/N9`
- [ ] Git diff 只包含 ch03 文档、实现、测试和学习笔记，不包含 `.dragon-code` 密钥
  配置或 `.idea/`。（验证：运行 `git status --short` 与
  `git diff --check`。）`AC17/AC18`

## 端到端场景

### 场景 1：真实 Read 单轮闭环

- [ ] 在 WSL 的 tmux 中启动 Dragon Code，使用真实 DeepSeek/OpenAI 配置询问
  “读取 README.md 并总结”；看到 `● Read(README.md)`、成功摘要和体现真实文件内容的
  最终答复。（验证：保存 `tmux capture-pane -p -S -` 输出。）`AC11/AC13`

### 场景 2：真实写文件与错误恢复

- [ ] 在 tmux 中要求创建工作目录内的临时文本文件；看到 Write 工具行，磁盘内容正确。
  随后要求读取不存在文件，看到结构化失败摘要和模型解释；再发送普通消息仍能正常回复。
  （验证：终端捕获 + 磁盘检查。）`AC3/AC15`

### 场景 3：真实搜索工具

- [ ] 在 tmux 中要求使用 Glob 查找 Python 文件并使用 Grep 搜索一个项目关键字；看到
  一个回复中的一个或多个工具调用、结果摘要和最终结论。（验证：终端捕获结果与磁盘
  实际搜索结果抽样对比。）`AC6/AC10`

### 场景 4：单轮上限

- [ ] 创建一个模型事先不知道文件名的临时目录，要求“先 Glob 找到其中的 secret
  文件，再读取内容”；首轮只执行 Glob，续答请求 Read 时不执行，并出现黄色单轮上限
  提示。（验证：tmux 捕获 + 确认没有第二个工具结果。）`AC12`

### 场景 5：scrollback 与退出

- [ ] 连续完成多轮工具对话后向上回滚，工具行、结果和最终答复仍存在；输入 `/exit`
  后终端状态正常，退出后的 tmux 历史仍可捕获。（验证：滚动观察 +
  `tmux capture-pane -p -S -`。）`AC14/AC18`

## 验收命令汇总

```powershell
uv lock --check
uv run python -m compileall -q src tests
uv run ruff format --check .
uv run ruff check .
uv run pytest -q
git diff --check
git status --short
```

真实端到端验收在 WSL 的 tmux 中执行，使用现有 `.dragon-code/config.yaml`，任何捕获
输出都不得打印或复制 API Key。
