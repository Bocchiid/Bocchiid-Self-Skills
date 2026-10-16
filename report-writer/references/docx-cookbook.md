# docx 技术要点与踩坑清单

这一页全是实测踩出来的。照着做能省掉大半天。

## 工具链选择

| 任务 | 工具 |
| --- | --- |
| 打开老式 `.doc` 模板 | Word COM（`SaveAs2(path, 16)`）→ `.docx` |
| 读写 `.docx` 内容 | python-docx |
| 更新 `SEQ` / `REF` / `TOC` 域 | Word COM（`Fields.Update()`） |
| 导出 PDF 看排版 | Word COM（`SaveAs2(path, 17)`） |
| 量页面利用率 | pymupdf 读 PDF |

`.doc` 是老二进制格式，python-docx 打不开，必须先转。转完再编辑，最后再转回去。

## ⚠️ 会让 Word 报"文件内容已经损坏"的三种写法

**这三种错误 python-docx 一律读不出来，只有 Word 打开时才报。** 写完一定要用 Word COM 打开验证一次，别只靠 python-docx 自检通过就交付。

### 1. 单元格以表格结尾

`w:tc` 的最后一个块级子元素不能是 `w:tbl`。

```python
# 错的：cell 里最后一个元素是表格
cell.append(table)

# 对的：补一个空段落
cell.append(table)
cell.append(new_p(tiny=True))    # 1pt 段落标记，不占一整行
```

这正是 python-docx 自己的 `_Cell.add_table()` 会在末尾悄悄 `add_paragraph()` 的原因。`docx_kit.finish_cell()` 就是这个守卫。

**特别注意**：删掉某节内容后，该行的最后一个元素可能从段落变成表格，于是"昨天还好好的"文档突然打不开。

### 2. OOXML 子元素顺序错了

schema 对子元素顺序是强约束的。常见的：

```
w:pPr  : pStyle → keepNext → keepLines → shd → snapToGrid → spacing → ind → jc → rPr
w:rPr  : rFonts → b → bCs → noProof → color → sz → szCs → u → vertAlign
w:tblPr: tblW → jc → tblBorders → tblLayout → tblCellMar → tblLook
w:trPr : cantSplit → trHeight → tblHeader → tblCellSpacing → jc
```

`tblLayout` 排在 `tblCellMar` 后面就会损坏文件——这种错误格外难查。

⚠️ **给 run 加下划线（封面填值常用）时，`w:u` 要插在 `sz`/`szCs` 之后、`vertAlign` 之前。**
直接 `rPr.append(u)` 在已有 `vertAlign`（上标引用）的 run 上会得到非法顺序。
`docx_kit._ensure_underline()` 是按这个规则插的。

### 3. `powershell -File` 不同步工作目录

**Word COM 按 .NET 的 `CurrentDirectory` 解析相对路径，而 `powershell -File script.ps1`
不会把 `$PWD` 同步过去**（它停在 `C:\windows\system32`）。结果就是：在正确的目录里执行、
路径也没写错，Word 却报"找不到文件"，而且错误信息里的路径是 `C:\windows\system32\...`。

在脚本开头修掉：

```powershell
[System.Environment]::CurrentDirectory = (Get-Location).Path
if (-not [System.IO.Path]::IsPathRooted($In)) { $In = Join-Path (Get-Location).Path $In }
if ($Out -and -not [System.IO.Path]::IsPathRooted($Out)) { $Out = Join-Path (Get-Location).Path $Out }
```

`word_com.ps1` 已经内置了这段。自己写 PowerShell 调 COM 时也要加，否则只能全程用绝对路径。

### 4. 中文路径 + PowerShell 5.1

Windows PowerShell 5.1 把 `.ps1` 文件按 ANSI 解析（除非有 BOM），所以**脚本文件里写中文路径**会变成乱码导致"找不到该文件"。

- 脚本文件保持纯 ASCII（`word_com.ps1` 就是这个原则）；
- 中文路径通过命令行参数传进去没问题；
- 实在要在脚本里写死中文路径，就走 ASCII 临时目录中转，最后再 `cp` 回去。

