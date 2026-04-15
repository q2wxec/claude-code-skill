# prompt-architect

审计并重构 CLAUDE.md，最大化 prompt cache 命中率，遵循 Claude Code 内部的 `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` 模式。

## 解决的问题

CLAUDE.md 中混入时间戳、绝对路径、动态内容等易变信息后，每次对话都会破坏 prompt cache，导致大量 cache miss，token 成本显著上升。这个 skill 诊断并修复这些问题。

## 核心原理

Claude Code 的 system prompt 分为两部分：
- **静态前缀**（`SYSTEM_PROMPT_DYNAMIC_BOUNDARY` 之前）：跨 turn 稳定，可被缓存
- **动态后缀**（之后）：每 turn 重新计算，破坏缓存

`systemPromptSection()` 创建可缓存的 section（直到 `/clear` 或 `/compact`）。
`DANGEROUS_uncachedSystemPromptSection()` 创建每 turn 重新计算的 section——每次值变化都会破坏整个后续缓存。

## 典型 cache-busting 反模式

| 反模式 | 示例 | 修复 |
|---|---|---|
| 内嵌时间戳 | "Last updated: March 2026" | 删除或移到注释 |
| 绝对路径 | `/Users/fxx/projects/...` | 改用相对路径 |
| 动态输出 | 粘贴的 `ls -la` 结果 | 删除，Claude 可以自己运行 |
| 频繁轮换的值 | Git branch 名 | 删除，按需读取 |

## 使用方式

对 Claude 说：
- `"优化我的 CLAUDE.md"`
- `"为什么我的 prompt cache 命中率这么低？"`
- `"检查 CLAUDE.md 有没有破坏缓存的内容"`
- `"重构系统提示词，减少 token 成本"`

## 附带脚本

| 脚本 | 功能 |
|---|---|
| `scripts/claudemd_audit.py` | 静态分析 CLAUDE.md，检测 cache-busting 反模式并评分 |

## 源码依据

- `src/constants/systemPromptSections.ts`: `systemPromptSection()` vs `DANGEROUS_uncachedSystemPromptSection()`
- `src/utils/systemPrompt.ts`: `buildEffectiveSystemPrompt()` 5 级优先级
- `src/constants/prompts.ts`: `SYSTEM_PROMPT_DYNAMIC_BOUNDARY` 标记
