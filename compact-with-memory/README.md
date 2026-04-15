# compact-with-memory

增强版 `/compact`：压缩对话之前，先把本次会话的关键决策、已排除方案和新发现提取写入 MEMORY.md。

## 解决的问题

标准 `/compact` 生成摘要后丢弃对话历史。这意味着本次会话中艰难得出的决策（"我们选 X 而非 Y 因为 Z"）、踩过的坑（"方案 A 行不通，因为 B"）在下次会话中需要重新发现。这个 skill 在压缩之前做一次记忆蒸馏。

## 工作流程

1. **审计当前对话** — 识别值得持久化的内容（决策、失败方案、新发现、当前阻塞点）
2. **写入 MEMORY.md** — 按三层架构写入或更新记忆文件
3. **执行标准压缩** — 运行 `/compact`，生成的摘要会引用已写入记忆的内容
4. **确认** — 报告写了哪些记忆文件、压缩完成

## 使用方式

对 Claude 说：
- `/compact`（安装了此 skill 后会自动增强）
- `"压缩上下文，保留重要决策"`
- `"compact 但别丢掉这次的决策"`

## 附带脚本

| 脚本 | 功能 |
|---|---|
| `scripts/pre_compact_extract.py` | 分析会话 JSONL 文件，提取值得记忆的内容草稿 |

## 源码依据

- `src/services/compact/autoCompact.ts`: 触发阈值（13k buffer）、circuit breaker（3次失败）
- `src/services/compact/compact.ts`: `compactConversation(customInstructions?)` 接受自定义指令
- `src/services/autoDream/consolidationPrompt.ts`: 记忆蒸馏的 4 阶段流程
- `src/memdir/memdir.ts`: MEMORY.md 格式规范
