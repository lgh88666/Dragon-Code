---
name: commit
description: 分析当前 Git 改动并生成范围清晰、格式规范的提交。
allowedTools:
  - Read
  - Bash
mode: inline
---
# Commit 工作流

用户补充要求：$ARGUMENTS

1. 使用 `git status` 和 `git diff` 了解当前改动。
2. 只处理用户要求范围内的文件，不夹带无关修改或敏感配置。
3. 根据实际 diff 生成简洁的提交说明。
4. 提交前再次确认暂存范围，完成后报告提交哈希和验证证据。
