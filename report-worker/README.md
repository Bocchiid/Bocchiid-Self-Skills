# report-worker

把 **规划 → 执行 → 取证 → 写报告 → 审核 → 修复** 串成一个闭环的通用 Agent Skill。

它不绑定 Claude Code，也不绑定某一家 Agent。只要能读写文件、执行命令，
Claude Code、Codex、DSH、豆包、WorkBuddy 等都可以用；不能执行命令的平台，
把 `prompts/` 里的提示词复制过去也能跑。

## 它解决什么

- 指导书/模板只有“做什么”，没有“先做什么、做到什么算成功”；
- 实验做完了才发现少截图，只能返工；
- 报告写完没人审，或者审了不知道怎么改；
- 多轮修改靠人搬运，改了执行忘了改报告、改了报告忘了补证据；
- 换 Agent/换会话后接不上之前的进度。

worker 的做法：

1. 用 `report-planner` 生成执行卡和可执行的 `plan.json`；
2. 按步骤真正执行（GUI/命令/改代码），每步验收、留证；
3. 按阶段验收截图，不通过只补拍缺口；
4. 用 `report-writer` 写报告；
5. 用 `report-reviewer` 审核；
6. 把审核发现分派回执行/证据/写作/规划，只重跑受影响的下游；
7. 直到“审核通过 + 零阻断”，或触发停止条件。

## 安装

把 **四个目录** 一起复制到技能目录/知识库：

```text
report-planner/
report-writer/
report-reviewer/
report-worker/
```

只复制 `report-worker` 也能跑，但 planner/writer/reviewer 的规则不在本地，
需要你在任务目录的 `_worker/skills.json` 里指定它们的路径。

### 各平台怎么加载

| 平台能力 | 做法 |
| --- | --- |
| 支持技能目录 | 加载 `report-worker/SKILL.md` |
| 只能粘贴系统提示 | 粘贴 `prompts/00_conductor.md`，按阶段再粘贴角色提示 |
| 能执行命令 | 直接跑 `python scripts/worker.py ...` |
| 不能执行命令 | 纯 Markdown 人工模式；仍按 `SKILL.md` 的闸门走 |

不同产品的技能目录名不一样，按该产品文档放；本 skill 不假设固定路径。
如果平台支持环境变量，设置 `REPORT_SKILLS_DIR` 指向包含三个依赖 skill 的父目录最稳。

## 依赖

- Python 3.8+（标准库为主）；
- 截图：Pillow（Windows 已装更好；Linux 可用 `scrot`/`gnome-screenshot`/`grim`）；
- Windows GUI：`pywin32`（基础键鼠/窗口）；可选 `pywinauto`（控件树）、`mss`、`opencv-python`；
- Linux guest GUI：`xdotool` + `wmctrl` + `scrot`（或 `gnome-screenshot`）；
- 报告：`python-docx`；`.doc` 需要 Word COM（Windows）或 LibreOffice。

缺依赖不会让整个流程崩：`env.py --install-plan` 会列出缺什么，worker 会降级或转人工。

```bash
python scripts/env.py --probe
python scripts/env.py --install-plan
python scripts/env.py --write /path/to/task
```

## 快速开始

```bash
# 1. 初始化
python scripts/worker.py --workspace /path/to/task init --autonomy assist --env local

# 2. 写能力清单
python scripts/env.py --write /path/to/task

# 3. 看下一步
python scripts/worker.py --workspace /path/to/task next

# 4. 规划完成后，用户确认，再冻结
python scripts/verify.py --workspace /path/to/task plan
python scripts/worker.py --workspace /path/to/task freeze --confirm

# 5. 之后每一步都按 next 的提示走
python scripts/worker.py --workspace /path/to/task status
```

在聊天里，最小用法：

> 这是实验指导书、报告模板和我的口述。请用 `report-worker` 帮我做完实验并写出报告：
> 先规划，规划确认后再执行；截图按阶段验收；报告写完后用 reviewer 审，改到通过为止。

## 自主等级

| 等级 | 行为 |
| --- | --- |
| `observe` | 只读、只规划，不执行 |
| `assist`（默认） | 安全命令/工作区写入自动；冻结计划、破坏性、提权、对外、凭证类动作确认 |
| `auto` | 工作区内自动；破坏性/提权/对外仍确认 |
| `full` | 仅隔离 VM/沙箱，不用于本机真实环境 |

## 目录结构

