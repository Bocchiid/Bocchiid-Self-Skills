# 示意图/架构图：AI 工具选型与验收

> 结论先说：**不要用 DALL·E / Midjourney / 文生图模型画技术示意图。**
> 它们生成的是像素图，不理解拓扑、箭头方向和文字，常见“箭头反向、连线穿框、
> 标签乱码、图看着专业但事实错误”，而且不可编辑。
>
> 可靠路线是：**LLM 生成结构化图/DSL → 确定性布局引擎 → 几何校验 → 人工终检。**

## 一、为什么文生图不适合

| 问题 | 文生图 | 图 DSL + 布局引擎 |
| --- | --- | --- |
| 文字准确 | 不保证，常乱码 | 文字是源数据，准确 |
| 箭头方向 | 不保证，可能反向/成环 | 由边定义决定 |
| 连线穿框 | 常见 | 布局/路由引擎处理 |
| 可编辑 | 只能重生成 | 改源码即可 |
| 版本管理 | 二进制图片 | 文本 diff |
| 复杂拓扑 | 超过几个节点就崩 | 可到几十个节点（仍建议控制规模） |

**推荐：让 LLM 写 D2 / Graphviz DOT / Mermaid / draw.io XML，由布局引擎算坐标。**
不要让 LLM 直接输出 SVG 坐标或像素图。

## 二、工具选型

### A. 最贴合“无重叠、箭头完整、不穿框”的

| 工具 | 形态 | 优点 | 注意 |
| --- | --- | --- | --- |
| **drawio-mcp**（yohasacura） | Python MCP，生成 `.drawio` | Sugiyama/tree/grid 布局；**obstacle-aware orthogonal routing**；`polish` 一次修布局/重叠/连线/标签；`inspect` 查 overlaps/ports；310+ 形状、21 主题 | 社区项目；装 `pip install drawio-mcp` 或 `uvx drawio-mcp`；版本以仓库为准 |
| **draw.io 官方 MCP**（jgraph） | 官方 MCP / hosted | 官方维护；vendored **libavoid** 做避障正交路由；ELK 后布局 | 能力随版本变化；必要时用 `check_layout` 类工具复核 |
| **drawio-skill**（Agents365-ai） | Agent Skill | Graphviz 布局 + `splines=ortho`；`edgeports.py` 分散端口；导出 PNG 后**视觉自检 + 自动修 2 轮**；`validate.py` 先查悬空边/重复 ID | 面向 Claude Code 等 Agent；Graphviz 可选依赖 |
| **D2 + ELK/TALA** | 本地 CLI，`.d2` → SVG/PNG | 架构图专用；ELK 有正交路由和更好标签；**TALA 已开源（MPL-2.0，D2 v0.9+）**，正交、白板风格、支持锁定坐标 | TALA 有随机性、长 DAG 较弱、大图较慢；安装 `winget install -e --id Terrastruct.D2` |
| **Excalidraw Architect MCP** | Python MCP，输出 `.excalidraw` | Sugiyama 分层；**obstacle-aware edge routing**（箭头绕开中间节点）；hub 节点自动拉伸；断开子图不重叠；50+ 技术组件；离线、MIT | 手绘风格；适合教学/草图；`pip install excalidraw-architect-mcp` 或 `uvx` |
| **Graphviz** | 本地 CLI | 大图（几百上千节点）最稳；`splines=ortho` 正交路由；语法刚性，LLM 出错率低 | 外观偏“学术论文”；架构图标少 |

### B. 校验/修复型（不负责画，负责抓问题）

| 工具 | 能抓什么 |
| --- | --- |
| **Agentic Mermaid** `verifyMermaid` | `NODE_OVERLAP`（节点重叠）、`ROUTE_SELF_CROSS`（边走线自交）、`EDGE_MISANCHORED`、`OFF_CANVAS`、`GROUP_BREACH`；按结构/几何/lint 分级，支持“检查→读码→修→再查” |
| **drawio-mcp `inspect` / `polish`** | overlaps、ports、reroute、fix labels |
| **drawio-mcp（abossard）`check_layout`** | 节点重叠、边标签碰撞、边穿节点、间距 |
| **drawio-skill PNG 自检** | 导出 PNG 后用视觉模型查重叠、截断、连错、穿框，自动修 2 轮 |

### C. 云端“AI 生成 + 可编辑”

| 工具 | 定位 | 适合 | 局限 |
| --- | --- | --- | --- |
| **Eraser DiagramGPT** | 文本/代码 → 架构图、时序图、ERD、云架构 | 软件架构、服务/数据库/队列；输出是可拖拽图形，不是图片 | 复杂图自动布局会乱，需要人工收尾；云服务、免费额度小 |
| **Mermaid Chart AI** | 文本 → 合法 Mermaid | 必须进 Git/Markdown、可 diff 的图 | 布局弱，约 20 节点以上边交叉明显；架构图类型支持有限 |
| **Lucidchart AI** | 企业级图表 + AI | 团队协作、模板、治理 | AI 架构图不如 Eraser 锐利；免费额度小 |
| **Napkin AI** | 文本 → 信息图/概念图 | 汇报、博客、概念示意 | **不是技术架构图工具**，不要用于系统事实图 |

