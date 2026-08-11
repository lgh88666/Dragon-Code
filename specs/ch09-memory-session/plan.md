# ch09：项目记忆与会话持久化 Plan

## 状态

- 阶段：已批准（2026-08-11）
- 输入：已批准的 `spec.md`
- 教材基线：Vibe Coding ch09 Python 技术方案
- Dragon Code 适配：保留现有 `session.py`，新持久化包命名为 `sessions`；完整保存 `hidden_blocks`；为用户记忆增加 Read 专用只读根

## 架构概览

本章沿用教材“3 个独立子系统 + 现有模块窄幅接入”的方案，不建立包办所有功能的大管理器。

### 项目指令子系统

新增 `instructions` 包，负责扫描三层 `DRAGON.md`、展开 `@include`、检查深度/环路/二进制文件/路径越界，并返回按优先级拼好的纯文本。它不直接操作 Agent 或 TUI；CLI 启动时调用一次，再把结果传给 Agent。

### 会话持久化子系统

保留现有 `session.py` 中的 Conversation，新增复数形式的 `sessions` 包：

- `SessionWriter` 追加 JSONL、刷盘并关闭文件。
- `SessionReader` 解析坏行、compact 边界和悬空工具调用。
- `SessionManager` 新建会话、扫描列表、恢复和清理。
- `SessionInfo`、`RestoredSession` 向上层提供简单结果。

Conversation 增加可选的追加/替换通知。未传通知时保持 ch08 行为。

### 自动记忆子系统

新增 `memory` 包，由 MemoryManager 协调两级索引、触发判断、后台 LLM 更新、结构化操作、笔记写入和任务清理。Agent 每次普通任务开始时读取最新索引，因此后台更新完成后的后续任务可以使用新记忆。

### Agent、TUI 与 CLI 接入

- Agent 负责系统提示注入、自然完成计数、记忆调度、存档警告事件和会话切换。
- TUI 增加 `RESUMING`、搜索选择屏幕和恢复 Worker。
- CLI 创建项目指令、会话、记忆服务以及清理任务，并在退出时统一收尾。
- ch08 ContextManager 继续负责 session 路径、工具结果落盘和恢复时的超限压缩。

### Dragon Code 特有适配

- JSONL 除教材字段外保存 `hidden_blocks` 以及 ToolCall/ToolResult 的完整字段，保证 Anthropic thinking/tool-use 历史能合法恢复。
- 用户级记忆位于项目外，只为 Read 增加 `~/.dragon-code/memory/` 精确只读根；其他文件工具不放宽边界。

## 核心数据结构与接口

### InstructionLoader

```python
class InstructionLoader:
    def __init__(self, project_root: Path, user_home: Path | None = None): ...

    def load(self) -> str:
        """加载三层 DRAGON.md，返回已按优先级拼接的文本。"""

    def _expand_file(
        self,
        path: Path,
        boundary: Path,
        depth: int,
        visited: set[Path],
    ) -> str: ...
```

`visited` 只服务于当前引用链；返回上一层时移除当前路径，避免把两个互不循环的合法引用误判为环路。

### SessionInfo 与 RestoredSession

```python
@dataclass
class SessionInfo:
    session_id: str
    title: str
    updated_at: datetime
    model: str
    file_size: int
    jsonl_path: Path


@dataclass
class RestoredSession:
    session_id: str
    messages: list[ChatMessage]
    model: str
    last_timestamp: int
    skipped_lines: int
    orphan_call_truncated: bool
```

`SessionInfo` 只用于列表。`RestoredSession` 表示已解析和修复的历史。记录中的模型只用于展示；恢复后继续使用本次启动选择的 Provider。

### ActiveSession

为避免 `sessions.models` 与 Writer/Conversation 形成导入环，ActiveSession 定义在 `sessions/manager.py`：

```python
@dataclass
class ActiveSession:
    session_id: str
    conversation: Conversation
    writer: SessionWriter
    restored_count: int = 0
```

TUI 始终只持有一个当前 ActiveSession。

### JSONL 编解码

```python
def message_to_record(
    message: ChatMessage,
    timestamp: int,
    model: str | None = None,
) -> dict: ...


def record_to_message(record: dict) -> ChatMessage: ...


def compact_record(timestamp: int) -> dict: ...
```

转换保留 ChatMessage、ToolCall、ToolResult 和 hidden_blocks 的完整字段。字段类型错误时抛出可识别解析错误，由 Reader 跳过整行。

### SessionWriter

```python
class SessionWriter:
    def __init__(self, jsonl_path: Path, model: str): ...
    def append(self, message: ChatMessage) -> None: ...
    def replace(self, messages: list[ChatMessage]) -> None: ...
    def close(self) -> None: ...
```

