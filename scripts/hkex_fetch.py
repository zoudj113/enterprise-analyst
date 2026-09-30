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
6. **中文版 PDF 可能字体损坏，英文版是兜底**（2026-09 地平线机器人 09660 实测）：
   中文版年报可能是未知 CID 字体（无 ToUnicode）→ 中文全乱码、后半页内容流损坏
   （渲染成空白图）、pypdf 报 `Object N not defined`。此时**不要急着搞 OCR 或修字体**，
   加 `--lang EN` 重下英文版即可（同一套报表，数字一一对应，还能反向核对）。
   ⚠️ 中英文标题的**年份位置相反**：中文「2025年年報」年份在前，
   英文「Annual Report 2025」年份在**后**，所以两套分类正则是分开维护的
   （`CATEGORY_RULES_ZH` / `CATEGORY_RULES_EN`）。

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

    # 5) 中文版 PDF 乱码/损坏时，改下英文版（强烈推荐先 --list 看一眼）
    python hkex_fetch.py 09660 --lang EN --list
    python hkex_fetch.py 09660 --lang EN --out ./_src

## 参数

code                 港股 5 位股票代码（如 09633 / 00700 / 09988），自动补零到 5 位
--out                下载目录（默认 ./hkex_dl）
--preset             standard（默认）/ none。传 --title 或 --type 时自动切 none
--years              默认套装取几年年报（默认 5）
--type               手工类别：annual/interim/prospectus，逗号分隔
--title              手工标题关键词（传了即退出默认套装）
--from / --to        公告日期区间 YYYYMMDD
--lang               ZH（默认，中文版）/ EN（英文版，中文版 PDF 损坏时的兜底）
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

# 类别 -> 本地标题分类规则，**按公告语言分组**（--lang ZH / EN）。
# 坑（2026-09 实测）：披露易 titleSearchServlet 的 `title` 参数已**失效**，
# 只要带 title 就返回 recordCnt=0，不带 title 才正常出结果。
# 所以不能按关键词远程过滤，必须拉全量列表后在本地按 TITLE 字段正则分类。
# 每个类别 = (标题正则, 要排除的子串)；排除子串可同时匹配 TITLE 或 LONG_TEXT。
# 排除子串可以是单个 str，也可以是 tuple（任一命中即排除）。
# 正则若带捕获组，第 1 组必须是**年份**（classify 用它填 year 字段）。
CATEGORY_RULES_ZH = {
    # 年报：兼容三种写法 —— `20XX年度報告` / `20XX年年報` / `20XX年報`。
    # 坑 1（2026-09 地平线机器人 09660 实测）：不少新上市公司（尤其 2024 年后 IPO 的）
    # 标题写「2025年年報」，**不含「年度報告」**；旧正则要求「年度報告」紧邻年份，
    # 会整批漏识别（--list 只剩招股书）。故必须把「年」设为可选、并允许重复。
    # 坑 2（2026-09 农夫山泉 09633 实测，**后果最严重**）：中期报告的标题里也会出现
    # 「年度報告」——农夫山泉有「2026中期報告及有關2025年度報告的補充資料」（2026-09-24）。
    # 该标题含「2025年度報告」→ 被 annual 抢走且 year 误判为 2025；又因为年报是**按年份
    # 去重留最新**，它（发布更晚）会把真正的「2025年度報告」（2026-04-17）挤掉，
    # 最终结果是**年报位置挂着一份中期报告、真年报和中报双双丢失**。
    # 故 annual 必须同时排除「企業年度報告書」（工商年报）与「中期報告」。
    "annual":     (re.compile(r"(20\d{2})\s*年[度年]?\s*報(?:告)?"),
                   ("企業年度報告書", "中期報告")),
    # 中报：同样兼容 `20XX中期報告` 与 `20XX年中期報告` 两种写法；
    # 「中期業績公告」是摘要简报（信息量不如完整中期报告），默认排除。
    "interim":    (re.compile(r"(20\d{2})\s*年?\s*中期報告"), "中期業績公告"),
    # 招股书：标题「全球發售」；但同日还有一份「正式通告」（379KB 小文件），
    # 其 LONG_TEXT 是「公告及通告 - [正式通告]」，必须筛掉，只留「上市文件 - [發售以供認購]」
    "prospectus": (re.compile(r"全球發售"), "正式通告"),
}

