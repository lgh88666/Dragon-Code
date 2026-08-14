---
name: test
description: 运行相关测试，区分源码缺陷与测试用例缺陷并完成修复验证。
allowedTools:
  - Read
  - Edit
  - Bash
  - Glob
  - Grep
mode: inline
---
# Test 工作流

测试范围或补充要求：$ARGUMENTS

1. 先确认项目使用的测试命令和目标范围。
2. 运行最小相关测试并阅读失败输出。
3. 对照需求、断言和源码，判断是源码缺陷还是测试用例错误。
4. 只修改正确的一侧，并重新运行相关测试。
5. 最后运行合理范围的回归测试，报告实际结果。
