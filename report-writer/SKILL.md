---
name: report-writer
description: 按模板撰写 Word 报告（实验报告为主场景）。当用户提供实验指导书/任务书、报告模板、待插入的截图或数据等材料，需要产出套用模板格式、图表带题注与交叉引用、页面排布紧凑的 Word 报告时使用。模板行数/列数/合并/栏目名写入前后零变化；表格不用 1×1 外层表并保证表后空行；显示公式 OMML 结构检查、行内公式 WPS 间距处理；Word/WPS 兼容模式与保存往返测试；写入前查文件锁。写好后可用 report-reviewer 自审。
---

# 报告撰写

> **本页是必须遵守的最小集。** 动手前至少再读：`references/template-analysis.md`（模板与封面）、
> `references/tables.md` + `references/formulas.md` + `references/diagrams.md`（图表公式）、
> `references/compatibility.md`（Word/WPS/文件锁）。只读本页会漏掉实现细节。

**流程：盘点材料 → 解析模板 → 规划结构 → 插入内容/填封面 → 图表公式 → 调页面利用率 → 更新域 → 交付审计。**

可单独使用，也可由 `report-worker` 编排；不绑定学校、课程或学科。

## 五条底线

1. **模板优先，只插入不覆盖**：框、页眉页脚、封面、评分表、内嵌题目表/信息表、样式定义原样保留。封面只能“填值”，用户给值才填。
2. **保护区逐字节不动**：封面、评分点、评分表、教师评语、模板原有说明文字，连空格/空行/换行都不动。
3. **模板骨架一行都不能变**：`K.template_shape()` 快照行数、列数、合并关系、左侧栏目名；写入后必须一致。**禁止加行/删行/拆行/改栏目名。** 评分表要求“摘要/结论”但模板没有对应行时，摘要嵌入“问题描述”开头，结论嵌入“算法的优缺点”末尾（如 `6 结论`）；确实要改结构，先问用户，再 `cur.resnapshot('理由')`。
4. **格式只对齐“需编写区域”**：模板里不需要你写的部分原样跳过。
5. **内容基于指导书/模板/用户材料/检索，不抄成品报告；代码/实践按用户选择的 `code_policy` 处理，没确认就先问。**

**需求优先级**：用户要求 > 指导书/任务书 > 模板明写要求 > 默认（最小化）。图、表、参考文献是条件项，没人要求就不加；模板明写的“不少于 N 篇”“必须有时序图”才是硬要求。

**交付格式跟模板走**：`.doc` → `.doc`，`.docx` → `.docx`。中间产物写在报告目录。

**模板/评分表冲突**（评分表要求摘要/参考文献/目录，但模板没有对应位置）：先问用户，**默认不保留**（模板问题，不是学生漏做）；用户要求保留时放文末/脚注/附录，不塞保护区，并在交付说明记录。无模板/纯文科自由写作先与用户协商结构，见 `references/freeform.md`。

## 开工前先问

1. 最终交 `.doc` 还是 `.docx`？老师接受 `.docx` 吗？
2. 主要用 Word 还是 WPS 批改？
3. 模板行数/栏目名能不能动？默认**绝对不能动**。
4. 公式是否必须可编辑？必须 → 优先 `.docx`；只收 `.doc` → 提前说明公式会变图片。

顺带问：有没有往届成品/老师样例？只参考版式，不抄内容。写之前把大纲、标题层级、图表清单发给用户过一眼。

**交互原则**：先盘点已有材料再列缺口，一次问完；用户说没有就接受，不反复追问；
用户说某点不对，先复述理解、说明影响，再确认；缺封面字段/格式要求先问，绝不猜；
用户看不到成品时，写前给大纲、写中给检查点、写完后置顶窗口提醒。

## 第零步：材料与环境

```bash
find . -type f -not -path "*/.git*" -printf "%10s  %p\n" | sort -k2
python scripts/docx_env.py --check
python scripts/docx_env.py --plan 模板.docx     # 形态、Target 候选、封面字段、内嵌表格
python scripts/docx_env.py --cover 模板.docx    # 待填封面字段
```

