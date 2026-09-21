#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
edgar_list_all.py — SEC EDGAR 全量 filing 检索（含历史分页）

用途：enterprise-analyst 分支 C（美股）的**前置检索工具**。

为什么需要它：SEC `data.sec.gov/submissions/CIK…….json` 的 `filings.recent`
数组只保留最近约 1000 条记录，追十年（如 Alphabet 2015 年的 10-K）时会漏。
更早的记录在 `filings.files` 指向的分页文件里（文件名形如
`CIK0001652044-submissions-001.json`）。

⚠️ 分页文件结构是**扁平的**（顶层直接是 form/filingDate/accessionNumber 等
并列数组），与主文件的 `filings.recent` 嵌套结构不同——直接套主文件的解析会
KeyError（2026-09 谷歌分析教训）。

用法：
    # 列出某 CIK 的全部 10-K（含修订稿）
    python edgar_list_all.py 1652044 --form 10-K --log _all.txt

    # 列出全部年报（20-F + 10-K）
    python edgar_list_all.py 1652044 --form 20-F,10-K --log _all.txt

    # 列出全部表单（不筛选），看清这家公司都报了什么
    python edgar_list_all.py 1652044 --log _all.txt

输出：`form\tfilingDate\taccession\tprimaryDoc` 每行一条，按 filingDate 倒序。

仅用标准库，managed python 即可运行。
"""

import argparse
import json
import re
import sys
import urllib.request

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

UA = "EnterpriseAnalyst/1.0 (research contact: analyst@example.com)"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK%010d.json"


def http_get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return json.loads(urllib.request.urlopen(req, timeout=60).read().decode("utf-8"))


def collect_rows(d, rows):
    """兼容两种结构：主文件（filings.recent 嵌套）与分页文件（扁平）。"""
    recent = d.get("filings", {}).get("recent")
    if recent is not None:
        form = recent["form"]; fd = recent["filingDate"]
        acc = recent["accessionNumber"]; pd = recent.get("primaryDocument", [])
    else:
        form = d.get("form", []); fd = d.get("filingDate", [])
        acc = d.get("accessionNumber", []); pd = d.get("primaryDocument", [])
    n = len(form)
    for i in range(n):
        rows.append({
            "form": form[i],
            "filingDate": fd[i],
            "accession": acc[i],
            "primaryDoc": pd[i] if i < len(pd) else "",
        })


def main():
    ap = argparse.ArgumentParser(description="SEC EDGAR 全量 filing 检索（含历史分页）")
    ap.add_argument("cik", help="CIK 数字（不带前缀，如 1652044）")
    ap.add_argument("--form", default="", help="筛选表单，逗号分隔（如 10-K 或 20-F,10-K）；不传则列全部")
    ap.add_argument("--include-amend", action="store_true", help="包含修订稿（如 10-K/A、20-F/A）")
    ap.add_argument("--log", default=None, help="结果同时写入该 UTF-8 文件（PowerShell 重定向中文会乱码）")
    args = ap.parse_args()

    cik = re.sub(r"\D", "", args.cik)
    wanted = [f.strip().upper() for f in args.form.split(",") if f.strip()]

    data = http_get_json(SUBMISSIONS % int(cik))
    rows = []
    collect_rows(data, rows)

    files = data["filings"].get("files", [])
    for f in files:
        name = f.get("name", "")
        if name.startswith("CIK"):
            d2 = http_get_json("https://data.sec.gov/submissions/" + name)
            collect_rows(d2, rows)

    # 去重（同 accession 可能主文件与分页都出现）
    seen = set()
    uniq = []
    for r in rows:
        if r["accession"] in seen:
            continue
        seen.add(r["accession"])
        uniq.append(r)

    def keep(r):
        if wanted and r["form"].upper() not in wanted:
            return False
        if not args.include_amend and "/A" in r["form"]:
            return False
        return True

    uniq = [r for r in uniq if keep(r)]
    uniq.sort(key=lambda r: r["filingDate"], reverse=True)

    lines = []
    lines.append("== CIK %s 共 %d 条（筛选后 %d 条）==" % (cik, len(seen), len(uniq)))
    for r in uniq:
        lines.append("%s\t%s\t%s\t%s" % (r["form"], r["filingDate"],
                                          r["accession"], r["primaryDoc"]))

    text = "\n".join(lines)
    print(text)
    if args.log:
        with open(args.log, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
