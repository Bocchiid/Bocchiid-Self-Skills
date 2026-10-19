#!/usr/bin/env python3
"""盘点任务材料并尽量提取正文，供 report-planner 使用。

用法：
    python scan_materials.py <文件或目录> [更多路径...]
    python scan_materials.py . --out 材料清单.md
    python scan_materials.py . --json 材料清单.json --max-chars 8000

特点：
- 只读，不执行文档宏、不打开外链、不解压压缩包；
- .docx / .pptx / .xlsx / .pdf / 文本可直接提取；
- .doc / .ppt / .xls 旧格式只提示转换，不尝试解析；
- 解析库缺失时降级并给出安装提示，不中断整个扫描；
- 输出 UTF-8 Markdown，避免 Windows 控制台编码问题。

依赖（均为可选，缺哪个降级哪个）：
    pip install python-docx python-pptx openpyxl pypdf
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
import zipfile
from pathlib import Path

SKIP_DIRS = {
    ".git", ".svn", ".hg", "__pycache__", "node_modules", ".venv", "venv",
    "env", ".idea", ".vscode", ".pytest_cache", ".mypy_cache", "dist", "build",
    ".next", ".nuxt", "target", "bin", "obj",
}

TEXT_SUFFIXES = {
    ".txt", ".md", ".markdown", ".csv", ".tsv", ".json", ".yaml", ".yml",
    ".ini", ".cfg", ".conf", ".log", ".py", ".c", ".h", ".cpp", ".hpp",
    ".java", ".js", ".ts", ".jsx", ".tsx", ".html", ".htm", ".css", ".xml",
    ".sh", ".bat", ".ps1", ".sql", ".r", ".m", ".go", ".rs", ".php",
}

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".tif", ".tiff"}


def _setup_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def human_size(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.1f} {unit}" if unit != "B" else f"{n} B"
        n /= 1024
    return f"{n:.1f} GB"


def md_escape(text: str, limit: int | None = None) -> str:
    if text is None:
        return ""
    text = str(text).replace("\r\n", "\n").replace("\r", "\n")
    if limit is not None and len(text) > limit:
        text = text[:limit] + f"…（截断，原长 {len(text)} 字）"
    text = text.replace("|", "\\|").replace("\n", "<br>")
    # 合并单元格常带连续空行，折叠成单个换行标记，避免清单被 <br> 淹没
    text = re.sub(r"(?:<br>){2,}", "<br>", text)
    text = re.sub(r"^(?:<br>)+|(?:<br>)+$", "", text)
    return text.strip()


def compact_cells(cells, limit: int = 300) -> list[str]:
    """折叠 Word/PPT 合并单元格造成的连续重复文本，减少清单噪音。

    只折叠连续重复的非空单元格，并在末尾标注重复次数；空单元格保持原样。
    这会让表格列数不再与原始网格一致，但用于阅读和规划足够。
    """
    values: list[str] = []
    counts: list[int] = []
    for cell in cells:
        value = md_escape(cell, limit)
        if values and value == values[-1]:
            counts[-1] += 1
        else:
            values.append(value)
            counts.append(1)
    return [
        f"{value}（×{count}）" if count > 1 and value else value
        for value, count in zip(values, counts)
    ]


def trim_trailing_empty(cells: list[str]) -> list[str]:
    """去掉行尾空单元格，避免表格被大量空列撑宽。"""
    while cells and not cells[-1]:
        cells.pop()
    return cells


def read_text_file(path: Path, max_chars: int) -> tuple[str, str | None]:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030", "gbk", "latin-1"):
        try:
            return raw.decode(enc), None
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), "编码无法确定，已用替换字符"


def extract_docx(path: Path, max_chars: int) -> dict:
    try:
        from docx import Document
    except ImportError:
        return {"ok": False, "warning": "缺少 python-docx，无法解析 .docx（pip install python-docx）"}

    try:
        doc = Document(str(path))
    except Exception as exc:
        return {"ok": False, "warning": f"python-docx 解析失败：{exc}"}

    lines: list[str] = []
    structured: list[dict] = []

    try:
        props = doc.core_properties
        meta = []
        for label, value in (("标题", props.title), ("作者", props.author),
                             ("主题", props.subject), ("创建", props.created),
                             ("修改", props.modified)):
            if value:
                meta.append(f"- {label}：{value}")
        if meta:
            lines.append("### 文档属性")
            lines.extend(meta)
            lines.append("")
    except Exception:
        pass

    lines.append("### 正文")
    for para in doc.paragraphs:
        text = para.text.strip()
        if text:
            lines.append(text)
            structured.append({
                "type": "paragraph",
                "style": para.style.name if para.style else None,
                "text": text,
            })

    for idx, table in enumerate(doc.tables):
        lines.append("")
        lines.append(f"### 表格 {idx + 1}（{len(table.rows)} 行 × {len(table.columns)} 列）")
        rows = []
        for row in list(table.rows)[:40]:
            cells = trim_trailing_empty(compact_cells([cell.text for cell in row.cells], 300)[:12])
            rows.append(cells)
        if rows:
            width = max(len(r) for r in rows)
            header = rows[0] + [""] * (width - len(rows[0]))
            lines.append("| " + " | ".join(header) + " |")
            lines.append("| " + " | ".join(["---"] * width) + " |")
            for r in rows[1:]:
                r = r + [""] * (width - len(r))
                lines.append("| " + " | ".join(r) + " |")
        if len(table.rows) > 40:
            lines.append(f"（表格共 {len(table.rows)} 行，仅显示前 40 行）")
        structured.append({"type": "table", "index": idx, "rows": len(table.rows)})

    try:
        for section_idx, section in enumerate(doc.sections):
            for kind, container in (("页眉", section.header), ("页脚", section.footer)):
                texts = [p.text.strip() for p in container.paragraphs if p.text.strip()]
                if texts:
                    lines.append("")
                    lines.append(f"### 第 {section_idx + 1} 节{kind}")
                    lines.extend(texts)
    except Exception:
        pass

    text = "\n".join(lines)
    truncated = len(text) > max_chars
    return {
        "ok": True,
        "text": text[:max_chars],
        "truncated": truncated,
        "original_chars": len(text),
        "structured": structured,
    }


def extract_pptx(path: Path, max_chars: int) -> dict:
    try:
        from pptx import Presentation
    except ImportError:
        return {"ok": False, "warning": "缺少 python-pptx，无法解析 .pptx（pip install python-pptx）"}

    try:
        prs = Presentation(str(path))
    except Exception as exc:
        return {"ok": False, "warning": f"python-pptx 解析失败：{exc}"}

    lines = []
    for slide_no, slide in enumerate(prs.slides, 1):
        texts = []
        for shape in slide.shapes:
            if getattr(shape, "has_text_frame", False):
                t = shape.text_frame.text.strip()
                if t:
                    texts.append(t)
            if getattr(shape, "has_table", False):
                table = shape.table
                rows = []
                for row in list(table.rows)[:30]:
                    rows.append(trim_trailing_empty(
                        compact_cells([cell.text for cell in row.cells], 200)[:10]))
                if rows:
                    width = max(len(r) for r in rows)
                    texts.append("")
                    texts.append("| " + " | ".join(rows[0] + [""] * (width - len(rows[0]))) + " |")
                    texts.append("| " + " | ".join(["---"] * width) + " |")
                    for r in rows[1:]:
                        r = r + [""] * (width - len(r))
                        texts.append("| " + " | ".join(r) + " |")
        notes = ""
        try:
            if slide.has_notes_slide and slide.notes_slide.notes_text_frame:
                notes = slide.notes_slide.notes_text_frame.text.strip()
        except Exception:
            pass
        if texts or notes:
            lines.append(f"### 幻灯片 {slide_no}")
            lines.extend(texts)
            if notes:
                lines.append(f"备注：{notes}")
            lines.append("")

    text = "\n".join(lines)
    truncated = len(text) > max_chars
    return {
        "ok": True,
        "text": text[:max_chars],
        "truncated": truncated,
        "original_chars": len(text),
    }


def extract_xlsx(path: Path, max_chars: int) -> dict:
    try:
        from openpyxl import load_workbook
    except ImportError:
        return {"ok": False, "warning": "缺少 openpyxl，无法解析 .xlsx（pip install openpyxl）"}

    try:
        wb = load_workbook(str(path), read_only=True, data_only=True)
    except Exception as exc:
        return {"ok": False, "warning": f"openpyxl 解析失败：{exc}"}

    lines = []
    for ws in wb.worksheets:
        lines.append(f"### 工作表：{ws.title}")
        max_row = getattr(ws, "max_row", None)
        max_col = getattr(ws, "max_column", None)
        if max_row and max_col:
            dims = f"{max_row} 行 × {max_col} 列"
        else:
            try:
                dims = ws.calculate_dimension() or "未知"
            except Exception:
                dims = "未知"
        lines.append(f"- 范围：{dims}")
        rows = []
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= 25:
                break
            cells = trim_trailing_empty(
                [md_escape("" if v is None else v, 120) for v in row[:15]])
            if cells:
                rows.append(cells)
        if rows:
            width = max(len(r) for r in rows)
            lines.append("| " + " | ".join(rows[0] + [""] * (width - len(rows[0]))) + " |")
            lines.append("| " + " | ".join(["---"] * width) + " |")
            for r in rows[1:]:
                r = r + [""] * (width - len(r))
                lines.append("| " + " | ".join(r) + " |")
            lines.append("（仅显示前 25 行 × 15 列）")
        lines.append("")
    wb.close()

    text = "\n".join(lines)
    truncated = len(text) > max_chars
    return {
        "ok": True,
        "text": text[:max_chars],
        "truncated": truncated,
        "original_chars": len(text),
    }


def extract_pdf(path: Path, max_chars: int) -> dict:
    reader = None
    module = None
    try:
        from pypdf import PdfReader
        reader, module = PdfReader, "pypdf"
    except ImportError:
        try:
            from PyPDF2 import PdfReader
            reader, module = PdfReader, "PyPDF2"
        except ImportError:
            return {
                "ok": False,
                "warning": "缺少 PDF 解析库。可安装 pypdf（pip install pypdf），"
                           "或用 Word/LibreOffice 转为 .docx 后再扫描。",
            }

    try:
        pdf = reader(str(path))
    except Exception as exc:
        return {"ok": False, "warning": f"{module} 解析失败：{exc}"}

    lines = []
    for i, page in enumerate(pdf.pages):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            text = f"（本页提取失败：{exc}）"
        if text.strip():
            lines.append(f"### 第 {i + 1} 页")
            lines.append(text.strip())
            lines.append("")
        if sum(len(x) for x in lines) > max_chars * 2:
            lines.append(f"（已到页数上限，后续页面未提取；总页数 {len(pdf.pages)}）")
            break

    text = "\n".join(lines)
    truncated = len(text) > max_chars
    return {
        "ok": True,
        "text": text[:max_chars],
        "truncated": truncated,
        "original_chars": len(text),
        "pages": len(pdf.pages),
    }


def extract_zip(path: Path, max_chars: int) -> dict:
    try:
        with zipfile.ZipFile(path) as zf:
            names = zf.namelist()
    except Exception as exc:
        return {"ok": False, "warning": f"zip 读取失败：{exc}"}
    lines = [f"- 压缩包内共 {len(names)} 个条目（仅列目录，不解压）"]
    for name in names[:80]:
        lines.append(f"  - {name}")
    if len(names) > 80:
        lines.append(f"  - …（其余 {len(names) - 80} 项省略）")
    text = "\n".join(lines)
    return {"ok": True, "text": text[:max_chars], "truncated": len(text) > max_chars,
            "original_chars": len(text)}


def extract_one(path: Path, max_chars: int) -> dict:
    suffix = path.suffix.lower()
    if suffix == ".docx":
        return extract_docx(path, max_chars)
    if suffix == ".pptx":
        return extract_pptx(path, max_chars)
    if suffix == ".xlsx":
        return extract_xlsx(path, max_chars)
    if suffix == ".pdf":
        return extract_pdf(path, max_chars)
    if suffix == ".zip":
        return extract_zip(path, max_chars)
    if suffix in TEXT_SUFFIXES:
        try:
            text, warning = read_text_file(path, max_chars)
            truncated = len(text) > max_chars
            result = {"ok": True, "text": text[:max_chars], "truncated": truncated,
                      "original_chars": len(text)}
            if warning:
                result["warning"] = warning
            return result
        except Exception as exc:
            return {"ok": False, "warning": f"文本读取失败：{exc}"}
    if suffix in {".doc", ".ppt", ".xls"}:
        return {
            "ok": False,
            "warning": "旧版 Office 格式，无法直接解析。请用 Word/PowerPoint/Excel "
                       "另存为 .docx/.pptx/.xlsx，或用 LibreOffice 转换后再扫描。",
        }
    if suffix in IMAGE_SUFFIXES:
        return {"ok": True, "text": "（图片文件；规划时请人工查看内容并决定是否作为证据）",
                "truncated": False, "original_chars": 0}
    return {"ok": False, "warning": f"不支持的文件类型：{suffix or '无扩展名'}"}


def collect_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        path = path.resolve()
        if path.is_file():
            files.append(path)
            continue
        if not path.is_dir():
            continue
        for root, dirs, names in os.walk(path):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith("."))
            for name in sorted(names):
                if name.startswith("~$") or name.startswith("."):
                    continue
                files.append(Path(root) / name)
    # 去重并保持稳定顺序
    seen = set()
    unique = []
    for f in files:
        key = str(f).lower()
        if key not in seen:
            seen.add(key)
            unique.append(f)
    return unique


def build_markdown(records: list[dict], args: argparse.Namespace) -> str:
    now = _dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# 材料清单",
        "",
        f"- 扫描时间：{now}",
        f"- 扫描路径：{', '.join(args.paths)}",
        f"- 文件数量：{len(records)}",
        "",
        "> 本清单只读取文件内容，不执行宏、不打开外链、不解压压缩包。",
        "> 旧版 .doc/.ppt/.xls 需先转换；扫描结果仅供规划参考，关键要求请回原文核对。",
        "",
        "## 文件概览",
        "",
        "| # | 文件 | 类型 | 大小 | 修改时间 | 解析 |",
        "| --- | --- | --- | --- | --- | --- |",
    ]
    for i, rec in enumerate(records, 1):
        rel = rec["path"]
        mtime = rec.get("mtime", "")
        status = "OK" if rec.get("ok") else "跳过"
        lines.append(
            f"| {i} | {md_escape(rel, 160)} | {rec['suffix'] or '无'} | "
            f"{human_size(rec['size'])} | {mtime} | {status} |"
        )

    warnings = [r for r in records if not r.get("ok") or r.get("warning")]
    if warnings:
        lines.extend(["", "## 解析提示", ""])
        for rec in warnings:
            note = rec.get("warning") or ""
            lines.append(f"- `{rec['path']}`：{note}")

    lines.extend(["", "## 提取内容", ""])
    for rec in records:
        lines.append(f"### {rec['path']}")
        lines.append("")
        lines.append(f"- 类型：{rec['suffix'] or '无扩展名'}；大小：{human_size(rec['size'])}")
        if rec.get("truncated"):
            lines.append(f"- ⚠️ 内容已截断：原长约 {rec.get('original_chars', '?')} 字，"
                         f"仅保留前 {args.max_chars} 字")
        if rec.get("warning"):
            lines.append(f"- ⚠️ {rec['warning']}")
        text = (rec.get("text") or "").strip()
        lines.append("")
        if text:
            lines.append(text)
        else:
            lines.append("（未提取到可读正文）")
        lines.append("")

    lines.extend([
        "",
        "## 下一步",
        "",
        "1. 先看《指导书/任务书》《报告模板》《评分表》三类文件；",
        "2. 找不到的用 `report-planner` 的追问清单集中问一次；",
        "3. 旧格式先用 Word 另存为 .docx，或 LibreOffice 转换后再扫描；",
        "4. 成品报告只参考格式，不作为内容或数据来源。",
        "",
    ])
    return "\n".join(lines)


def main() -> int:
    _setup_stdout()
    parser = argparse.ArgumentParser(description="盘点任务材料并提取正文")
    parser.add_argument("paths", nargs="+", help="文件或目录")
    parser.add_argument("--out", help="输出 Markdown 文件（默认打印到 stdout）")
    parser.add_argument("--json", dest="json_out", help="可选：输出 JSON 文件")
    parser.add_argument("--max-chars", type=int, default=12000,
                        help="每个文件最多提取的字符数（默认 12000）")
    args = parser.parse_args()
    args.paths = [str(p) for p in args.paths]

    paths = [Path(p) for p in args.paths]
    files = collect_files(paths)
    if not files:
        print("没有找到可扫描的文件。", file=sys.stderr)
        return 1

    records = []
    for path in files:
        try:
            stat = path.stat()
        except OSError as exc:
            records.append({
                "path": str(path), "suffix": path.suffix.lower(), "size": 0,
                "mtime": "", "ok": False, "warning": f"无法读取文件信息：{exc}",
            })
            continue
        result = extract_one(path, args.max_chars)
        record = {
            "path": str(path),
            "suffix": path.suffix.lower(),
            "size": stat.st_size,
            "mtime": _dt.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            **result,
        }
        records.append(record)

    markdown = build_markdown(records, args)
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(markdown, encoding="utf-8")
        print(f"已写入：{out_path}")
    else:
        print(markdown)

    if args.json_out:
        json_path = Path(args.json_out)
        json_path.parent.mkdir(parents=True, exist_ok=True)
        json_path.write_text(
            json.dumps({"generated": _dt.datetime.now().isoformat(timespec="seconds"),
                        "records": records}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"已写入：{json_path}")

    ok = sum(1 for r in records if r.get("ok"))
    print(f"扫描完成：{len(records)} 个文件，成功提取 {ok} 个，跳过 {len(records) - ok} 个。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
