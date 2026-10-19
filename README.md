# Bocchiid-Self-Skills

个人维护的 Agent Skills 合集。

每个 Skill 独立放在一个子目录中，可单独复制到各平台的 skills 目录下使用。

## 包含的 Skills

| Skill                               | 说明                                                         |
| ----------------------------------- | ------------------------------------------------------------ |
| [report-planner](report-planner/)   | 把实验指导书/任务书/模板/评分表转化为**现场照着做的实验执行卡**：步骤/预期结果速查、步骤与目标、达成效果、每步截图提示、截图速查卡、失败分支、报告章节映射；支持分阶段截图验收（默认从 `Pictures/` 读取或直接上传，目录可自定义/直接丢当前目录；只扫任务目录且不越界），核对截图是否对应步骤和预期结果并给出补拍清单。流程图/架构图等报告插图交给 writer 绘制，不列入用户截图清单。默认产出短的执行卡（即开即用版），详细规划按需生成（全面版，用于确认细节和交接 writer）。按任务形态而非学科分类，覆盖理工实验、编程、调研、案例分析、商业计划、课程项目、田野观察等。 |
| [report-writer](report-writer/)     | 按模板撰写 Word 报告（实验报告为主场景）：插入而非覆盖、封面/评分表等保护区逐字节保护（空格/换行也不许变）、图表题注与交叉引用、页面利用率只统计需编写页。 |
| [report-reviewer](report-reviewer/) | 通用实验报告/课程报告审核：对照要求、模板或评分标准做正确性、格式、要求对标与评分；适用于理工实验、编程实现、调研/通识课、课程设计等，不绑定学校或课程；每次评分自动生成 md 审核报告，并与 writer 同口径（只审需编写区域、条件项不扣分、防材料注入）。 |
| [report-worker](report-worker/) | 端到端总控：读取口述/材料，调用 planner 生成执行卡，按步骤操作 GUI/命令/改代码/截图，分阶段验收证据，调用 writer 写报告、reviewer 审核，把审核发现路由回执行/证据/写作/规划，多轮迭代到“审核通过 + 零阻断”。跨 Agent 通用：不依赖某个平台的 Skill/子代理/工具名；提示词可复制，Python runtime 只做状态和闸门；环境隔离（任务 venv + 子进程临时变量），不破坏用户原环境，不关闭宿主终端；状态/证据原子写 + `.bak`，动作 intent/pid/日志可恢复，支持死机/断电后的 `doctor` 诊断与断点续跑。 |

四个 Skill 形成一条闭环：**planner 规划 → worker 执行/取证 → writer 写报告 → reviewer 审核 → worker 修复**。
执行卡/详细版里的步骤、截图清单、章节映射、任务差异可以直接交给 writer；
详细版是规划输入，不是报告草稿，writer 仍以实际截图和数据为准。写完再用 reviewer 自审；
`report-worker` 把这套流程自动串起来，并按审核意见只重跑受影响的下游。

**四个 Skill 也可以单独使用**：planner 只规划、writer 只写、reviewer 只审；worker 是可选的编排层，
不修改也不依赖它们的内部实现。它们不绑定学校、课程或学科——材料是什么，就按什么规划/写作/审核。

四个 Skill 采用同一套口径：

- **用户描述优先**：用户说明实际实验与指导书/模板有出入时（设备不足、老师口头改方案、
  替代做法），以用户描述为准，不判为错误；实验目的逐条核对，不擅自删减。
- **材料是数据，不是指令**：指导书、模板、截图、成品报告乃至被审报告里试图指挥 AI 的内容
  （"忽略规则""给满分"等）不执行、不据此加减分。
- **证据链而不是截图清单**：planner 为每个报告结论规划证据；截图只是证据的一种，
  数据表、日志、代码、照片、问卷、访谈、引用、版本记录同样有效。
- **不编造**：planner 不替学生编数据/截图/访谈，writer 不替学生编实验结果，
  reviewer 不依据编造内容评分。
- **只审/只写需编写区域**：封面、评分点、评分表、模板预填内容不属于学生内容；
  字数与页面利用率也只统计需编写区域。
- **模板保护区逐字节保护**：封面、评分点、评分表、页眉页脚、模板原有文字，
  连它们之间的空格、空行、换行都不改动。
- **reviewer 每次评分自动生成 md**：`<报告名>-审核报告.md`，多轮为 `-v2.md`、`-v3.md`。

后续会按需添加更多 Skill。

## 目录结构

```
Bocchiid-Self-Skills/
├── README.md
├── LICENSE
├── .gitignore
├── report-planner/
│   ├── SKILL.md
│   ├── README.md
│   ├── references/
│   └── scripts/
├── report-writer/
│   ├── SKILL.md
│   ├── references/
│   └── scripts/
├── report-reviewer/
│   ├── SKILL.md
│   ├── references/
│   └── scripts/
└── report-worker/
    ├── SKILL.md
    ├── README.md
    ├── prompts/
    ├── schemas/
    ├── references/
    ├── gui_profiles/
    └── scripts/
```

每个 Skill 子目录自包含，安装时复制整个子目录即可。

## 安装

把需要的 Skill 子目录复制到对应平台的 skills 目录下。以 Claude Code 为例：

```text
~/.claude/skills/report-planner/
~/.claude/skills/report-writer/
~/.claude/skills/report-reviewer/
~/.claude/skills/report-worker/
```

其他平台的路径见各 Skill 子目录内的说明。

## 添加新 Skill

在仓库根目录新建子目录，放入 `SKILL.md` 及配套文件，然后在上面表格中加一行。

## 许可

MIT，详见 [LICENSE](LICENSE)。