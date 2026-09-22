#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
extract_series.py — 从多份年报 .txt 拼接近 N 年核心财务序列（单值兜底工具）

用途：enterprise-analyst 的多年趋势分析。年报逐年滚动披露「近三年」数据，单份最新
年报只覆盖三年；要凑十年序列必须回到对应年份的旧年报去取。本脚本自动完成
「逐份提取 → 按财年归档 → 拼接」。

输入：一个目录，内含多份已转文本的**年报**（`edgar_fetch.py --to-text` 的 .txt，
或 `extract_pdf_text.py` 的 .txt）。脚本靠**内容**判断财年与报告类型，不靠文件名。

提取指标：营收 / 净利润 / 经营现金流净额（英 US GAAP 与中文 CAS 都覆盖）。

输出：CSV 风格文本，`year,revenue,net_income,ocf`，按年份升序；写到 --out 文件
（UTF-8），同时打印到控制台。单位随原始报表，脚本不换算。

──────────────────────────────────────────────────────────────────────────
⚠️ 定位（重要）：本脚本是「单值兜底」工具，**不做交叉验证**。

  要「重叠年份交叉验证」（同一财年在多份年报中的重复披露比对）→
  用 **`fetch_facts.py`**（SEC XBRL 结构化接口，能区分期间与申报来源）。
  2026-09-22 实测：fetch_facts.py 对 Meta 识别出 139 个可验证区间、抓到 4 处真实差异；
  而本脚本的正则方案**做不到**——原因见下。

  本脚本真正适用的是：**A 股 / 港股 PDF 转文本后的口径校核**。那类文本用不上 XBRL 接口，
  正则反而是唯一手段（但也只能取到骨架值，**须回原文核对**）。

已知边界（2026-09-22 实测记录，**勿重复尝试**）：
  正则方案无法可靠重建「一份年报 = 一张报表的三列」这个结构，因此做不了窗口映射，
  也就做不了交叉验证。三次尝试都失败：
    ① 全文反复 findall 科目名 → 科目名在每张表里只出现一次，只能拿到 1 个值；
    ② 定位报表锚点（`CONSOLIDATED STATEMENTS OF INCOME`）后取其后的连续数值 →
       锚点名会作为**页眉**在每页重复出现（Meta 10-K 命中 20+ 次），取"最后一次"
       落不到报表正文；
    ③ 从后往前遍历所有锚点位置、取第一个能凑够三列的位置 → 会抓到委托书/附注里的
       「31 / 2021 / 2020」这类年份片段，产出满屏**假差异**（比不验更糟）。
  结论：要么改进为解析 PDF 版式（成本远高于收益），要么接受「单值兜底」定位。
  —— 这正是 `fetch_facts.py` 存在的理由：**结构化接口 > 正则启发式**。
──────────────────────────────────────────────────────────────────────────

关键坑（均已在实现中规避，勿回退）：
  1. **多格式正则是「按优先级兜底」，不是「结果拼接」**。把各条正则的结果拼起来会让
     同一数字被重复计入（2026-09-22 实测：revenue 因此整列取空）。
  2. **季报会混进来**。10-Q 里也有 `Total revenue`，但那是季度数。若目录混有 10-Q，
     不排除就会把季度值当年度值（实测 `revenue 2025 = 60,801` 实为 2026Q2 单季营收）。
     故用「年度期间表述 vs 季度期间表述」的占比判定报告类型，季报直接跳过。
  3. **取「最后一个匹配」**：报表正文排在 MD&A / 主席报告之后，最后一个匹配才是报表值。
  4. **委托书会冒充年报并清空数据**。DEF 14A 里满是 `year ended December 31, 2025`
     这类表述，会被判为年报、且财年与真年报相同；但它取不到任何财务科目，
     若无条件写入会把该财年整行**覆盖成空**（2026-09-22 实测：Meta 2025 年整行被清空）。
     故：取不到值就跳过；同一财年多份文件时取「科目覆盖更全」的那份。

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

