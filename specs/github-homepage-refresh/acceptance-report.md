# Dragon Code GitHub 项目主页美化验收报告

## 结论

README 已按“专业、克制、有趣”的方向完成重构。本地内容、Markdown、链接、敏感信息、全量回归和远端 GitHub 验证均通过。

## 页面结果

- 首屏包含 Dragon Banner、中文价值主张与 Python/Textual/MCP/Ruff/章节进度徽章。
- ch02–ch13 能力按自主执行、上下文、安全、扩展、终端体验和多协议进行分组。
- Mermaid 图串起 TUI、Agent、LLMClient、工具调度、权限、MCP、Skill、Hook、记忆和 SubAgent。
- 快速开始覆盖克隆、uv 安装、两类 Provider 配置和启动命令。
- 常用命令表由当前 CommandRegistry 与内置 Skill 反查生成。
- 源码导航、章节进度、验证方式和当前边界均已补齐，ch14 明确为学习与规划中。

### 能力矩阵视觉修订

- 根据用户反馈，将 GitHub 自动分栏的 Markdown 表格改为 HTML table。
- “能力域”列固定为 27%，说明列固定为 73%，六项能力名称更完整。
- 右栏描述进一步压缩，降低文字墙感；没有增加 CSS 或外部图片依赖。
- HTML table、thead、tbody、tr、th、td 标签数量成对，宽度合计 100%。

## 本地证据

```text
uv sync --locked                    PASS
Markdown code fences               32（成对）
Repository-relative links          2（全部存在）
Sensitive pattern hits             0
Personal absolute path hits        0
uv run ruff format --check .       234 files already formatted
uv run ruff check .                All checks passed
uv run pytest -q                    530 passed, 2 skipped
HTML table width                    27% / 73%
HTML tag pairs                      PASS
```

## 远端证据

```text
Homepage commit                    c66a47a729c257a3d648169e863485e8e3335799
git push origin master             PASS（HTTP/1.1）
git ls-remote origin master        与主页提交一致
GitHub project page                HTTP 200
Remote README source               包含标题、徽章、Mermaid、快速开始和 ch14 边界
```

首次普通推送遇到两次 `Recv failure: Connection was reset`；GitHub 443 与网页访问正常，改为仅本次命令使用 `git -c http.version=HTTP/1.1 push origin master` 后成功，没有修改提交历史。
