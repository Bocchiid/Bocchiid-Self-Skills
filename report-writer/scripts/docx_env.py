#!/usr/bin/env python3
"""探测撰写 Word 报告所需的环境。写报告前跑一次。

用法：
    python docx_env.py --check              # 输出 JSON 环境报告
    python docx_env.py --describe <文件>     # 打印文档结构，标出可写入区域

--check 输出：
    {
      "python": "3.11.0",
      "python_docx": "1.2.0",
      "word_com": true,
      "ready": true
    }

能力与依赖的对应关系：
    python-docx   读写 .docx（插入段落、图片、表格、域）
    Word COM      处理老式 .doc、更新域、导出 PDF   —— 仅 Windows + 装了 Office
    两者都没有     只能产出纯文本/Markdown，交不出符合模板的 Word 文件
"""

import argparse
import io
import json
import os
import sys


def check_env():
    result = {"python": sys.version.split()[0], "python_docx": None,
              "word_com": None, "ready": False}
    try:
        import docx
        result["python_docx"] = getattr(docx, "__version__", "unknown")
    except ImportError:
        result["install"] = "pip install python-docx"
        result["mirror"] = ("pip install python-docx "
                            "-i https://pypi.tuna.tsinghua.edu.cn/simple")

    if sys.platform == "win32":
        try:
            import win32com.client  # noqa: F401
            result["word_com"] = True
        except ImportError:
            # pywin32 没装也可能能用 PowerShell 调 COM，非致命
            result["word_com"] = None
            result["word_com_note"] = ("pywin32 未安装；若需转换 .doc 或更新域，"
                                       "改用 scripts/word_com.ps1（走 PowerShell COM）")

    result["ready"] = bool(result["python_docx"])
    return result


# --------------------------------------------------------------------
# --describe：把文档结构摊平，方便判断“往哪里写、会不会破坏模板”
# --------------------------------------------------------------------

def _out():
    return io.open(1, 'w', encoding='utf-8', closefd=False)


def describe(path):
    from docx import Document
    from docx.oxml.ns import qn
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    doc = Document(path)
    w = _out()
    body = doc.element.body
    sects = doc.sections
    s = sects[0]
    w.write('页面: %.0f x %.0f pt, 页边距 左%.0f 右%.0f 上%.0f 下%.0f\n' % (
        s.page_width.pt, s.page_height.pt, s.left_margin.pt,
        s.right_margin.pt, s.top_margin.pt, s.bottom_margin.pt))

    def ptext(p):
        pPr = p._p.find(qn('w:pPr'))
        extra = []
        if pPr is not None:
            st = pPr.find(qn('w:pStyle'))
            if st is not None:
                extra.append('style=' + st.get(qn('w:val')))
            if pPr.find(qn('w:numPr')) is not None:
                extra.append('numbering')
        img = bool(p._p.findall('.//' + qn('w:drawing'))) or \
              bool(p._p.findall('.//' + qn('w:pict')))
        if img:
            extra.append('IMAGE')
        return '[%s] %s' % (','.join(extra) or '-', p.text.strip()[:70])

    def walk(el, indent, depth):
        mi = 0
        for child in el.iterchildren():
            tag = child.tag.split('}')[-1]
            if tag == 'p':
                w.write('%s%s\n' % (indent, ptext(Paragraph(child, doc._body))))
            elif tag == 'tbl':
                mi += 1
                t = Table(child, doc._body)
                pr = child.find(qn('w:tblPr'))
                bd = pr.find(qn('w:tblBorders')) if pr is not None else None
                w.write('%s<TABLE %dx%d %s>\n' % (
                    indent, len(t.rows), len(t.columns),
                    'BORDERED' if bd is not None else 'borderless'))
                if depth < 3:
                    for ri, row in enumerate(t.rows):
                        for ci, cell in enumerate(row.cells):
                            chars = len(cell.text.strip())
                            w.write('%s  cell[%d][%d] 已用%d字\n' % (indent, ri, ci, chars))
                            walk(cell._tc, indent + '    ', depth + 1)

    walk(body, '', 0)

    w.write('\n--- 判定提示 ---\n')
    w.write('这是一份**全量**结构转储（含所有段落），用来通读模板。\n'
            '\n'
            '要确定"往哪里写"，别靠猜——模板留给作者填写的区域有四种形态：\n'
            '  ① 单列长表 ② 多列表单（每行一个栏目）\n'
            '  ③ 正文区与评分表拼在一张表 ④ 纯段落结构\n'
            '只有 ① 能自动识别。请改用 **docx_kit.survey(doc)** 看逐行勘察，\n'
            '再用 Target 显式指定目标，最后用 Cursor.finish() 比对验证。\n'
            '详见 references/template-analysis.md。\n')
    w.flush()


def write(s):
    """往 stdout 写。中文 Windows 控制台是 cp936，打不出的字符直接替换掉，
    不让一条 emoji 把整个命令搞崩。"""
    enc = getattr(sys.stdout, 'encoding', None) or 'utf-8'
    try:
        sys.stdout.write(s.encode(enc, 'replace').decode(enc, 'replace') + '\n')
    except Exception:
        sys.stdout.write(repr(s) + '\n')


def show_plan(path):
    """一条命令给出写入方案：形态、可复制的 Target、要避开的表、下一步代码。"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from docx import Document
    import docx_kit as K
    write(K.plan(Document(path)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', action='store_true')
    ap.add_argument('--describe', metavar='文件', help='全量结构转储（含所有段落）')
    ap.add_argument('--plan', metavar='文件', help='写入方案建议（先跑这个）')
    a = ap.parse_args()
    if a.check:
        print(json.dumps(check_env(), ensure_ascii=False, indent=2))
    elif a.plan:
        show_plan(a.plan)
    elif a.describe:
        describe(a.describe)
    else:
        ap.print_help()


if __name__ == '__main__':
    main()
