---
name: review
description: 在独立只读 Agent 中审查当前 Git 改动或用户指定范围。
allowedTools:
  - Read
  - Glob
  - Grep
mode: fork
context: recent
---
# 代码审查工作流

审查范围或补充要求：$ARGUMENTS

只进行读取和分析，不修改文件。重点检查：

1. 功能错误与边界情况。
2. 安全问题和敏感信息泄漏。
3. 异步任务、文件和子进程清理。
4. 对既有行为的回归风险。
5. 缺失或不足的测试。

只报告可以实际说明的问题，按严重程度排序并标明文件位置。
