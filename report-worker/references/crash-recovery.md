# 崩溃恢复与日志管理

实验机器可能死机、断电、重启、磁盘满、Agent 被中断。worker 要保证：

1. 已经完成的步骤不会因为崩溃而“看起来没做”；
2. 正在执行的动作有意图记录，恢复时知道它可能做到一半；
3. 日志、证据、状态都能从磁盘恢复；
4. 不盲目重跑破坏性/不可逆动作。

## 崩溃后还剩什么

| 文件 | 作用 | 崩溃后 |
| --- | --- | --- |
| `_worker/state.json` | 当前阶段、步骤、轮次 | 原子写入，保留 `.bak` |
| `_worker/state.json.bak` | 上一版状态 | 主文件损坏时回退 |
| `_worker/actions.jsonl` | 所有动作的追加日志 | 已 fsync |
| `_worker/actions/<id>.intent.json` | 动作开始前的意图 | 崩溃时残留 = 可能做了一半 |
| `_worker/actions/<id>.pid` | 子进程 PID | 用来判断进程是否还活着 |
| `_worker/actions/<id>.json` | 动作结果 | 有它说明动作已记录完成 |
| `_worker/logs/<id>.stdout.txt` | 命令标准输出 | 可能截断，但保留已有内容 |
| `_worker/logs/<id>.stderr.txt` | 命令标准错误 | 同上 |
| `_worker/logs/session.log` | 人类可读事件流 | 追加 + fsync |
| `_worker/logs/events.jsonl` | 机器可读事件流 | 追加 + fsync |
| `_worker/evidence.json` | 证据清单 + SHA256 | 原子写入，保留 `.bak` |
| `_worker/logs/crashes/doctor-*.json` | 每次恢复诊断 | 保留 |

## 恢复流程

### 1. 先诊断，不改状态

```bash
python "<SKILL_DIR>/scripts/worker.py" --workspace "<WS>" doctor
```

输出：

- `issues`：状态损坏、心跳超时、残留 intent、证据清单损坏、日志超预算、残留 `.tmp`/锁文件；
- `hints`：已有通过动作但步骤还没标记完成（应核实后 `complete-step`，不要盲重跑）；
- `in_flight`：未完成的动作（ID、步骤、命令、PID）；
- `log_bytes`：日志占用；
- `ok`：是否没有发现问题。

**不要**在诊断前直接重跑步骤。

### 2. 状态损坏就恢复

```bash
python "<SKILL_DIR>/scripts/worker.py" --workspace "<WS>" doctor --recover
```

- 主 `state.json` 读不了时，从 `.bak` 恢复；
- 写 `_worker/recovery.json` 和 `_worker/logs/crashes/doctor-*.json`；
- 不会自动删 intent；in-flight 动作仍需人工判断。

### 3. 处理 in-flight 动作

看：

```bash
python "<SKILL_DIR>/scripts/actions.py" --workspace "<WS>" list --json
```

或直接读 `_worker/actions/<id>.intent.json`、`.pid`、前后截图、stdout/stderr。

判断：

| 情况 | 处理 |
| --- | --- |
| 动作其实已经完成（输出/截图/文件都在） | `actions.py resolve --id <id> --status done` |
| 明确失败 | `resolve --status failed`，再按失败分支重试 |
| 不确定做没做 | `resolve --status unknown`，标记需人工/重跑前先检查；不要直接重跑不可逆动作 |
| 进程还活着 | 先看它是否还在正常工作；不要杀宿主进程；实验进程可等待或按计划处理 |

```bash
python "<SKILL_DIR>/scripts/actions.py" --workspace "<WS>" resolve \
  --id A012345 --status unknown --note "机器重启，命令是否完成未知"
```

`resolve` 会写一条结果、清掉 intent、记日志；不会重跑，也不等于“步骤验收通过”。
如果标 `done`，仍要用 `verify.py step` 或人工核对证据后再 `complete-step`。

### 4. 恢复状态机

```bash
python "<SKILL_DIR>/scripts/worker.py" --workspace "<WS>" status
python "<SKILL_DIR>/scripts/worker.py" --workspace "<WS>" next
```

按 `next` 继续。**不要**重新 `init`；`init --force` 会丢历史。

### 5. 心跳

长步骤/长等待前后：

```bash
python "<SKILL_DIR>/scripts/worker.py" --workspace "<WS>" heartbeat
```

