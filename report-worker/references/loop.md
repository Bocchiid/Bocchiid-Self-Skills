# 闭环、闸门与恢复

## 8 个阶段

```text
ANALYZE → COLLECT → ORGANIZE → PLAN → PLAN_FREEZE
→ EXECUTE → WRITE → REVIEW → REVISE
↺ 受影响的上游
→ DONE / BLOCKED / WAITING_USER
```

| 阶段 | 目标 | 闸门 |
| --- | --- | --- |
| ANALYZE | 盘点已有材料、列缺口、确认真实方案 | 关键材料/问题已列出 |
| COLLECT | 用户补材料/数据/截图 | 缺口有结论（补/没有） |
| ORGANIZE | 整理证据、数据、来源 | 每个目的至少一条证据 |
| PLAN | 调 planner 出执行卡/plan.json | `verify.py plan` |
| PLAN_FREEZE | 用户确认实际方案/目的/交付 | 用户确认 + `freeze --confirm` |
| EXECUTE | 按步骤操作、截图、验收 | 步骤/证据验收 |
| WRITE | 调 writer 出报告 | 报告可打开、格式跟模板 |
| REVIEW | 调 reviewer 出审核报告 | `verify.py review` |
| REVISE | 核实并路由发现 | 修复清单 |
| DONE | DoD 满足 | `verify.py dod` |
| BLOCKED | 预算/权限/环境/人工 | 阻塞说明 |
| WAITING_USER | 等用户补材料/做物理步骤/确认 | 用户回传 |

## 冻结

**未冻结不执行。** 用户确认前只做分析、收集、整理、规划。
用户改方案就回 PLAN；不偷偷改计划继续。

## 步骤闸门

每步至少一条可观察验收：

- `exit_code` / `stdout_regex` / `stderr_regex`
- `file_exists` / `file_contains` / `json_field`
- `visual`（交截图验收）
- `manual`（用户确认）

`partial` 不当 `pass`；先截图验收或让用户确认。

## 证据闸门

- 文件存在、SHA256 一致、状态 `通过`；
- L1 全部通过才进 WRITE；
- 截图只截核心：代码截改动段，终端截命令+结果，GUI 截目标面板；
- 截图合格但结果不符：先排错，不重拍同样结果。

## 报告 / 审核闸门

- 报告存在、非空、能打开、扩展名跟模板；
- 审核结论 `通过` 或 `有条件通过` 且只剩建议/可选；
- 零正确性错误、零要求未满足、零模板保护问题；
- 模板/评分表冲突（如参考文献没位置）默认不保留，不扣分，单列记录。

## DoD

- 计划冻结；目的全覆盖；
- L1 证据全通过；
- reviewer 通过/仅有条件通过且只剩建议；
- 硬要求 100%；
- 报告可打开、格式一致；
- 证据可追溯；
- 最后一轮无新增阻断。

## 路由

| 发现 | 责任方 | 下一步 |
| --- | --- | --- |
| 数据/结果错误 | operator | EXECUTE |
| 截图缺字段/模糊/错步 | operator | 补拍 |
| 内容浅/缺要求/表述错 | writer | WRITE |
| 格式/题注/引用/版面/保护区 | writer | WRITE |
| 计划缺步骤/证据/目的 | planner | PLAN |
| 需求冲突/无法判断 | human | WAITING_USER |
| 只有建议/可选 | none | DONE |

先核实再路由；reviewer 误报标“需人工复核”；同一问题 2 轮未修复 → BLOCKED。
只重跑受影响的下游，不整场重来。

## 预算

- 报告轮次默认 3；
- 单步重试默认 3；
- 证据补拍默认 2 轮/阶段；
- 动作数/墙钟时间/日志大小可配；
- 超预算 → BLOCKED，不偷偷继续。

## 崩溃恢复

- `state.json`/`evidence.json` 原子写 + `.bak`；
- 动作先写 intent，结束后写结果并清 intent；
- 残留 intent = 可能做了一半；`actions.py list --json` 查看，`resolve` 标记；
- `worker.py doctor` 查状态损坏、残留 intent、心跳、日志超预算、残留 `.tmp`；
- `worker.py heartbeat` 更新心跳；
- 恢复顺序：`doctor` → 处理 in-flight → `status`/`next`；不要重新 init；
- 不杀宿主进程/窗口；不删任务目录外文件。
