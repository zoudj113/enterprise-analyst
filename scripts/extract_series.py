#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
extract_series.py — 从多份年报 .txt 拼接近 N 年核心财务序列

用途：enterprise-analyst 的多年趋势分析。美股 20-F / A 股年报都逐年滚动披露
「近三年」数据（重叠年份天然交叉验证），单份最新年报只覆盖三年；要凑十年序列
必须回到对应年份的旧年报去取。本脚本自动完成「逐份提取 → 按财年去重 → 拼接」。

输入：一个目录，内含多份已转文本的年报（`edgar_fetch.py --to-text` 的 .txt，
或 `extract_pdf_text.py` 的 .txt）。文件名里建议含财年/年份（脚本靠内容判断财年，
不靠文件名）。

提取指标（能从标准三表稳定取到的）：
  - 营收（Revenues / 营业收入）
  - 净利润（Net income / 净利润）
  - 经营现金流净额（Net cash provided by operating activities）

输出：CSV 风格文本，`year,revenue,net_income,ocf`，按年份升序；写到 --out 文件
（UTF-8），同时打印到控制台。单位随原始报表（美股是百万美元、A 股是元/万元），
脚本不换算，调用方自行处理单位。

仅用标准库，managed python 即可运行。

用法：
    python extract_series.py <目录> --out series.csv
    python extract_series.py <目录> --out series.csv --fields revenue,net_income
"""

import argparse
import glob
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 各指标的锚点正则（英文 US GAAP 与中文 CAS 都覆盖）
_PATTERNS = {
    "revenue": [
        r"Revenues\s*\$\s*([\d,]+)",      # 美股合并利润表（取第一个匹配，通常是当年）
        r"营业收入\s*([\d,]+(?:\.[\d]+)?)",  # 中文利润表
    ],
    "net_income": [
        r"Net income\s*\$\s*([\d,]+)",
        r"净利润\s*([\d,]+(?:\.[\d]+)?)",
    ],
    "ocf": [
        r"Net cash provided by operating activities\s*\(?\$?\s*\(?([\d,]+)",
        r"经营活动产生的现金流量净额\s*([\d,]+(?:\.[\d]+)?)",
    ],
}


def detect_fiscal_year(txt):
    """返回该年报的「众数财年」。美股看 'year ended December 31, YYYY' 众数。"""
    hits = re.findall(r"(?:year|Year) ended [A-Za-z]+ \d{1,2},\s*(\d{4})", txt)
    hits += re.findall(r"fiscal year ended[^\d]{0,20}(\d{4})", txt, re.I)
    counts = {}
    for y in hits:
        if 1990 < int(y) < 2100:
            counts[y] = counts.get(y, 0) + 1
    if not counts:
        return None
    return max(counts, key=lambda k: counts[k])


def main():
    ap = argparse.ArgumentParser(description="从多份年报拼接近 N 年财务序列")
    ap.add_argument("txt_dir", help="含多份年报 .txt 的目录")
    ap.add_argument("--out", default="series.csv", help="输出文件（UTF-8）")
    ap.add_argument("--fields", default="revenue,net_income,ocf",
                    help="要提取的指标，逗号分隔")
    ap.add_argument("--log", default=None, help="控制台输出同时写该文件")
    args = ap.parse_args()

    fields = [f.strip() for f in args.fields.split(",") if f.strip()]

    files = sorted(glob.glob(os.path.join(args.txt_dir, "*.txt")))
    # 合并利润表从左到右是「旧→中→新」三年窗口，当年 = 每个指标锚点的最后一个匹配。
    # 逐份年报取「众数财年 + 最后一个匹配」，按财年去重（同年多份年报只留一份）。
    final = {}
    for fp in files:
        try:
            txt = open(fp, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        fy = detect_fiscal_year(txt)
        if fy is None:
            continue
        rec = {}
        for key, pats in _PATTERNS.items():
            vals = []
            for p in pats:
                vals += re.findall(p, txt)
            # 三年窗口：最后一个匹配是当年（最新）
            rec[key] = vals[-1].replace(",", "") if vals else None
        final[fy] = rec

    years = sorted(final.keys(), key=int)
    lines = [",".join(["year"] + fields)]
    for y in years:
        cells = [y]
        for f in fields:
            cells.append(final[y].get(f, "") or "")
        lines.append(",".join(cells))

    text = "\n".join(lines)
    print(text)
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    if args.log:
        with open(args.log, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