Writer 使用 `threading.Lock`；第一条消息附带模型；每条 JSON 行写入后 flush + fsync；`close()` 幂等。

### Conversation 扩展

```python
AppendCallback = Callable[[ChatMessage], None]
ReplaceCallback = Callable[[list[ChatMessage]], None]


class Conversation:
    def __init__(
        self,
        initial_messages: list[ChatMessage] | None = None,
        on_append: AppendCallback | None = None,
        on_replace: ReplaceCallback | None = None,
    ): ...

    def commit_messages(self, messages: list[ChatMessage]) -> None: ...
    def replace_messages(self, messages: list[ChatMessage]) -> None: ...
    def take_persistence_warning(self) -> str: ...
```

Conversation 先更新内存再通知 Writer。Writer 失败时保留内存历史并记录待展示警告。恢复消息通过 `initial_messages` 初始化，不重复写入旧消息。

### SessionManager

```python
class SessionManager:
    def __init__(self, project_root: Path): ...
    def open_new(self, model: str) -> ActiveSession: ...
    def list_sessions(self) -> list[SessionInfo]: ...
    def restore(self, session_id: str, model: str) -> ActiveSession: ...
    def cleanup_expired(self, retention_days: int = 45) -> list[str]: ...
    def close(self) -> None: ...
```

Manager 只允许新格式 ID 进入列表、恢复和清理；底层 SessionPaths 仍兼容旧安全格式。

### Session ID

```python
def make_session_id() -> str: ...
def is_new_session_id(value: str) -> bool: ...
def is_safe_session_id(value: str) -> bool: ...
```

新建只产生 `YYYYMMDD-HHMMSS-xxxx`；底层路径校验同时接受 ch08 旧格式。

### MemoryOperation

```python
@dataclass
class MemoryOperation:
    action: str
    level: str
    memory_type: str = ""
    title: str = ""
    slug: str = ""
    filename: str = ""
    content: str = ""
```

仅接受 create/update/delete、project/user、四种 memory_type 及安全文件名。

### MemoryManager

```python
class MemoryManager:
    def __init__(self, project_root: Path, user_home: Path | None = None): ...
    def load_indexes(self) -> str: ...
    def current_index(self) -> str: ...
    def should_update(self, completed_turns: int, user_text: str) -> bool: ...
    def schedule_update(
        self,
        client: LLMClient,
        turn_messages: list[ChatMessage],
        completed_turns: int,
        user_text: str,
    ) -> None: ...
    async def close(self) -> None: ...
```

内部接口：

```python
async def _update_memory(...) -> None: ...
async def _collect_response(...) -> str: ...
def _parse_operations(text: str) -> list[MemoryOperation]: ...
def _apply_operations(operations: list[MemoryOperation]) -> None: ...
```

文件修改由 `asyncio.Lock` 串行保护；同步磁盘操作放入 `asyncio.to_thread()`；每批操作完成后重新生成并加载索引。

### Agent 调整

```python
class Agent:
    def __init__(
        ...,
        custom_instructions: str = "",
        memory_manager: MemoryManager | None = None,
    ): ...

    def replace_session(
        self,
        conversation: Conversation,
        context_manager: ContextManager,
    ) -> None: ...
```

Agent 增加 `completed_turns`；每次 run 读取最新记忆；自然完成才调度更新；存档失败产生 `session_warning`；恢复后按用户消息数重算轮次并清除旧 Plan 标记。

### TUI 恢复接口

```python
class SessionResumeScreen(ModalScreen[str | None]): ...


def _show_resume_screen(self) -> None: ...
def _resume_selected(self, session_id: str | None) -> None: ...
async def _restore_session(self, session_id: str) -> None: ...
```

文件扫描和读取通过 `asyncio.to_thread()`，超限压缩使用现有 ContextManager。

### Read 额外根目录

```python
class ReadTool:
    def __init__(
        self,
        workdir: Path,
        extra_read_roots: list[Path] | None = None,
    ): ...
```

PathSandbox 同样接收 extra_read_roots，但仅当工具为 Read 时使用。

## 模块设计

### `instructions/loader.py`

**职责：** 三层加载、UTF-8/二进制判断、独占行 include、深度/环路/边界检查、稳定拼接。
**对外接口：** `InstructionLoader.load()`。
**依赖：** Python 标准库。
**覆盖：** F1–F8、AC1–AC6。

### `sessions/codec.py`

**职责：** ChatMessage 与 JSON 字典双向转换，完整保留协议字段，识别 compact。
**依赖：** `models.py`。
**覆盖：** F11–F14、AC8–AC10。

### `sessions/writer.py`

