# session-dream

手动触发记忆蒸馏：从当前会话提取关键决策和发现，写入 MEMORY.md 主题文件。

## 解决的问题

Claude Code 的 `autoDream` 服务在后台自动蒸馏记忆，但需要满足 24 小时间隔 + 5 个会话的条件才会触发。这个 skill 让你随时手动执行同样的蒸馏——尤其适合在长会话结束、上下文即将压缩之前使用。

## 四阶段蒸馏流程

遵循 `services/autoDream/consolidationPrompt.ts` 中的真实流程：

| 阶段 | 动作 |
|---|---|
| **1. Orient** | 扫描现有记忆文件，避免创建重复内容 |
| **2. Gather** | 从当前会话识别高价值信号 |
| **3. Consolidate** | 写入/更新主题文件，合并而非复制 |
| **4. Prune & Index** | 更新 MEMORY.md 指针，保持 ≤200 行 |

## 使用方式

对 Claude 说：
- `"dream"`
- `"/dream"`
- `"保存这次会话的关键发现"`
- `"会话快结束了，蒸馏一下记忆"`

## 附带脚本

| 脚本 | 功能 |
|---|---|
| `scripts/session_extract.py` | 从 JSONL 会话文件中提取对话文本，便于离线分析 |

## 与 compact-with-memory 的区别

| | session-dream | compact-with-memory |
|---|---|---|
| 触发时机 | 任意时刻，会话结束前 | 执行 `/compact` 时 |
| 是否压缩 | 否，只提取记忆 | 是，先提取再压缩 |
| 适用场景 | 会话中途存档 | 上下文即将满时 |

## 源码依据

- `src/services/autoDream/consolidationPrompt.ts`: 真实的 4 阶段 prompt 结构
- `src/services/autoDream/autoDream.ts`: 触发条件（`minHours: 24`, `minSessions: 5`）
- `src/memdir/memoryTypes.ts`: memory frontmatter 格式和 4 种类型定义
