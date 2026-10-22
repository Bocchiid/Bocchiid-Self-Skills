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
| PLAN | 调 planner 出执行卡 + 实验指导书 + plan.json | `verify.py plan` + `artifacts` |
| PLAN_FREEZE | 用户确认实际方案/目的/交付 | 用户确认 + `freeze --confirm` |
| EXECUTE | 按步骤操作、截图、分阶段验收 | 步骤/证据验收 + `execution` |
| WRITE | 调 writer 出报告 | 报告可打开、格式跟模板 |
| REVIEW | 调 reviewer 出审核报告 | `verify.py review` |
| REVISE | 核实并路由发现 | 修复清单 |
| DONE | DoD 满足 | `verify.py dod` |
| BLOCKED | 预算/权限/环境/人工 | 阻塞说明 |
| WAITING_USER | 等用户补材料/做物理步骤/确认 | 用户回传 |

## ANALYZE 闸门（硬）

进入 PLAN 前必须：

- `材料清单.md` 存在，含“已有/还缺/用户确认”；
- `_worker/decisions.json` 至少有 1 条用户决策（`worker.py decide` 写入）；
- 模板/评分表冲突在 `plan.json.conflicts` 里没有 `pending`。

```bash
python worker.py gate --name analyze
```

没通过不允许 `advance --to PLAN`。

## 规划产出闸门（硬）

进入 PLAN_FREEZE 前必须：

1. 五项交互决策已用 `worker.py decide` 落盘：
   `code_policy`、`delivery.format`、`delivery.editor`、`template_editable`、
   `formula_editable`（缺一项就拒绝，不能靠沉默跳过）；
2. 同时存在且非空：
   - `实验执行卡.md`（即开即用版）；
   - `实验指导书.md`（完整版；旧名 `实验规划书.md` 也接受）。

```bash
python verify.py decisions
python verify.py artifacts
```

只出执行卡会被拒绝。不要用“用户只要执行卡”绕过——用户要的是能确认方案和写报告，
执行卡本身不承担这个功能。

## 冻结

**未冻结不执行。** 用户确认前只做分析、收集、整理、规划。
用户改方案就回 PLAN；不偷偷改计划继续。

冻结前把方案/大纲发给用户确认：目的、实际步骤、环境、代码处理方式、交付格式、
报告结构。

## 执行闸门（硬）

进入 WRITE 前必须：

- 计划步骤全部完成或明确跳过；
- 有证据时，L1 全部通过；
- `截图验收.md` 存在，且没有“不通过/待补拍”；
- 无证据的纯文字任务：在计划里说明清楚，允许放行。

```bash
python verify.py execution
```

**截图没验完不能进 writer。** 验收后先给“继续下一阶段 / 修改执行卡 / 补证据”
三个选项，不要只问“要不要进入 writer”。

计划里的 `conflicts` 用 `skip|keep|pending`：
`pending` 不允许冻结；`skip` 不写不扣分；`keep` 按 location 写/审。

## 步骤闸门

每步至少一条可观察验收：

- `exit_code` / `stdout_regex` / `stderr_regex`
- `file_exists` / `file_contains` / `json_field`
- `visual`（交截图验收）
- `manual`（用户确认）

`partial` 不当 `pass`；先截图验收或让用户确认。

## 证据闸门

- 文件存在、SHA256 一致、状态 `通过`；
- L1 全部通过、`截图验收.md` 无待补拍才进 WRITE；
- 截图只截核心：代码截改动段，终端截命令+结果，GUI 截目标面板；
- 截图合格但结果不符：先排错，不重拍同样结果。

## 报告 / 审核闸门

- 报告存在、非空、能打开、扩展名跟模板；
- 审核结论 `通过` 或 `有条件通过` 且只剩建议/可选；
- 零正确性错误、零要求未满足、零模板保护问题；
- 模板/评分表冲突（如参考文献没位置）默认不保留，不扣分，单列记录。

## DoD

- 计划冻结；五项交互决策已落盘；执行卡 + 实验指导书都在；目的全覆盖；
- L1 证据全通过；截图验收无待补拍；
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
| 模板骨架/1×1 外层表/公式 OMML/兼容模式 | writer | WRITE |
| WPS 实机问题（未实测或确认存在） | human | WAITING_USER |
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
