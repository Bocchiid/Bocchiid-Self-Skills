# 公式：显示公式与行内公式分开处理

## 一、显示公式：转 OMML，但必须做结构检查

显示公式（独占一行、单独编号）统一转 OMML。**BuildUp 之后不能只看“能显示”**，
要检查 XML 结构：

| 检查 | 错误表现 | 正确结构 |
| --- | --- | --- |
| 分式分母 | `m:den` 为空，分母跑到 `m:f` 外面 | 分母必须在 `m:den` 内且非空 |
| 函数参数 | `Rα(T)` 的 `(T)` 被并进 `m:sub` | 参数属于函数/普通文本，不在下标里 |
| 求和上下限 | `m:limLow`/`m:limUpp` 出现空占位 | 上下限有内容或明确省略 |
| 上下标 | `m:e` 为空、`m:sub` 为空 | 每个 `m:e`/`m:sub`/`m:sup` 都有内容 |

检查方式：

```python
from docx import Document
M = '{http://schemas.openxmlformats.org/officeDocument/2006/math}'
doc = Document('out.docx')
for f in doc.element.body.iter(M + 'f'):
    den = f.find(M + 'den')
    assert den is not None and ''.join(den.itertext()).strip(), 'empty m:den'
```

更长一段的结构检查可写成 build.py 里的断言：分母非空、`m:sub` 没有整段函数参数、
上下标没有空 `m:e`。

## 二、行内公式：不要一刀切全转 OMML

全转 OMML 有两个副作用：

1. 长公式不能断行，容易顶出表格单元格或页面；
2. `.doc` 交付时全部变成图片。

规则：

- 只对**短小、独立、确实需要公式排版**的表达式转 OMML；
- 其他保留为文本（可用 Unicode 上下标），但必须处理字体与对齐；
- 不要用“真上下标 run”批量替换 Unicode 下标：短公式可以，长公式会出现
  Σ 在行尾、下标跑到下一行的断行问题。

## 三、WPS 行内公式间距过大：先查三个原因

不要一看到间距大就直接转 OMML。

### 1. 段落继承了两端对齐

`Normal` 样式常带 `w:jc=both`，公式会被拉伸。公式段落显式改左对齐，
并关闭自动间距：

```python
import docx_kit as K
print('math paragraphs:', K.left_align_math_paragraphs(doc))
```

等价 XML：

```xml
<w:pPr>
  <w:autoSpaceDE w:val="0"/>
  <w:autoSpaceDN w:val="0"/>
  <w:jc w:val="left"/>
</w:pPr>
```

### 2. 使用了 Unicode 下标/上标字符

Word 保存后会把 `x₁`、`H₂O` 这类字符拆成多个 run，WPS 对 run 边界更敏感，
角标间距会被拉开。

### 3. run 只有 eastAsia hint，没有显式西文字体

WPS 会把希腊字母/下标回退到宋体，按中文字宽排。

## 四、本次有效的方案

1. 行内公式保留 Unicode 下标（避免 Σ 和下标被拆到两行）；
2. **在 Word 保存之后**，给所有非中文 run 写入显式 Times New Roman：

```python
import docx_kit as K
changed = K.force_western_font(doc, 'Times New Roman')   # Word 保存之后调用
print('updated runs:', changed)
```

**顺序很重要**：必须在 Word 保存之后做，否则 Word 会把 `rFonts` 改回
`hint=eastAsia`。

## 五、`.doc` 的限制

`.doc` 格式会把 OMML 显示公式转成图片，这是格式限制，不是 bug。

- 老师要求公式可编辑 → 交付 `.docx`，并在交付说明里写清楚；
- 只收 `.doc` → 提前说明“显示公式会变成图片”，不要交付后才说；
- `.doc` 转换前可用 `word_com.ps1 -Action to-doc`，脚本会提示 OMML 数量。

## 六、自检

- [ ] 显示公式的 `m:den` 非空，分母在 `m:den` 内
- [ ] 函数参数没有落进 `m:sub`
- [ ] 上下限/上下标没有空占位
- [ ] 行内公式没有一刀切全转 OMML
- [ ] 公式段落显式左对齐，关闭 `autoSpaceDE` / `autoSpaceDN`
- [ ] 非中文 run 有显式 Times New Roman（ascii/hAnsi/eastAsia/cs，hint=default）
- [ ] Word 保存后 OMaths 数量不变、InlineShapes 不增加
- [ ] `.doc` 交付已说明公式会变图片
