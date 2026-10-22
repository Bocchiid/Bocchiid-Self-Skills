#!/usr/bin/env python3
"""交付前独立审计：不依赖 build 脚本是否用了 Cursor。

用法：
    python verify_output.py 报告.docx
    python verify_output.py 报告.docx --template 模板.docx
    python verify_output.py 报告.docx --template 模板.docx --expect-tables 6

检查：
  - 模板行数/列数/合并/栏目名是否与模板一致（给了 --template 才查）
  - 1×1 外层包裹表
  - 表格后是否空一行
  - compatibilityMode 是否为 15
  - OMML 公式数、InlineShapes 数
  - 表格总数（可用 --expect-tables 核对“主表 + N 张数据表”）

退出码：0 = 通过；1 = 有错误。输出 JSON，方便写进交付说明或审核记录。
"""

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import docx_kit as K  # noqa: E402

M_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/math}"


def audit(report, template=None, expect_tables=None):
    from docx import Document

    doc = Document(report)
    errors = []
    warnings = []

    compat = K.compatibility_mode(doc)
    if compat != 15:
        errors.append(f"compatibilityMode={compat}（应为 15；否则 Word 保存时"
                      "可能把 OMML 公式转成图片）")

    wrappers = K.wrapper_tables(doc)
    if wrappers:
        errors.append("发现 1×1 外层包裹表：%s" %
                      "; ".join(f"{label} {text}" for label, text in wrappers))

    no_blank = K.tables_without_blank(doc)
    if no_blank:
        errors.append("表格后没有空段落：%s" %
                      "; ".join(f"{label} {why}" for label, why in no_blank))

    top, all_count = K.table_counts(doc)
    if expect_tables is not None and all_count != int(expect_tables):
        errors.append(f"表格总数 {all_count} ≠ 预期 {expect_tables}"
                      "（多出来的通常是 1×1 外层表）")

    shape_issues = []
    if template:
        tpl = Document(template)
        shape_issues = K.diff_template_documents(tpl, doc)
        if shape_issues:
            errors.append("模板骨架被改动：" + "; ".join(shape_issues[:5]))

    # InlineShapes 包含所有截图，不能拿它和 OMath 数量直接比；
    # “公式是否变图片”要用 word_com.ps1 -Action roundtrip 比较保存前后。
    omml = len(list(doc.element.body.iter(M_NS + "oMath")))
    inline = len(doc.inline_shapes)

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "compatibility_mode": compat,
        "tables": {"top_level": top, "all": all_count},
        "wrappers": [{"table": label, "caption": text} for label, text in wrappers],
        "tables_without_blank": [{"table": label, "why": why}
                                 for label, why in no_blank],
        "template_shape_issues": shape_issues,
        "omml_count": omml,
        "inline_shapes": inline,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("report")
    ap.add_argument("--template", default="")
    ap.add_argument("--expect-tables", type=int, default=None)
    args = ap.parse_args()
    result = audit(args.report, args.template or None, args.expect_tables)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
