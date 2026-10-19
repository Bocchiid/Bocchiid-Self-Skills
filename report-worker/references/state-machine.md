# 状态机与断点续跑

## 状态

| 状态 | 含义 | 主要角色 |
| --- | --- | --- |
| `INIT` | 建目录、探测环境、确认工作区 | 总控 |
| `PLAN` | 生成执行卡 + `plan.json` | planner |
| `PLAN_FREEZE` | 用户确认实际方案，冻结计划 | 总控 + 用户 |
| `EXECUTE` | 执行下一个步骤 | operator |
| `STEP_VERIFY` | 校验这一步的退出码/输出/文件/画面 | operator |
| `EVIDENCE_REVIEW` | 按阶段验收 L1 证据 | screenshot reviewer |
| `RECAPTURE` | 补拍/重做缺口 | operator |
| `WRITE` | 写 `报告-vN` | writer |
| `REVIEW` | 审核 `报告-vN` | reviewer |
| `TRIAGE` | 核实并路由审核发现 | triage |
| `WAITING_USER` | 人工接管/等待用户决定 | 用户 |
| `DONE` | DoD 满足 | — |
| `BLOCKED` | 预算/权限/环境/人工阻塞 | — |

## 允许的迁移

```text
INIT            -> PLAN | BLOCKED
PLAN            -> PLAN_FREEZE | WAITING_USER | BLOCKED
PLAN_FREEZE     -> EXECUTE | PLAN | WAITING_USER | BLOCKED
EXECUTE         -> STEP_VERIFY | EVIDENCE_REVIEW | WAITING_USER | BLOCKED
STEP_VERIFY     -> EXECUTE | EVIDENCE_REVIEW | RECAPTURE | WAITING_USER | BLOCKED
EVIDENCE_REVIEW -> WRITE | RECAPTURE | WAITING_USER | BLOCKED
RECAPTURE       -> EVIDENCE_REVIEW | EXECUTE | WAITING_USER | BLOCKED
WRITE           -> REVIEW | WAITING_USER | BLOCKED
REVIEW          -> TRIAGE | WAITING_USER | BLOCKED
TRIAGE          -> EXECUTE | RECAPTURE | WRITE | PLAN | DONE | WAITING_USER | BLOCKED
WAITING_USER    -> EXECUTE | RECAPTURE | PLAN | WRITE | REVIEW | BLOCKED
BLOCKED         -> PLAN | EXECUTE | WAITING_USER
DONE            -> (end)
```

`worker.py advance` 会拒绝非法迁移。不要手改 `state.json` 绕过；确实需要时先说明原因。

## 一次执行循环

```text
worker.py next
  -> 读 prompts/02_operator.md
  -> 执行当前步骤
  -> 写 operator.result.json
  -> worker.py record --role operator ...
  -> verify.py step
  -> 通过：worker.py complete-step --step Sx
  -> 该阶段还有步骤：回 EXECUTE
  -> 没有步骤：advance --to EVIDENCE_REVIEW
```

## 轮次与预算

`state.budgets`：

| 键 | 默认 | 用途 |
| --- | --- | --- |
| `max_report_rounds` | 3 | 报告写-审-修最多几轮 |
| `max_step_attempts` | 3 | 单步失败最多重试几次 |
| `max_evidence_rounds` | 2 | 单阶段补拍最多几轮 |
| `max_actions` | 500 | 动作总数上限 |
| `max_minutes` | 240 | 墙钟时间上限 |
| `heartbeat_seconds` | 60 | 心跳间隔；`doctor` 超过 2 倍报警 |
| `max_log_bytes` | 50MB | 单日志轮转阈值 |
| `max_log_files` | 500 | 日志文件数参考上限（不自动删） |

达到上限：停止并输出 `BLOCKED`，不要偷偷继续。

## 断点续跑

任何角色都可以停。恢复时先诊断：

```bash
worker.py doctor
worker.py status
worker.py next
```

如果状态损坏：`worker.py doctor --recover`。如果有残留动作：看
`_worker/actions/*.intent.json`，用 `actions.py resolve` 标记，不要直接重跑。
详细见 `crash-recovery.md`。

`next` 会给出：

- 当前阶段；
- 该读的提示词；
- 该写的文件；
- 该跑的校验；
- 建议的下一步命令。

换 Agent/换会话后，不要从头重来；先读 `state.json` 和 `roles/*.result.json`。

## 版本

- 计划：`v0.9（待确认）` → `v1.0（已确认）`；变更 `v1.1`/`v2.0`，不覆盖旧版。
- 报告：`报告-v1`、`报告-v2`，不覆盖。
- 审核：`报告-审核报告-v1.md`、`-v2.md`，不覆盖。
- 截图：重名自动 `_v2`，不覆盖。

## 常见错误

| 错误 | 处理 |
| --- | --- |
| 未冻结就执行 | 回 `PLAN_FREEZE`，让用户确认 |
| 跳过证据验收直接写 | 回 `EVIDENCE_REVIEW` |
| 报告轮次不增 | `worker.py round --next` |
| 同一问题反复 | 标 `BLOCKED`，让用户决定 |
| 状态文件损坏 | 从 `_worker/backups/` 恢复，或重新 `init --force`（会丢历史） |