**职责：** UTF-8 追加、锁、模型首行、compact 标记、flush/fsync、幂等关闭。
**依赖：** `sessions/codec.py`。
**覆盖：** F12–F16、AC8–AC10、AC32。

### `sessions/reader.py`

**职责：** 坏行跳过、最后 compact 边界、悬空工具调用修复、列表元信息提取。
**依赖：** `sessions/codec.py`、`sessions/models.py`。
**覆盖：** F18、F20、F21、AC12、AC14、AC15、AC17。

### `sessions/manager.py`

**职责：** 新建、列表、恢复、时间提醒、45 天清理、Writer 生命周期。
**依赖：** Reader、Writer、Conversation、SessionPaths。
**覆盖：** F9、F10、F17–F26、AC7、AC11–AC20。

### `memory/prompt.py`

**职责：** 构造无工具、只返回 JSON 操作数组的记忆更新请求。
**依赖：** 协议无关模型。
**覆盖：** F27、F35、F37–F39。

### `memory/manager.py`

**职责：** 两级索引、25KB 截断、触发判断、后台收集、操作校验、原子文件更新、索引重建、失败隔离和任务清理。
**依赖：** MemoryOperation、Memory Prompt、LLMClient、StreamCollector。
**覆盖：** F27–F42、F47、AC21–AC26、AC30、AC31。

### `session.py`

**职责变化：** 初始历史、追加/替换回调、持久化警告；保留深拷贝和无回调兼容。
**覆盖：** F13、F15、F44、AC28、AC32。

### `context/state.py` 与 `context/manager.py`

**职责变化：** 新旧 ID 校验、统一会话目录、恢复历史阈值判断、复用 ch08 摘要。
**覆盖：** F9、F10、F21、F22、AC7、AC16。

### `agent.py`

**职责变化：** 最新记忆注入、自然完成计数、后台记忆调度、存档警告、会话切换。
**覆盖：** F32、F35–F37、F43、F44、F47、AC23–AC25、AC27、AC30–AC32。

### `tui.py`

**职责变化：** RESUMING、搜索选择、恢复 Worker、超限压缩、原子切换、恢复/警告展示和帮助文本。
**覆盖：** F17–F24、F46、AC11–AC18、AC29、AC32。

### `cli.py`

**职责变化：** 初始化三个服务、配置 Read 只读根、后台清理和统一关闭。
**覆盖：** F25、F26、F45、N8、N9。

### Read 与沙箱模块

**职责变化：** Read 接受项目根或用户 memory 根；Write/Edit/Glob/Grep 不变。
**覆盖：** F33，并保持 ch06 权限边界。

## 模块交互

### 启动

```text
CLI 加载配置
→ InstructionLoader.load
→ MemoryManager.load_indexes
→ SessionManager 初始化 + 后台 cleanup_expired(45)
→ 工具注册中心配置用户 memory 只读根
→ MCP 连接与工具注册
→ TUI
→ Provider 选择
→ SessionManager.open_new
→ ContextManager(同一 session ID)
→ Agent
```

### 普通任务与存档

```text
TUI 提交
→ Agent 读取最新 memory 索引并构造 System Prompt
→ Agent Loop
→ Conversation.commit_messages
→ SessionWriter.append
→ 写入失败则 Conversation 记录 warning
→ Agent 发 session_warning
→ TUI 黄色提示
```

只保存完整逻辑消息，不保存流式碎片。

### 自动记忆

```text
Agent 自然完成
→ 截取本轮消息快照
→ completed_turns + 1
→ MemoryManager.should_update
→ schedule_update 后立即 completed
→ 后台无工具 LLMRequest
→ JSON 操作数组
→ memory 写锁
→ 原子修改 Markdown + 重建 MEMORY.md
→ 替换内存索引快照
```

错误、取消和迭代上限不触发。

### `/resume`

```text
IDLE 输入 /resume
→ RESUMING
→ to_thread(list_sessions)
→ 搜索/选择屏幕
→ to_thread(restore)
→ 修复历史 + 时间提醒
→ ContextManager(恢复 ID)
→ 超限则尝试摘要
→ 新对象准备完成
→ Agent.replace_session
→ 关闭旧 Writer
→ 显示结果并回到 IDLE
```

失败发生在切换前时保留旧会话。恢复模型标签只展示，继续对话使用当前 Provider。

### 压缩

```text
ContextManager 生成新历史
→ Conversation.replace_messages
→ 内存一次性替换
→ SessionWriter 写 compact + 新历史
```

记忆更新持有深拷贝，不与 `/compact` 共享可变 Conversation。

### 清理与退出

清理只解析新格式 ID，超过 45 天且再次确认目标位于 sessions 根下才删除。退出时依次取消 Agent、关闭 Writer、取消并等待记忆/清理任务、关闭 MCP、恢复终端。

