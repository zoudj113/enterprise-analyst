#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
hkex_fetch.py — 港股 / 中概股披露易（hkexnews.hk）财报检索与下载

用途：enterprise-analyst 的「外部获取」分支 C（港股）。
当本地无 PDF、ima 知识库也没有（或缺最新报告期）时，用它从港交所披露易
拉取**一手财报 PDF**（年报 / 中期报告 / 招股书），作为后续分析的数据源。

仅用标准库（urllib / re / json），managed python 即可运行；校验页数时可选 pypdf。

## 港股与 A 股 / 美股的关键差异

1. **没有季报**：港股只强制披露**年报 + 中期报告（中报）**，没有一季报/三季报。
   默认套装据此 = 近 5 年年报 + 招股书 + 最近 1 期中报。
2. **招股书标题是「全球發售」**，不含「招股章程」字样 —— 搜「招股章程」会返回 0 条。
3. 标题里带「企業年度報告書」的是**工商年报**，不是财报，必须排除。
4. 披露易的搜索结果 `result` 字段是**二次编码的 JSON**，要 `json.loads` 两次。
5. 港股无增值税，销售收现比基准取 1.0（不是 A 股的 1.13），与脚本无关但分析时要记住。

## 默认套装（preset=standard，不传 --type 时的默认行为）

    python hkex_fetch.py 09633 --out ./_src

一次拉齐一份公司分析所需的全部一手材料：

| 内容       | 数量规则                                    |
|------------|---------------------------------------------|
| 年报       | **近 5 年**（`--years N` 可调）             |
| 中期报告   | 最近 1 期                                    |
| 招股书     | 全部命中（标题含「全球發售」，按页数筛掉小文件）|

## 常用命令

    # 1) 先干跑，看清会下载什么（强烈推荐第一步）
    python hkex_fetch.py 09633 --list --log _plan.txt

    # 2) 正式下载
    python hkex_fetch.py 09633 --out ./_src --json --log _dl.txt

    # 3) 只拉近 3 年年报
    python hkex_fetch.py 09633 --years 3 --out ./_src

    # 4) 按标题关键词手工检索（退出默认套装）
    python hkex_fetch.py 09633 --title 全球發售 --out ./_src

## 参数

code                 港股 5 位股票代码（如 09633 / 00700 / 09988），自动补零到 5 位
--out                下载目录（默认 ./hkex_dl）
--preset             standard（默认）/ none。传 --title 或 --type 时自动切 none
--years              默认套装取几年年报（默认 5）
--type               手工类别：annual/interim/prospectus，逗号分隔
--title              手工标题关键词（传了即退出默认套装）
--from / --to        公告日期区间 YYYYMMDD
--list               只列不下载
--json               公告元数据写进 <out>/_filings.json
--overwrite          覆盖同名文件（默认跳过已存在）
--check-pdf          下载后用 pypdf 校验页数（需 venv python）
--log                把控制台输出同时写入该文件（UTF-8，PowerShell 重定向会乱码）

## 输出

    <out>/<分类>_<年份>_<newsId>_<原标题>.pdf    财报原文件
    <out>/_filings.json                         --json 时产出

下载后文件名带「分類 + 年份」，方便核对数量；招股书按页数筛掉 6 页的电子发售通告。
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

# Windows 控制台默认 GBK，重定向到文件后再按 UTF-8 读会乱码 —— 强制 UTF-8 输出
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

HKEX = "https://www1.hkexnews.hk"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
REFERER = "https://www1.hkexnews.hk/listedco/listconews/advancedsearchlist.html"

