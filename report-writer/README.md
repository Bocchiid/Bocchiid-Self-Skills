# report-writer

按模板撰写 Word 报告的 Skill，实验报告为主场景。

从材料到成稿：盘点材料 → 解析模板 → 规划结构 → 往模板里插入内容 → 图表题注与交叉引用 → 调页面利用率 → 更新域并交付。

与 [report-reviewer](../report-reviewer/) 配对：**一个写、一个审**。

## 功能

- **需求优先**：写什么由**用户要求 → 指导书 → 模板明写的要求 → 默认（最小化）**逐级决定。
  图、表、参考文献**都不是默认项**，没人要求就不加；模板写了「不少于 3 篇」之类的硬要求则必须做。
- **材料盘点与追问**：实验指导书、模板、截图、成品报告的清单与缺失话术。
- **模板解析**：勘察模板形态、显式指定写入目标、提取并迁移格式。
- **只插入不覆盖，且可验证**：内容追加进模板既有区域，框、页眉页脚、评分表、样式定义原样保留；
  写入前后比对表格结构指纹，**除了目标格以外的任何变化都会被报出来**。
- **防写错地方**：自动拦下"往评分表里写正文"和"覆盖模板原有内容"这两类致命操作。
- **题注与交叉引用**：`SEQ`/`REF` 域自动编号，图与题注保证同页，空格格式统一。
- **页面利用率调优**：量出"只填了一半"的页，定位阻塞块，按优先级处理。
- **环境探测**：python-docx / Word COM 可用性，以及目标文件是否被 Word 占用。

## 目录结构

```
report-writer/
├── SKILL.md                        # 主指令
├── references/
│   ├── intake.md                   # 材料盘点、追问话术、环境与占用检查
│   ├── course-conventions.md       # 各课程的材料位置、命名惯例、报告类型
│   ├── template-analysis.md        # 判断"框"、定位可编写区、提取并迁移格式
│   ├── writing.md                  # 标题层级、题注写法、正文与分析的写法
│   ├── citations.md                # 文献引用规范（GB/T 7714、上标标注）
│   ├── layout-tuning.md            # 页面利用率的度量与收敛方法
│   └── docx-cookbook.md            # python-docx / Word COM 技术要点与踩坑清单
└── scripts/
    ├── docx_env.py                 # 环境探测 + 文档结构探查
    ├── docx_kit.py                 # 插入内容的工具库
    ├── page_fill.py                # 页面利用率测量
    └── word_com.ps1                # .doc ↔ .docx、更新域、导出 PDF
```

## 安装

将整个 `report-writer` 文件夹复制到对应平台的 skills 目录下。

| 平台                         | 项目级路径                         | 个人级路径                                   |
| ---------------------------- | ---------------------------------- | -------------------------------------------- |
| Claude Code                  | `.claude/skills/report-writer/`    | `~/.claude/skills/report-writer/`            |
| Codex                        | `.codex/skills/report-writer/`     | `~/.codex/skills/report-writer/`             |
| GitHub Copilot               | `.github/skills/report-writer/`    | `~/.copilot/skills/report-writer/`           |
| Cursor                       | `.cursor/skills/report-writer/`    | `~/.cursor/skills/report-writer/`            |
| Windsurf                     | `.windsurf/skills/report-writer/`  | `~/.codeium/windsurf/skills/report-writer/`  |
| 豆包（Windows/macOS 客户端） | —                                  | `~/Doubao/skills/report-writer/`             |
| DSH                          | `.dsh/skills/report-writer/`       | `~/.dsh/skills/report-writer/`               |

复制完成后重启会话，Skill 即可被加载。

## 依赖

### 必需

```
pip install python-docx
```

**不装会怎样**：连 `.docx` 都读写不了，只能产出纯文本，交不出符合模板的 Word 文件。**这个是真的必需。**

**装不上怎么办**：

```bash
pip install python-docx -i https://pypi.tuna.tsinghua.edu.cn/simple
```

### 可选

| 依赖 | 用途 | 没有怎么办 |
| --- | --- | --- |
| Microsoft Word（Windows） | 打开老式 `.doc`、更新域、导出 PDF | 目标文件是 `.docx` 且不需要导出 PDF 时可不用；否则只能手工在 Word 里打开刷新域 |
| `pip install pymupdf` | `page_fill.py` 量页面利用率 | 跳过版面调优，靠肉眼翻 PDF 检查 |
| `pip install pillow` | `docx_kit.compact_image()` 压缩截图 | 文档体积会偏大（实测 4 MB → 21 MB） |