`doctor` 会在心跳超过 `2 × heartbeat_seconds`（默认 120s）且阶段不是
`DONE`/`BLOCKED` 时提示。心跳只说明“worker 还活着”，不代表实验没崩。

## 不同崩溃场景

### Agent 被中断 / 终端关闭

- 状态已保存到最后一个 checkpoint；
- 当前命令可能还在跑（如果子进程没被杀），也可能已经死；
- 先 `doctor` + `list --json`，看 PID 和输出。

### 机器断电 / 重启

- 子进程全死；
- intent 残留；
- 文件可能截断（pcap、日志、截图）；
- 先检查文件完整性（大小、能否打开），再决定补拍/重做。

### 磁盘满

- 原子写可能失败；旧 `state.json`/`.bak` 仍在；
- 先清理**任务目录内**的旧日志/临时文件（用户确认），不要删任务外文件；
- `worker.py logs --rotate` 可轮转会话日志；
- 释放空间后 `doctor` 再继续。

### VM/实验环境崩溃

- host 的 state/logs 还在；
- guest 内 pcap/日志/截图可能不完整；
- 重新启动 guest 后，先检查受影响步骤的证据，再补做；
- 不要用旧图冒充本次结果。

### 报告写一半 Word 崩溃

- writer 的工作副本/中间产物在报告目录；
- 从模板重新生成工作副本，不要直接改坏的原文件；
- `报告-vN` 不覆盖，失败版本保留；
- writer 应先把内容写到 `报告-vN.tmp.<ext>`，自检后再原子改名；
  `worker.py doctor` 会把残留 `.tmp`/`~$*` 锁文件列为问题；
- 确认上一版 `报告-v(N-1)` 完好后，再重跑 writer。

### 计划/审核 md 写一半

- planner/reviewer 先写 `.tmp` 再改名；
- 残留 `.tmp` 不要当正式产物；
- 如果 `plan.json` 损坏，`verify.py plan` 会失败，回 planner 重写；
- 旧版本计划/审核报告不覆盖，按 `v1.1`/`-v2` 递增。

## 日志管理

### 目录

```text
_worker/
├── logs/
│   ├── session.log          # 人类可读
│   ├── events.jsonl         # 机器可读
│   ├── A...stdout.txt       # 每条命令
│   ├── A...stderr.txt
│   └── crashes/             # doctor 诊断
├── actions/
│   ├── A...json             # 动作结果
│   ├── A....intent.json     # 未完成动作
│   ├── A....pid
│   └── last.json
└── actions.jsonl            # 所有动作的汇总
```

### 写入策略

- 状态/证据/结果：临时文件 + fsync + `os.replace`，保留 `.bak`；
- 事件/动作日志：`O_APPEND` + fsync；
- 每条命令的 stdout/stderr 单独文件，避免互相覆盖；
- 截图/证据文件名不覆盖，重名自动 `_v2`；
- 命令和输出里的密码/token 做脱敏；不要把密码写进命令行。

### 轮转

```bash
python "<SKILL_DIR>/scripts/worker.py" --workspace "<WS>" logs --list
python "<SKILL_DIR>/scripts/worker.py" --workspace "<WS>" logs --tail 40
python "<SKILL_DIR>/scripts/worker.py" --workspace "<WS>" logs --rotate
```

- 单文件超过 `max_log_bytes`（默认 50MB）时轮转为 `.1`、`.2`、`.3`；
- 不自动删除日志；清理由用户决定；
- 不要把整个日志目录提交到 git（`.gitignore` 已忽略 `.venv/`，日志在任务目录）。

### 保留什么

- 失败/异常的输出和截图：报告“问题与解决”要用；
- pcap/原始数据/脚本：复现要用；
- `doctor-*.json`：崩溃恢复记录；
- 审核报告每一轮：不要覆盖。

## 检查清单

- [ ] 崩溃后先 `doctor`，没有直接重跑
- [ ] in-flight 动作已 `resolve` 或明确等待
- [ ] 状态从 `.bak` 恢复后，`status/next` 正常
- [ ] 截断的 pcap/日志/截图已识别，没当完好证据
- [ ] 日志没有超过预算，必要时已轮转
- [ ] 没有删任务目录外的文件
- [ ] 没有杀宿主 Agent 的进程/窗口
