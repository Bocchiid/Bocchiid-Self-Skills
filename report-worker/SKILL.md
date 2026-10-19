---
name: report-worker
description: 把 report-planner / report-writer / report-reviewer 串成闭环的薄编排层。读取用户口述或材料，先盘点材料、补齐缺口、规划，再执行实验并截取核心证据，调用 writer 写报告、reviewer 审核，按发现修改，多轮直到可提交。适用于实验、课程设计、调研、案例分析、商业计划、自由写作等；不绑定学校、课程、学科或平台。可单独调用三个 skill，也可用本 worker 编排。
---

# report-worker：薄编排层

worker 不重复 planner/writer/reviewer 的规则。它只做四件事：

1. **组织流程**：分析 → 收集 → 整理 → 规划 → 执行 → 撰写 → 评审 → 修改；
2. **推动交互**：材料缺口、方案冲突、危险动作、依赖缺失，先问用户；
3. **守住证据**：动作留日志，截图只截核心，证据可追溯；
4. **闭环修复**：审核发现路由回执行/证据/写作/规划，只重跑受影响的下游。

三个依赖 skill 可单独使用；worker 只是可选编排层，不修改它们的内部实现。

---

## 一、开始前：先问材料，再动手

**先盘点用户已经给了什么，再列缺口；不要先埋头做。**

一次问完：

1. 材料：指导书/任务书、模板、评分表、老师通知、已有截图/数据/代码/访谈；
2. 实际方案：设备限制、老师口头要求、替代做法、分组；
3. 交付：格式（`.doc`/`.docx`/PDF）、命名、截止、字数/页数；
4. 环境：本机 / WSL / 远程；有没有 GUI；缺不缺依赖；
5. 授权：课程是否允许自动化；哪些步骤必须本人做；
6. 参考：有没有往届成品/老师样例？（只用于格式，不抄内容，也可能完全没用）

缺关键材料时说明“缺什么、影响哪一步/哪条证据/哪一章”；用户说没有就按没有规划，
不反复追问，把“没有”记为假设。

**交互硬闸门**：先写 `材料清单.md`（已有/还缺/用户确认），再用
`worker.py decide --key ... --value ... --note ...` 记录用户回答；
没有这两样，`worker.py advance --to PLAN` 会被拒绝。

**依赖检查**：worker 需要 `report-planner`、`report-writer`、`report-reviewer`。
找不到就先问用户安装/复制，缺依赖不能硬跑。

---

## 二、闭环：8 个阶段

```text
分析 ANALYZE
  → 收集 COLLECT
  → 整理 ORGANIZE
  → 规划 PLAN → 冻结 PLAN_FREEZE
  → 执行 EXECUTE
  → 撰写 WRITE
  → 评审 REVIEW
  → 修改 REVISE
  ↺ 回到受影响的上游
  → DONE / BLOCKED / WAITING_USER
```

| 阶段 | 做什么 | 产出 |
| --- | --- | --- |
| ANALYZE | 盘点材料、确认真实方案、列缺口、问用户 | `材料清单.md`、待确认问题 |
| COLLECT | 等用户补材料/收集数据/补截图 | 更新材料清单 |
| ORGANIZE | 整理证据、数据、引用、来源 | `证据计划.md` / `Data/` |
| PLAN | 调用 `report-planner` | `实验执行卡.md`、可选详细版 |
| PLAN_FREEZE | 用户确认实际方案、目的、交付 | 冻结计划 |
| EXECUTE | 按执行卡操作、截图、验收 | 动作日志、`Pictures/`、`Data/` |
| WRITE | 调用 `report-writer` | `报告-vN` |
| REVIEW | 调用 `report-reviewer` | `报告-审核报告-vN.md` |
| REVISE | 核实并路由审核发现 | 修复清单、下一阶段 |
| DONE | DoD 满足 | 报告 + 证据 + 审核记录 |
| BLOCKED | 预算/权限/环境/人工阻塞 | 阻塞说明 |
| WAITING_USER | 等用户补材料/做物理步骤/确认 | 人工操作卡 |

**未冻结计划不执行。** 用户确认前只做分析、收集、整理、规划。

---

## 三、执行策略：CLI 主力，GUI 补视觉证据

不强制 WSL/Linux；用户机器上有什么就用什么。

| 步骤 | 默认 | 说明 |
| --- | --- | --- |
| 命令/脚本/数据处理 | **CLI** | 快、可复现、输出可断言；在可见终端里跑，方便截图 |
| 必须看界面/点按钮/还原人做实验 | **GUI** | 窗口聚焦、UIA 控件、键鼠；动作前后截图 |
| 物理设备/本人签字/线下 | **人工接管** | 生成操作卡，暂停等用户 |
| 需要 Linux 工具 | 先问用户 | 不擅自装 WSL/VM/系统包；用户没有就换方案或人工 |

**证据保真**：指导书要求 Wireshark 界面截图，就不能用 `tshark` 文本替代；
CLI 用来高效执行，GUI 用来出真实截图，两者不互相冒充。

### 截图只截核心

- 代码：只截改动段/关键函数/报错行 + 文件名/行号；完整代码用文本块。
- 终端：只截命令 + 关键输出 + 提示符；不要整屏历史和无关窗口。
- GUI：只截目标对话框/面板/关键字段；只有拓扑/装置全景才截大图。
- 截图后按核心区域裁剪；保留能证明应用/版本的标题栏。

