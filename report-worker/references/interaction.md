# 交互：先问材料，再动手

## 0. 记下 Agent 窗口

开始前用 `desktop.py list-windows` 看窗口标题，或直接问用户“这个对话窗口的标题是什么”，
然后记下来：

```bash
python scripts/worker.py --workspace <WS> set --agent-window "<标题>"
```

之后每批操作完成时，用它把窗口置顶/闪烁提醒用户。

## 1. 开始时的材料清单

先盘点用户已经给了什么，再列缺口；一次问完。

### 先问五件事（不要默认）

1. **代码/实践部分怎么处理**：我直接生成可运行代码 / 只给骨架 / 你写我审？
   课程是否允许 AI 代写？
2. **交付格式**：`.doc` 还是 `.docx`？老师接受 `.docx` 吗？
3. **主要软件**：Word 还是 WPS？
4. **模板结构**：行数/栏目名能不能动？默认绝对不能动。
5. **公式**：是否必须可编辑？必须 → 优先 `.docx`。

顺带问：有没有往届成品/老师样例？只用于格式，不抄内容。

**五项回答必须落盘**，否则 `PLAN_FREEZE` 会被 `decisions` 闸门拒绝：

```bash
python scripts/worker.py --workspace <WS> decide --key code_policy --value skeleton --note "用户说自己写，我只审查"
python scripts/worker.py --workspace <WS> decide --key delivery.format --value docx --note "老师接受 docx"
python scripts/worker.py --workspace <WS> decide --key delivery.editor --value wps --note "主要用 WPS 批改"
python scripts/worker.py --workspace <WS> decide --key template_editable --value no --note "用户要求严格保持模板行数"
python scripts/worker.py --workspace <WS> decide --key formula_editable --value yes --note "公式必须可编辑"
```

合法值：

| key | 可选值 |
| --- | --- |
| `code_policy` | `generate` / `skeleton` / `user_writes_review` / `not_applicable` |
| `delivery.format` | `doc` / `docx` / `pdf` / `same_as_template` |
| `delivery.editor` | `word` / `wps` / `both` / `unknown` |
| `template_editable` | `yes` / `no` |
| `formula_editable` | `yes` / `no` / `not_applicable` |

用户说“随便/你定”也要记录一个值，并在 note 里写“用户授权按默认”，不能沉默跳过。

```markdown
## 我看到的材料
- [x] 指导书：<路径>
- [x] 模板：<路径>
- [ ] 评分表：缺
- [ ] 实际方案：缺
- [ ] 成品参考：缺

## 需要你确认
1. 实际方案/老师口头要求：...
2. 交付格式/截止：...
3. 环境：本机/WSL/远程；有没有 GUI：...
4. 课程是否允许自动化：...
```

缺关键材料时说明影响：

> 缺评分表会影响“写到什么程度”和证据重点；缺实际方案会影响步骤和报告差异。
> 如果都没有，我先按通用流程规划，并把假设标出来。

用户说没有就接受，不反复追问。

### 材料清单模板

```markdown
# 材料清单

## 已有
- [x] 指导书：<路径>
- [x] 模板：<路径>

## 还缺
- [ ] 评分表：影响证据重点和写作深度
- [ ] 实际方案：影响步骤和差异说明

## 用户确认
- 用户确认：没有评分表；按通用流程规划
- 用户确认：没有往届成品；只按模板格式
```

### 记录用户决策

每次用户回答“有/没有/不需要/这样改”都用命令落盘，ANALYZE 闸门会检查：

```bash
python scripts/worker.py --workspace <WS> decide \
  --key materials --value no --note "用户确认没有评分表，按通用流程规划"
python scripts/worker.py --workspace <WS> decide \
  --key conflict.C1 --value skip --note "模板没有参考文献区，用户确认不保留"
```

没有 `材料清单.md` 和至少一条 decision，`worker.py advance --to PLAN` 会被拒绝。

## 2. 执行前

需要 GUI/截图时：

> 接下来要操作键鼠/截图，请全程不要触碰键盘鼠标；完成后我会提醒你。
> 如果现在不方便，我可以先做不需要 GUI 的步骤。

等用户确认后再开始；需要时分阶段。

## 2.5 方案确认（冻结前）