# 类别 -> 本地标题分类规则。
# 坑（2026-09 实测）：披露易 titleSearchServlet 的 `title` 参数已**失效**，
# 只要带 title 就返回 recordCnt=0，不带 title 才正常出结果。
# 所以不能按关键词远程过滤，必须拉全量列表后在本地按 TITLE 字段正则分类。
# 每个类别 = (标题正则, 要排除的子串)；排除子串可同时匹配 TITLE 或 LONG_TEXT。
CATEGORY_RULES = {
    # 年报：`20XX年度報告`（含空格变体）；排除「企業年度報告書」（工商年报）
    "annual":     (re.compile(r"(20\d{2})\s*年度報告"), "企業年度報告書"),
    # 中报：`20XX中期報告` 是完整报告；「中期業績公告」是摘要简报，信息量少，排除
    "interim":    (re.compile(r"(20\d{2})\s*中期報告"), "中期業績公告"),
    # 招股书：标题「全球發售」；但同日还有一份「正式通告」（379KB 小文件），
    # 其 LONG_TEXT 是「公告及通告 - [正式通告]」，必须筛掉，只留「上市文件 - [發售以供認購]」
    "prospectus": (re.compile(r"全球發售"), "正式通告"),
}

ILLEGAL = re.compile(r'[\\/:*?"<>|\r\n\t]')
HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")


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


def http_get(url, retries=3, timeout=60, headers=None):
    """带 UA + Referer 的 GET，返回 str。失败整份重试。"""
    hdrs = {"User-Agent": UA, "Referer": REFERER}
    if headers:
        hdrs.update(headers)
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return r.read().decode("utf-8", errors="replace")
        except Exception as e:              # noqa: BLE001
            last = e
            time.sleep(2)
    raise RuntimeError("请求失败 %s ：%s" % (url, last))


def http_get_bytes(url, retries=3, timeout=120):
    """带 UA + Referer 的 GET，返回 bytes。分块读 + 整份重试。"""
    hdrs = {"User-Agent": UA, "Referer": REFERER}
    last = None
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=hdrs)
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

def get_stock_id(code):
    """从披露易 prefix.do 反查 stockId。"""
    url = ("%s/search/prefix.do?callback=cb&lang=ZH&type=A&name=%s&market=SEHK"
           % (HKEX, code))
    body = http_get(url)
    m = re.search(r'"stockId":(\d+)', body)
    if not m:
        # 也可能返回多只股票，取第一只
        ids = re.findall(r'"stockId":(\d+)', body)
        if ids:
            return ids[0]
        raise RuntimeError("查不到 %s 的 stockId（检查代码是否正确）" % code)
    return m.group(1)


def search(stock_id, keyword="", from_date="", to_date="", category="0",
           document_type="-1", row_range=200, lang="ZH"):
    """搜披露易公告。坑：result 是二次编码 JSON，要 json.loads 两次。

    注意：`keyword`（即 title 参数）现已失效，传了反而返回 0 条。
    一律传空，拉全量后在本地按 TITLE 分类。
    """
    q = urllib.parse.urlencode({
        "sortDir": "0", "sortByOptions": "DateTime", "category": category,
        "market": "SEHK", "stockId": stock_id, "documentType": document_type,
        "fromDate": from_date, "toDate": to_date,
        "searchType": "1", "t1code": "-2", "t2Gcode": "-2", "t2code": "-2",
        "rowRange": str(row_range), "lang": lang,
    })
    url = "%s/search/titleSearchServlet.do?%s" % (HKEX, q)
    body = http_get(url)
    # 去 callback(...) 包裹（有时是纯 JSON，无包裹）
    m = re.search(r'callback\((.*)\)\s*;?\s*$', body, re.S)
    inner = m.group(1) if m else body
    data = json.loads(inner)
    result = data.get("result")
    if isinstance(result, str):
        result = json.loads(result)          # 二次编码，再解一次
    return result or []


def fetch_all(stock_id, from_date="", to_date="", row_range=500):
    """拉全量公告列表（title 参数失效，只能全量拉取后本地过滤）。"""
    rows = search(stock_id, from_date=from_date, to_date=to_date,
                  row_range=row_range)
    out = []
    for r in rows:
        title = HTML_TAG.sub("", r.get("TITLE", "")).strip()
        link = r.get("FILE_LINK", "")
        if link and not link.startswith("http"):
            link = HKEX + link
        out.append({
            "title": title,
            "long_text": r.get("LONG_TEXT", ""),
            "link": link,
            "date": r.get("DATE_TIME", ""),
            "news_id": str(r.get("NEWS_ID", "")),
        })
    return out


