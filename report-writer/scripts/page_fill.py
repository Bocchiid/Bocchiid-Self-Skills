#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""量每页的版面利用率，只统计“需要我们自己编写”的页面。

参数是一份 PDF —— 先用 word_com.ps1 把成稿导出 PDF，再跑本脚本：

    python page_fill.py out.pdf
    python page_fill.py out.pdf --list                  # 先看每页是什么，再决定范围
    python page_fill.py out.pdf --exclude 2,11          # 手动排除模板页
    python page_fill.py out.pdf --pages 3-9,12-15       # 只统计这些页（显式优先）
    python page_fill.py out.pdf --no-auto-skip          # 不自动排除封面/评分页
    python page_fill.py out.pdf --json                  # 输出 JSON，便于批量比较

统计口径（重要）
    只统计**报告里需要我们编写的页**：实验步骤、实验结果分析、用例分析等。
    封面、评分表/评分页、教师评语页、空白页、模板自带的“实验说明/格式说明”页
    都**不参与**利用率计算——它们不是我们排版的产物，页面不满是正常的。

    默认会自动跳过：封面页、含评分/评价关键词的页、空白页。其余模板页
    （例如实验说明、格式说明）无法可靠自动识别，请用 `--list` 看页码后用
    `--exclude` 显式排除，或用 `--pages` 只圈定自己写的那几页。

判读
    利用率 = (页面可写区顶端 .. 最后一行内容的距离) / 可写区高度
    参与统计的页里，**最后一页**天然不满（正文到此结束），不计入最差页；
    中途某页低于 ~85% 基本都是同一个原因：紧接着的大块（图或表）被自动排到
    下一页，而它塞不进本页剩余空间。下一张块的“可容纳宽度”算法见
    references/layout-tuning.md。