- 先找模板、指导书、同课程成品；成品只用于格式/章节惯例。
- 姓名、学号、日期、题目等字段缺了直接问，**绝不猜**；一次问完。
- **写入前查文件锁**：`K.file_in_use(path)` 或 `word_com.ps1` 会检查 `~$`/独占打开；被占用就请用户关闭，或另存 `报告-修正版.docx` / `报告-v2.docx`，交付说明里写清哪个最新。

## 第一步：解析模板

**四种形态**：①单列长表 ②多列表单 ③正文+评分表同表 ④纯段落。只有①能可靠自动识别；其余**不要猜**，显式指定 Target。

```python
K.Target.cell(table=1, row=3)   # 表格式
K.Target.after('主要内容：')     # 段落式
K.Target.at_end()               # 追加
```

**四步防护**：

1. `K.survey(d)` / `docx_env.py --plan` 勘察；内嵌表格、评分区、封面字段都会标出。
2. 显式指定 Target；不要清空含内嵌表格的格子（用 `Target.after` 或 `clear=False`）。
3. 首次 `put()` 自动跑 `check_target()`：评分行/封面行/含内嵌表格/已有内容会拦截；误报用 `cur.force('理由')`。
4. `cur.finish()` 报**表格结构指纹 + 模板骨架 + 保护区 XML 哈希**；目标格以外的变化一律回滚。

**封面**：识别 → 问用户（报值/自己手填/只填几项）→ `K.fill_cover(d, {...})` → 检查 `missed/manual`。标签、下划线、封面图不动。

**内嵌题目表**：不能清空所在格；填字段走 `fill_cover()`，附近写正文走 `Target.after()` / `clear=False`。

详细说明见 `references/template-analysis.md`、`references/docx-cookbook.md`。

## 第二步：规划结构

先把要求拆成两份清单：

- **评分表**：每行拆成“可核对的写作要点 + 对应章节”。
- **硬要求**：字数下限、参考文献篇数、必须覆盖的角度、必须有的图、要求删除的说明文字、程序清单/数据记录。

再定大纲：`1.` → `(1)` → `①②③` → `1.1`，层级格式随模板。定完给用户过一眼。

## 第三步：写入内容

```python
import sys; sys.path.insert(0, r'<skill>/scripts')
from docx import Document
import docx_kit as K

d = Document('work.docx')                       # .doc 先由 word_com.ps1 转来
cur = K.Cursor(d, K.Target.cell(1, 3), keep_paras=1)
caps = K.Captions()
caps.declare('fig_topo', '图')
caps.declare('tab_host', '表')

cur.put(K.heading(1, '1. 网络拓扑搭建'))
cur.put(K.body(caps, '拓扑见<<fig_topo>>，端口见表<<tab_host>>。'))
cur.put_image('pics/topo.png', 400)
cur.put(K.caption(caps, 'fig_topo', '实验网络拓扑'))
cur.put_table(caps, 'tab_host', '主机地址规划', rows, widths)

assert not cur.finish()                         # 非空 = 模板被动，回滚
d.save('out.docx')
```

结果分析要**字段级解读**：读数、算差值、核对、下结论；不要复述“如图所示”。代码有截图用截图，没有用 `K.code_block()` 文本块。写法见 `references/writing.md`。

## 第四步：图表、公式、WPS

### 题注

- 固定 `图 3 名称` / `表 2 名称`；编号用 `SEQ` 域 + 书签，正文用 `REF` 域。
- 图注在图下方，表注在表上方；图与题注同页（插图段落自带 `keepNext`）。
- 模板原有图表不加题注、不改编号、不参与编号。

### 表格

- **禁止 1×1 外层表**包“表题 + 表格”（WPS 会多显示一圈边框）。
- 用 `K.table_block()` / `cur.put_table()`：表题段（keepNext）→ 表格 → 表后空段落。
- 三线表：左右/内部竖线 `nil`，表头下横线；单元格左右留白 80 twips。
- 交付前核对表格总数：主表 + N 张数据表；多出的通常是外层表（`K.table_counts()`）。
- 列宽按中英文混排实际长度核对：表头不换行、长单元格不超过 3 行。