```text
report-worker/
├── SKILL.md
├── README.md
├── prompts/              # 可复制的角色提示词
├── schemas/              # plan/state/evidence/action/role-result
├── references/           # 状态机、GUI、验收、路由、恢复、可移植性
├── gui_profiles/         # Wireshark/MiniEdit/终端等操作提示
└── scripts/              # env/worker/actions/capture/desktop/uia/guest_agent/verify
```

任务目录产物：

```text
<task>/
├── 实验执行卡.md
├── 实验规划书.md          # 可选
├── 截图验收.md
├── 人工操作卡.md          # 需要人工接管时
├── Pictures/
├── Data/
├── 报告/
└── _worker/
    ├── state.json / state.json.bak
    ├── actions/            # 动作结果 + 未完成 intent/pid
    ├── logs/               # session.log / events.jsonl / stdout/stderr
    ├── roles/*.result.json
    ├── backups/
    └── recovery.json       # 崩溃恢复记录（如有）
```

## 跨 Agent 的边界

- 不依赖 `Skill`/子代理/某个工具名；
- 角色之间用 `result.json` 和 `state.json` 交接，换平台/换会话可续跑；
- 平台不能看图：截图验收转人工；
- 平台没有子代理：单会话顺序执行；
- 平台不能执行命令：纯 Markdown 人工模式。

## 环境隔离（不破坏用户环境）

- Python 依赖装进任务目录的 `.venv`，不装全局；`actions.py run` 自动优先用 venv，
  `capture.py`/`desktop.py`/`verify.py` 缺依赖时也会自动用 venv 重跑；
- 环境变量用 `actions.py run --env-var` / `--env-file`，只作用于子进程；
- 不改系统环境变量、shell profile、全局 PATH；
- 不在 Windows 宿主装系统包/驱动/服务；WSL/VM 内 `apt install` 先确认；
- 所有临时文件在任务目录或 `_worker/` 内；
- **不关闭/杀掉宿主 Agent 的终端、IDE 或进程**；宽范围杀进程会被拒绝。

```bash
# 建任务 venv
python scripts/actions.py --workspace /path/to/task venv

# 只在这一次命令里设置变量
python scripts/actions.py --workspace /path/to/task run \
  --env-var "MY_FLAG=1" --command "python experiment.py"

# 看当前子进程环境（不含全局修改）
python scripts/actions.py --workspace /path/to/task env
```

## 崩溃恢复与日志

机器死机/断电/重启/磁盘满、Agent 被中断时：

- 状态、证据清单原子写，保留 `.bak`；损坏用 `doctor --recover` 回退；
- 每个命令/GUI 动作先写 intent，结束后写结果；崩溃后残留 intent = 可能做了一半，
  **先检查再决定**，不要盲目重跑；
- `actions.py resolve --id ... --status done|failed|unknown` 标记 in-flight 动作；
- `worker.py doctor` 检查状态损坏、残留 intent、心跳超时、日志超预算；
- `worker.py heartbeat` 更新心跳；
- `worker.py logs --list/--tail/--rotate` 管理日志；只轮转，不自动删除；
- 恢复顺序：`doctor` → 处理 in-flight → `status`/`next`，不要重新 `init`。

```bash
python scripts/worker.py --workspace /path/to/task doctor
python scripts/worker.py --workspace /path/to/task doctor --recover
python scripts/actions.py --workspace /path/to/task list --json
python scripts/actions.py --workspace /path/to/task resolve --id A012345 --status unknown
python scripts/worker.py --workspace /path/to/task logs --rotate
```

详细场景见 `references/crash-recovery.md`。

## 安全与诚信

- 不伪造数据/截图/日志/访谈；截图来自真实操作；
- 不 P 图、不合成终端截图、不用网图或别人的材料；
- 不替用户提交作业/发邮件/下单/登录；
- 破坏性/提权/对外动作必须确认；
- 所有动作进 `_worker/actions.jsonl`，所有证据进 `_worker/evidence.json`（含 SHA256）。

## 限制

- GUI 自动化对自定义渲染/游戏/无控件树的应用不稳定；v0.1 用坐标兜底 + 人工确认。
- Wayland 下 xdotool 可能不可用，v0.2 再补 ydotool/AT-SPI。
- macOS GUI 自动化需要在“辅助功能”里授权。
- `.doc` 的完整保真依赖 Word COM；Linux/macOS 用 LibreOffice 可能有格式差异。
- “完美”是当前 reviewer 口径下的“通过 + 零阻断”，不是绝对满分。

## 许可

MIT，详见仓库根目录 [LICENSE](../LICENSE)。
