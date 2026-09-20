#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
edgar_fetch.py — 美股 / 中概股 SEC EDGAR 财报检索与下载

用途：enterprise-analyst 的「外部获取」分支 C（美股）。
当本地无 PDF、ima 知识库也没有（或缺最新报告期）时，用它从 SEC EDGAR
拉取**一手财报原文件**（20-F / 424B4 / 6-K），作为后续分析的数据源。

仅用标准库（urllib / html.parser），managed python 即可运行，无需 venv。

## ⚠️ 覆盖此脚本解决的问题

1. 中概股多为「外国私人发行人 FPI」，年报是 **20-F**，不是 10-K；
   季报挂在 **6-K 的 EX-99.1** 里，不是 10-Q。按 10-K/10-Q 检索会颗粒无收。
2. `data.sec.gov` 的 submissions 接口要求 CIK **补零到 10 位**
   （`CIK0001737806.json`）；直接写 `CIK1737806.json` 会 404。
3. 4 MB 的 iXBRL 年报用 `urlopen(...).read()` 会 `IncompleteRead`，
   必须分块读 + 整份重试。
4. SEC 对无 User-Agent 的请求返回 403。

## 默认套装（preset=standard，不传 --forms 时的默认行为）

    python edgar_fetch.py 1737806 --out ./_src

一次拉齐一份公司分析所需的全部一手材料：

| 内容               | 数量规则                                        |
|--------------------|-------------------------------------------------|
| 20-F 年报          | **近 5 年**（`--years N` 可调）                 |
| 424B4 招股书/增发  | 全部命中（IPO 稿 + 后续增发稿）                 |
| 6-K 季度业绩        | 最近 1 期（自动从近期 6-K 里找出含季报正文的那份）|

> 默认套装的数量规则对所有公司一律适用，不要只下最新一份就开工。

## 常用命令

    # 1) 先干跑，看清会下载什么（强烈推荐第一步）
    python edgar_fetch.py 1737806 --list

    # 2) 正式下载 + 转文本 + 校验财年
    python edgar_fetch.py 1737806 --out ./_src --to-text

    # 3) 用公司名反查 CIK（支持 ATOM 检索）
    python edgar_fetch.py "PDD Holdings" --list

    # 4) 精确指定 accession，绕过检索
    python edgar_fetch.py 1737806 --acc 0001104659-26-050727 --out ./_src

    # 5) 只拉近 3 年年报，跳过 6-K
    python edgar_fetch.py 1737806 --years 3 --no-6k --out ./_src

## 参数

target                CIK 数字（推荐）或公司英文名（走 ATOM 检索反查）
--out                 下载目录（默认 ./edgar_dl）
--preset              standard（默认）/ none。传 --forms 或 --acc 时自动切 none
--years               默认套装取几年年报（默认 5）
--forms               手工表单列表，逗号分隔，如 20-F,424B4,6-K
--acc                 手工 accession 列表，逗号分隔（形如 0001104659-26-050727）
--no-6k               默认套装里不探测 6-K 季度业绩
--max-6k-probe        最多往前探测几份 6-K（默认 8）
--include-amend       包含修订稿（20-F/A，默认排除）
--list                只列不下载
--to-text             下载后顺便转成 .txt（标准库剥 HTML 标签）
--json                filing 元数据写入 <out>/_filings.json
--overwrite           覆盖同名文件（默认跳过已存在）
--log                 把控制台输出同时写入该文件（UTF-8，PowerShell 重定向会乱码）

## 输出

    <out>/PDD_20F_2025_<acc>.htm       财报原文件（iXBRL HTML）
    <out>/PDD_20F_2025_<acc>.txt       --to-text 时产出，供 Grep/Read 用
    <out>/_filings.json                --json 时产出