详见 `references/tables.md`。

### 公式

- 显示公式转 OMML 后检查：`m:den`/`m:num` 非空，函数参数不进 `m:sub`，上下标/求和上下限无空占位。
- 行内公式**不要一刀切全转 OMML**；长公式会断行、`.doc` 会全变图片。
- WPS 角标间距大先查：两端对齐、Unicode 上下标拆 run、非中文 run 缺显式字体。
- 用 `K.left_align_math_paragraphs(doc)` 显式左对齐并关闭 autoSpace；**Word 保存之后**用 `K.force_western_font(doc)` 写显式 Times New Roman。

详见 `references/formulas.md`。

### 流程图/示意图

- **不要用文生图模型**（DALL·E / Midjourney）画技术图：箭头方向、文字、拓扑不可靠。
- **本 skill 自带生成+校验**（6~15 节点，无需外部工具）：
  ```bash
  python scripts/diagram_kit.py spec.json -o figure.svg
  python scripts/check_diagram.py figure.layout.json
  ```
  `diagram_kit.py` 分层布局、避障折线、端口分散、实心箭头、标签避让；
  `check_diagram.py` 查节点重叠、文字溢出、线穿框、边自交、箭头缺失/方向错、
  标签重叠、有效 DPI。规格示例见 `references/diagram-spec-example.json`。
  `diagram_kit.py` 渲染需要 `matplotlib`（`pip install matplotlib`）；
  没装时 `check_diagram.py` 仍可检查已有 sidecar。
- 更复杂的架构图：drawio-mcp / drawio-skill（避障正交路由、`polish`/`inspect`）
  或 D2 + ELK/TALA；手绘风用 Excalidraw Architect MCP；大图用 Graphviz；
  必须进 GitHub 才用 Mermaid（节点 6~15）。
- 箭头 `shrinkA=shrinkB=0`，线宽 ≥1.5 pt，`mutation_scale≈9`；短箭头按框体边缘重算端点。
- 文字与框线留内边距，标签移出箭头线；判定框加高；边不穿过非端点节点。
- 按最终插入宽度检查可读性；图题与图同页；左右对比图两栏分别检查。

工具对比/安装见 `references/diagram-tools.md`；绘制细节见 `references/diagrams.md`。

### Word/WPS 兼容

```bash
powershell -File scripts/word_com.ps1 -Action compat -In 报告.docx
powershell -File scripts/word_com.ps1 -Action roundtrip -In 报告.docx
powershell -File scripts/word_com.ps1 -Action audit -In 报告.docx
```

- `compatibilityMode` 必须是 15（11 = Word 2003，公式会被转图片）。
- `roundtrip` 做打开→保存→关闭→重开，OMaths 不变、InlineShapes 不增加。
- `.doc` 会把 OMML 显示公式转图片；要求可编辑就交 `.docx`，并提前说明。
- **没有 WPS 实机就写“结构层面已处理，WPS 实机需用户确认”**，不要声称已修复。

详见 `references/compatibility.md`。

## 第五步：文献引用（引用了才做）

- 模板自带规范严格照抄；没写用 GB/T 7714 顺序编码制。
- 正文序号是**右上角标**（`<<cite:1>>` / `<<cite:1-3>>`）。
- 文末按正文首次引用顺序编号，每条带 `[J]` `[M]` `[Z]` 等标识；正文与列表一一对应。

详见 `references/citations.md`。

## 第六步：调页面利用率

只统计**需要编写**的页；封面、评分表、评语页、模板说明页、空白页不参与。

```bash
python scripts/page_fill.py out.pdf --list
python scripts/page_fill.py out.pdf --exclude 2,3
python scripts/page_fill.py out.pdf --pages 4-9
```

发现空洞先定位被顶到下一页的块：表格卡住 → `split=True` 允许跨页；图片卡住 → 只缩那一张，低于默认宽度 85% 就不硬缩。**不要全文统一缩放。**

详见 `references/layout-tuning.md`。

## 第七步：交付与审计

