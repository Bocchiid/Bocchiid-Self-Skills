#!/usr/bin/env python3
"""几何校验 diagram_kit.py 生成的图（或任意 .layout.json）。

用法：
    python check_diagram.py figure.layout.json
    python check_diagram.py figure.svg              # 自动找同名 .layout.json
    python check_diagram.py figure.png --insert-width-pt 400
    python check_diagram.py figure.layout.json --strict

检查：
  - 节点与节点不重叠
  - 节点文字不溢出框
  - 边不穿过非端点节点
  - 边不自交；边与边交叉/共线重叠只警告
  - 箭头有实心头部、杆身长度足够、方向与最后一段一致
  - 边标签不压节点、不压其他标签；压到边上只警告
  - 所有元素在画布内
  - PNG 有效 DPI（像素宽 ÷ 插入宽度英寸），低于 150 报错

退出码：0 = 通过（可有警告）；1 = 有错误。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

TOL = 0.5


def load_layout(path: Path) -> dict:
    if path.suffix.lower() == ".layout.json" or path.name.endswith(".layout.json"):
        return json.loads(path.read_text(encoding="utf-8"))
    # 从 svg/png 找同名 sidecar
    for cand in (path.with_suffix(".layout.json"),
                 Path(str(path) + ".layout.json")):
        if cand.exists():
            return json.loads(cand.read_text(encoding="utf-8"))
    raise SystemExit(f"layout json not found for {path}; run diagram_kit.py first")


def rect_overlap(a: dict, b: dict, tol: float = TOL) -> tuple[float, float]:
    dx = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    dy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    return (dx, dy) if dx > tol and dy > tol else (0.0, 0.0)


def inside(inner: dict, outer: dict, tol: float = 1.0) -> bool:
    return (inner["x"] >= outer["x"] - tol and
            inner["y"] >= outer["y"] - tol and
            inner["x"] + inner["w"] <= outer["x"] + outer["w"] + tol and
            inner["y"] + inner["h"] <= outer["y"] + outer["h"] + tol)


def seg_rect(a, b, r: dict, pad: float = 1.0) -> bool:
    """Liang-Barsky：线段是否穿过矩形。"""
    x1, y1 = a
    x2, y2 = b
    dx, dy = x2 - x1, y2 - y1
    p = [-dx, dx, -dy, dy]
    q = [x1 - (r["x"] - pad), (r["x"] + r["w"] + pad) - x1,
         y1 - (r["y"] - pad), (r["y"] + r["h"] + pad) - y1]
    u1, u2 = 0.0, 1.0
    for pi, qi in zip(p, q):
        if abs(pi) < 1e-9:
            if qi < 0:
                return False
        else:
            t = qi / pi
            if pi < 0:
                u1 = max(u1, t)
            else:
                u2 = min(u2, t)
            if u1 > u2:
                return False
    return True


def _orient(a, b, c) -> float:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def seg_intersect(a, b, c, d) -> bool:
    """两线段是否相交（含端点接触）。"""
    o1, o2 = _orient(a, b, c), _orient(a, b, d)
    o3, o4 = _orient(c, d, a), _orient(c, d, b)
    if (o1 > 0) != (o2 > 0) and (o3 > 0) != (o4 > 0):
        return True
    eps = 1e-9
    def on(p, q, r):
        return (abs(_orient(p, q, r)) < eps and
                min(p[0], q[0]) - eps <= r[0] <= max(p[0], q[0]) + eps and
                min(p[1], q[1]) - eps <= r[1] <= max(p[1], q[1]) + eps)
    return (on(a, b, c) or on(a, b, d) or on(c, d, a) or on(c, d, b))


def _collinear_overlap(a, b, c, d) -> bool:
    if abs(_orient(a, b, c)) > 1e-6 or abs(_orient(a, b, d)) > 1e-6:
        return False
    # 投影到主方向
    if abs(b[0] - a[0]) >= abs(b[1] - a[1]):
        vals = sorted([(a[0], 0), (b[0], 1), (c[0], 0), (d[0], 1)])
    else:
        vals = sorted([(a[1], 0), (b[1], 1), (c[1], 0), (d[1], 1)])
    return vals[1][1] != vals[2][1] and vals[1][0] < vals[2][0] - TOL


def _char_w(ch: str, fs: float) -> float:
    o = ord(ch)
    if o >= 0x2E80 or ch in "，。；：！？、（）【】《》":
        return fs * 1.0
    if ch in "ilI.,:;|! ":
        return fs * 0.30
    if ch.isupper():
        return fs * 0.62
    return fs * 0.55


def _text_size(label: str, fs: float) -> tuple[float, float]:
    lines = str(label).split("\n") or [""]
    return (max(sum(_char_w(c, fs) for c in line) for line in lines),
            len(lines) * 14.0)


def _band_label_rects(layout: dict) -> list[dict]:
    fs = float((layout.get("metrics") or {}).get("font_size", 10.0)) * 0.85
    out = []
    for band in layout.get("layers") or []:
        w, h = _text_size(str(band.get("name", "")), fs)
        out.append({"x": band["x"] + 6, "y": band["y"] + band["h"] - 12 - h / 2,
                    "w": w, "h": h, "name": band.get("name", "")})
    return out


def _node_distance(p, r: dict) -> float:
    dx = max(r["x"] - p[0], 0, p[0] - (r["x"] + r["w"]))
    dy = max(r["y"] - p[1], 0, p[1] - (r["y"] + r["h"]))
    return math.hypot(dx, dy)


def check(layout: dict, insert_width_pt: float | None = None,
          strict: bool = False) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    nodes = layout.get("nodes") or []
    edges = layout.get("edges") or []
    canvas = layout.get("canvas") or {}
    W, H = float(canvas.get("width", 0)), float(canvas.get("height", 0))

    if not nodes:
        errors.append("no nodes")
    if W <= 0 or H <= 0:
        errors.append("invalid canvas")

    # 节点重叠
    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            a, b = nodes[i]["rect"], nodes[j]["rect"]
            dx, dy = rect_overlap(a, b)
            if dx > 0 and dy > 0:
                errors.append(f"节点重叠：{nodes[i]['id']} 与 {nodes[j]['id']}"
                              f"（重叠 {dx:.1f}×{dy:.1f} pt）")

    # 节点文字不溢出
    for n in nodes:
        if n.get("label_rect") and not inside(n["label_rect"], n["rect"]):
            errors.append(f"文字溢出节点框：{n['id']}")

    # 画布边界
    for n in nodes:
        r = n["rect"]
        if r["x"] < -TOL or r["y"] < -TOL or r["x"] + r["w"] > W + TOL or r["y"] + r["h"] > H + TOL:
            errors.append(f"节点超出画布：{n['id']}")

    node_by_id = {n["id"]: n for n in nodes}
    band_labels = _band_label_rects(layout)

    for e in edges:
        eid = e.get("id", "?")
        pts = list(e.get("points") or [])
        arrow = e.get("arrow") or {}
        if len(pts) < 2:
            errors.append(f"边 {eid} 少于两个点")
            continue
        if not arrow:
            errors.append(f"边 {eid} 缺少箭头数据")
        else:
            # 箭头面积
            tip = tuple(arrow.get("tip", (0, 0)))
            b1 = tuple(arrow.get("base1", (0, 0)))
            b2 = tuple(arrow.get("base2", (0, 0)))
            area = abs((b1[0] - tip[0]) * (b2[1] - tip[1]) -
                       (b1[1] - tip[1]) * (b2[0] - tip[0])) / 2
            if area < 3:
                errors.append(f"边 {eid} 箭头头部过小/缺失（面积 {area:.1f}）")
            # 杆身长度
            shaft = math.hypot(pts[-1][0] - pts[-2][0], pts[-1][1] - pts[-2][1])
            if shaft < 5:
                errors.append(f"边 {eid} 杆身过短（{shaft:.1f} pt），可能只剩箭头")
            # 方向一致
            dx, dy = tip[0] - pts[-1][0], tip[1] - pts[-1][1]
            d = math.hypot(dx, dy) or 1
            ux, uy = dx / d, dy / d
            adx, ady = arrow.get("dir", (0, 0))
            ad = math.hypot(adx, ady) or 1
            adx, ady = adx / ad, ady / ad
            if ux * adx + uy * ady < 0.9:
                errors.append(f"边 {eid} 箭头方向与最后一段不一致")
            # 箭头尖应贴目标节点
            target = node_by_id.get(e.get("to"))
            if target and _node_distance(tip, target["rect"]) > 2.5:
                warnings.append(f"边 {eid} 箭头尖未贴目标节点边框（{_node_distance(tip, target['rect']):.1f} pt）")

        # 完整折线（含箭头尖）用于穿框检查
        full = pts + ([tuple(arrow["tip"])] if arrow else [])

        # 穿过非端点节点
        for n in nodes:
            if n["id"] in (e.get("from"), e.get("to")):
                continue
            for a, b in zip(full, full[1:]):
                if seg_rect(a, b, n["rect"], pad=0.5):
                    errors.append(f"边 {eid} 穿过节点 {n['id']}")
                    break
            else:
                continue
            break

        # 自交
        for i in range(len(full) - 1):
            for j in range(i + 2, len(full) - 1):
                if i == 0 and j == len(full) - 2:
                    continue
                if seg_intersect(full[i], full[i + 1], full[j], full[j + 1]):
                    errors.append(f"边 {eid} 自交（段 {i} 与段 {j}）")
                    break
            else:
                continue
            break

        # 标签
        lr = e.get("label_rect")
        if lr:
            for n in nodes:
                if rect_overlap(lr, n["rect"])[0] > 0:
                    errors.append(f"边 {eid} 的标签压住节点 {n['id']}")
                    break
            for br in band_labels:
                if rect_overlap(lr, br)[0] > 0:
                    errors.append(f"边 {eid} 的标签压住层标题「{br['name']}」")
                    break
            for a, b in zip(full, full[1:]):
                if seg_rect(a, b, lr, pad=0.0):
                    warnings.append(f"边 {eid} 的标签压在自己的线上")
                    break

    # 标签互压
    labelled = [(e.get("id", "?"), e["label_rect"]) for e in edges if e.get("label_rect")]
    for i in range(len(labelled)):
        for j in range(i + 1, len(labelled)):
            if rect_overlap(labelled[i][1], labelled[j][1])[0] > 0:
                errors.append(f"边标签重叠：{labelled[i][0]} 与 {labelled[j][0]}")

    # 边与边交叉 / 共线重叠
    crossings = 0
    overlaps = 0
    for i in range(len(edges)):
        for j in range(i + 1, len(edges)):
            a = list(edges[i].get("points") or []) + (
                [tuple(edges[i]["arrow"]["tip"])] if edges[i].get("arrow") else [])
            b = list(edges[j].get("points") or []) + (
                [tuple(edges[j]["arrow"]["tip"])] if edges[j].get("arrow") else [])
            hit = False
            for p1, p2 in zip(a, a[1:]):
                for p3, p4 in zip(b, b[1:]):
                    if _collinear_overlap(p1, p2, p3, p4):
                        overlaps += 1
                        hit = True
                        break
                    if seg_intersect(p1, p2, p3, p4):
                        crossings += 1
                        hit = True
                        break
                if hit:
                    break
    if crossings:
        warnings.append(f"边与边交叉 {crossings} 处（架构图建议尽量减少）")
    if overlaps:
        warnings.append(f"边与边共线重叠 {overlaps} 处（端口/通道可能没分开）")

    # DPI
    image = layout.get("image") or {}
    if image.get("width_px") and W > 0:
        if insert_width_pt:
            dpi = image["width_px"] / (float(insert_width_pt) / 72.0)
            label = "按插入宽度"
        else:
            dpi = image["width_px"] / (W / 72.0)
            label = "按画布宽度"
        if dpi < 150:
            errors.append(f"图片有效 DPI {dpi:.0f} 过低（{label}），插入后会糊")
        elif dpi < 200:
            warnings.append(f"图片有效 DPI {dpi:.0f}（{label}），建议 ≥200")

    if strict:
        errors.extend(warnings)
        warnings = []

    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "counts": {"nodes": len(nodes), "edges": len(edges),
                   "edge_crossings": crossings, "edge_overlaps": overlaps,
                   "labels": len(labelled)},
    }


def check_png(path: Path, insert_width_pt: float) -> dict:
    try:
        from PIL import Image
    except ImportError:
        return {"ok": False, "errors": ["Pillow not installed"], "warnings": []}
    with Image.open(path) as im:
        w, h = im.size
    dpi = w / (insert_width_pt / 72.0)
    errors = []
    warnings = []
    if dpi < 150:
        errors.append(f"PNG 有效 DPI {dpi:.0f} 过低（插入宽 {insert_width_pt} pt）")
    elif dpi < 200:
        warnings.append(f"PNG 有效 DPI {dpi:.0f}，建议 ≥200")
    return {"ok": not errors, "errors": errors, "warnings": warnings,
            "width_px": w, "height_px": h, "effective_dpi": round(dpi, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", help=".layout.json / .svg / .png")
    ap.add_argument("--insert-width-pt", type=float, default=None,
                    help="图片在 Word 里的插入宽度（pt），用于算有效 DPI")
    ap.add_argument("--strict", action="store_true", help="warnings 也算失败")
    args = ap.parse_args()
    path = Path(args.path)
    if path.suffix.lower() == ".png":
        if not args.insert_width_pt:
            ap.error("--insert-width-pt is required for PNG-only checks")
        result = check_png(path, args.insert_width_pt)
    else:
        layout = load_layout(path)
        result = check(layout, args.insert_width_pt, args.strict)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