"""

import argparse
import glob
import json
import re
import sys

import pymupdf  # pip install pymupdf


# 只用于“自动识别要排除的页”，不参与排版判断。
# 规范化后匹配（去掉空白/全角空格），避免模板写成「评　分」时漏掉。
RUBRIC_HINTS = ('评分标准', '评分表', '评分细则', '评价内容', '评价依据',
                '赋分', '得分', '成绩', '考核', '教师评语', '评语',
                '分值', '权重', '评阅')
# 正文分析里也可能出现"得分""成绩"这类词。只有命中这些结构性词，或命中
# 三个以上，才认定为评分页，避免把正文页误排除。
STRONG_RUBRIC_HINTS = ('评分标准', '评分表', '评分细则', '评价内容', '评价依据',
                       '赋分', '教师评语', '评语', '评阅')
COVER_HINTS = ('课程名称', '实验名称', '姓名', '学号', '班级', '指导教师',
               '实验日期', '报告日期', '专业', '学院', '题目', '报告名称',
               '项目名称', '小组成员', '组员')


def _norm(s):
    """去掉所有空白（含全角空格）再比对。"""
    return re.sub(r'[\s　]+', '', s or '')


def parse_pages(spec):
    """解析 "3-8,11,14-16" 这类页码表达（1 起）。"""
    pages = set()
    if not spec:
        return pages
    for part in str(spec).split(','):
        part = part.strip()
        if not part:
            continue
        if '-' in part:
            a, b = part.split('-', 1)
            a, b = int(a), int(b)
            if a > b:
                a, b = b, a
            pages.update(range(a, b + 1))
        else:
            pages.add(int(part))
    return pages


def classify_page(pg, index):
    """判断一页是不是“需要我们编写”的页。返回 (kind, 原因)。

    kind: body / cover / rubric / blank
    只做**保守**的关键词判断，拿不准时一律按 body 处理——宁可让我们多看一眼，
    也不要把真正的正文页漏掉。真正的模板说明页请用 --exclude 显式排除。
    """
    text = pg.get_text('text')
    norm = _norm(text)
    has_image = bool(pg.get_image_info())

    if not norm and not has_image:
        return 'blank', '空白页'

    rubric_hits = [h for h in RUBRIC_HINTS if _norm(h) in norm]
    strong_hit = any(_norm(h) in norm for h in STRONG_RUBRIC_HINTS)
    if len(rubric_hits) >= 3 or (len(rubric_hits) >= 2 and strong_hit):
        return 'rubric', '评分/评价页（命中：%s）' % '、'.join(rubric_hits[:3])

    if index == 0:
        cover_hits = [h for h in COVER_HINTS if _norm(h) in norm]
        # 封面通常字段多、正文少；只对第 1 页做这个判断，避免误伤正文页
        if len(cover_hits) >= 3 and len(norm) < 800:
            return 'cover', '封面页（命中：%s）' % '、'.join(cover_hits[:3])

    return 'body', ''


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
        kind, why = classify_page(pg, pg.number)
        snippet = ' '.join(pg.get_text('text').split())[:48]
        pages.append({
            'page': pg.number + 1,
            'kind': kind,
            'kind_reason': why,
            'first_text': snippet,
            'last_y': round(last, 1),
            'gap_pt': round(bottom - last, 1) if last else None,
            'ratio': round(used / usable, 3) if last else 0.0,
        })
    doc.close()
    return pages


def select_pages(pages, args):
    """按命令行参数决定哪些页参与统计，返回 (selected, skipped)。

    selected / skipped 都是 page dict 列表；skipped 额外带 `skip_reason`。
    """
    explicit = parse_pages(args.pages)
    excluded = parse_pages(args.exclude)
    selected, skipped = [], []

    for p in pages:
        p = dict(p)
        if explicit and p['page'] not in explicit:
            p['skip_reason'] = '不在 --pages 范围内'
            skipped.append(p)
            continue
        if p['page'] in excluded:
            p['skip_reason'] = '--exclude 指定排除'
            skipped.append(p)
            continue
        # 显式给了 --pages 就以它为准，不再自动跳过——否则用户圈定的页会被
        # 悄悄减掉，统计口径不可预期。
        if args.auto_skip and not explicit and p['kind'] in ('cover', 'rubric', 'blank'):
            p['skip_reason'] = p['kind_reason']
            skipped.append(p)
            continue
        selected.append(p)
    return selected, skipped


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('pdf', nargs='+', help='PDF 路径，支持通配符')
    ap.add_argument('--min', type=float, default=0.0,
                    help='只列利用率低于该值的页（0~1）')
    ap.add_argument('--bottom', type=float, default=785.0,
                    help='页面可写区底端的 y 坐标（pt）')
    ap.add_argument('--pages', default='',
                    help='只统计这些页（1 起），如 "3-8,11-14"')
    ap.add_argument('--exclude', default='',
                    help='排除这些页（1 起），如 "1,2,11"；用于模板说明页')
    ap.add_argument('--no-auto-skip', dest='auto_skip', action='store_false',
                    help='不自动排除封面页/评分页/空白页')
    ap.add_argument('--list', action='store_true',
                    help='列出每页的初步分类与首行文字，便于决定统计范围')
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

        try:
            selected, skipped = select_pages(pages, a)
        except ValueError as exc:
            ap.error('页码格式错误（--pages/--exclude）：%s' % exc)
        # 参与统计的“最后一页”是正文自然收尾处，不算未填满；
        # 不能再用“原始 PDF 的最后两页”，因为那可能是评分表/封面。
        body = selected[:-1] if len(selected) > 1 else selected
        slack = sum(p['gap_pt'] or 0 for p in body)
        worst = min((p['ratio'] for p in body), default=1.0)

        if a.list:
            print('=== %s  共 %d 页' % (path, len(pages)))
            for p in pages:
                mark = '统计' if p in selected else '排除'
                why = '' if mark == '统计' else '  ← %s' % (
                    next((s.get('skip_reason', '') for s in skipped
                          if s['page'] == p['page']), ''))
                print('    第 %2d 页  %5.1f%%  [%s] %s  %s%s' % (
                    p['page'], 100 * p['ratio'], mark, p['kind'],
                    p['first_text'], why))
            print('    自动跳过规则：封面 / 评分评价页 / 空白页；'
                  '模板说明页请用 --exclude 指定。')
            print()

        report[path] = {
            'pages': pages,
            'selected_pages': [p['page'] for p in selected],
            'skipped_pages': [{'page': p['page'],
                               'reason': p.get('skip_reason', p['kind_reason'])}
                              for p in skipped],
            'body_slack_pt': round(slack, 1),
            'worst_ratio': worst,
        }

    if a.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    for path, info in report.items():
        selected = info['selected_pages']
        skipped = info['skipped_pages']
        print('=== %s  共 %d 页；参与统计 %d 页（只算需编写的页），'
              '正文段底部空白合计 %.0f pt，最低利用率 %.0f%%' % (
                  path, len(info['pages']), len(selected),
                  info['body_slack_pt'], 100 * info['worst_ratio']))
        if skipped:
            print('    已排除：%s' % '；'.join(
                '第%d页（%s）' % (s['page'], s['reason']) for s in skipped))
        if not selected:
            print('    没有可统计的页。若整份都是模板页，说明不需要做版面调优。')
            continue
        bad = [p for p in info['pages']
               if p['page'] in selected and p['ratio'] < max(a.min, 0.85)]
        # 最后一页是正文收尾，天然不满，不算问题
        bad = [p for p in bad if p['page'] != selected[-1]]
        if not bad:
            print('    需编写页的利用率均 >= 85%（正文末页除外）')
        for p in bad:
            print('    第 %2d 页  利用率 %5.1f%%  底部空白 %6.1f pt' % (
                p['page'], 100 * p['ratio'], p['gap_pt'] or 0))


if __name__ == '__main__':
    main()