```bash
python scripts/verify_output.py 报告.docx --template 模板.docx --expect-tables 6
powershell -File scripts/word_com.ps1 -Action to-doc -In out.docx -Out 报告.doc
powershell -File scripts/word_com.ps1 -Action to-pdf -In out.docx -Out preview.pdf
```

`verify_output.py` **不依赖是否用了 Cursor**：模板骨架、1×1 外层表、表后空行、兼容模式、表格总数都会独立检查。交付前必须跑。

交付目录只留交付文件 + 审核记录；构建脚本、预览 PDF、测试 docx 放 `build/` 或交付前清理。完工时置顶 Agent 窗口/发通知。

## 交付前自检

- [ ] `cur.finish()` 只有目标格字数变化；模板骨架零变化；保护区未被改
- [ ] 封面字段按用户选择处理；标签、下划线、封面图未动；内嵌题目表行列未变
- [ ] 评分表逐项核过；硬要求逐条打勾；模板要求删除的说明文字删干净
- [ ] 标题层级符合模板；结果分析有读数/核对/结论，不是流水账
- [ ] 表格：无 1×1 外层表、表后空行、三线表边框 nil、留白 80 twips、总数符合预期
- [ ] 公式：显示公式结构正确；行内公式左对齐/关 autoSpace；非中文 run 有显式字体
- [ ] 图片：箭头有杆身、文字不压框、图题同页、按最终宽度可读
- [ ] 自绘图跑过 `check_diagram.py`：无节点重叠、线穿框、边自交、箭头缺失/方向错、
      标签重叠；有效 DPI ≥150
- [ ] `compatibilityMode=15`；保存往返 OMaths 不变、InlineShapes 不增加
- [ ] `verify_output.py` 通过；WPS 未实测项已注明
- [ ] 文件锁已查；被占用时用 `-修正版` 并说明；中间产物已收好
- [ ] 完工已置顶窗口/发通知

导出 PDF 翻一遍——排版问题在 PDF 里最直观。

## 脚本与参考

| 脚本 | 用途 |
| --- | --- |
| `docx_env.py --check/--plan/--cover` | 环境探测、模板勘察、封面字段 |
| `docx_kit.py` | 勘察/安全写入/封面填值/骨架与保护区校验/题注/表格/公式/兼容模式/文件锁 |
| `verify_output.py` | 交付前独立审计 |
| `diagram_kit.py` | JSON 规格 → 分层架构图 SVG/PNG + `.layout.json` |
| `check_diagram.py` | 图形几何校验：重叠/穿框/自交/箭头/标签/DPI |
| `page_fill.py` | 页面利用率（只统计需编写页） |
| `word_com.ps1` | `.doc ↔ .docx`、更新域、PDF、`compat`/`audit`/`roundtrip` |

| 参考 | 内容 |
| --- | --- |
| `intake.md` | 材料盘点、追问、封面字段、文件占用 |
| `course-conventions.md` | 材料检索、成品命名惯例、报告类型 |
| `template-analysis.md` | 四种形态、四步防护、封面/内嵌表格、格式提取 |
| `writing.md` | 标题层级、题注、正文与分析、代码、学术诚信 |
| `freeform.md` | 无模板/纯文科自由写作 |
| `citations.md` | 文献引用规范 |
| `tables.md` | 表格：无外层表、表后空行、三线表、留白、列宽 |
| `formulas.md` | OMML 结构、行内公式 WPS 间距、字体 |
| `diagrams.md` | 流程图/对比图：箭头、端点、文字、缩放 |
| `diagram-tools.md` | AI 画图工具选型：drawio-mcp、D2、Excalidraw、Agentic Mermaid、Eraser 等 |
| `diagram-spec-example.json` | `diagram_kit.py` 的 JSON 规格示例 |
| `compatibility.md` | Word/WPS、兼容模式、往返测试、文件锁 |
| `layout-tuning.md` | 页面利用率度量与收敛 |
| `docx-cookbook.md` | python-docx / Word COM 踩坑 |

## 边界

**做**：按模板产出 Word 报告；插入段落/图片/表格；题注与交叉引用；版面紧凑化；交付前结构审计。

**不做**：编造实验数据；把成品报告改头换面；没有模板也没有参照时凭空发明格式（先问）。