下载完成后会按文件内容自动判定每份年报的**主导财年**，用于校验有没有下错
（切勿用字节数判断，实测不同年报可能字节数完全相同）。
"""

import argparse
import html.parser
import json
import os
import re
import sys
import time
import urllib.request

# Windows 控制台默认 GBK，重定向到文件后再按 UTF-8 读会乱码 —— 强制 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# SEC 强制要求：无 UA 一律 403。请改成自己的邮箱，否则可能被限流。
UA = "EnterpriseAnalyst/1.0 (research contact: analyst@example.com)"

SUBMISSIONS = "https://data.sec.gov/submissions/CIK%010d.json"
ARCHIVES = "https://www.sec.gov/Archives/edgar/data/%s/%s/%s"
COMPANY_SEARCH = (
    "https://www.sec.gov/cgi-bin/browse-edgar"
    "?action=getcompany&company=%s&type=&dateb=&owner=include&count=10&output=atom"
)

# 6-K 里季度业绩 press release 的识别关键词（须同时命中文案 + 数字表）
QUARTER_HINTS = ("unaudited", "three months", "quarterly", "quarter ended")


class _Tee(object):
    """同时写多个流（用于 --log：控制台 + UTF-8 文件）"""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            try:
                st.write(s)
            except Exception:
                pass

    def flush(self):
        for st in self.streams:
            try:
                st.flush()
            except Exception:
                pass


def http_get(url, retries=3, timeout=60, raw=False):
    """带 UA 的 GET，返回 str；失败整份重试。"""
    data = http_get_bytes(url, retries=retries, timeout=timeout)
    return data if raw else data.decode("utf-8", errors="replace")


def http_get_bytes(url, retries=3, timeout=60):
    """带 UA 的 GET，返回 bytes。分块读 + 整份重试，规避 IncompleteRead。"""
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            buf = b""
            with urllib.request.urlopen(req, timeout=timeout) as r:
                while True:
                    chunk = r.read(65536)
                    if not chunk:
                        break
                    buf += chunk
            return buf
        except Exception as e:              # noqa: BLE001
            last = e
            print("   ! 第 %d 次失败：%s，2s 后重试" % (i + 1, e))
            time.sleep(2)
    raise RuntimeError("下载失败 %s ：%s" % (url, last))


# ---------------------------------------------------------------- 检索

def resolve_cik(target):
    """把 target 解析成 CIK 数字串。支持直接给 CIK，或公司英文名走 ATOM 检索。"""
    digits = re.sub(r"\D", "", target)
    if target.strip().isdigit() or (digits and target.upper().startswith("CIK")):
        return digits.lstrip("0") or "0"

    print("== 按公司名反查 CIK：%s ==" % target)
    xml = http_get(COMPANY_SEARCH % urllib.request.quote(target))
    hits = []
    for m in re.finditer(
        r"<conformed-name>([^<]+)</conformed-name>.*?CIK=(\d{10})",
        xml, re.S,
    ):
        hits.append((m.group(2).lstrip("0"), m.group(1).strip()))
    if not hits:
        print("!! 没查到，建议直接用 WebFetch 打开 browse-edgar 页面肉眼确认 CIK")
        return None
    for cik, name in hits:
        print("   CIK %-10s  %s" % (cik, name))
    return hits[0][0]


def load_filings(cik):
    """拉 submissions 元数据。坑：CIK 必须补零到 10 位。"""
    url = SUBMISSIONS % int(cik)
    data = json.loads(http_get(url))
    recent = data.get("filings", {}).get("recent", {})
    rows = []
    n = len(recent.get("form", []))
    for i in range(n):
        rows.append({
            "form": recent["form"][i],
            "filingDate": recent["filingDate"][i],
            "accession": recent["accessionNumber"][i],
            "primaryDoc": recent.get("primaryDocument", [""])[i],
            "description": recent.get("primaryDocDescription", [""])[i],
        })
    print("== CIK %s (%s) 共 %d 条 recent filings ==" % (
        cik, data.get("name", "?"), n))
    return rows


def select_standard(rows, years=5, want_6k=True, max_probe=8, include_amend=False):
    """按默认套装挑出要下的 accession 清单。"""
    def keep(r, form):
        if r["form"] != form:
            return False
        return include_amend or "/A" not in r["form"]

    plan = []
    seen = set()

    annuals = sorted([r for r in rows if keep(r, "20-F")],
                     key=lambda r: r["filingDate"], reverse=True)
    # 同一财年可能有多份（修订稿），按 filing 年份去重留最新
    by_year = {}
    for r in annuals:
        y = int(r["filingDate"][:4])
        by_year.setdefault(y, r)
    for y in sorted(by_year, reverse=True)[:years]:
        r = by_year[y]
        plan.append(dict(r, tag="20F_%d" % (y - 1), kind="annual"))
        seen.add(r["accession"])

    for r in rows:
        if r["form"] in ("424B4", "424B5") and r["accession"] not in seen:
            plan.append(dict(r, tag="PROSPECTUS_%s" % r["filingDate"][:4],
                             kind="prospectus"))
            seen.add(r["accession"])

    if want_6k:
        # 6-K 数量很多且大部分与业绩无关（处罚、人事、股东会等）。默认按倒序
        # 把最近若干份列为候选，下载后按内容判断是不是季度业绩，是的话留下。
        sixks = sorted([r for r in rows if r["form"] == "6-K"],
                       key=lambda r: r["filingDate"], reverse=True)
        for r in sixks[:max_probe]:
            if r["accession"] not in seen:
                plan.append(dict(r, tag="6K_%s" % r["filingDate"],
                                 kind="quarter_probe"))
                seen.add(r["accession"])

    plan.sort(key=lambda r: r["filingDate"], reverse=True)
    return plan


# ---------------------------------------------------------------- 主文档识别

_EXHIBIT = re.compile(r'href="([^"]+\.htm)"', re.I)


def pick_doc(index_html, prefer):
    """从 index 页里挑主文档文件名。prefer 可为文件名片段。"""
    hrefs = []
    for h in _EXHIBIT.findall(index_html):
        name = h.rsplit("/", 1)[-1]
        low = name.lower()
        if "-index.htm" in low or low.startswith("filingsummary"):
            continue
        hrefs.append(name)
    if not hrefs:
        return None
    if prefer:
        for name in hrefs:
            if prefer.lower() in name.lower():
                return name
    for key in ("20f", "424b4", "424b5", "ex99-1", "ex99.1", "40f", "10-k"):
        for name in hrefs:
            if key in name.lower():
                return name
    return hrefs[0]


def acc_paths(cik, acc):
    no_dash = acc.replace("-", "")
    base = ARCHIVES % (cik, no_dash, "")
    return base, base + acc + "-index.htm"


# ---------------------------------------------------------------- 文本与校验

class _Stripper(html.parser.HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self._skip = False

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip = True
        elif tag in ("tr", "p", "div", "br", "td", "th", "h1", "h2", "h3", "li"):
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self._skip = False

    def handle_data(self, d):
        if not self._skip:
            self.parts.append(d)


def to_text(html_src, out_path):
    p = _Stripper()
    p.feed(html_src)
    p.close()
    txt = re.sub(r"[ \t\xa0]+", " ", "".join(p.parts))
    txt = re.sub(r"\n\s*\n+", "\n", txt)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(txt)
    return len(txt)


def detect_fiscal_year(txt):
    """返回 (众数年份, 众数次數, 最新提及年份)。

    切勿用文件大小或字节数判断财年 —— 不同年份的年报可能字节数完全相同。

    年报看**众数**：正文绝大多数引用的是当期财年。
    季报既不能看众数也不能看短语最新：Q2 稿子里「去年同期」提及次数相当，
    且报表列头是「2026」单独成行的排版，短语正则抓不到。
    所以季报一律看**全文最新年份**（latest_any）。
    """
    hits = re.findall(r"(?:year|months) ended [A-Za-z]+ \d{1,2},\s*(\d{4})", txt)
    hits += re.findall(r"fiscal year ended[^\d]{0,20}(\d{4})", txt)
    counts = {}
    if hits:
        hits = [h for h in hits if 1990 < int(h) < 2100]
        for y in hits:
            counts[y] = counts.get(y, 0) + 1
    mode, cnt = max(counts.items(), key=lambda kv: kv[1]) if counts \
        else (None, 0)

    this_year = time.localtime().tm_year
    any_years = [y for y in re.findall(r"\b(19[89]\d|20[0-5]\d)\b", txt)
                 if int(y) <= this_year + 1]
    return mode, cnt, (max(any_years, key=int) if any_years else None)


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description="SEC EDGAR 财报检索与下载（默认：近5年20-F年报+424B4招股书+最近一期6-K季度业绩）")
    ap.add_argument("target", help="CIK 数字（推荐）或公司英文名")
    ap.add_argument("--out", default="edgar_dl", help="下载目录（默认 ./edgar_dl）")
    ap.add_argument("--preset", default="standard", choices=["standard", "none"])
    ap.add_argument("--years", type=int, default=5, help="默认套装取几年年报（默认 5）")
    ap.add_argument("--forms", default="", help="手工表单列表，逗号分隔，如 20-F,424B4")
    ap.add_argument("--acc", default="", help="手工 accession 列表，逗号分隔")
    ap.add_argument("--no-6k", action="store_true", help="默认套装里不探测 6-K")
    ap.add_argument("--max-6k-probe", dest="max_probe", type=int, default=8)
    ap.add_argument("--include-amend", action="store_true", help="包含修订稿 20-F/A")
    ap.add_argument("--list", action="store_true", help="只列不下载")
    ap.add_argument("--to-text", action="store_true", help="下载后转 .txt")
    ap.add_argument("--json", dest="dump_json", action="store_true")
    ap.add_argument("--overwrite", action="store_true", help="覆盖同名文件")
    ap.add_argument("--log", default=None, help="控制台输出同时写入该文件（UTF-8）")
    args = ap.parse_args()

    if args.log:
        sys.stdout = _Tee(sys.stdout, open(args.log, "w", encoding="utf-8",
                                           errors="replace"))
        sys.stderr = sys.stdout

    cik = resolve_cik(args.target)
    if not cik:
        return 1

    manual = bool(args.forms or args.acc)

    if args.acc:
        plan = [{"form": "?", "filingDate": "", "accession": a.strip(),
                 "primaryDoc": "", "tag": "ACC", "kind": "manual"}
                for a in args.acc.split(",") if a.strip()]
    else:
        rows = load_filings(cik)
        if args.forms:
            wanted = [f.strip().upper() for f in args.forms.split(",")]
            plan = [dict(r, tag=r["form"].replace("-", ""), kind="manual")
                    for r in rows if r["form"].upper() in wanted]
        elif args.preset == "none" or manual:
            plan = []
        else:
            plan = select_standard(rows, years=args.years,
                                   want_6k=not args.no_6k,
                                   max_probe=args.max_probe,
                                   include_amend=args.include_amend)

    print("\n== 计划下载 %d 份 ==" % len(plan))
    for p in plan:
        print("   [%s] %s  %s  %s" % (p["tag"], p["form"],
                                      p["filingDate"], p["accession"]))
    if args.list:
        return 0
    os.makedirs(args.out, exist_ok=True)   # 干跑不要留下空目录

    got = []
    for p in plan:
        acc = p["accession"]
        base, index_url = acc_paths(cik, acc)
        try:
            idx = http_get(index_url)
        except Exception as e:              # noqa: BLE001
            print("!! 跳过 %s，index 打不开：%s" % (acc, e))
            continue

        doc = pick_doc(idx, p.get("primaryDoc"))
        if not doc:
            print("!! 跳过 %s，index 里找不到主文档" % acc)
            continue

        url = base + doc
        fname = "%s_%s_%s" % (p["tag"], acc.replace("-", "_"), doc)
        fname = re.sub(r"[^\w.\-]", "_", fname)
        path = os.path.join(args.out, fname)
        if os.path.exists(path) and not args.overwrite:
            print("== 已存在，跳过 %s" % fname)
        else:
            try:
                raw = http_get_bytes(url)
            except Exception as e:          # noqa: BLE001
                print("!! 下载失败 %s：%s" % (doc, e))
                continue
            with open(path, "wb") as f:
                f.write(raw)
            print("== 下载 %-46s %7.2f MB" % (fname, len(raw) / 1048576))

        # 6-K 季度业绩探测：主文档太薄就顺延到 EX-99.1
        txt_path = None
        html_src = open(path, encoding="utf-8", errors="replace").read()
        if p["kind"] in ("quarter_probe", "quarter"):
            hits = [k for k in QUARTER_HINTS if k.lower() in html_src.lower()]
            print("   -> %s" % ("含季度业绩线索：%s" % "、".join(hits)
                                if hits else "非业绩类 6-K，可删"))
            if len(html_src) < 100000 or "Revenue" not in html_src:
                alt = pick_doc(idx, "ex99-1")
                if alt and alt != doc:
                    alt_url = base + alt
                    alt_name = re.sub(r"[^\w.\-]", "_",
                                      "%s_%s_%s" % (p["tag"],
                                                    acc.replace("-", "_"), alt))
                    alt_path = os.path.join(args.out, alt_name)
                    if not (os.path.exists(alt_path) and not args.overwrite):
                        try:
                            raw2 = http_get_bytes(alt_url)
                            with open(alt_path, "wb") as f:
                                f.write(raw2)
                            print("   + 取到业绩 exhibit：%s" % alt_name)
                        except Exception:   # noqa: BLE001
                            pass

        if args.to_text:
            txt_path = path.rsplit(".", 1)[0] + ".txt"
            n = to_text(html_src, txt_path)
            year, cnt, latest = detect_fiscal_year(
                open(txt_path, encoding="utf-8", errors="replace").read())
            if year:
                tail = ("主导财年 %s（众数 %d 处）；全文最新年份 %s"
                        % (year, cnt, latest))
            else:
                tail = "未识别到财年"
            print("   -> %s  %d 字符  %s" % (os.path.basename(txt_path), n, tail))
        got.append(dict(p, file=fname, doc=doc))

    if args.dump_json:
        with open(os.path.join(args.out, "_filings.json"), "w",
                  encoding="utf-8") as f:
            json.dump(got, f, ensure_ascii=False, indent=2)

    print("\n== 完成，共 %d 份，输出目录 %s ==" % (len(got), os.path.abspath(args.out)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