## 嵌套表格（框里的题目表）

`w:tc` 的直接子元素可以是 `w:tbl` —— 模板里的题目表、学生信息表就是这么放的。

| 要干的事 | 正确做法 |
| --- | --- |
| 列出**所有**表格 | 递归：`docx_kit.iter_tables(doc.element.body)`；`doc.tables` 只给顶层 |
| 结构指纹 | **必须**递归（`snapshot()` 已改）——只盯顶层的话，内嵌表被改坏了看不见 |
| 判断"格子里有没有表" | `tc.findall(qn('w:tbl'))`（直接子元素，别用 `iter`） |
| 判断"格子空不空" | 只看 `tc.findall(qn('w:p'))` 的文字。`cell.text` 会**把内嵌表格里的字也算进去** |
| 往这种格子写内容 | `Target.after('锚点')` 或 `Cursor(..., clear=False)`，**不要清空** |

⚠️ 清空格子（删 `w:p`）时内嵌表格会**浮到格子最前面**——它本来在某个说明段落下面，
清完上面的文字没了、表格顶上去，版式就毁了。所以 `check_target()` 见到目标格里有
`w:tbl` 直接拦下来（见 `template-analysis.md` 第七节）。

⚠️ 删完段落，单元格的最后一个块级元素可能从 `w:p` 变成 `w:tbl`，于是"昨天还能打开的
文档"突然报损坏（见上面第 1 条）。`finish()` 会往上找最近的单元格补一个 1pt 段落，
锚点在单元格里时也管用。

## 往既有的 run 里填值（封面字段）

封面字段不能"重写这一段"，只能**只动值那几个 run**（`docx_kit.fill_field()`）：

- 先按**字符**定位「标签：」结束的位置，落到第几个 run 上就把那个 run 从该字符处
  切开（`_split_run_at`）——所以「姓」「　」「名」「：」四个 run 的写法也不会被破坏。
- 标签之后如果全是空白 run（下划线 / 空格 / 空文字），**第一个填值、其余置空**。
  置空而不是删除：格式（下划线、字号）留在原地，肉眼就是"那条下划线被写上了字"。
- "这是空白 run"的判据是 `text.strip('_＿ \t　') == ''`——**全角空格 `　` 也要算进去**，
  模板爱用它占位。
- 一个 run 里挤着「标签：值」时切开后只替换值那一半，标签一个字不动。
- 写 `<w:t>` 时记得 `xml:space="preserve"`，否则值前后的空格会被吃掉。

## 域（域的缓存值必须填对）

题注编号用 `SEQ` 域、交叉引用用 `REF` 域：

```
SEQ 图 \* ARABIC          生成递增编号
REF _Ref_fig01 \h         引用书签内容（显示为"图 3"）
```

书签要包住"图 3"整段：`bookmarkStart` 放在 `图` 之前，`bookmarkEnd` 放在 SEQ 域之后，这样 `REF` 才能取到完整文本。

**关键**：域的 `separate` 与 `end` 之间那段 run 是**缓存结果**。很多人打开文档从不按 F9，看到的就是缓存值。所以生成时必须把缓存值填成正确的编号，不能留空或占位符。

`docx_kit.Captions` 用两遍法保证这一点：先按最终出现顺序把编号全登记好，再渲染——因为正文里"如图 4 所示"很可能出现在图 4 *之前*，一边写一边编号必然串号。

交付前用 `word_com.ps1` 刷两遍 `Fields.Update()` + `Repaginate()` 兜底。

## 图片体积

截图原样嵌入会让文档爆炸：22 张截图的 RGBA PNG 合计 19.7 MB，成稿 21.6 MB。

处理办法是**生成小体积副本再插**，别动原图：

```python
from docx_kit import compact_image
compact_image('shots/raw.png', 'pics/small.png', max_px=1800)
```

- 缩到 1800 px 宽：显示宽度 420 pt 时约 308 dpi，肉眼无差；
- 转 256 色 PNG：截图色数本就少，几乎无损。

实测 19.7 MB → 3.1 MB，成稿 4.0 MB。打印尺寸下完全看不出区别。

