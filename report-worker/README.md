# report-worker

把 **report-planner / report-writer / report-reviewer** 串成闭环的薄编排层。

它不重复三个 skill 的规则，只负责：

**分析 → 收集 → 整理 → 规划 → 执行 → 撰写 → 评审 → 修改**

- 先盘点用户材料，列缺口并询问；
- 调用 planner 出执行卡；
- 执行实验/任务，CLI 为主、GUI 补视觉证据，截图只截核心；
- 调用 writer 写报告、reviewer 审核；
- 把审核发现路由回执行/证据/写作/规划，只重跑受影响的下游。

三个依赖 skill 可以单独使用；worker 只是可选编排层。

## 适用

- 实验、课程设计、编程、调研、案例分析、商业计划、课程项目、田野观察；
- 有材料但不知道怎么落地、截图、写报告、改到通过；
- 需要断点续跑、换 Agent 接手。

不绑定学校、课程、学科或平台。Wireshark、MiniEdit、SDN 只是执行示例，不是范围限制。

## 安装

把四个目录一起复制到技能目录：

```text
report-planner/
report-writer/
report-reviewer/
report-worker/
```

只复制 worker 也能跑，但要通过 `REPORT_SKILLS_DIR` 或 `_worker/skills.json` 指定三个依赖 skill 的路径。
**缺依赖时 worker 会先问你安装/复制，不会硬跑。**

依赖：

- Python 3.8+（标准库为主）；
- 截图：Pillow（推荐）；
- Windows GUI：pywin32（基础键鼠/窗口）；可选 pywinauto/mss/opencv；
- 报告：python-docx；`.doc` 需要 Word COM 或 LibreOffice；
- 不强制 WSL/Linux；需要时先问你，不擅自装系统包。

```bash
python scripts/env.py --check-skills --workspace /path/to/task
python scripts/env.py --install-plan
```

## 快速开始

```bash
python scripts/worker.py --workspace /path/to/task init --autonomy assist
python scripts/worker.py --workspace /path/to/task next
python scripts/worker.py --workspace /path/to/task doctor
# 盘点材料后记录用户回答，再过 ANALYZE 闸门
python scripts/worker.py --workspace /path/to/task decide --key materials --value no --note "..."
python scripts/worker.py --workspace /path/to/task gate --name analyze
```

对 Agent 说：

> 用 report-worker 做这个实验/任务。先盘点材料、列缺口，再规划；
> 执行前告诉我不要碰键鼠；截图只截核心；写完用 reviewer 审，改到通过。

## 交互约定

- **先问材料**：指导书/模板/评分表/已有数据/成品参考/实际方案/交付格式；
- 写 `材料清单.md`（已有/还缺/用户确认），用 `worker.py decide` 记录用户回答；
  **没有清单+决策记录，不能进入 PLAN**；
- 缺关键材料先说明影响；用户说没有就按没有规划，不反复追问；
- **执行/截图前**：告诉用户“接下来请全程不要触碰键盘鼠标”，确认后再开始；
- **做完后**：把 Agent 窗口置顶/提醒用户；
- 缺依赖/缺 skill/缺权限：先问，不装就不硬跑；
- 用户说某点不对：复述理解 + 影响，再确认；
- 模板/评分表冲突：先问，默认不保留（模板问题），记录原因；
- 结束前问是否清理 `_worker/` 和中间文件，**不自动删**。

## 执行策略

| 场景 | 默认 |
| --- | --- |
| 命令/脚本/数据处理 | CLI（可见终端 + 截图） |
| 必须看界面/点按钮 | GUI（UIA/键鼠 + 前后截图） |
| 物理设备/本人签字/线下 | 人工接管 |
| 需要 WSL/Linux | 先问用户，不擅自安装 |

**截图只截核心**：代码截改动段，终端截命令+结果，GUI 截目标面板；不要整屏/整个 IDE。

## 环境隔离、崩溃与日志

- Python 依赖进任务 `.venv`，不全局安装；
- 环境变量用 `--env-var`/`--env-file`，只作用于子进程；
- 状态/证据原子写 + `.bak`；动作 intent/pid；`doctor` 检查残留/心跳/损坏；
- `session.log`/`events.jsonl`/每动作 stdout/stderr；`logs --rotate` 轮转，不自动删除；
- 不关闭/杀宿主 Agent 的终端、IDE 或进程。

## 文件

```text
<task>/
├── 材料清单.md
├── 实验执行卡.md
├── 实验规划书.md          # 可选
├── 截图验收.md
├── 人工操作卡.md
├── Pictures/
├── Data/
├── 报告/
└── _worker/
```

## 限制

- GUI 自动化对自绘/无控件树应用不稳定；坐标兜底要人工确认；
- 物理实验、线下调研、必须本人登录的步骤只能人工接管；
- “完成”指当前 reviewer 口径下的“通过 + 零阻断”，不是绝对满分；
- `.doc` 完整保真依赖 Word COM；非 Windows 用 LibreOffice 可能格式差异。

## 许可

MIT，详见仓库根目录 [LICENSE](../LICENSE)。