CATEGORY_RULES_EN = {
    # ⚠️ 英文标题的年份位置**连公司之间都不统一**（2026-09 两家实测）：
    #   地平线 09660：`Annual Report 2025` / `Interim Report 2025`（年份在**后**）
    #   农夫山泉 09633：`2025 Interim Report`（年份在**前**）
    # 所以英文正则一律写成「前或后都能认」的 alternation：
    #   `(?:\S+\s+\S+\D{0,6}(20\d{2})|(20\d{2})\s+\S+\s+\S+)` 的展开形式。
    # 两个分支各带一个捕获组，**只有一个会是非空**——classify() 取第一个非空组
    # 作为年份（见其中 `next((g for g in m.groups() if g), None)`）。
    # `\D{0,6}` 允许 "Report" 与年份之间夹少量非数字（如 "Annual Report 2025"
    # 里的空格），但不会跨过单词去抓别处的年份（实测 `2026 Interim Report and
    # Supplementary Information in relation to the 2025 Annual Report` 不会
    # 被误判成年报 2025，因为它先被下面的排除词挡住）。
    #
    # 英文正则要求 `Annual Report` 连写，因此**不会误伤** `Annual Return`
    # （周年申报表 / 工商年报，非财报）——这是英文侧不需要配工商年报排除词的
    # 原因；`Monthly Return of Equity Issuer...` 同理天然不受影响。
    "annual":     (re.compile(r"(?:Annual\s+Report\D{0,6}(20\d{2})"
                              r"|(20\d{2})\s+Annual\s+Report)", re.I),
                   "Interim Report"),
    # 中报：两种写法都要认（见上）。排除词 "Interim Results" 对应中文的
    # 「中期業績公告」——英文写作 `INTERIM RESULTS ANNOUNCEMENT FOR THE SIX
    # MONTHS ENDED...`，本来就不含 `Interim Report`，此排除是双保险。
    "interim":    (re.compile(r"(?:Interim\s+Report\D{0,6}(20\d{2})"
                              r"|(20\d{2})\s+Interim\s+Report)", re.I),
                   "Interim Results"),
    # 招股书：英文标题是全大写的 `GLOBAL OFFERING`（无年份）。
    # 同日三条同类公告靠 LONG_TEXT 区分：
    #   Listing Documents - [Offer for Subscription]              ← 招股书正本（要）
    #   Announcements and Notices - [Formal Notice]               ← 正式通告（379KB，排除）
    # 实测地平线英文招股书还有一份 .htm 网页版，由 classify() 的非 PDF 过滤挡掉。
    "prospectus": (re.compile(r"Global\s+Offering", re.I), "Formal Notice"),
}

# 兼容旧引用：不传 lang 时一律按中文规则（与修复前行保持一致）。
CATEGORY_RULES = CATEGORY_RULES_ZH
RULES_BY_LANG = {"ZH": CATEGORY_RULES_ZH, "EN": CATEGORY_RULES_EN}

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


def fetch_all(stock_id, from_date="", to_date="", row_range=500, lang="ZH"):
    """拉全量公告列表（title 参数失效，只能全量拉取后本地过滤）。

    `lang` 决定公告**语言**：ZH 中文版（默认）/ EN 英文版。
    英文版是中文版 PDF 损坏时的兜底手段（见文件头「关键差异」第 6 条）。
    """
    rows = search(stock_id, from_date=from_date, to_date=to_date,
                  row_range=row_range, lang=lang)
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


def _ymd(date_str):
    """把披露易 DATE_TIME（**DD/MM/YYYY HH:MM**）解析成 (YYYY, MM, DD)。

    解析不出时返回空串三元组，调用方需容忍。
    ⚠️ 别再用 `date[:4]` 当"年份"——对 DD/MM/YYYY 它会返回 `16/1` 这种
    既不是年份、又含 `/` 的东西（`/` 在路径里是分隔符，会直接搞坏文件名）。
    """
    d = (date_str or "")[:10]
    if len(d) == 10 and d[2] == "/" and d[5] == "/":
        return d[6:10], d[3:5], d[0:2]
    return "", "", ""


def date_year(date_str):
    """取四位年份，供文件名与 year 字段使用。"""
    y, _, _ = _ymd(date_str)
    return y or (date_str or "")[:4]