## 段前段后

**插入的段落不要带 `w:before` / `w:after`。** 让它继承 Normal 样式的 0 值。写了显式间距，用户会一眼看出来"这不是模板的样式"。

题注也一样——靠 `Caption` 样式本身，不要额外加段间距。

## 样式：不要假设模板里有某个样式

同样是"实验报告模板"，不同实验的模板可能完全不同：

- 有个模板的 `Caption`（题注）段落样式存在，`styleId="a4"`；
- 另一个模板的 `a4` 其实是**字符样式**「页眉 字符」，根本没有 `Caption` 段落样式。

照抄前一份报告用的 `pStyle` 值，就会静默套错样式。

**动手前先列出模板的样式表**：

```python
for s in doc.styles:
    print(s.style_id, s.type, s.name)
```

要用的样式不存在时，可以往 `d.styles.element` 里**追加**一个（只增不改，不破坏模板），同时给每个 run 写上显式字体字号，这样即使样式被丢弃外观也不变。

## 老式 `.doc` 往返会丢元数据——不要追

`.docx` 存回 `.doc`（哪怕是原封不动的模板）都会掉一些东西：`w:rFonts w:hint="eastAsia"`、每个 `w:tblPr` 里的 `w:tblInd`、`Default Paragraph Font` / `Normal Table` / `Table Grid` 的样式定义会被重新规范化。

这些是**不可避免且不可见**的。判断"模板有没有被我破坏"的正确方法是：把原始模板也走一遍同样的往返，再比较两者的 XML 差异集合；差异集合一致即视为没破坏，而不是要求差异为零。

`w:trHeight` 是**会**保留下来的，所以如果框的每行最小高度明显丢了，那才是真的把表格重建了。

## bash 里拼 Windows 路径：`\$` 会被吃掉

从 bash 调 PowerShell 传路径时，这个坑极其容易踩：

```bash
f=p1
echo "C:\temp\lab5\$f.docx"      # → C:\temp\lab5$f.docx     ← 错了！
echo "C:/temp/lab5/$f.docx"      # → C:/temp/lab5/p1.docx    ← 对了
```

`\$` 在双引号里被 bash 当成**转义的美元符**，变量不再展开，路径里直接多出一个
字面量 `$f`。症状是脚本报"找不到文件"，而文件明明在——很容易误判成 Word/脚本的问题。

**对策**：用正斜杠 `C:/temp/lab5/$f.docx`（Windows 和 Word COM 都接受），
或者写成 `"C:\\temp\\lab5\\$f.docx"`。

⚠️ 别急着把它当成"Word COM 不稳定"。先 `echo` 一下实际传进去的字符串，
或者让脚本把收到的路径打出来，再下结论。

## Word 文件被占用

文件在 Word 里开着时写入会失败。`word_com.ps1` 会先试着自己打开目标文件（独占方式），失败就提示大概率被 Word 占用。

**提前告知用户比事后报错好**——在动手写之前就检查一次。

## 工作目录约定

**中间产物写在报告所在目录下**，不要图省事丢到系统临时目录：

```
报告目录/
├── <学号>-<姓名>-实验5.doc          ← 交付物
├── <学号><姓名>-实验5-模板.doc       ← 模板（原样不动）
├── <实验N>-实验指导.pdf              ← 指导书（原样不动）
├── Pictures/                        ← 用户给的截图（原图不动）
├── build/                           ← 你的中间产物
│   ├── work.docx                    ← 从模板转来的工作副本
│   ├── build.py                     ← 本次报告专用构建脚本
│   ├── pics/                        ← 压缩后的图片副本
│   └── preview.pdf                  ← 自查排版用
```

好处：用户一眼能看全过程、相对路径不会突然失效、事后要改也找得到脚本。

**只有遇到绕不过去的权限问题时**才退到临时目录（目录只读、被同步盘锁住、路径太长），并在交付时说明中间产物在哪。

⚠️ 反过来也要注意：**不要覆盖用户给的原始材料**——截图原图、指导书、模板都只读不动。压缩图片时生成到 `build/pics/`，别原地改 `Pictures/`。