Word COM 通过 `scripts/word_com.ps1`（PowerShell）调用，**不需要** `pywin32`。

## 使用

把材料放进工作目录，然后提出撰写需求：

> 帮我完成这份实验报告，模板和实验指导书都在同目录下，截图在 Pictures 目录里。

Skill 会自动：

1. 盘点材料，缺什么问什么（姓名、学号、日期这类细节也会问）。
2. 探测环境，并检查目标文件是否被 Word 占用。
3. 解析模板，判断"框"与需编写区域，提取格式。
4. 列出大纲与用户对齐。
5. 往模板里插入内容，同时做图表题注与交叉引用。
6. 量页面利用率，收敛版面。
7. 更新域、另存为交付格式、导出 PDF 自检。

## 常用命令

```bash
# 环境探测
python scripts/docx_env.py --check

# 写入方案建议：形态判定 + 可直接复制的 Target 候选 + 要避开的评分区
python scripts/docx_env.py --plan "模板.docx"

# 全量结构转储（含所有段落），用来通读模板
python scripts/docx_env.py --describe "模板.docx"

# .doc → .docx
powershell -File scripts/word_com.ps1 -Action to-docx -In 模板.doc -Out work.docx

# 更新域并另存为 .doc
powershell -File scripts/word_com.ps1 -Action to-doc -In out.docx -Out 报告.doc

# 导出 PDF 看排版
powershell -File scripts/word_com.ps1 -Action to-pdf -In out.docx -Out preview.pdf

# 量页面利用率
python scripts/page_fill.py preview.pdf
```

在自己的构建脚本里用工具库：

```python
import sys; sys.path.insert(0, r'<skill>/scripts')
from docx import Document
import docx_kit as K

d = Document('work.docx')

print(K.survey(d))                          # 1) 勘察：看清模板结构
target = K.Target.cell(table=1, row=3)      # 2) 显式指定写入目标
cur = K.Cursor(d, target, keep_paras=1)
# 3) 写入前检查在首次 put() 时自动执行，拦到就抛错（拦下时文档零改动）

caps = K.Captions()
caps.declare('fig_topo', '图')

cur.put(K.heading(1, '1. 网络拓扑搭建'))
cur.put(K.body(caps, '拓扑如<<fig_topo>>所示。'))
cur.put_image('pics/topo.png', 400)
cur.put(K.caption(caps, 'fig_topo', '实验网络拓扑'))

report = cur.finish()                       # 4) 写入后比对模板结构
print(report)                               # 正常只有目标格有变化
d.save('out.docx')
```

## 已知限制

- **"框"的形态需要人来定**。模板留给作者填写的区域至少有四种形态（单列长表 /
  多列表单 / 正文区与评分表拼在一张表 / 纯段落结构），**只有第一种能自动识别**。
  其余三种要跑 `survey()` 看清结构后**显式指定**目标——这是刻意的设计：
  自动猜在某一门上一定会猜错，而猜错的代价是静默地把正文写进评分表。
  写入前的 `check()` 和写入后的 `finish()` 比对会把这类事故拦在交付之前。
- **表格跨页时不会重复表头**。Word 不支持为嵌套在单元格里的表格重复表头行（`w:tblHeader` 被静默忽略）。让表格跨页是填满页面最有效的手段，代价就是续页没有表头。
- **`.docx` 存回 `.doc` 会丢少量不可见的元数据**，这是格式转换本身导致的，无法避免（见 `references/docx-cookbook.md`）。
- **整理版面无法 100% 消除空白**。一张必须占大半页的大图放在页尾，空洞就消不掉；这时应当向用户说明原因并给出取舍选项，而不是把图缩到看不清。

## 适用与不适用

**适用**

- 有模板（或能协商出格式）的 Word 报告撰写。
- 需要插入大量截图、表格并做图表编号引用的实验报告。
- 需要沿用既有模板、不能破坏其版式与固定内容（封面、评分表）的场景。

**不适用**

- 没有模板也没有任何格式参照，且用户不愿协商格式——应先问清楚再动手。
- 需要伪造实验数据的场景。
- 纯文字、无 Word 格式要求的写作。

## 许可

MIT，详见 [LICENSE](../LICENSE)。
