#!/usr/bin/env python3
"""提取 .docx 的文本与格式信息，供实验报告审核使用。

用法：
    python parse_docx.py --check          # 仅检查环境是否就绪
    python parse_docx.py <文件路径>        # 解析指定文档

环境检查输出 JSON：
    {"python": "3.11.0", "python_docx": "1.1.0", "ready": true}
    或
    {"python": "3.11.0", "python_docx": null, "ready": false,
     "install": "pip install python-docx"}
"""

import json
import sys


def check_env():
    """检查 Python 与 python-docx 是否可用。"""
    result = {"python": sys.version.split()[0], "python_docx": None, "ready": False}
    try:
        import docx
        result["python_docx"] = getattr(docx, "__version__", "unknown")
        result["ready"] = True
    except ImportError:
        result["install"] = "pip install python-docx"
        result["mirror"] = "pip install python-docx -i https://pypi.tuna.tsinghua.edu.cn/simple"
    return result


def get_font_info(run):
    info = {"text": run.text}
    if run.font.name:
        info["font"] = run.font.name
    if run.font.size:
        info["size_pt"] = run.font.size.pt
    if run.bold:
        info["bold"] = True
    if run.italic:
        info["italic"] = True
    return info


def parse(path):
    from docx import Document

    doc = Document(path)
    result = {"paragraphs": []}

    for para in doc.paragraphs:
        if not para.text.strip():
            continue
        entry = {
            "text": para.text,
            "style": para.style.name if para.style else None,
            "runs": [get_font_info(r) for r in para.runs if r.text],
        }
        if para.paragraph_format.alignment is not None:
            entry["alignment"] = str(para.paragraph_format.alignment)
        result["paragraphs"].append(entry)

    result["tables"] = []
    for table in doc.tables:
        rows = []
        for row in table.rows:
            rows.append([cell.text for cell in row.cells])
        result["tables"].append(rows)

    return result


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法：python parse_docx.py --check | <文件路径>")
        sys.exit(1)

    if sys.argv[1] == "--check":
        print(json.dumps(check_env(), ensure_ascii=False, indent=2))
        sys.exit(0)

    env = check_env()
    if not env["ready"]:
        print(json.dumps({
            "error": "python-docx 未安装",
            "install": env.get("install"),
            "mirror": env.get("mirror"),
        }, ensure_ascii=False, indent=2))
        sys.exit(1)

    print(json.dumps(parse(sys.argv[1]), ensure_ascii=False, indent=2))