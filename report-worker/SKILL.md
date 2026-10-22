---
name: report-worker
description: 把 report-planner / report-writer / report-reviewer 串成闭环的薄编排层。先问清代码/实践处理方式、交付格式、Word/WPS、模板能否改、公式是否可编辑并落盘；规划阶段强制产出执行卡和实验指导书；执行阶段分阶段截图验收，L1 全过才允许写报告；支持多轮审核修复与断点续跑，完工时置顶 Agent 窗口提醒用户。适用于实验、课程设计、调研、案例分析、商业计划、自由写作等；不绑定学校、课程、学科或平台。可单独调用三个 skill，也可用本 worker 编排。
---

# report-worker：薄编排层

> **本页是必须遵守的最小集。** 动手前至少再读：`references/interaction.md`（交互与决策）、
> `references/loop.md`（闸门与路由），以及当前阶段对应的 `prompts/` 角色提示
> （`00_conductor.md` 到 `04_reviewer.md`）。
> 只读本页会漏掉 gate 命令和话术。

worker 不重复 planner/writer/reviewer 的规则，只做四件事：

1. **组织流程**：分析 → 收集 → 整理 → 规划 → 执行 → 撰写 → 评审 → 修改；
2. **推动交互**：材料缺口、方案冲突、危险动作、依赖缺失，先问用户，并把关键回答落盘；
3. **守住证据**：动作留日志，截图只截核心，证据可追溯；
4. **闭环修复**：审核发现路由回执行/证据/写作/规划，只重跑受影响的下游。

三个依赖 skill 可单独使用；worker 只是可选编排层。

## 一、开始前

**先盘点已有材料，再列缺口；一次问完：**

1. 材料：指导书/任务书、模板、评分表、老师通知、已有截图/数据/代码/访谈；
2. 实际方案：设备限制、老师口头要求、替代做法、分组；
3. 交付：格式、命名、截止、字数/页数；
4. 环境：本机/WSL/远程、有没有 GUI、依赖；
5. 授权：课程是否允许自动化、哪些步骤必须本人做；
6. 参考：往届成品/老师样例（只参考格式）；
7. **代码/实践部分**：代写 / 骨架 / 用户写我审？
8. **交付软件**：Word 还是 WPS？
9. **模板结构**：行数/栏目名能不能动？默认不能。
10. **公式**：是否必须可编辑？必须 → 优先 `.docx`。

**五项决策必须用 `worker.py decide` 落盘**：`code_policy`、`delivery.format`、`delivery.editor`、`template_editable`、`formula_editable`。缺一项，`PLAN_FREEZE` 会被 `decisions` 闸门拒绝。合法值见 `references/interaction.md`。

```bash
python scripts/worker.py --workspace <WS> decide --key code_policy --value skeleton --note "用户说自己写"
python scripts/worker.py --workspace <WS> decide --key delivery.format --value docx --note "老师接受 docx"
```

**依赖检查**：worker 需要 planner/writer/reviewer；找不到先问用户安装/复制，缺依赖不硬跑。

## 二、闭环与硬闸门

```text
ANALYZE → COLLECT → ORGANIZE → PLAN → PLAN_FREEZE
→ EXECUTE → WRITE → REVIEW → REVISE ↺ → DONE / BLOCKED / WAITING_USER
```

| 阶段 | 做什么 | 产出 |
| --- | --- | --- |
| ANALYZE | 盘点材料、确认真实方案、列缺口、问用户 | `材料清单.md`、decisions |
| COLLECT | 等用户补材料/数据/截图 | 更新材料清单 |
| ORGANIZE | 整理证据、数据、引用 | `证据计划.md` / `Data/` |
| PLAN | 调用 planner | **执行卡 + 实验指导书** + `plan.json` |
| PLAN_FREEZE | 用户确认方案/目的/交付 | 冻结计划 |
| EXECUTE | 按执行卡操作、截图、分阶段验收 | 动作日志、`Pictures/`、`截图验收.md` |
| WRITE | 调用 writer | `报告-vN` |
| REVIEW | 调用 reviewer | `报告-审核报告-vN.md` |
| REVISE | 核实并路由审核发现 | 修复清单 |
| DONE / BLOCKED / WAITING_USER | DoD 满足 / 阻塞 / 等用户 | 说明 |

**三道硬闸门**（脚本拒绝跳过）：

1. **`decisions`**：五项交互决策已落盘；
2. **`artifacts`**：`实验执行卡.md` + `实验指导书.md` 都存在且非空；
3. **`execution`**：步骤全部完成/跳过、L1 证据通过、`截图验收.md` 无“不通过/待补拍”。

```bash
python scripts/verify.py --workspace <WS> decisions
python scripts/verify.py --workspace <WS> artifacts
python scripts/verify.py --workspace <WS> execution
```

**未冻结不执行。** 用户确认前只做分析、收集、整理、规划；用户改方案就回 PLAN。

