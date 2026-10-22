# 流程图 / 对比图：箭头、文字、缩放

报告里的流程图、架构图、时序图、左右对比图，默认由 writer 用代码绘制
（D2 / Graphviz / draw.io / Mermaid 导出）。这一页讲**画出来能不能看**。

> **不要用 DALL·E / Midjourney 之类的文生图模型画技术图。** 它们不理解拓扑和箭头，
> 常出现反向箭头、连线穿框、标签乱码、图看着专业但事实错误。正确路线是
> **LLM 生成 D2/Graphviz/Mermaid/draw.io 结构 → 确定性布局引擎 → 几何校验 → 人工终检**。
> 具体工具选型、安装命令、能力对比见 `diagram-tools.md`。

## 零、工具速选

| 场景 | 首选 |
| --- | --- |
| 系统架构图，要干净、可编辑 | drawio-mcp（`polish`/`inspect`）或 drawio-skill |
| 本地、无云、架构图 | D2 + `--layout=elk` 或 `tala` |
| 手绘风/教学示意 | Excalidraw Architect MCP |
| 必须进 GitHub/Markdown | Mermaid（节点 6~15，边多就拆图） |
| 大型依赖/调用图 | Graphviz（`splines=ortho`） |
| 已有图，查重叠/穿框 | Agentic Mermaid `verify` / drawio `inspect` |

完整对比、安装与局限见 `diagram-tools.md`。

## 零·五、用 `diagram_kit.py` 生成 + `check_diagram.py` 校验

本 skill 自带一个轻量生成器，适合 6~15 个节点的架构图/流程图，不依赖 D2/Graphviz：

```bash
# 1. 写 JSON 规格（示例见 references/diagram-spec-example.json）
python scripts/diagram_kit.py --example spec.json

# 2. 生成 SVG + PNG + 几何 sidecar
python scripts/diagram_kit.py spec.json -o figure.svg

# 3. 自动校验：节点重叠、文字溢出、线穿框、边自交、箭头缺失/方向错、标签重叠、DPI
python scripts/check_diagram.py figure.layout.json
```

`diagram_kit` 的布局策略：

- 分层（LR/TB）+ 层内 barycenter 排序，节点尺寸按标签自动估算；
- 相邻层在层间通道走线，跨层绕到所有中间节点之外，同层走层外侧；
- 端口按出入边数量分散，并做微小抖动，避免多条线共线重叠；
- 箭头 = 折线杆身 + 实心三角形，`shrink` 逻辑天然为 0；
- 标签在候选位置里选一个不压节点、不压其他标签的位置；
- 输出 `.layout.json`，checker 不靠图像识别，直接做几何判定。

**边界**：它是简单分层布局，不是通用图引擎。节点超过 ~20、交叉密集或需要复杂分组时，
改用 drawio-mcp / D2+ELK/TALA / Graphviz；`check_diagram.py` 仍可检查
`diagram_kit` 生成的 sidecar。

## 一、箭头：杆身不能消失

### 症状

短箭头只显示箭头头部，中间的杆身没了。原因是：

- `shrinkA` / `shrinkB` 设成了 2（或更大），短箭头被两端各“缩”掉一截，
  只剩箭头头；
- 短箭头的端点按“框中心 + 固定偏移”估算，没有按框体边缘重新计算。

### 规则

- 箭头统一 `shrinkA=0`、`shrinkB=0`（matplotlib `annotate` / `FancyArrowPatch`）；
- 线宽不低于 **1.5~1.7 pt**；
- 箭头头部不要过大，`mutation_scale≈9`；
- 短箭头必须按“上一个框的下边 → 下一个框的上边”重新算端点：

```python
# 竖直短箭头：从上一个框的下边到下一个框的上边
start = (x, prev_box_bottom)
end = (x, next_box_top)
if end[1] - start[1] < 12:          # 太短就加长间距，别硬缩
    end = (x, start[1] + 12)
ax.annotate('', xy=end, xytext=start,
            arrowprops=dict(arrowstyle='-|>', lw=1.6,
                            shrinkA=0, shrinkB=0,
                            mutation_scale=9))
```

- 左右对比图（“修改前 / 修改后”）两栏的箭头逻辑**分别检查**，不能只修左栏；
- 时序图的箭头端点落在参与者的生命线上，不要落在文字标签上。

## 二、文字：不能压框、不能压线

- 框内文字与框线之间留内边距（建议 `pad=6~10`），必要时加高判定框；
- 标签移出箭头线：放在箭头旁边，或给标签加白底（`bbox=dict(facecolor='white', edgecolor='none', pad=2)`）；
- 文字不要盖住数据点、坐标轴刻度、图例；
- 中英文混排时给字体设置显式中文字体（如 SimSun / Microsoft YaHei），
  避免方框或回退。

## 三、尺寸：按最终插入宽度检查

不要只看原始大图。报告里图片通常以 380~430 pt 宽插入，必须按这个宽度看：

1. 生成图片时按目标宽度设定 figsize 和字号（例如 7 in 宽、8~9 pt 字）；
2. 插入后再导出 PDF，放大到 100% 检查：
   - 最小字号是否还清楚；
   - 箭头杆身是否可见；
   - 文字是否压框；
3. 图题必须与图同页（插图段落 `keepNext`）。

## 四、常见图的检查清单

### 流程图 / 架构图

- [ ] 每个框都有清楚的文字，文字不压框线
- [ ] 箭头有杆身，方向明确
- [ ] 分支条件标在箭头上或箭头旁，不压线
- [ ] 图例/注释不遮挡主体

### 时序图

- [ ] 参与者名称完整
- [ ] 箭头端点落在生命线上
- [ ] 消息顺序与正文/截图一致
- [ ] 消息标签不被箭头穿过

### 左右对比图

- [ ] 左右两栏的箭头逻辑分别检查过
- [ ] 两栏标题、坐标轴、图例一致
- [ ] 差异标注没有遮挡数据

## 五、生成后自检

- [ ] `shrinkA=shrinkB=0`，线宽 ≥1.5 pt，`mutation_scale≈9`
- [ ] 短箭头端点按框体边缘计算，没有“只剩箭头头”
- [ ] 文字与框线有内边距，标签不在箭头线上
- [ ] 判定框已加高，文字没有挤成多行
- [ ] 按最终插入宽度可读
- [ ] 图题与图同页
- [ ] 左右对比图两栏都检查过