def classify(rows, kind):
    """按本地标题规则给记录分类，返回带 year 的记录列表。

    排除子串同时匹配 TITLE 与 LONG_TEXT（招股书靠 LONG_TEXT 区分
    「上市文件」与「正式通告」小文件）。
    """
    rx, exclude = CATEGORY_RULES[kind]
    kept = []
    for r in rows:
        if exclude and (exclude in r["title"] or exclude in r.get("long_text", "")):
            continue
        m = rx.search(r["title"])
        if not m:
            continue
        year = m.group(1) if m.lastindex else r["date"][:4]
        kept.append(dict(r, kind=kind, year=year))
    return kept


def sort_key(r):
    """DATE_TIME 是 DD/MM/YYYY HH:MM 格式，转 YYYYMMDD 才能正确排序。"""
    d = r["date"][:10]            # DD/MM/YYYY
    if len(d) == 10 and d[2] == "/" and d[5] == "/":
        return d[6:10] + d[3:5] + d[0:2]
    return d


def select_standard(stock_id, years=5, from_date="", to_date=""):
    """按默认套装：近 5 年年报 + 招股书 + 最近 1 期中报。

    坑（2026-09 实测）：日期区间**不能留空**——空日期只返回最近 3 条，
    必须显式给一个够宽的区间才能拉全量。默认往前推 6 年覆盖上市年至今。
    """
    if not from_date or not to_date:
        this_year = time.localtime().tm_year
        from_date = from_date or "%d0101" % (this_year - years - 1)
        to_date = to_date or "%d1231" % (this_year + 1)
    rows = fetch_all(stock_id, from_date, to_date)

    # 年报：按标题年份去重，留最新
    by_year = {}
    for r in classify(rows, "annual"):
        by_year.setdefault(r["year"], r)
    plan = [by_year[y] for y in sorted(by_year, reverse=True)[:years]]

    # 招股书
    plan += classify(rows, "prospectus")

    # 中报（最近 1 期，按发布日排序）
    interims = sorted(classify(rows, "interim"), key=sort_key, reverse=True)
    if interims:
        plan.append(interims[0])

    # 去重（按 link）
    seen, dedup = set(), []
    for p in plan:
        if p["link"] not in seen:
            seen.add(p["link"])
            dedup.append(p)
    return dedup


# ---------------------------------------------------------------- 校验

def check_pdf(path):
    """校验 PDF 头 + 页数（可选 pypdf）。"""
    with open(path, "rb") as f:
        head = f.read(4)
    if head != b"%PDF":
        return False, "非 %PDF 头，可能下载到 HTML 错误页"
    try:
        from pypdf import PdfReader
        n = len(PdfReader(path).pages)
        return True, "PDF 正常，%d 页" % n
    except ImportError:
        return True, "PDF 头正常（未装 pypdf，未校验页数）"
    except Exception as e:                  # noqa: BLE001
        return False, "PDF 解析失败：%s" % e


