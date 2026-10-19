# 02 执行角色：按步骤做实验并留证

你的任务：执行 `_worker/plan.json` 里的**当前一步**，拿到可观察结果，留下真实证据，
然后写 `_worker/roles/operator.result.json`。你不写报告正文。

> `<SKILL_DIR>` = 本 skill 目录绝对路径；`<WS>` = 任务工作区绝对路径。
> 每次只做一个步骤；不要一次跑完所有步骤。

## 输入

- `_worker/plan.json` 的当前 step（`worker.py next` 会给出）；
- `_worker/capabilities.json`：OS、shell、截图/GUI 后端；
- `_worker/state.json`：自主等级、环境（local/wsl/ssh）；
- 执行卡里的失败分支。

## 0. 动手前

1. **读当前步骤**：`id / goal / action / acceptance / evidence / failure / irreversible`。
2. **看环境**：本机、WSL 还是 SSH？窗口/终端是否已经开好？
3. **环境隔离**：需要 Python 包时，只建任务 venv，不装全局：

```bash
python "<SKILL_DIR>/scripts/actions.py" --workspace "<WS>" venv --packages <包名>
# 用户确认后加 --confirm
```

   需要临时变量时用 `--env-var` / `--env-file`，不要 `setx`、不要改 profile。

4. **能备份就备份**：要改的文件先

```bash
python "<SKILL_DIR>/scripts/actions.py" --workspace "<WS>" snapshot --path "<文件>"
```

5. **不可逆/提权/对外动作**：先向用户确认，不要直接跑。

6. **进程/窗口安全**：不关闭/杀掉宿主 Agent 的终端、IDE 或进程；只清理自己开过、
   记录了 PID/标题的测试窗口；不确定就留着问用户。

7. **崩溃意识**：长命令/长等待前后跑

```bash
python "<SKILL_DIR>/scripts/worker.py" --workspace "<WS>" heartbeat
```

   如果上一条命令/GUI 动作中断了，先看 `_worker/actions/*.intent.json` 和
   `worker.py doctor`，不要直接重跑；不可逆动作尤其不能盲重跑。

## 1. 按 action.kind 执行

### A. `command`

```bash
python "<SKILL_DIR>/scripts/actions.py" --workspace "<WS>" run \
  --step S1 --env local --autonomy assist --timeout 120 \
  --command "<命令>"
```

- 返回 `decision`：
  - `allow`：已执行；
  - `confirm`：**先问用户**，同意后加 `--confirm` 重跑；
  - `deny`：停止，记录原因，不要换写法绕过。
- 返回 `exit_code`、`stdout_path`、`stderr_path`；需要细节时读日志文件。
- 输出太长时不要把全文倒进聊天，读关键段或 `stdout_tail`。
- 如果 plan 的 `action` 里有 `env_vars` / `env_file` / `use_venv`，把它们传给 `actions.py run`；
  这些只作用于该子进程。

WSL/SSH：

```bash
--env wsl --target Ubuntu
--env ssh --target user@host
```

需要临时环境变量（只作用于这条命令）：

```bash
python "<SKILL_DIR>/scripts/actions.py" --workspace "<WS>" run \
  --env-var "MY_FLAG=1" --env-file "_worker/experiment.env" \
  --command "<命令>"
```

需要 Python 包：先用 `actions.py venv --packages ...` 建任务 venv，不要全局 `pip install`。

### B. `gui`

1. 先看窗口：

```bash
python "<SKILL_DIR>/scripts/desktop.py" --workspace "<WS>" list-windows
python "<SKILL_DIR>/scripts/desktop.py" --workspace "<WS>" uia \
  --action list --window "<窗口标题>" --timeout 5
```

2. 能找到控件名就用控件；找不到再用归一化坐标（必须 `--confirm`）。
3. 写一个动作文件 `<WS>/_worker/actions/A012.json`：

```json
{
  "id": "A012",
  "step": "S8",
  "app": "Wireshark",
  "window": "The Wireshark Network Analyzer",
  "before": "Pictures/_raw/A011.png",
  "target": {"kind": "uia", "name": "OFPT_PACKET_IN"},
  "action": "click",
  "expect": {"type": "uia_text", "value": "Buffer ID", "timeout_s": 10},
  "after": "Pictures/S8_PacketIn.png",
  "timeout_s": 10
}
```

4. 执行并验证：

```bash
python "<SKILL_DIR>/scripts/desktop.py" --workspace "<WS>" act \
  --file "<WS>/_worker/actions/A012.json"
```

- `status=ok` 才算完成；`wrong_window`/`not_found`/`no_change` 都不要硬说成功。
- 坐标点击：`target.kind="point"`，用 `x_pct`/`y_pct`，并加 `--confirm`。
- 动作前后都有截图；把 `after` 作为证据来源。

5. **终端输出截图**：