详细操作见 `references/automation.md`。

---

## 四、交互：把使用方式教给用户

- **开始 GUI 操作/截图前**：明确告诉用户“接下来要操作键鼠/截图，请全程不要触碰键盘鼠标”，
  等用户确认后再开始；需要时可分阶段进行。
- **做完一批操作后**：把 Agent 窗口置顶/提醒用户，避免“做完了但用户没看到”。
- **缺依赖/缺 skill/缺权限**：先说明缺什么、为什么需要、怎么装；用户不装就不硬跑。
- **用户说没有/不需要**：接受并记录，不反复追问。
- **用户说某点不对**：先复述理解，说明改/不改的影响，再确认；不争辩，也不沉默照做。
- **模板/评分表冲突**（如要求参考文献但模板没位置）：先问；默认不保留（模板问题），记录原因。
- **结束前**：询问用户是否清理 `_worker/`、中间稿、临时截图；**不自动删**。

详细话术见 `references/interaction.md`。

---

## 五、证据与闭环

- 每个动作记录到 `_worker/actions.jsonl`：命令/窗口、退出码、输出、截图、时间；
- 截图进 `_worker/evidence.json`：证据 ID、步骤、文件、SHA256、验收状态；
- 每步有“达成效果”；截图合格但结果不符，先排错，不要重拍一张同样结果的图；
- 审核发现先核实，再分派：
  - 数据/结果错 → 回 EXECUTE；
  - 截图缺字段 → 补拍；
  - 报告内容/格式 → WRITE；
  - 计划缺步骤/证据 → PLAN；
  - 需求冲突/无法判断 → WAITING_USER；
- 同一问题连续 2 轮没修好 → BLOCKED，不无限循环；
- 只重跑受影响的下游，不整场重来。

---

## 六、环境、崩溃与日志（保留原有设计）

- **Python 依赖**：任务目录 `.venv`；`actions.py run` 自动优先用；不全局 `pip install`。
- **环境变量**：`actions.py run --env-var` / `--env-file`，只作用于子进程；不改系统变量/profile。
- **崩溃恢复**：`state.json`/`evidence.json` 原子写 + `.bak`；动作先写 intent，结束后写结果；
  `worker.py doctor` 检查残留 intent、心跳、损坏、日志超预算。
- **日志**：`_worker/logs/session.log`、`events.jsonl`、每条动作 stdout/stderr；
  `worker.py logs --rotate` 按大小轮转，不自动删除。
- **进程安全**：不关闭/杀宿主 Agent 的终端/IDE/进程；宽范围 `taskkill`/`pkill` 直接拒绝。
- **临时文件**：全部放当前任务目录/`_worker/`；结束前问用户是否清理。

详见 `references/automation.md`。

---

## 七、跨 Agent / 独立使用

- 不依赖某个平台的 Skill/子代理/工具名；提示词可复制，脚本只用 Python + shell。
- 平台有子代理就用；没有就单会话按角色顺序执行，状态在磁盘。
- 能力缺失时降级：
  - 不能看图 → 截图验收交用户；
  - 没有 GUI → 只做 CLI/人工；
  - 没有 Python/shell → 纯 Markdown 人工模式；
  - 没有 Word COM → `.docx`/LibreOffice，`.doc` 说明限制。
- 三个依赖 skill 单独可用；worker 不修改它们。

---

## 八、文件

```text
<任务目录>/
├── 材料清单.md
├── 实验执行卡.md
├── 实验规划书.md          # 可选
├── 截图验收.md
├── 人工操作卡.md          # 需要人工时
├── Pictures/              # 截图
├── Data/                  # 数据/日志/来源
├── 报告/
│   ├── 报告-vN.<doc|docx>
│   └── 报告-审核报告-vN.md
└── _worker/
    ├── state.json
    ├── plan.json
    ├── evidence.json
    ├── actions.jsonl
    ├── roles/*.result.json
    ├── logs/
    └── backups/
```

---

## 九、脚本

| 脚本 | 用途 |
| --- | --- |
| `env.py` | 探测 OS/依赖/截图/GUI/Word；检查三个 skill 是否存在 |
| `worker.py` | 状态机：`init/status/next/record/advance/freeze/gate/decide/complete-step/doctor/logs/resume/cleanup` |
| `actions.py` | 命令执行、分类、策略、日志；venv/临时变量；local/WSL/SSH |
| `capture.py` | 截图、窗口、裁剪、证据 manifest |
| `desktop.py` | GUI：窗口聚焦、UIA、键鼠、可见终端、通知 |
| `uia.ps1` | Windows UIA 控件查找/点击/等待 |
| `verify.py` | 计划/步骤/证据/报告/审核/DoD 闸门 |
| `_durable.py` | 原子写、intent/pid、日志轮转 |
| `_venv.py` | 缺依赖时用任务 venv 重跑 helper |

---

## 十、边界

**做**：编排三个 skill、执行数字操作、截图取证、闭环修复、断点续跑。

**不做**：伪造数据/截图/访谈、替用户提交/登录/下单、绕过学术诚信、
在没有授权时操作系统或他人材料、承诺“全自动做完物理实验”。
