# context-budget-planner

在长任务开始前规划 context window 预算，基于 Claude Code 真实的 autocompact 阈值。

## 解决的问题

长任务（大规模重构、批量文件处理、长研究会话）中，context 往往在最关键的时候达到上限，被迫自动压缩，丢失重要状态。这个 skill 帮你在任务开始前预估各阶段的 token 消耗，主动规划压缩检查点，而不是被动应对。

## 关键阈值（来自真实源码）

| 阈值 | Buffer | 触发行为 |
|---|---|---|
| 警告区 | 20,000 tokens 剩余 | 黄色警告 |
| **autocompact 触发** | **13,000 tokens 剩余** | 自动压缩 |
| 阻塞上限 | 3,000 tokens 剩余 | 新消息被阻塞 |

有效上下文窗口 = 模型窗口 − 20,000（摘要输出预留，基于 p99.99 实测 17,387 tokens）

## 使用方式

对 Claude 说：
- `"这个任务需要读 30 个文件，会不会超出 context？"`
- `"帮我规划这次大重构的 context 预算"`
- `"什么时候应该手动 /compact？"`
- `"context 快满了，怎么安排接下来的步骤？"`

## 附带脚本

| 脚本 | 功能 |
|---|---|
| `scripts/token_estimator.py` | 估算文件/目录的 token 消耗，辅助预算规划 |

## 源码依据

- `src/services/compact/autoCompact.ts`:
  - `AUTOCOMPACT_BUFFER_TOKENS = 13_000`
  - `MAX_OUTPUT_TOKENS_FOR_SUMMARY = 20_000`
  - `MAX_CONSECUTIVE_AUTOCOMPACT_FAILURES = 3`
- `src/utils/tokens.ts`: `tokenCountWithEstimation()` — 字符数/4 ≈ token 数