## 三、执行策略

- **CLI 主力**：命令/脚本/数据处理，快、可复现；在可见终端里跑，方便截图。
- **GUI 补视觉证据**：必须看界面/点按钮时用；UIA 优先，坐标兜底。
- **人工接管**：物理设备/本人签字/线下，写 `人工操作卡.md`，暂停等用户。
- **不强制 WSL/Linux**：需要时先问，不擅自装系统包/驱动/服务。
- **证据保真**：指导书要 Wireshark 界面截图，就不能用 `tshark` 文本替代。
- **截图只截核心**：代码截改动段，终端截命令+结果，GUI 截目标面板；不整屏。

详细操作见 `references/automation.md`；执行角色见 `prompts/02_operator.md`。

## 四、交互

- **开工前**：先问五件事，再给方案/大纲让用户确认；不闷头跑。
- **执行/截图前**：告诉用户“接下来要操作键鼠/截图，请全程不要触碰键盘鼠标”，确认后再开始。
- **做完一批操作后**：置顶 Agent 窗口/提醒用户。
- **验收后**：先给“继续下一阶段 / 修改执行卡 / 补证据”三个选项，**不要直接问要不要进 writer**。
- **缺依赖/权限**：说明缺什么、为什么、怎么装；用户不装就不硬跑。
- **用户说没有/不需要**：接受并记录，不反复追问。
- **用户说某点不对**：复述理解，说明影响，再确认；不争辩，也不沉默照做。
- **完成时**：`worker.py` 进入 DONE 会自动 `desktop.notify`；没设置 `agent_window` 就手动提醒。
- **结束前**：问用户是否清理 `_worker/`、中间稿、临时截图；不自动删。

详细话术见 `references/interaction.md`。

## 五、证据与闭环

- 每个动作记录到 `_worker/actions.jsonl`（命令/窗口、退出码、输出、截图、时间）。
- 截图进 `_worker/evidence.json`：证据 ID、步骤、文件、SHA256、验收状态。
- 每步有“达成效果”；截图合格但结果不符，先排错，不重拍同样结果的图。
- 审核发现先核实再分派：
  - 数据/结果错 → EXECUTE；截图缺字段 → 补拍；
  - 内容/格式/模板骨架/公式/兼容 → WRITE；
  - 计划缺步骤/证据 → PLAN；
  - WPS 实机/需求冲突/无法判断 → WAITING_USER。
- 同一问题连续 2 轮没修好 → BLOCKED；只重跑受影响的下游。

## 六、环境、崩溃与日志

- **Python 依赖**：任务目录 `.venv`；`actions.py run` 自动优先用；不全局 `pip install`。
- **环境变量**：`--env-var` / `--env-file` 只作用于子进程；不改系统变量/profile。
- **崩溃恢复**：`state.json`/`evidence.json` 原子写 + `.bak`；动作先写 intent；`worker.py doctor` 查残留/心跳/损坏/日志。
- **日志**：`_worker/logs/`；`worker.py logs --rotate` 按大小轮转，不自动删除。
- **进程安全**：不关闭/杀宿主 Agent 的终端/IDE/进程；宽范围 `taskkill`/`pkill` 直接拒绝。
- **临时文件**：放任务目录/`_worker/`；结束前问用户是否清理。

详见 `references/automation.md`、`references/portability.md`。

## 七、文件

```text
<任务目录>/
├── 材料清单.md
├── 实验执行卡.md          # 即开即用版
├── 实验指导书.md          # 完整版（必做；旧名 实验规划书.md）
├── 截图验收.md
├── 人工操作卡.md
├── Pictures/
├── Data/
├── 报告/报告-vN.<doc|docx>、报告-审核报告-vN.md
└── _worker/state.json、plan.json、evidence.json、actions.jsonl、roles/、logs/
```

## 八、脚本

| 脚本 | 用途 |
| --- | --- |
| `env.py` | 探测 OS/依赖/截图/GUI/Word；检查三个 skill |
| `worker.py` | 状态机：`init/status/next/record/advance/freeze/gate/decide/complete-step/doctor/logs/resume/cleanup` |
| `actions.py` | 命令执行、分类、策略、日志；venv/临时变量；local/WSL/SSH |
| `capture.py` | 截图、窗口、裁剪、证据 manifest |
| `desktop.py` | GUI：聚焦、UIA、键鼠、可见终端、通知 |
| `uia.ps1` / `verify.py` | Windows UIA；计划/步骤/证据/报告/审核/DoD 闸门 |
| `_durable.py` / `_venv.py` | 原子写、intent/pid、日志轮转；缺依赖时用任务 venv 重跑 |

## 九、边界

**做**：编排三个 skill、执行数字操作、截图取证、闭环修复、断点续跑。

**不做**：伪造数据/截图/访谈、替用户提交/登录/下单、绕过学术诚信、未授权操作系统或他人材料、承诺“全自动做完物理实验”。
