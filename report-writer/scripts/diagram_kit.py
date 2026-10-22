#!/usr/bin/env python3
"""按 JSON 规格生成架构图/流程图，并输出几何布局 sidecar 供 check_diagram.py 校验。

用法：
    python diagram_kit.py spec.json -o figure.svg
    python diagram_kit.py spec.json -o figure.svg --direction TB
    python diagram_kit.py --example spec.json          # 写一份示例规格
    python diagram_kit.py spec.json -o figure.svg --no-png

设计目标（对应报告里最常见的三个毛病）：
  1. 节点/文字不重叠：节点尺寸按标签自动估算，分层布局 + 固定间距；
  2. 箭头完整：边是“杆身折线 + 实心箭头”两件套，不会只剩箭头头；
  3. 线不穿框：相邻层在层间通道走线，跨层绕到所有中间节点之外，
     同层走层外侧；端口按出入边数量分散。

输出：
  - .svg / .png
  - 同名 .layout.json：canvas、节点矩形、边折线、箭头多边形、标签矩形。
    check_diagram.py 直接读这个 sidecar 做几何校验，不依赖图像识别。

规格（JSON）：
{
  "title": "示例：三层 Web 架构",
  "direction": "LR",                  // LR | TB
  "layers": [{"id":"client","name":"接入层"}, ...],
  "nodes": [
    {"id":"browser","label":"浏览器","layer":"client","style":"client"},
    ...
  ],
  "edges": [
    {"from":"browser","to":"lb","label":"HTTPS"},
    ...
  ]
}
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from pathlib import Path

# 字体：Windows 优先微软雅黑，其次黑体；避免中文变方框。
# 布局/检查不依赖 matplotlib；只有 render() 需要。
_MPL_OK = True
try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import FancyBboxPatch, Polygon
    from matplotlib import font_manager
except ImportError:
    _MPL_OK = False
    plt = None
    FancyBboxPatch = Polygon = None

if _MPL_OK:
    for _f in ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
               "Source Han Sans SC", "Arial Unicode MS"):
        try:
            font_manager.findfont(_f, fallback_to_default=False)
            plt.rcParams["font.sans-serif"] = [_f] + list(plt.rcParams["font.sans-serif"])
            break
        except Exception:
            continue
    plt.rcParams["axes.unicode_minus"] = False

UNIT = "pt"
MARGIN = 40.0
LAYER_GAP = 90.0
NODE_GAP = 24.0
FONT_SIZE = 10.0
LINE_H = 14.0
PAD_X = 12.0
PAD_Y = 9.0
MIN_W = 78.0
MIN_H = 34.0
ROUTE_CLEAR = 24.0
ARROW_LEN = 9.0
ARROW_W = 7.0

STYLES = {
    "client": ("#F2F2F2", "#7F7F7F"),
    "gateway": ("#FFF2CC", "#BF9000"),
    "service": ("#DEEBF7", "#2F5597"),
    "data": ("#E2F0D9", "#548235"),
    "external": ("#FCE4D6", "#C55A11"),
    "default": ("#FFFFFF", "#2F5597"),
}


# ---------------------------------------------------------------------------
# 文本尺寸
# ---------------------------------------------------------------------------

def _char_w(ch: str, fs: float) -> float:
    o = ord(ch)
    if o >= 0x2E80 or ch in "，。；：！？、（）【】《》":
        return fs * 1.0
    if ch in "ilI.,:;|! ":
        return fs * 0.30
    if ch.isupper():
        return fs * 0.62
    return fs * 0.55


def text_size(label: str, fs: float = FONT_SIZE) -> tuple[float, float]:
    lines = str(label).split("\n") or [""]
    w = max(sum(_char_w(c, fs) for c in line) for line in lines)
    h = len(lines) * LINE_H
    return w, h


def node_size(label: str) -> tuple[float, float]:
    tw, th = text_size(label)
    return (max(MIN_W, tw + 2 * PAD_X), max(MIN_H, th + 2 * PAD_Y))


# ---------------------------------------------------------------------------
# 分层与排序
# ---------------------------------------------------------------------------

def _layer_index(node: dict, layer_ids: list[str]) -> int | None:
    layer = node.get("layer")
    if layer is None:
        return None
    if isinstance(layer, int):
        return layer
    return layer_ids.index(str(layer)) if str(layer) in layer_ids else None


def _topo_rank(nodes: list[dict], edges: list[dict]) -> dict[str, int]:
    ids = [str(n["id"]) for n in nodes]
    adj: dict[str, list[str]] = {i: [] for i in ids}
    for e in edges:
        a, b = str(e["from"]), str(e["to"])
        if a in adj and b in adj and b not in adj[a]:
            adj[a].append(b)

    state: dict[str, int] = {}
    order: list[str] = []
    back: set[tuple[str, str]] = set()

    def dfs(u: str) -> None:
        state[u] = 1
        for v in adj[u]:
            if state.get(v, 0) == 0:
                dfs(v)
            elif state.get(v) == 1:
                back.add((u, v))
        state[u] = 2
        order.append(u)

    for i in ids:
        if state.get(i, 0) == 0:
            dfs(i)
    order.reverse()

    rank = {i: 0 for i in ids}
    for u in order:
        for v in adj[u]:
            if (u, v) in back:
                continue
            rank[v] = max(rank[v], rank[u] + 1)
    return rank


def _barycenter_order(layers: list[list[dict]], edges: list[dict],
                      rounds: int = 4) -> None:
    pos = {}
    for li, layer in enumerate(layers):
        for i, n in enumerate(layer):
            pos[str(n["id"])] = (li, i)
    adj: dict[str, list[str]] = {}
    for e in edges:
        a, b = str(e["from"]), str(e["to"])
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    for _ in range(rounds):
        for li in range(1, len(layers)):
            def bary(n):
                vals = [pos[v][1] for v in adj.get(str(n["id"]), [])
                        if pos.get(v, (None,))[0] == li - 1]
                return sum(vals) / len(vals) if vals else pos[str(n["id"])][1]
            layers[li].sort(key=bary)
            for i, n in enumerate(layers[li]):
                pos[str(n["id"])] = (li, i)
        for li in range(len(layers) - 2, -1, -1):
            def bary2(n):
                vals = [pos[v][1] for v in adj.get(str(n["id"]), [])
                        if pos.get(v, (None,))[0] == li + 1]
                return sum(vals) / len(vals) if vals else pos[str(n["id"])][1]
            layers[li].sort(key=bary2)
            for i, n in enumerate(layers[li]):
                pos[str(n["id"])] = (li, i)


# ---------------------------------------------------------------------------
# 布局
# ---------------------------------------------------------------------------

def compute_layout(spec: dict) -> dict:
    direction = str(spec.get("direction", "LR")).upper()
    if direction not in ("LR", "TB"):
        direction = "LR"
    nodes_in = spec.get("nodes") or []
    edges_in = spec.get("edges") or []
    if not nodes_in:
        raise ValueError("spec.nodes is empty")
    ids = [str(n.get("id", "")) for n in nodes_in]
    if any(not i for i in ids):
        raise ValueError("every node needs a non-empty id")
    if len(set(ids)) != len(ids):
        raise ValueError("duplicate node id in spec")

    layer_specs = spec.get("layers") or []
    layer_ids: list[str] = []
    layer_names: dict[str, str] = {}
    for i, item in enumerate(layer_specs):
        if isinstance(item, dict):
            lid = str(item.get("id", f"L{i}"))
            layer_ids.append(lid)
            layer_names[lid] = str(item.get("name", lid))
        else:
            lid = str(item)
            layer_ids.append(lid)
            layer_names[lid] = lid

    rank = _topo_rank(nodes_in, edges_in)
    assigned: list[int] = []
    for n in nodes_in:
        li = _layer_index(n, layer_ids)
        if li is None:
            li = rank.get(str(n["id"]), 0)
        assigned.append(li)

    # 把显式层 id 映射到 0..k-1；未命名层按 rank 排序
    max_li = max(assigned) if assigned else 0
    if layer_ids:
        # 显式层优先；rank 超出时追加
        while len(layer_ids) <= max_li:
            layer_ids.append(f"L{len(layer_ids)}")
            layer_names[layer_ids[-1]] = layer_ids[-1]
    else:
        layer_ids = [f"L{i}" for i in range(max_li + 1)]
        layer_names = {x: f"第 {i + 1} 层" for i, x in enumerate(layer_ids)}
        # rank 直接当层号

    layers: list[list[dict]] = [[] for _ in layer_ids]
    for n, li in zip(nodes_in, assigned):
        li = max(0, min(li, len(layers) - 1))
        layers[li].append(n)          # 同一对象，后面把坐标写回 nodes_in

    _barycenter_order(layers, edges_in)

    # 尺寸
    for n in nodes_in:
        label = str(n.get("label", n["id"]))
        w, h = node_size(label)
        n["_w"], n["_h"] = w, h

    sizes = []
    for layer in layers:
        sizes.append((max([n["_w"] for n in layer], default=MIN_W),
                      sum(n["_h"] for n in layer) + NODE_GAP * max(0, len(layer) - 1)))
    max_cross = max([s[1] for s in sizes], default=MIN_H)

    # 坐标（y 向上；TB 时第 0 层放在最上面，向下排）
    x = MARGIN
    bands = []
    if direction == "LR":
        for li, layer in enumerate(layers):
            lw, lh = sizes[li]
            top = MARGIN + (max_cross - lh) / 2
            for n in layer:
                n["_x"] = x + (lw - n["_w"]) / 2
                n["_y"] = top
                top += n["_h"] + NODE_GAP
            bands.append({"id": layer_ids[li],
                          "name": layer_names.get(layer_ids[li], layer_ids[li]),
                          "x": x, "y": MARGIN, "w": lw, "h": max_cross})
            x += lw + LAYER_GAP
    else:
        total_h = sum(s[1] for s in sizes) + LAYER_GAP * max(0, len(sizes) - 1)
        y_cursor = MARGIN + total_h
        for li, layer in enumerate(layers):
            lw, lh = sizes[li]
            layer_bottom = y_cursor - lh
            left = MARGIN + (max_cross - lw) / 2
            for n in layer:
                n["_x"] = left
                n["_y"] = layer_bottom
                left += n["_w"] + NODE_GAP
            bands.append({"id": layer_ids[li],
                          "name": layer_names.get(layer_ids[li], layer_ids[li]),
                          "x": MARGIN, "y": layer_bottom,
                          "w": max_cross, "h": lh})
            y_cursor = layer_bottom - LAYER_GAP

    node_map = {str(n["id"]): n for n in nodes_in}
    for n in nodes_in:
        n["_right"] = n["_x"] + n["_w"]
        n["_top"] = n["_y"] + n["_h"]
        n["_cx"] = n["_x"] + n["_w"] / 2
        n["_cy"] = n["_y"] + n["_h"] / 2
        n["_layer"] = assigned[nodes_in.index(n)]

    # 端口：出口/入口分别按对端位置排序，分散在边框上
    out_edges = {str(n["id"]): [] for n in nodes_in}
    in_edges = {str(n["id"]): [] for n in nodes_in}
    for ei, e in enumerate(edges_in):
        a, b = str(e["from"]), str(e["to"])
        if a not in node_map or b not in node_map:
            raise ValueError(f"edge references unknown node: {a} -> {b}")
        out_edges[a].append((ei, b))
        in_edges[b].append((ei, a))

    ports: dict[int, tuple[tuple[float, float], tuple[float, float]]] = {}
    for nid, items in out_edges.items():
        n = node_map[nid]
        items.sort(key=lambda it: _cross_pos(node_map[it[1]], direction))
        for k, (ei, other) in enumerate(items):
            # 用边序号做微小抖动，避免不同节点的端口恰好落在同一条水平/垂直线上
            jitter = ((ei * 37) % 7 - 3) * 0.012
            frac = min(0.85, max(0.15, (k + 1) / (len(items) + 1) + jitter))
            if direction == "LR":
                p = (n["_right"], n["_y"] + n["_h"] * frac)
            else:
                p = (n["_x"] + n["_w"] * frac, n["_y"])
            ports[ei] = (p, ports.get(ei, (None, None))[1])

    for nid, items in in_edges.items():
        n = node_map[nid]
        items.sort(key=lambda it: _cross_pos(node_map[it[1]], direction))
        for k, (ei, other) in enumerate(items):
            same = node_map[nid]["_layer"] == node_map[other]["_layer"]
            jitter = ((ei * 37) % 7 - 3) * 0.012
            frac = min(0.85, max(0.15, (k + 1) / (len(items) + 1) + jitter))
            if direction == "LR":
                p = (n["_right"] if same else n["_x"], n["_y"] + n["_h"] * frac)
            else:
                p = (n["_x"] + n["_w"] * frac,
                     n["_y"] if same else n["_top"])
            ports[ei] = (ports.get(ei, (None, None))[0], p)

    # 层间通道
    layer_bounds = []
    for li in range(len(layers)):
        if direction == "LR":
            left = min([n["_x"] for n in layers[li]])
            right = max([n["_right"] for n in layers[li]])
            layer_bounds.append((left, right))
        else:
            bottom = min([n["_y"] for n in layers[li]])
            top = max([n["_top"] for n in layers[li]])
            layer_bounds.append((bottom, top))

    def gap_between(i: int, j: int) -> float:
        i = max(0, min(i, len(layer_bounds) - 1))
        j = max(0, min(j, len(layer_bounds) - 1))
        if i == j:
            # 同层时返回该层外侧一点，调用方只在跨层使用
            return layer_bounds[i][1] + ROUTE_CLEAR
        if i > j:
            i, j = j, i
        return (layer_bounds[i][1] + layer_bounds[j][0]) / 2

    def cross_extent(li_range) -> tuple[float, float]:
        vals = []
        for li in li_range:
            for n in layers[li]:
                vals.append(n["_y"] if direction == "LR" else n["_x"])
                vals.append(n["_top"] if direction == "LR" else n["_right"])
        return (min(vals), max(vals)) if vals else (0.0, 0.0)

    edges = []
    route_counts: dict[tuple, int] = {}
    for ei, e in enumerate(edges_in):
        a, b = str(e["from"]), str(e["to"])
        s, t = node_map[a], node_map[b]
        sp, tp = ports.get(ei, (None, None))
        if sp is None or tp is None:
            continue
        li, lj = s["_layer"], t["_layer"]
        pts = _route(ei, s, t, sp, tp, li, lj, direction,
                     gap_between, cross_extent, route_counts, len(layers))
        lbl = str(e.get("label", "") or "")
        edges.append({
            "id": str(e.get("id", f"E{ei + 1}")),
            "from": a, "to": b, "label": lbl,
            "points": pts,
            "label_rect": None,
        })

    _place_edge_labels(edges, nodes_in, bands)

    # 箭头
    for edge in edges:
        pts = edge["points"]
        p0, p1 = pts[-2], pts[-1]
        dx, dy = p1[0] - p0[0], p1[1] - p0[1]
        dist = math.hypot(dx, dy) or 1.0
        ux, uy = dx / dist, dy / dist
        tip = p1
        base = (tip[0] - ux * ARROW_LEN, tip[1] - uy * ARROW_LEN)
        nx, ny = -uy, ux
        b1 = (base[0] + nx * ARROW_W / 2, base[1] + ny * ARROW_W / 2)
        b2 = (base[0] - nx * ARROW_W / 2, base[1] - ny * ARROW_W / 2)
        # 杆身缩到箭头底，避免线头从箭头尖冒出来
        edge["points"][-1] = base
        edge["arrow"] = {"tip": tip, "base1": b1, "base2": b2, "dir": (ux, uy)}
        edge["shaft_end"] = base

    # 边界
    all_x, all_y = [], []
    for n in nodes_in:
        all_x += [n["_x"], n["_right"]]
        all_y += [n["_y"], n["_top"]]
    for band in bands:
        all_x += [band["x"], band["x"] + band["w"]]
        all_y += [band["y"], band["y"] + band["h"]]
    for edge in edges:
        for x, y in edge["points"]:
            all_x.append(x)
            all_y.append(y)
        if edge["label_rect"]:
            r = edge["label_rect"]
            all_x += [r["x"], r["x"] + r["w"]]
            all_y += [r["y"], r["y"] + r["h"]]
    min_x, max_x = min(all_x) - MARGIN, max(all_x) + MARGIN
    min_y, max_y = min(all_y) - MARGIN, max(all_y) + MARGIN
    W, H = max_x - min_x, max_y - min_y
    dx, dy = -min_x, -min_y

    def tr(p):
        return (p[0] + dx, p[1] + dy)

    for n in nodes_in:
        n["x"], n["y"] = n["_x"] + dx, n["_y"] + dy
        n["w"], n["h"] = n["_w"], n["_h"]
    for band in bands:
        band["x"] += dx
        band["y"] += dy
    for edge in edges:
        edge["points"] = [tr(p) for p in edge["points"]]
        edge["arrow"] = {k: (v if k == "dir" else tr(v))
                         for k, v in edge["arrow"].items()}
        if edge["label_rect"]:
            r = edge["label_rect"]
            r["x"] += dx
            r["y"] += dy
        # 供检查器用的端口
        edge["source_port"] = edge["points"][0]
        edge["target_port"] = edge["arrow"]["tip"]

    title = str(spec.get("title", "") or "")
    title_h = 26 if title else 0
    if title:
        for n in nodes_in:
            n["y"] += title_h
        for band in bands:
            band["y"] += title_h
        for edge in edges:
            edge["points"] = [(x, y + title_h) for x, y in edge["points"]]
            # dir 是方向向量，不能跟着标题偏移；只平移点
            edge["arrow"] = {
                k: (v if k == "dir" else (v[0], v[1] + title_h))
                for k, v in edge["arrow"].items()
            }
            if edge["label_rect"]:
                edge["label_rect"]["y"] += title_h
            edge["source_port"] = edge["points"][0]
            edge["target_port"] = edge["arrow"]["tip"]
        H += title_h

    return {
        "version": 1,
        "direction": direction,
        "title": title,
        "canvas": {"width": W, "height": H, "unit": UNIT},
        "layers": bands,
        "nodes": [{
            "id": str(n["id"]), "label": str(n.get("label", n["id"])),
            "style": str(n.get("style", "default")),
            "layer": n["_layer"],
            "rect": {"x": n["x"], "y": n["y"], "w": n["w"], "h": n["h"]},
            "label_rect": _text_rect(n["x"] + n["w"] / 2, n["y"] + n["h"] / 2,
                                     str(n.get("label", n["id"]))),
        } for n in nodes_in],
        "edges": edges,
        "metrics": {"font_size": FONT_SIZE, "line_height": LINE_H,
                    "arrow_len": ARROW_LEN, "arrow_width": ARROW_W},
    }


def _cross_pos(n: dict, direction: str) -> float:
    return n["_cy"] if direction == "LR" else n["_cx"]


def _text_rect(cx: float, cy: float, label: str) -> dict:
    w, h = text_size(label)
    return {"x": cx - w / 2, "y": cy - h / 2, "w": w, "h": h}


def _route(ei: int, s: dict, t: dict, sp, tp, li: int, lj: int,
           direction: str, gap_between, cross_extent, counts,
           n_layers: int) -> list:
    """正交折线。层间通道保证线不穿中间节点；跨层绕到所有中间节点之外。"""
    if li == lj:
        key = ("same", li)
        k = counts.get(key, 0)
        counts[key] = k + 1
        off = ROUTE_CLEAR + k * 8
        if direction == "LR":
            side_x = max(s["_right"], t["_right"]) + off
            return [sp, (side_x, sp[1]), (side_x, tp[1]), tp]
        side_y = max(s["_top"], t["_top"]) + off
        return [sp, (sp[0], side_y), (tp[0], side_y), tp]

    if lj > li:
        # 正向
        if direction == "LR":
            gap1 = gap_between(li, li + 1)
            if lj == li + 1:
                key = ("adj", li)
                k = counts.get(key, 0)
                counts[key] = k + 1
                mx = gap1 + (k - 2) * 3
                if abs(sp[1] - tp[1]) < 0.5:
                    return [sp, tp]
                return [sp, (mx, sp[1]), (mx, tp[1]), tp]
            gap2 = gap_between(lj - 1, lj)
            lo, hi = cross_extent(range(li + 1, lj))
            top, bottom = hi + ROUTE_CLEAR, lo - ROUTE_CLEAR
            key = ("long", li, lj)
            k = counts.get(key, 0)
            counts[key] = k + 1
            use_top = (abs(sp[1] - top) + abs(tp[1] - top)
                       <= abs(sp[1] - bottom) + abs(tp[1] - bottom))
            ch = (top if use_top else bottom) + (k * 7 if use_top else -k * 7)
            return [sp, (gap1, sp[1]), (gap1, ch), (gap2, ch), (gap2, tp[1]), tp]
        # TB 正向
        gap1 = gap_between(li, li + 1)
        if lj == li + 1:
            key = ("adj", li)
            k = counts.get(key, 0)
            counts[key] = k + 1
            my = gap1 + (k - 2) * 3
            if abs(sp[0] - tp[0]) < 0.5:
                return [sp, tp]
            return [sp, (sp[0], my), (tp[0], my), tp]
        gap2 = gap_between(lj - 1, lj)
        lo, hi = cross_extent(range(li + 1, lj))
        left, right = lo - ROUTE_CLEAR, hi + ROUTE_CLEAR
        key = ("long", li, lj)
        k = counts.get(key, 0)
        counts[key] = k + 1
        use_left = (abs(sp[0] - left) + abs(tp[0] - left)
                    <= abs(sp[0] - right) + abs(tp[0] - right))
        ch = (left if use_left else right) + (-k * 7 if use_left else k * 7)
        return [sp, (sp[0], gap1), (ch, gap1), (ch, gap2), (tp[0], gap2), tp]

    # 反向：从源层外侧出发，绕到所有中间层之外，再从目标层外侧进入
    lo, hi = cross_extent(range(min(li, lj), max(li, lj) + 1))
    key = ("back", li, lj)
    k = counts.get(key, 0)
    counts[key] = k + 1
    if direction == "LR":
        # 源层右侧的间隙；目标层左侧的间隙
        g1 = (gap_between(li, li + 1) if li + 1 < n_layers
              else gap_between(li - 1, li))
        g2 = (gap_between(lj - 1, lj) if lj > 0 else gap_between(lj, lj + 1))
        top, bottom = hi + ROUTE_CLEAR, lo - ROUTE_CLEAR
        use_top = (abs(sp[1] - top) + abs(tp[1] - top)
                   <= abs(sp[1] - bottom) + abs(tp[1] - bottom))
        ch = (top if use_top else bottom) + (k * 7 if use_top else -k * 7)
        return [sp, (g1, sp[1]), (g1, ch), (g2, ch), (g2, tp[1]), tp]
    # TB 反向：源层下方的间隙；目标层上方的间隙
    g1 = (gap_between(li - 1, li) if li > 0 else gap_between(li, li + 1))
    g2 = (gap_between(lj, lj + 1) if lj + 1 < n_layers
          else gap_between(lj - 1, lj))
    left, right = lo - ROUTE_CLEAR, hi + ROUTE_CLEAR
    use_left = (abs(sp[0] - left) + abs(tp[0] - left)
                <= abs(sp[0] - right) + abs(tp[0] - right))
    ch = (left if use_left else right) + (-k * 7 if use_left else k * 7)
    return [sp, (sp[0], g1), (ch, g1), (ch, g2), (tp[0], g2), tp]


def _rect_overlap(a: dict, b: dict) -> float:
    dx = min(a["x"] + a["w"], b["x"] + b["w"]) - max(a["x"], b["x"])
    dy = min(a["y"] + a["h"], b["y"] + b["h"]) - max(a["y"], b["y"])
    return dx * dy if dx > 0 and dy > 0 else 0.0


def _seg_hits_rect(a, b, r, pad=1.0) -> bool:
    """线段是否穿过矩形（Liang-Barsky 裁剪）。"""
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


def _label_candidates(points: list, label: str) -> list[dict]:
    """在最长两段上生成候选标签位置，左右/上下各一个。"""
    segs = []
    for a, b in zip(points, points[1:]):
        d = math.hypot(b[0] - a[0], b[1] - a[1])
        segs.append((d, a, b))
    segs.sort(key=lambda s: -s[0])
    w, h = text_size(label)
    out = []
    for d, a, b in segs[:2]:
        if d < 1:
            continue
        vertical = abs(b[0] - a[0]) < abs(b[1] - a[1])
        for t in (0.5, 0.35, 0.65, 0.2, 0.8):
            mx, my = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            if vertical:
                out.append({"x": mx + 5, "y": my - h / 2, "w": w, "h": h})
                out.append({"x": mx - 5 - w, "y": my - h / 2, "w": w, "h": h})
            else:
                out.append({"x": mx - w / 2, "y": my + 5, "w": w, "h": h})
                out.append({"x": mx - w / 2, "y": my - 5 - h, "w": w, "h": h})
    return out


def _place_edge_labels(edges: list[dict], nodes: list[dict],
                       bands: list[dict] | None = None) -> None:
    """给边标签选一个不压节点、不压层标题、不压其他标签的位置。"""
    node_rects = []
    # nodes 此时还是内部格式（_x/_y/_w/_h）
    for n in nodes:
        node_rects.append({"x": n["_x"], "y": n["_y"], "w": n["_w"], "h": n["_h"]})
    for band in (bands or []):
        w, h = text_size(str(band.get("name", "")))
        node_rects.append({"x": band["x"] + 6, "y": band["y"] + band["h"] - 12 - h / 2,
                           "w": w, "h": h})
    placed: list[dict] = []
    for edge in edges:
        label = str(edge.get("label", "") or "")
        if not label:
            continue
        candidates = _label_candidates(edge["points"], label)
        if not candidates:
            r = _text_rect(edge["points"][0][0], edge["points"][0][1], label)
            edge["label_rect"] = r
            placed.append(r)
            continue
        best, best_score = None, float("inf")
        for cand in candidates:
            score = 0.0
            for nr in node_rects:
                score += 10000 * _rect_overlap(cand, nr)
            for pr in placed:
                score += 10000 * _rect_overlap(cand, pr)
            # 标签不要压在其他边上
            for other in edges:
                if other is edge:
                    continue
                for a, b in zip(other["points"], other["points"][1:]):
                    if _seg_hits_rect(a, b, cand, pad=1.0):
                        score += 80
            # 轻微偏好靠近第一段中点
            score += 0.01 * abs(cand["x"] + cand["w"] / 2 - edge["points"][0][0])
            if score < best_score:
                best, best_score = cand, score
        edge["label_rect"] = best
        placed.append(best)


# ---------------------------------------------------------------------------
# 渲染
# ---------------------------------------------------------------------------

def render(layout: dict, out_svg: Path, out_png: Path | None = None,
           dpi: int = 220) -> dict:
    if not _MPL_OK:
        raise RuntimeError("matplotlib is required for rendering: "
                           "pip install matplotlib (or use D2/Graphviz)")
    W = float(layout["canvas"]["width"])
    H = float(layout["canvas"]["height"])
    fig = plt.figure(figsize=(W / 72, H / 72), dpi=dpi)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, W)
    ax.set_ylim(0, H)
    ax.axis("off")

    # 层背景
    for band in layout["layers"]:
        ax.add_patch(FancyBboxPatch(
            (band["x"], band["y"]), band["w"], band["h"],
            boxstyle="round,pad=0,rounding_size=6",
            linewidth=0.9, edgecolor="#D9E2F3", facecolor="#F7F9FC",
            linestyle=(0, (4, 3)), zorder=0))
        ax.text(band["x"] + 6, band["y"] + band["h"] - 12, band["name"],
                fontsize=8.5, color="#7F7F7F", ha="left", va="center", zorder=1)

    # 边
    for edge in layout["edges"]:
        xs = [p[0] for p in edge["points"]]
        ys = [p[1] for p in edge["points"]]
        ax.plot(xs, ys, color="#44546A", linewidth=1.5,
                solid_capstyle="butt", solid_joinstyle="miter", zorder=2)
        ar = edge["arrow"]
        ax.add_patch(Polygon([ar["tip"], ar["base1"], ar["base2"]],
                             closed=True, facecolor="#44546A",
                             edgecolor="#44546A", linewidth=0.5, zorder=3))
        if edge.get("label_rect"):
            r = edge["label_rect"]
            ax.text(r["x"] + r["w"] / 2, r["y"] + r["h"] / 2, edge["label"],
                    fontsize=8.2, color="#333333", ha="center", va="center",
                    zorder=4,
                    bbox=dict(boxstyle="round,pad=0.18", facecolor="white",
                              edgecolor="none", alpha=0.95))

    # 节点
    for node in layout["nodes"]:
        r = node["rect"]
        face, edge = STYLES.get(node.get("style", "default"), STYLES["default"])
        ax.add_patch(FancyBboxPatch(
            (r["x"], r["y"]), r["w"], r["h"],
            boxstyle="round,pad=0,rounding_size=5",
            linewidth=1.2, edgecolor=edge, facecolor=face, zorder=5))
        ax.text(r["x"] + r["w"] / 2, r["y"] + r["h"] / 2, node["label"],
                fontsize=FONT_SIZE * 0.95, color="#1F1F1F",
                ha="center", va="center", linespacing=1.15, zorder=6)

    if layout.get("title"):
        ax.text(W / 2, H - 13, layout["title"], fontsize=11.5,
                color="#1F1F1F", ha="center", va="center", zorder=6)

    out_svg.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_svg, format="svg", dpi=dpi, transparent=False,
                facecolor="white")
    png_info = {}
    if out_png is not None:
        out_png.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(out_png, format="png", dpi=dpi, transparent=False,
                    facecolor="white")
        png_info = {"path": str(out_png), "width_px": round(W / 72 * dpi),
                    "height_px": round(H / 72 * dpi), "dpi": dpi}
    plt.close(fig)
    return png_info


# ---------------------------------------------------------------------------
# 示例与 CLI
# ---------------------------------------------------------------------------

def example_spec() -> dict:
    return {
        "title": "示例：三层 Web 架构",
        "direction": "LR",
        "layers": [
            {"id": "client", "name": "接入层"},
            {"id": "gateway", "name": "网关层"},
            {"id": "service", "name": "服务层"},
            {"id": "data", "name": "数据层"},
        ],
        "nodes": [
            {"id": "browser", "label": "浏览器", "layer": "client", "style": "client"},
            {"id": "cdn", "label": "CDN", "layer": "client", "style": "external"},
            {"id": "lb", "label": "负载均衡\nNginx", "layer": "gateway", "style": "gateway"},
            {"id": "api", "label": "API 服务", "layer": "service", "style": "service"},
            {"id": "auth", "label": "认证服务", "layer": "service", "style": "service"},
            {"id": "db", "label": "PostgreSQL", "layer": "data", "style": "data"},
            {"id": "cache", "label": "Redis", "layer": "data", "style": "data"},
        ],
        "edges": [
            {"from": "browser", "to": "cdn", "label": "静态资源"},
            {"from": "browser", "to": "lb", "label": "HTTPS"},
            {"from": "cdn", "to": "lb"},
            {"from": "lb", "to": "api"},
            {"from": "lb", "to": "auth"},
            {"from": "api", "to": "db", "label": "读写"},
            {"from": "auth", "to": "db"},
            {"from": "api", "to": "cache", "label": "缓存"},
        ],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("spec", nargs="?", help="JSON spec")
    ap.add_argument("-o", "--out", default="diagram.svg", help="output SVG")
    ap.add_argument("--png", default=None, help="output PNG (default: same stem)")
    ap.add_argument("--no-png", action="store_true")
    ap.add_argument("--layout-json", default=None)
    ap.add_argument("--dpi", type=int, default=220)
    ap.add_argument("--example", metavar="PATH", help="write example spec and exit")
    args = ap.parse_args()

    if args.example:
        Path(args.example).write_text(
            json.dumps(example_spec(), ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(args.example)
        return 0

    if not args.spec:
        ap.error("spec is required (or use --example PATH)")
    spec = json.loads(Path(args.spec).read_text(encoding="utf-8"))
    layout = compute_layout(spec)

    out_svg = Path(args.out)
    out_png = None if args.no_png else (
        Path(args.png) if args.png else out_svg.with_suffix(".png"))
    png_info = render(layout, out_svg, out_png, dpi=args.dpi)
    if png_info:
        layout["image"] = png_info

    layout_json = Path(args.layout_json) if args.layout_json else out_svg.with_suffix(".layout.json")
    layout_json.write_text(json.dumps(layout, ensure_ascii=False, indent=2),
                           encoding="utf-8")
    print(json.dumps({"svg": str(out_svg), "png": str(out_png) if out_png else "",
                      "layout": str(layout_json),
                      "canvas": layout["canvas"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