# 各指标的锚点正则，**按优先级兜底**（坑 1：先匹配上的胜出，绝不拼接结果）
_PATTERNS = {
    "revenue": [
        r"Total revenue\s*\$\s*([\d,]+)",        # 美股常见（Meta 等）
        r"Revenues\s*\$\s*([\d,]+)",             # 美股常见
        r"Revenue\s*\$\s*([\d,]+)",              # 美股：Revenue（单数）
        r"营业收入\s*([\d,]+(?:\.[\d]+)?)",         # 中文利润表
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


def is_annual_report(txt):
    """判断是年报还是季报/半年报（坑 2）。

    判据：**年度期间表述**出现次数 > **季度/半年期间表述**出现次数。
    10-K 通篇是 "year ended December 31, YYYY"；10-Q 则以 "three / six / nine months
    ended" 为主。文件名不可靠（accession 号看不出来），只能靠内容判。
    """
    annual = len(re.findall(r"(?:year|Year)\s+ended\s+[A-Za-z]+\s+\d{1,2},\s*\d{4}", txt))
    interim = len(re.findall(r"(?:three|Three|six|Six|nine|Nine)\s+months\s+ended", txt))
    interim += len(re.findall(r"年初至报告期末|本报告期|上年同期", txt))
    return annual > interim


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


def extract_value(txt, pats):
    """按优先级取该指标的年度值。

    取**最后一个匹配**（坑 3）：报表正文排在 MD&A / 主席报告之后。
    """
    for p in pats:
        got = re.findall(p, txt)
        if got:
            return got[-1].replace(",", "")
    return ""


def main():
    ap = argparse.ArgumentParser(description="从多份年报拼接近 N 年财务序列（单值兜底）")
    ap.add_argument("txt_dir", help="含多份年报 .txt 的目录")
    ap.add_argument("--out", default="series.csv", help="输出文件（UTF-8）")
    ap.add_argument("--fields", default="revenue,net_income,ocf",
                    help="要提取的指标，逗号分隔")
    ap.add_argument("--log", default=None, help="控制台输出同时写该文件")
    args = ap.parse_args()

    fields = [f.strip() for f in args.fields.split(",") if f.strip()]

    files = sorted(glob.glob(os.path.join(args.txt_dir, "*.txt")))
    final = {}
    n_skipped_interim = 0
    n_skipped_nonreport = 0
    for fp in files:
        try:
            txt = open(fp, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        if not is_annual_report(txt):        # 坑 2：季报/半年报直接跳过
            n_skipped_interim += 1
            continue
        fy = detect_fiscal_year(txt)
        if fy is None:
            continue
        rec = {k: extract_value(txt, v) for k, v in _PATTERNS.items()}
        n_ok = sum(bool(v) for v in rec.values())
        # 坑 4：委托书（DEF 14A）等非财报文件也会被判为"年报"，且财年相同 ——
        #       它取不到任何科目值，若直接写进 final 会**用空记录覆盖**真年报的数据
        #       （2026-09-22 实测：Meta 2025 年整行被委托书清空）。故取不到值就跳过。
        if n_ok == 0:
            n_skipped_nonreport += 1
            continue
        prev = final.get(fy)
        # 同一财年多份文件时，取「科目覆盖更全」的那份
        if prev is None or n_ok > sum(bool(v) for v in prev.values()):
            final[fy] = rec

    years = sorted(final.keys(), key=int)
    lines = [",".join(["year"] + fields)]
    for y in years:
        cells = [y] + [final[y].get(f) or "" for f in fields]
        lines.append(",".join(cells))

    text = "\n".join(lines)
    print(text)
    if n_skipped_interim:
        print("\nℹ️ 已跳过 %d 个季报/半年报文件（只取年报口径）。" % n_skipped_interim)
    if n_skipped_nonreport:
        print("ℹ️ 已跳过 %d 个取不到财务科目的文件（如委托书 / 附件）。" % n_skipped_nonreport)

    notes = [
        "",
        "> ⚠️ 本脚本为**单值兜底**工具：每个财年只取一个值，**不做重叠年份交叉验证**",
        "> （正则方案无法可靠重建「一份年报 = 一张报表的三列」，详见文件头「已知边界」）。",
        "> **要交叉验证请用 `<python> scripts/fetch_facts.py <CIK>`**（SEC XBRL 结构化接口）；",
        "> A 股 / 港股请人工抽检：用「该年本年报本年列」核「次年年报的本年比较列」。",
        "> 另：本表所有数字仍须回年报原文核对后才可写进报告。",
    ]
    print("\n".join(notes))

    blob = text + "\n" + "\n".join(notes) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(blob)
    if args.log:
        with open(args.log, "w", encoding="utf-8") as f:
            f.write(blob)
    return 0


if __name__ == "__main__":
    sys.exit(main())
