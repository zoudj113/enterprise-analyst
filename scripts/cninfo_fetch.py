#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
cninfo_fetch.py — A 股公告检索与下载（巨潮资讯网 cninfo.com.cn）

用途：enterprise-analyst 的「外部获取」分支（Step 0 分支 C）。
当本地无 PDF、ima 知识库也没有（或缺最新报告期）时，用它从巨潮官网
直接拉取**一手公告 PDF**，作为后续分析的数据源。

仅用标准库（urllib），managed python 即可运行，无需 venv。

## 默认套装（preset=standard，不传 --type 时的默认行为）

    python cninfo_fetch.py 000807 --out ./_src

一次拉齐一份公司分析所需的全部一手材料：

| 内容           | 数量                                   |
|----------------|----------------------------------------|
| 年报           | **近 5 年**（按标题年份去重，每年 1 份） |
| 招股说明书     | 全部命中（关键词检索，排除摘要）        |
| 最近一期半年报 | 1 份                                   |
| 最近一期一季报 | 1 份                                   |
| 最近一期三季报 | 1 份                                   |

公司上市不足 5 年 / 招股书年代久远未电子化时，有多少取多少，不报错。

## 常用命令

    # 1) 先干跑，看清会下载什么（强烈推荐第一步）
    python cninfo_fetch.py 000807 --list

    # 2) 正式下载
    python cninfo_fetch.py 000807 --out ./_src --json

    # 3) 手工指定类别（走 custom 模式）
    python cninfo_fetch.py 000807 --type annual --per-type 3 --out ./_src

    # 4) 只要近 3 年年报
    python cninfo_fetch.py 000807 --years 3 --out ./_src

    # 5) 限定公告日期区间
    python cninfo_fetch.py 000807 --se-date 2020-01-01~2026-12-31 --out ./_src

## 参数

code                 股票代码（6 位，如 000807 / 600519）
--out                下载目录（默认 ./cninfo_dl）
--preset             standard（默认）/ none。传 --type 时自动切 none
--years              默认套装取几年年报（默认 5）
--type               手工类别，逗号分隔：annual/interim/q1/q3/all
--per-type           手工模式下每类取几份（默认 2）
--se-date            公告日期区间 YYYY-MM-DD~YYYY-MM-DD
--list               只列不下载
--include-summary    包含「摘要」版本（默认排除）
--no-prospectus      默认套装里不拉招股说明书
--json               公告元数据写进 <out>/_announcements.json
--overwrite          覆盖同名文件（默认跳过已存在）

## 输出
- PDF 下载到 <out>/，文件名 = 公告标题（清洗非法字符与 HTML 标签）+ .pdf
- 控制台打印分类清单（PowerShell 不回显时看 --json 落盘）

## 后续
下载的 PDF 用 extract_pdf_text.py 提取文本（**必须用 venv python**，需 pymupdf）：
    <venv-python> extract_pdf_text.py <out> <out>

## 已知坑
- **招股说明书不能用 category 编码**：巨潮对未知 category 会退化成「返回全部公告」
  （实测 category_zsg_szsh 等 8 个候选全部返回 2537 条全量）。必须用 searchkey 检索。
- searchkey 返回的标题带 `<em>` 高亮标签，脚本已清洗。
- announcementTime 是毫秒时间戳。
- 部分老公告是**扫描件（图片型 PDF）**，提取后文本为空 —— 换源或人工处理，
  **严禁凭空编造数字**。
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

BASE = "http://www.cninfo.com.cn"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")

# 定期报告类别 -> 巨潮 category 编码
CATEGORIES = {
    "annual":  ("category_ndbg_szsh", "年报"),
    "interim": ("category_bndbg_szsh", "半年报"),
    "q1":      ("category_yjdbg_szsh", "一季报"),
    "q3":      ("category_sjdbg_szsh", "三季报"),
}

# 招股说明书：无可靠 category，用标题关键词检索
PROSPECTUS_KEYS = ["招股说明书", "招股意向书"]

ILLEGAL = re.compile(r'[\\/:*?"<>|\r\n\t]')
HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
YEAR_IN_TITLE = re.compile(r"(20\d{2})")


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