把方案发给用户过一眼，不要闷头做：

> 我准备按这个方案执行：
> - 实验目的：...
> - 实际步骤/环境：...
> - 代码/实践部分：<代写/骨架/你写我审>
> - 交付：<.doc/.docx>，主要用 <Word/WPS>
> - 报告结构：<章节大纲>
> - 需要你确认：<1~3 个关键点>
>
> 确认后我冻结计划并开始；要改哪一项直接说。

用户说“先改一下”就回 PLAN；不要偷偷改计划继续。

## 2.6 截图验收后（不要直接跳 writer）

| 结果 | 提示 |
| --- | --- |
| 本阶段通过，还有后续 | 继续下一阶段。 |
| 本阶段通过，全部完成 | A. 交给 writer；B. 先改执行卡/指导书（升 v1.1）；C. 补 L2/L3。 |
| 不通过/部分通过 | 给补拍清单；执行卡与实际不符就先改卡。 |
| 截图合格但结果不符 | 先排错，不重拍同样结果的图。 |

只有所有阶段 L1 通过 + 步骤完成/跳过，才运行：

```bash
python scripts/verify.py --workspace <WS> execution
python scripts/worker.py --workspace <WS> advance --to WRITE
```

## 3. 执行后

> 本阶段完成，截图/日志已保存到 ...；接下来做 ...。
> （把 Agent 窗口置顶/提醒用户）

```bash
python scripts/desktop.py --workspace <WS> notify \
  --title "<Agent 窗口标题>" --message "本阶段完成，请查看"
```

## 4. 缺依赖 / 缺 skill

> 当前缺少 <依赖>，没有它无法 <动作>。
> 选项：1) 我给出安装/复制命令，你确认后执行；2) 你手动安装；3) 换不需要它的方案。
> 不安装的话，这一步只能人工做。

不要擅自装系统包/驱动/服务；不要全局 `pip install`。

## 5. 用户说“没有/不需要”

- 接受，记录为假设/决策；
- 不反复追问；
- 在计划/报告/审核里注明“用户确认没有/不需要”。

## 5.5 用户问“这个材料需要吗 / 这个点要吗”

先给判断依据和影响，再给建议：

> 这个材料主要影响 <步骤/证据/章节>；有它会更稳，没有也能按 <降级方案> 做。
> 如果你没有/不想补，我就按没有规划，并把假设标出来。

不替用户做决定，也不把“建议”说成“必须”。

## 6. 用户说“这点不对”

先复述理解，再说明影响，最后请确认：

> 我理解你说的是 <复述>。如果保留，会影响 <步骤/证据/章节>；如果删掉，会 <影响>。
> 你希望保留、删除，还是先按 <折中>？

不争辩，也不沉默照做。

## 7. 模板/评分表冲突

> 评分表要求“参考文献”，但模板没有参考文献区，也没有正文引用要求。
> 这更像模板/评分表的问题。默认我不保留这一点；如果你确认要保留，我会放在文末/脚注，
> 不动封面和评分表。你选哪个？

默认不保留，记录原因，同步 writer/reviewer。

## 7.5 完成时置顶窗口

报告做完后，用户被要求“不要触碰键鼠”。如果完工不提醒，他根本不知道已经好了。

`worker.py` 进入 DONE 会自动调用 `desktop.notify`（需要先 `set --agent-window`）。
手动兜底：

```bash
python scripts/desktop.py --workspace <WS> notify \
  --title "<Agent 窗口标题>" --message "报告已完成，请查看交付文件与审核报告"
```

如果窗口标题未知，先问用户，或用 `list-windows` 找。

## 8. 结束前清理

> 报告和证据已经完成。工作过程中产生了 `_worker/`、`报告/_work/`、`Pictures/_raw/` 等临时文件。
> 要我清理吗？可以：1) 全部保留；2) 只删中间稿；3) 全部清理（报告/证据保留）。

**不自动删**；用户确认后再清理。可以选择：

```bash
# 只清理中间稿（保留 state/证据/日志）
python scripts/worker.py --workspace <WS> cleanup --scope intermediate --confirm
# 连 _worker 一起清理（报告/证据保留）
python scripts/worker.py --workspace <WS> cleanup --scope all --confirm
```