def _is_excluded(rec, exclude):
    """exclude 命中 TITLE 或 LONG_TEXT 即排除。

    `exclude` 支持 None / 单个 str / tuple（任一命中即排除，见 CATEGORY_RULES_ZH
    里 annual 同时要排「工商年报」与「中期報告」的用例）。

    ⚠️ 匹配**不区分大小写**（2026-09 农夫山泉 09633 实测）：该公司英文标题
    全大写，写成 `2025 ANNUAL REPORT`、`2026 INTERIM REPORT AND SUPPLEMENTARY
    INFORMATION IN RELATION TO THE 2025 ANNUAL REPORT`。若排除词按大小写敏感
    比对，"Interim Report" 就挡不住全大写写法，那份中报会被 annual 抢走。
    """
    if not exclude:
        return False
    pats = (exclude,) if isinstance(exclude, str) else tuple(exclude)
    hay = ("%s %s" % (rec.get("title") or "", rec.get("long_text") or "")).lower()
    return any(p.lower() in hay for p in pats)


def classify(rows, kind, rules=None):
    """按本地标题规则给记录分类，返回带 year 的记录列表。

    排除子串同时匹配 TITLE 与 LONG_TEXT（招股书靠 LONG_TEXT 区分
    「上市文件」与「正式通告」小文件）。

    `rules` 为 None 时用中文规则；传 RULES_BY_LANG["EN"] 则按英文标题分类。
    """
    rx, exclude = (rules or CATEGORY_RULES)[kind]
    kept = []
    for r in rows:
        # 只要 PDF：披露易有的条目是 .htm 网页版（实测地平线英文招股书同日
        # 同时挂了 .htm 与 .pdf 两份）。不在这里挡掉的话，会白下一遍几十 MB
        # 的网页版，再被 main() 的 %PDF 头校验丢弃。
        if not r["link"].lower().split("?")[0].endswith(".pdf"):
            continue
        if _is_excluded(r, exclude):
            continue
        m = rx.search(r["title"])
        if not m:
            continue
        # 正则可能带多个捕获组（英文规则用 alternation 兼容年份在前/在后，
        # 两组里只有一个非空）→ 取第一个非空组；都没有就退回公告日期年份。
        year = None
        if m.lastindex:
            year = next((g for g in m.groups() if g), None)
        year = year or date_year(r["date"])
        kept.append(dict(r, kind=kind, year=year))
    return kept


def sort_key(r):
    """DATE_TIME 是 DD/MM/YYYY HH:MM 格式，转 YYYYMMDD 才能正确排序。"""
    y, mo, d = _ymd(r["date"])
    if y:
        return y + mo + d
    return r["date"]


def select_standard(stock_id, years=5, from_date="", to_date="", lang="ZH"):
    """按默认套装：近 5 年年报 + 招股书 + 最近 1 期中报。

    坑（2026-09 实测）：日期区间**不能留空**——空日期只返回最近 3 条，
    必须显式给一个够宽的区间才能拉全量。默认往前推 6 年覆盖上市年至今。
    """
    rules = RULES_BY_LANG.get(lang, CATEGORY_RULES_ZH)
    if not from_date or not to_date:
        this_year = time.localtime().tm_year
        from_date = from_date or "%d0101" % (this_year - years - 1)
        to_date = to_date or "%d1231" % (this_year + 1)
    rows = fetch_all(stock_id, from_date, to_date, lang=lang)

    # 年报：按标题年份去重，留最新
    by_year = {}
    for r in classify(rows, "annual", rules):
        by_year.setdefault(r["year"], r)
    plan = [by_year[y] for y in sorted(by_year, reverse=True)[:years]]

    # 招股书
    plan += classify(rows, "prospectus", rules)

    # 中报（最近 1 期，按发布日排序）
    interims = sorted(classify(rows, "interim", rules), key=sort_key, reverse=True)
    if interims:
        plan.append(interims[0])

    # 去重（按 link）
    seen, dedup = set(), []
    for p in plan:
        if p["link"] not in seen:
            seen.add(p["link"])
            dedup.append(p)
    return dedup