def _post(path, data, timeout=30):
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(BASE + path, data=body, headers={
        "User-Agent": UA,
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Referer": BASE + "/new/commonUrl?url=disclosure/list/notice",
        "Accept": "*/*",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", "replace")


def get_org(code):
    """股票代码 -> (orgId, 证券代码, 中文简称)。查不到返回 (None, None, None)"""
    try:
        j = json.loads(_post("/new/information/topSearch/query",
                             {"keyWord": code, "maxNum": "10"}))
    except Exception as e:
        print("  [ERR] 查询 orgId 失败: %r" % e)
        return None, None, None
    if not j:
        print("  [ERR] 巨潮未找到代码 %s" % code)
        return None, None, None
    hit = next((x for x in j if str(x.get("code", "")).zfill(6) == code.zfill(6)), j[0])
    return hit.get("orgId"), hit.get("code"), hit.get("zwjc")


def _decorate(anns, label):
    for a in anns:
        a["_label"] = label
        a["announcementTitle"] = clean_title(a.get("announcementTitle"))
        ts = a.get("announcementTime")
        a["_date"] = time.strftime("%Y-%m-%d", time.localtime(ts / 1000)) if ts else ""
    anns.sort(key=lambda a: a.get("announcementTime") or 0, reverse=True)
    return anns


def clean_title(t):
    """去掉 searchkey 高亮的 <em> 等 HTML 标签，压平空白"""
    s = HTML_TAG.sub("", t or "")
    return re.sub(r"\s+", " ", s).strip()


def query_announcements(code, org, cat_key, se_date=""):
    """按 category 检索定期报告"""
    cat, label = CATEGORIES[cat_key]
    data = {
        "pageNum": "1", "pageSize": "50", "column": "szse", "tabName": "fulltext",
        "plate": "", "stock": "%s,%s" % (code, org), "searchkey": "", "secid": "",
        "category": cat, "trade": "", "seDate": se_date or "",
        "sortName": "", "sortType": "", "isHLtitle": "true",
    }
    try:
        j = json.loads(_post("/new/hisAnnouncement/query", data))
    except Exception as e:
        print("  [ERR] %s 查询失败: %r" % (label, e))
        return []
    return _decorate(j.get("announcements") or [], label)


def query_by_keyword(code, org, keyword, se_date=""):
    """按标题关键词检索（category 留空）。用于招股说明书等无固定 category 的公告"""
    data = {
        "pageNum": "1", "pageSize": "30", "column": "szse", "tabName": "fulltext",
        "plate": "", "stock": "%s,%s" % (code, org), "searchkey": keyword, "secid": "",
        "category": "", "trade": "", "seDate": se_date or "",
        "sortName": "", "sortType": "", "isHLtitle": "true",
    }
    try:
        j = json.loads(_post("/new/hisAnnouncement/query", data))
    except Exception as e:
        print("  [ERR] 关键词「%s」查询失败: %r" % (keyword, e))
        return []
    return _decorate(j.get("announcements") or [], "招股说明书")


def drop_summary(anns, include_summary=False):
    if include_summary:
        return anns
    return [a for a in anns if "摘要" not in (a.get("announcementTitle") or "")]


def dedup(anns):
    """按 adjunctUrl 去重，保留首次出现（列表已按时间倒序）"""
    seen, out = set(), []
    for a in anns:
        u = a.get("adjunctUrl") or ""
        if u in seen:
            continue
        seen.add(u)
        out.append(a)
    return out


def pick_by_year(anns, years):
    """年报按标题中的年份分组，同年只留最新一份，取最近 N 个年份"""
    buckets = {}
    for a in anns:
        m = YEAR_IN_TITLE.search(a.get("announcementTitle") or "")
        if not m:
            continue
        y = int(m.group(1))
        if y not in buckets:          # 已按时间倒序，第一个即最新
            buckets[y] = a
    picked = [buckets[y] for y in sorted(buckets.keys(), reverse=True)[:years]]
    return picked


def pick_latest(anns, n=1):
    return anns[:n]


def clean_name(title):
    return ILLEGAL.sub("_", (title or "").strip())[:80]


def download(a, out_dir, overwrite=False):
    url = a.get("adjunctUrl") or ""
    if not url:
        return None, "无 adjunctUrl"
    full = ("http://static.cninfo.com.cn" + url) if url.startswith("/") else (
        url if url.startswith("http") else "http://static.cninfo.com.cn/" + url)

    path = os.path.join(out_dir, clean_name(a.get("announcementTitle", "announcement")) + ".pdf")
    if os.path.exists(path) and not overwrite:
        return path, "skip(已存在)"
    try:
        req = urllib.request.Request(full, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read()
        if not data.startswith(b"%PDF"):
            return None, "非 PDF 内容(%d 字节, 前 8 字节=%r)" % (len(data), data[:8])
        with open(path, "wb") as f:
            f.write(data)
        return path, "OK %d 字节" % len(data)
    except Exception as e:
        return None, "下载失败: %r" % e


def build_standard(code, org, years, se_date, include_summary, want_prospectus):
    """默认套装：近 N 年年报 + 招股说明书 + 最近一期半年报/一季报/三季报"""
    plan, summary = [], []

    anns = drop_summary(query_announcements(code, org, "annual", se_date), include_summary)
    got = pick_by_year(dedup(anns), years)
    plan += got
    summary.append(("年报", len(dedup(anns)), len(got), "近 %d 年（按年份去重）" % years))

    if want_prospectus:
        pros = []
        for kw in PROSPECTUS_KEYS:
            pros += drop_summary(query_by_keyword(code, org, kw, se_date), include_summary)
        pros = dedup(pros)
        plan += pros
        summary.append(("招股说明书/意向书", len(pros), len(pros),
                        "关键词检索，有多少取多少"))

    for key, label in (("interim", "半年报"), ("q1", "一季报"), ("q3", "三季报")):
        lst = drop_summary(query_announcements(code, org, key, se_date), include_summary)
        lst = dedup(lst)
        got = pick_latest(lst, 1)
        plan += got
        summary.append((label, len(lst), len(got), "最近一期"))

    return dedup(plan), summary


def main():
    ap = argparse.ArgumentParser(description="巨潮资讯网公告检索与下载（默认：近5年年报+招股书+最近各期季报）")
    ap.add_argument("code", help="6 位股票代码，如 000807")
    ap.add_argument("--out", default="cninfo_dl", help="下载目录（默认 ./cninfo_dl）")
    ap.add_argument("--preset", default="standard", choices=["standard", "none"],
                    help="standard=默认套装（默认）；none=不套用。传 --type 时自动为 none")
    ap.add_argument("--years", type=int, default=5, help="默认套装取几年年报（默认 5）")
    ap.add_argument("--type", default=None,
                    help="手工类别，逗号分隔：annual/interim/q1/q3/all（传了即退出默认套装）")
    ap.add_argument("--per-type", "--limit", dest="per_type", type=int, default=2,
                    help="手工模式下每类取几份（默认 2）")
    ap.add_argument("--se-date", dest="se_date", default="",
                    help="公告日期区间 YYYY-MM-DD~YYYY-MM-DD")
    ap.add_argument("--list", action="store_true", help="只列公告，不下载")
    ap.add_argument("--include-summary", action="store_true", help="包含「摘要」版本（默认排除）")
    ap.add_argument("--no-prospectus", action="store_true", help="默认套装里不拉招股说明书")
    ap.add_argument("--json", dest="dump_json", action="store_true",
                    help="公告元数据写入 <out>/_announcements.json")
    ap.add_argument("--overwrite", action="store_true", help="覆盖同名文件")
    ap.add_argument("--log", default=None,
                    help="把控制台输出同时写入该文件（UTF-8）。PowerShell 重定向会乱码，用它更稳")
    args = ap.parse_args()

    if args.log:
        sys.stdout = _Tee(sys.stdout, open(args.log, "w", encoding="utf-8", errors="replace"))
        sys.stderr = sys.stdout

    code = re.sub(r"\D", "", args.code).zfill(6)
    print("== 巨潮资讯网检索：%s ==" % code)
    org, real_code, name = get_org(code)
    if not org:
        return 1
    print("  证券：%s %s（orgId=%s）" % (real_code, name, org))

    use_preset = (args.preset == "standard") and not args.type
    picked = []
    if use_preset:
        print("  模式：默认套装（近 %d 年年报 + 招股说明书 + 最近一期半年报/一季报/三季报）"
              % args.years)
        picked, summary = build_standard(
            real_code, org, args.years, args.se_date,
            args.include_summary, not args.no_prospectus)
        print("  " + "-" * 66)
        for label, total, n, rule in summary:
            print("    %-14s 命中 %-4d 取 %-3d  %s" % (label, total, n, rule))
        print("  " + "-" * 66)
    else:
        if args.type and args.type.strip().lower() == "all":
            keys = list(CATEGORIES.keys())
        elif args.type:
            keys = [k.strip().lower() for k in args.type.split(",") if k.strip()]
        else:
            print("[FATAL] --preset none 时必须给 --type")
            return 2
        bad = [k for k in keys if k not in CATEGORIES]
        if bad:
            print("[FATAL] 未知类别 %s，可选：%s" % (bad, "/".join(CATEGORIES)))
            return 2
        for k in keys:
            label = CATEGORIES[k][1]
            lst = dedup(drop_summary(query_announcements(real_code, org, k, args.se_date),
                                     args.include_summary))
            got = lst[:args.per_type]
            print("  %s：命中 %d 份，取 %d 份" % (label, len(lst), len(got)))
            picked += got
        picked = dedup(picked)

    if not picked:
        print("[WARN] 未命中任何公告，检查代码/类别/日期区间")
        return 1

    print("\n  待下载清单：")
    for a in picked:
        print("    [%s] %s  %s" % (a.get("_label", ""), a.get("_date", ""),
                                   a.get("announcementTitle", "")))

    if args.list:
        print("\n（--list 模式，未下载）")
        return 0

    os.makedirs(args.out, exist_ok=True)
    print("\n== 下载到 %s ==" % os.path.abspath(args.out))
    ok = 0
    for a in picked:
        path, msg = download(a, args.out, args.overwrite)
        print("  %-58s %s" % (clean_name(a.get("announcementTitle", ""))[:58], msg))
        if path:
            a["_local"] = path
            ok += 1

    if args.dump_json:
        p = os.path.join(args.out, "_announcements.json")
        slim = [{k: a.get(k) for k in
                 ("announcementTitle", "_date", "_label", "adjunctUrl", "_local")}
                for a in picked]
        with open(p, "w", encoding="utf-8") as f:
            json.dump(slim, f, ensure_ascii=False, indent=2)
        print("\n元数据 -> %s" % p)

    print("\n完成：%d/%d 份已就绪" % (ok, len(picked)))
    if ok:
        print("下一步（**必须用 venv python**，需 pymupdf）：")
        print('  <venv-python> extract_pdf_text.py "%s" "%s"' % (args.out, args.out))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