## 三、按场景选

| 场景 | 首选 | 备选 |
| --- | --- | --- |
| 报告里的系统架构图，要干净、可编辑 | **drawio-mcp** 或 **drawio-skill** | D2 + ELK/TALA |
| 课程/答辩用的手绘风示意图 | **Excalidraw Architect MCP** | Excalidraw + Mermaid 导入 |
| 必须放在 README/GitHub 里 | **Mermaid**（节点控制在 6~15） | D2 导出 SVG 再嵌入 |
| 大型依赖/调用图 | **Graphviz** | D2 + ELK |
| 企业汇报、需要精美成品 | **Eraser** / **Lucidchart**，再人工收尾 | draw.io 手工排版 |
| 已有图，只想查重叠/穿框 | **Agentic Mermaid** / drawio `inspect` | 自己写 bbox 检查 |

## 四、硬规则（写进生成流程）

1. **节点规模**：架构图 6~15 个节点、流程图 10~25 个；超过就拆子图或分层，不要指望布局引擎在 40+ 节点上还好看。
2. **不让 LLM 定坐标**：只让它输出“组件 + 连接”的结构（D2/Mermaid/DOT/draw.io XML），坐标交给布局引擎。
3. **稳定 ID**：节点 ID 用英文/短横线，显示文字单独给 label；中文长标签会撑大节点、触发换行和重叠。
4. **高分辨率渲染**：SVG 优先；PNG 至少 2× 目标插入尺寸（报告里 400 pt 宽 ≈ 800~1200 px）。
5. **几何校验必做**：
   - 节点/文字框两两不重叠；
   - 边不穿过非端点节点；
   - 边不自交、不叠在同一条主干上；
   - 标签不压节点/边；
   - 箭头有杆身、箭头头完整。
6. **人工终检**：按最终插入宽度看一遍；左右对比图两栏分别看；图题与图同页。

## 五、给本 skill 的推荐流水线

```text
1. 先定“图要说明什么”（3~8 个关键组件，不要把所有细节塞进去）
2. 让 LLM 输出结构化 DSL：
   - 本 skill 自带：JSON spec → diagram_kit.py（轻量、无需外部工具）
   - 架构图：D2（ELK/TALA）或 draw.io XML
   - 流程/时序：Mermaid 或 D2
   - 大型依赖：Graphviz DOT
3. 用确定性布局引擎渲染（diagram_kit / D2 / draw.io / Graphviz / Mermaid）
4. 跑几何校验：
   - 自带：check_diagram.py（节点重叠/穿框/自交/箭头/标签/DPI）
   - 外部：drawio inspect/polish、Agentic Mermaid verify、drawio-skill PNG 自检
5. 导出 SVG/PNG → 按最终宽度检查 → 插入 Word → 图题同页
```

**没有外部工具时**，`diagram_kit.py + check_diagram.py` 就是兜底方案；
需要更复杂的架构分组时再装 D2/drawio。

**没有安装上述工具时**：直接用本 skill 自带的 `diagram_kit.py`（JSON → 分层布局）
和 `check_diagram.py`（几何校验），不要退回文生图。
如果只能用 Mermaid，控制节点数并人工检查边交叉；必要时拆成两张图。

**校验器的边界**：`check_diagram.py` 检查的是 `diagram_kit.py` 生成的
`.layout.json` sidecar，或 PNG 的有效 DPI；它不会对任意截图做视觉识别。
外部工具请用它们自己的 validator（drawio `inspect`/`polish`、Agentic Mermaid `verify`、
drawio-skill PNG 自检）。

## 六、验收清单（对应三条用户要求）

- [ ] **图案与图案、图案与文字不重叠**：节点 bbox 两两不相交；标签不压节点/边
- [ ] **图案完整**：箭头有杆身 + 箭头头；框线闭合；没有缺角/断线
- [ ] **线条不穿图案、指向合理**：边不穿过非端点节点；分支从合适端口出发；避免长对角线
- [ ] 架构图按层/子网/服务分组，跨组边尽量少
- [ ] 图在最终插入宽度下文字可读（≥8 pt）
- [ ] 图题与图同页；正文引用了图

## 七、来源

- D2 layouts / TALA open source：<https://d2lang.com/tour/layouts/>、<https://d2lang.com/blog/tala-is-open-source/>
- drawio-mcp（yohasacura）：<https://pypi.org/project/drawio-mcp/>
- draw.io 官方 MCP：<https://www.drawio.com/docs/manual/generate/drawio-mcp-server/>
- drawio-skill：<https://github.com/Agents365-ai/drawio-skill>
- Excalidraw Architect MCP：<https://github.com/BV-Venky/excalidraw-architect-mcp>
- Agentic Mermaid warnings：<https://agentic-mermaid.dev/warnings/>
- Eraser DiagramGPT：<https://www.eraser.io/ai>
- Mermaid Chart AI：<https://www.mermaidchart.com/ai>
- 文生图不适合技术图：<https://dev.to/msteja/why-ai-agents-cant-draw-svg-and-what-to-do-instead-1ci>