def warn_if_lang_incomplete(plan, stock_id, years, from_date, to_date):
    """--lang EN 的兜底告警：英文侧一份年报都没搜到、而中文侧有。

    英文接口**不保证**覆盖与中文完全一致——有的公司未单独发布英文版年报，
    也有公司英文标题写法特殊（如全大写 `2025 ANNUAL REPORT`、年份在前的
    `Interim Report`）。「以为拉全了、其实没有」对投研而言比明确报错更危险，
    故在英文侧年报为 0 时自动拉一次中文列表做对照并告警
    （只在异常路径多花一次请求，正常路径零开销）。
    """
    if any(p["kind"] == "annual" for p in plan):
        return
    try:
        zh = select_standard(stock_id, years=years, from_date=from_date,
                             to_date=to_date, lang="ZH")
    except Exception:                        # noqa: BLE001
        return
    n = sum(1 for p in zh if p["kind"] == "annual")
    if n:
        print("\n!! 警告：英文版一份年报都没搜到，而中文版有 %d 份。" % n)
        print("   可能是该公司未单独发布英文年报，也可能只是英文标题写法特殊未被识别。")
        print("   建议：① 优先用 --lang ZH 下载年报；② 若确认存在英文版，")
        print("   用 --title <关键词> 手工检索兜底；③ 英文版仅作「中文版 PDF 损坏」兜底。")


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
    """标题 -> 文件名安全片段。

    空格（英文标题如 `Annual Report 2025` 必有）统一压成下划线，
    避免后续 shell 命令里因路径含空格而反复踩引号问题。
    """
    s = HTML_TAG.sub("", s)
    s = ILLEGAL.sub("_", s)
    s = re.sub(r"\s+", "_", s)
    return s.strip("_") or "unnamed"


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
    ap.add_argument("--lang", default="ZH", choices=["ZH", "EN"],
                    help="公告语言：ZH 中文版（默认）/ EN 英文版（中文版 PDF 字体损坏时的兜底）")
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
    lang = args.lang.upper()
    rules = RULES_BY_LANG.get(lang, CATEGORY_RULES_ZH)
    print("== 披露易 stockId：%s（代码 %s，公告语言 %s）==" % (stock_id, code, lang))

    if args.title:
        # 手工标题：仍是全量拉取后本地过滤（title 参数已失效）
        rx = re.compile(re.escape(args.title))
        plan = [dict(r, kind="manual", year=date_year(r["date"]))
                for r in fetch_all(stock_id, args.from_date, args.to_date, lang=lang)
                if rx.search(r["title"])]
    elif args.type:
        rows = fetch_all(stock_id, args.from_date, args.to_date, lang=lang)
        plan = []
        for t in [x.strip() for x in args.type.split(",") if x.strip()]:
            if t in rules:
                plan += classify(rows, t, rules)
            else:
                rx = re.compile(re.escape(t))
                plan += [dict(r, kind=t, year=date_year(r["date"]))
                         for r in rows if rx.search(r["title"])]
    else:
        plan = select_standard(stock_id, years=args.years,
                               from_date=args.from_date, to_date=args.to_date,
                               lang=lang)

    print("\n== 计划下载 %d 份 ==" % len(plan))
    for p in plan:
        print("   [%s] %s  %s  %s" % (p["kind"], p.get("year", "?"),
                                      p["date"], p["title"]))
    # 英文兜底路径的完整性检查（仅默认套装；手工 --title/--type 不适用）
    if lang == "EN" and not args.title and not args.type:
        warn_if_lang_incomplete(plan, stock_id, args.years,
                                args.from_date, args.to_date)
    if args.list:
        return 0
    os.makedirs(args.out, exist_ok=True)   # 干跑不要留下空目录

    got = []
    for p in plan:
        title = p["title"]
        fname = "%s_%s_%s_%s.pdf" % (p["kind"], p.get("year", "?"),
                                     p["news_id"], safe_name(title))
        # 整名再过一遍 safe_name：kind / year / news_id 是直接拼进来的，
        # 任一含 `/` 或 `\` 都会让 open() 去找一个不存在的子目录并抛
        # FileNotFoundError（2026-09 实测：prospectus 无捕获组时 year 曾取到
        # 日期串 `16/1`，属于同一类事故）。
        fname = safe_name(fname)
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
        # 写盘也放进异常保护：单份失败不该终止整批（后面还有年报/中报要下）。
        try:
            with open(path, "wb") as f:
                f.write(raw)
        except OSError as e:
            print("!! 写入失败 %s：%s" % (fname, e))
            continue
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