## 文件组织

```text
src/dragon_code/
├── instructions/
│   ├── __init__.py
│   └── loader.py
├── sessions/
│   ├── __init__.py
│   ├── models.py
│   ├── codec.py
│   ├── writer.py
│   ├── reader.py
│   └── manager.py
├── memory/
│   ├── __init__.py
│   ├── models.py
│   ├── prompt.py
│   └── manager.py
├── context/state.py
├── context/manager.py
├── permissions/__init__.py
├── permissions/sandbox.py
├── tools/path_utils.py
├── tools/file_tools.py
├── tools/registry.py
├── agent.py
├── cli.py
├── prompt.py
├── session.py
├── tui.py
└── dragon_code.tcss

tests/
├── test_instructions.py
├── test_session_persistence.py
├── test_memory.py
├── test_session.py
├── test_context_manager.py
├── test_agent.py
├── test_tui.py
├── test_tools.py
└── test_permissions.py
```

同时修改 `.gitignore`、`README.md`；验收后更新 `docs/PROJECT_HANDOFF.md` 和 `docs/learning-notes.md`。

## 依赖方向

```text
models
  ↑
sessions.codec
  ↑
sessions.reader / sessions.writer
  ↑
sessions.manager
  ↑
tui
  ↑
cli

models + clients + stream_collector
  ↑
memory.prompt / memory.manager
  ↑
agent
  ↑
tui
```

InstructionLoader 独立；Agent 不导入 TUI；SessionManager 不导入 Agent；MemoryManager 不导入 Agent，因此不存在循环依赖。

## 技术决策

| 决策点 | 选择 | 理由 |
|---|---|---|
| 整体架构 | instructions、sessions、memory 三个子系统 | 与教材一致，职责清晰 |
| session 包名 | 复数 `sessions` | 避免与现有 `session.py` 冲突 |
| ActiveSession 位置 | `sessions/manager.py` | 避免 models 与 Writer/Conversation 导入环 |
| 会话格式 | 单 JSONL，无 meta | 追加快，不同步双份状态 |
| 消息完整性 | 保存 hidden_blocks 和完整工具字段 | 恢复 Anthropic 合法历史 |
| Conversation 顺序 | 先内存，后 Writer | 磁盘失败时按已批准设计继续会话 |
| Writer | 同步 + threading.Lock | 保持 Conversation 简单同步接口 |
| 压缩持久化 | compact 标记后追加新历史 | 对齐教材和 ch08 replace |
| 新旧 ID | 新建仅新格式，底层兼容旧格式 | 满足 ch09 并保护遗留目录 |
| 恢复 Provider | 当前活动 Provider | 本章不做运行时切换 |
| 恢复切换 | 全部准备后原子替换 | 失败不留下半状态 |
| 时间提醒 | 只加入恢复后的内存历史 | 模型感知间隔但不立即改写旧 JSONL |
| 记忆模型 | 当前 LLMClient、无工具 | 同端点且不允许后台操作项目 |
| 记忆去重 | LLM + 完整索引 | 不引入 RAG/相似度系统 |
| 笔记写入 | 锁内临时文件原子替换 | 避免半文件 |
| 索引一致性 | 根据笔记重建 | 减少笔记与索引漂移 |
| 索引生效 | 更新完成立即换快照 | 当前会话后续任务可使用 |
| 提示缓存 | 记忆变化时允许稳定前缀更新 | 服从 F32 的实时记忆要求 |
| 用户记忆读取 | Read 专用只读根 | 不放宽其他沙箱边界 |
| 清理 | 45 天、只识别新 ID | 采用用户选择并保护旧数据 |
| 任务归属 | MemoryManager 管记忆，CLI 管总生命周期 | 退出清理明确 |
| 新依赖 | 不新增 | 现有依赖足够 |
| Slash 命令 | 继续直接分发 | 通用框架留给 ch10 |

## Spec 覆盖自检

| Spec 范围 | 架构归属 |
|---|---|
| F1–F8 | InstructionLoader、CLI、Prompt |
| F9–F16 | Session ID、Codec、Writer、Conversation |
| F17–F26 | Reader、SessionManager、TUI、ContextManager |
| F27–F42 | Memory Prompt、MemoryManager、Agent |
| F43–F47 | Prompt、Conversation、Agent、TUI、CLI |

- 覆盖缺口：无。
- 接口完整性：每个模块均有明确输入、输出和错误边界。
- 依赖检查：无循环依赖；ActiveSession 已从原草案的 models 移到 manager。
- 冲突检查：与已批准 Spec 无冲突；教材 30 天已按用户选择改为 45 天。