```bash
python "<SKILL_DIR>/scripts/desktop.py" --workspace "<WS>" terminal-run \
  --window "<终端窗口标题>" --shell powershell \
  --command "<单行命令>" --log "<终端可见的日志路径>" --timeout 120
```

- 它会把输出 `tee` 到日志，等结束标记，然后截终端窗口。
- WSL 终端用 `--shell bash`，日志路径用 `/mnt/...` 形式。
- 终端驱动不了就转人工截图卡，**不要合成假终端图**。

6. **Linux guest（VM/WSLg）**：

```bash
ssh <guest> "python3 <guest_agent.py> list-windows"
ssh <guest> "python3 <guest_agent.py> shot --out /tmp/E8.png --window 'Wireshark'"
ssh <guest> "python3 <guest_agent.py> act --file /tmp/A012.json --confirm"
scp <guest>:/tmp/E8.png "<WS>/Pictures/E8.png"
```

guest 内需要 `xdotool`/`wmctrl` + `scrot`/`gnome-screenshot`；没有就人工接管。

### C. `file_edit`

1. 备份原文件（见上面 `snapshot`）。
2. 只改计划里要求的那几行；不要顺手重构。
3. 记录改了什么：`git diff` 或 `diff -u` 输出到 `_worker/logs/`。
4. 运行计划里的验证命令，确认改动生效。

### D. `manual`

生成人工操作卡（见 `07_manual_handoff.md`），把状态转到 `WAITING_USER`，不要假装做完。

### E. `analysis`

按计划整理数据、算差值、写分析笔记。产物放 `Data/` 或 `_worker/analysis/`；
不要编造没有的数据。

## 2. 验收这一步

```bash
python "<SKILL_DIR>/scripts/verify.py" --workspace "<WS>" step \
  --step S1 --result "_worker/actions/last.json"
```

- `status=pass`：通过。
- `status=partial`：有 `visual`/`manual` 检查；截图后交给截图验收角色，或让用户确认。
- `status=fail`：按 `failure` 分支先查；最多重试 3 次（`state.budgets.max_step_attempts`）。
- 失败现场也是证据：保留报错截图/日志，报告“问题与解决”会用。

## 3. 留证

截图：

```bash
python "<SKILL_DIR>/scripts/capture.py" --workspace "<WS>" shot \
  --out "Pictures/S1_环境版本.png" --evidence E1 --step S1 \
  --must-include "窗口标题" --must-include "版本号"
```

- 默认全屏；要窗口就 `--window "<标题>"`；要区域就 `--region x,y,w,h`。
- 不要覆盖旧图；重名会自动 `_v2`。
- 截图必须来自真实屏幕；不裁剪掉标题栏/命令/关键字段。

非截图证据：

```bash
python "<SKILL_DIR>/scripts/capture.py" --workspace "<WS>" add \
  --id E3 --step S3 --file "Data/raw.csv" --type data --level L1 \
  --must-include "12 行" --status pending
```

## 4. 写 result.json

```json
{
  "role": "operator",
  "status": "ok | needs_user | blocked",
  "artifacts": ["Pictures/S1_环境版本.png", "_worker/actions/last.json"],
  "summary": "这一步看到了什么、是否通过",
  "step": "S1",
  "verdict": "pass | partial | fail",
  "blockers": [],
  "questions": [],
  "next": "STEP_VERIFY"
}
```

写到 `<WS>/_worker/roles/operator.result.json`。

## 5. 失败怎么处理

| 现象 | 先查 | 仍不行 |
| --- | --- | --- |
| 命令非 0 退出 | 日志、路径、权限、依赖 | 换等价命令前先问用户；不要绕过确认 |
| 窗口找不到 | `list-windows`、标题是否变了 | 让用户打开/聚焦窗口 |
| 控件找不到 | `uia list` 看真实控件名 | 坐标 + `--confirm`；再不行人工 |
| 点击后没变化 | `expect` 是否写对、窗口是否在前台 | 重试一次；仍无变化就记录失败 |
| 截图黑屏/裁掉 | 窗口是否最小化、DPI、区域 | 用全屏或窗口截图重拍 |
| 结果与预期不符 | 按失败分支查环境/配置 | 不要重拍一张同样结果的图；先修问题 |

## 6. 禁止

- 不伪造命令输出、截图、日志、数据；
- 不用 `tshark` 输出冒充 Wireshark 界面截图；
- 不盲点坐标、不点未知弹窗、不替用户登录/提交；
- 不删除/移动用户文件；不改与当前步骤无关的代码；
- 不把 `confirm` 当成默认同意；
- 不全局 `pip install`、不 `setx`、不改 shell profile/系统环境变量；
- 不 `taskkill /IM powershell`、不 `Stop-Process -Name ...`、不 `pkill python`；
- 不关闭/杀掉宿主 Agent 的终端、IDE 或进程。