def safe_name(s):
    s = HTML_TAG.sub("", s)
    s = ILLEGAL.sub("_", s)
    return s.strip() or "unnamed"


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(
        description="港交所披露易财报检索与下载（默认：近5年年报+招股书+最近1期中报）")
    ap.add_argument("code", help="港股 5 位股票代码，如 09633 / 00700 / 09988")
    ap.add_argument("--out", default="hkex_dl", help="下载目录（默认 ./hkex_dl）")
    ap.add_argument("--preset", default="standard", choices=["standard", "none"])
    ap.add_argument("--years", type=int, default=5, help="默认套装取几年年报（默认 5）")
    ap.add_argument("--type", default="", help="手工类别：annual/interim/prospectus，逗号分隔")
    ap.add_argument("--title", default="", help="手工标题关键词（传了即退出默认套装）")
    ap.add_argument("--from", dest="from_date", default="", help="公告起始日期 YYYYMMDD")
    ap.add_argument("--to", dest="to_date", default="", help="公告截止日期 YYYYMMDD")
    ap.add_argument("--list", action="store_true", help="只列不下载")
    ap.add_argument("--json", dest="dump_json", action="store_true")
    ap.add_argument("--overwrite", action="store_true", help="覆盖同名文件")
    ap.add_argument("--check-pdf", dest="check_pdf", action="store_true",
                    help="下载后校验 PDF 头与页数（需 venv python 装 pypdf）")
    ap.add_argument("--log", default=None, help="控制台输出同时写入该文件（UTF-8）")
    args = ap.parse_args()

    if args.log:
        sys.stdout = _Tee(sys.stdout, open(args.log, "w", encoding="utf-8",
                                           errors="replace"))
        sys.stderr = sys.stdout

    code = re.sub(r"\D", "", args.code).zfill(5)
    stock_id = get_stock_id(code)
    print("== 披露易 stockId：%s（代码 %s）==" % (stock_id, code))

    if args.title:
        # 手工标题：仍是全量拉取后本地过滤（title 参数已失效）
        rx = re.compile(re.escape(args.title))
        plan = [dict(r, kind="manual", year=r["date"][:4])
                for r in fetch_all(stock_id, args.from_date, args.to_date)
                if rx.search(r["title"])]
    elif args.type:
        rows = fetch_all(stock_id, args.from_date, args.to_date)
        plan = []
        for t in [x.strip() for x in args.type.split(",") if x.strip()]:
            if t in CATEGORY_RULES:
                plan += classify(rows, t)
            else:
                rx = re.compile(re.escape(t))
                plan += [dict(r, kind=t, year=r["date"][:4])
                         for r in rows if rx.search(r["title"])]
    else:
        plan = select_standard(stock_id, years=args.years,
                               from_date=args.from_date, to_date=args.to_date)

    print("\n== 计划下载 %d 份 ==" % len(plan))
    for p in plan:
        print("   [%s] %s  %s  %s" % (p["kind"], p.get("year", "?"),
                                      p["date"], p["title"]))
    if args.list:
        return 0
    os.makedirs(args.out, exist_ok=True)   # 干跑不要留下空目录

    got = []
    for p in plan:
        title = p["title"]
        fname = "%s_%s_%s_%s.pdf" % (p["kind"], p.get("year", "?"),
                                     p["news_id"], safe_name(title))
        path = os.path.join(args.out, fname)
        if os.path.exists(path) and not args.overwrite:
            print("== 已存在，跳过 %s" % fname)
            got.append(dict(p, file=fname, skipped=True))
            continue
        try:
            raw = http_get_bytes(p["link"])
        except Exception as e:              # noqa: BLE001
            print("!! 下载失败 %s：%s" % (title, e))
            continue
        if not raw.startswith(b"%PDF"):
            print("!! 跳过 %s（非 PDF，可能是 HTML 错误页）" % title)
            continue
        with open(path, "wb") as f:
            f.write(raw)
        note = ""
        if args.check_pdf:
            ok, msg = check_pdf(path)
            note = "  [%s]" % msg
            if not ok:
                note += "（警告：文件可能异常）"
        print("== 下载 %-40s %7.2f MB%s" % (fname, len(raw) / 1048576, note))
        got.append(dict(p, file=fname, bytes=len(raw)))

    if args.dump_json:
        with open(os.path.join(args.out, "_filings.json"), "w",
                  encoding="utf-8") as f:
            json.dump(got, f, ensure_ascii=False, indent=2)

    print("\n== 完成，共 %d 份，输出目录 %s ==" % (len(got), os.path.abspath(args.out)))
    print("提示：PDF 用 <venv-python> extract_pdf_text.py <out> <out> 转文本（需 pymupdf）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
