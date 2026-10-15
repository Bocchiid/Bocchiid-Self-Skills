#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量每页的版面利用率，找出“只填了一半”的页。

参数是一份 PDF —— 先用 word_com.ps1 把成稿导出 PDF，再跑本脚本：

    python page_fill.py out.pdf
    python page_fill.py out.pdf --min 0.9      # 只列利用率低于 90% 的页
    python page_fill.py out.pdf --json         # 输出 JSON，便于批量比较

判读：
    利用率 = (页面可写区顶端 .. 最后一行内容的距离) / 可写区高度
    末尾一到两页天然不满（正文就此结束、之后是成绩表之类的模板内容），不算问题。
    中途某页低于 ~85% 基本都是同一个原因：紧接着的大块（图或表）被自动排到
    下一页，而它塞不进本页剩余空间。下一张块的“可容纳宽度”算法见
    references/layout-tuning.md。
"""

import argparse
import glob
import json
import sys

import pymupdf  # pip install pymupdf


def analyze(path, bottom=785.0, top=56.7):
    doc = pymupdf.open(path)
    pages = []
    for pg in doc:
        if bottom is None:
            bottom = pg.rect.height - 56.7    # 按页面高度推算，模板边距不同时不准
        last = 0.0
        for blk in pg.get_text('dict')['blocks']:
            r = pymupdf.Rect(blk['bbox'])
            if r.y1 < bottom:
                last = max(last, r.y1)
        for info in pg.get_image_info():
            r = pymupdf.Rect(info['bbox'])
            if r.y1 < bottom:
                last = max(last, r.y1)
        usable = bottom - top
        used = (last - top) if last else 0.0
        pages.append({
            'page': pg.number + 1,
            'last_y': round(last, 1),
            'gap_pt': round(bottom - last, 1) if last else None,
            'ratio': round(used / usable, 3) if last else 0.0,
        })
    doc.close()
    return pages


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf', nargs='+', help='PDF 路径，支持通配符')
    ap.add_argument('--min', type=float, default=0.0,
                    help='只列利用率低于该值的页（0~1）')
    ap.add_argument('--bottom', type=float, default=785.0,
                    help='页面可写区底端的 y 坐标（pt）')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args()

    paths = []
    for p in a.pdf:
        paths.extend(sorted(glob.glob(p)) or [p])

    report = {}
    for path in paths:
        try:
            pages = analyze(path, bottom=a.bottom, top=a.bottom - 728.3)
        except Exception as exc:                       # noqa: BLE001
            print('跳过 %s：%s' % (path, exc), file=sys.stderr)
            continue
        # 末尾两页通常是收尾，不算未填满
        body = pages[:-2] if len(pages) > 2 else pages
        slack = sum(p['gap_pt'] or 0 for p in body)
        worst = min((p['ratio'] for p in body), default=1.0)
        report[path] = {'pages': pages, 'body_slack_pt': round(slack, 1),
                        'worst_ratio': worst}

    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    for path, info in report.items():
        print('=== %s  共 %d 页，正文段底部空白合计 %.0f pt，最低利用率 %.0f%%' % (
            path, len(info['pages']), info['body_slack_pt'],
            100 * info['worst_ratio']))
        bad = [p for p in info['pages'] if p['ratio'] < max(a.min, 0.85)]
        if not bad:
            print('    各页利用率均 >= 85%（末页除外）')
        for p in bad:
            print('    第 %2d 页  利用率 %5.1f%%  底部空白 %6.1f pt' % (
                p['page'], 100 * p['ratio'], p['gap_pt'] or 0))


if __name__ == '__main__':
    main()
