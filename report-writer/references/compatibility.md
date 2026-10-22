# Word / WPS 兼容、文件锁与交付

## 一、为什么 Word 正常、WPS 不正常

WPS 与 Word 在几处行为不同，Word 里看不出来的问题会在 WPS 里现形：

| 现象 | 原因 | 修法 |
| --- | --- | --- |
| 表格外多一圈边框 | 用 1×1 外层表包“表题 + 表格” | 删掉外层表，用 `K.table_block()` |
| 行内公式角标间距大 | 两端对齐、Unicode 上下标拆 run、非中文 run 缺显式字体 | 见 `formulas.md` |
| 公式被拉伸 | 段落继承 `Normal` 的 `w:jc=both` | 公式段落显式左对齐 |
| 关闭时提示“公式转图片” | `compatibilityMode=11` | 改为 15 |

## 二、compatibilityMode

`.doc` 转 `.docx` 后，`word/settings.xml` 里常常仍是：

```xml
<w:compatibilityMode w:val="11"/>
```

`11` = Word 2003。保持 11 时，Word 保存会把 OMML 公式转成图片，关闭时提示
“以前版本/公式转图片”。

改成：

```xml
<w:compatibilityMode w:val="15"/>
```

两种做法：

```python
import docx_kit as K
K.set_compatibility_mode(doc, 15)
```

```bash
powershell -File scripts/word_com.ps1 -Action compat -In 报告.docx
```

⚠️ **顺序**：如果同时要改 `rFonts`，兼容模式要在 Word 保存之后设置，
否则 Word 可能写回 11。

## 三、保存往返测试

修改后必须做：

```bash
python scripts/verify_output.py 报告.docx --template 模板.docx --expect-tables 6
powershell -File scripts/word_com.ps1 -Action audit -In 报告.docx
powershell -File scripts/word_com.ps1 -Action roundtrip -In 报告.docx
```

`verify_output.py` 独立于 build 脚本，复核模板骨架、1×1 外层表、表后空行、
兼容模式与表格总数。

`roundtrip` 会执行“打开 → 保存 → 关闭 → 重新打开”，输出前后：

- `compatibility_mode`
- `omml`（OMML 公式数）
- `inline_shapes`（InlineShapes 数）

判定：

- `omml` 前后不变；
- `inline_shapes` 不增加；
- 否则说明公式在保存时变成了图片，必须修兼容模式后重做。

## 四、WPS 专项检查（审核必列）

以下四项**没有 WPS 实机就不能打勾**：

- [ ] 表格外圈没有多一圈
- [ ] 行内公式角标没有被拉开
- [ ] 两端对齐段落里的公式没有被拉伸
- [ ] 关闭文档时没有“公式转图片/以前版本”提示

如果当前环境没有 WPS，审核报告里要明确写：

> **结构层面已处理，WPS 实机需用户确认。**

**不要写“WPS 已修复”**——没测就是没测。

## 五、文件锁：先检查，再覆盖

目标文件在 Word/WPS 里开着时，覆盖会失败。表现为：

- 目录里有 `~$报告.docx` 锁文件；
- 无法以独占方式打开目标文件；
- `word_com.ps1` 以退出码 3 失败并打印 `FILE_LOCKED`。

处理：

1. **先查再写**：`K.file_in_use(path)` 或 `word_com.ps1` 内置检测；
2. 被占用时**不要反复重试**，直接告诉用户关闭；
3. 需要继续交付时，生成带后缀的文件：
   - `报告-修正版.docx`
   - 或 `报告-v2.docx`
4. 在交付说明里写清楚：
   - 当前最新文件是哪个；
   - 原文件关闭后如何替换（覆盖/改名）；
   - 哪个是中间产物、可以删。

## 六、交付目录

```text
报告目录/
├── <学号>-<姓名>-实验5.doc          ← 交付物
├── <报告名>-审核报告-v2.md          ← 审核记录（保留）
├── build/                           ← 中间产物
│   ├── work.docx
│   ├── build.py
│   ├── pics/
│   └── preview.pdf
└── 备份/                            ← 需要时保留，交付前问用户
```

交付前清理：

- 构建脚本、预览 PDF、测试 docx、备份目录放进子目录，或明确告诉用户；
- 最终目录只留交付文件和必要审核记录；
- **不自动删**用户文件，清理前先问。

## 七、交付前兼容自检

- [ ] `compatibilityMode=15`
- [ ] `roundtrip` 前后 OMML 数不变、InlineShapes 不增加
- [ ] 没有 1×1 外层包裹表
- [ ] WPS 四项已实测，或已注明“需用户确认”
- [ ] 目标文件未被占用；被占用时已用 `-修正版` 并说明
- [ ] 中间产物已收进子目录或说明保留原因
- [ ] 交付完成已置顶 Agent 窗口/发通知
