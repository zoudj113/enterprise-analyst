#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
fetch_facts.py — SEC XBRL 多年财务序列抓取（enterprise-analyst 分支 C 美股）

用途：一次拿全「10-K / 20-F 派生」的多年财务序列（利润表 / 现金流 / 资产负债表）。
      这些数据与年报原文同源（都是同一份 10-K 的 XBRL 标签），但结构化，
      比在 5 份年报 .txt 里逐项 Grep 更快、更全、更不易抄错。

定位：**建骨架序列用它，关键数字回年报原文核**。
      与 scripts/extract_series.py 的分工：
        - fetch_facts.py（本脚本）→ 结构化 API，一次拿 10+ 年，适合建完整序列
        - extract_series.py         → 正则在 .txt 里抓，适合校核 / API 未覆盖的口径

用法：
    <python> scripts/fetch_facts.py 1326801
    <python> scripts/fetch_facts.py 1326801 --scale yi --from 2018
    <python> scripts/fetch_facts.py 1737806 --taxonomy us-gaap --form 20-F
    <python> scripts/fetch_facts.py 1326801 --tag Revenues,NetIncomeLoss
    <python> scripts/fetch_facts.py 1326801 --json facts.json --log facts.txt
    <python> scripts/fetch_facts.py 1326801 --no-verify      # 跳过重叠年份交叉验证

输出默认遵守「时间列排序规则」：**最新财年在最左**，可直接粘进报告表格。
末段附「重叠年份交叉验证」：同一期间被多份年报重复披露时自动比对，
不一致 = 重述或口径变更（**必须写进报告**），一致 = 序列可信度有实证支撑。
标准库实现（urllib + json），managed python 即可运行，无需第三方包。

关键坑（均已在实现中规避，勿回退）：
  1. **时点型科目（资产负债表）的 fact 没有 `start` 字段**。
     若统一按「必须有 start 且跨满一年」过滤，资产负债表会**整片抓空**——
     这是 2026-09 美股 Meta 分析时实际踩过的坑。本脚本按 duration / instant 分路处理。
  2. **财年 key 用 `end` 日期年份，不要用 fact 的 `fy` 字段**。
     一份 10-K 会同时披露三年数据（滚动对比），这些 fact 的 `fy` 都标成该 filing 的财年，
     用它当 key 会让三年互相覆盖。用 `end[:4]` 才不会串年。
  3. **非 12 月财年不能硬编码 12-31**（如苹果 9 月结）。年度判定按「期间长度 330–400 天」。
  4. **同一财年会被后续年报重复披露**，须按 `filed` 日期取最新，否则拿到未重述的旧值。
  5. 请求必须带 `User-Agent`，否则 SEC 返 403；SEC 限速约 10 req/s，故默认每标签间隔 0.2s。
  6. **重复披露不要静默抹平——它是免费的重述检测器**（2026-09-22 新增）。
     坑 4 说「取最新值」，但**只取最新、不留旧值 = 把重述悄悄吃掉**：如果公司今年把
     去年的营收改了，旧值被丢弃后报告里只有新值，读者永远看不到这件事。
     正确做法是两者都留：出表用最新值（坑 4），同时把同期间的全部观测交给
     cross_verify() 比对，不一致就报警。**一致本身也是结论**——说明该数字在后续
     年报里被原样重申，序列可信度有独立支撑。
"""
import argparse
import json
import re
import ssl
import sys
import time
import urllib.error
import urllib.request
from datetime import date

# SEC 强制要求：无 UA 一律 403。请改成自己的邮箱，否则可能被限流。
UA = "EnterpriseAnalyst/1.0 (research contact: analyst@example.com)"

CONCEPT = "https://data.sec.gov/api/xbrl/companyconcept/CIK%010d/%s/%s.json"

# 默认套装：(tag, kind, 中文标签, 是否金额科目)
#   kind: "duration" = 期间型（利润表 / 现金流量表，有 start+end）
#         "instant"  = 时点型（资产负债表，只有 end）
DEFAULT_TAGS = [
    # ---- 利润表 ----
    ("Revenues", "duration", "营收", True),
    ("RevenueFromContractWithCustomerExcludingAssessedTax", "duration", "营收（合同口径）", True),
    ("CostOfRevenue", "duration", "营业成本", True),
    ("ResearchAndDevelopmentExpense", "duration", "研发费用", True),
    ("SellingGeneralAndAdministrativeExpense", "duration", "销售及管理费用", True),
    ("SellingAndMarketingExpense", "duration", "销售与市场费用", True),
    ("GeneralAndAdministrativeExpense", "duration", "一般及行政费用", True),
    ("OperatingIncomeLoss", "duration", "经营利润", True),
    ("IncomeTaxExpenseBenefit", "duration", "所得税费用", True),
    ("NetIncomeLoss", "duration", "净利润", True),
    ("EarningsPerShareDiluted", "duration", "稀释每股收益（美元）", False),
    # ---- 现金流量表 ----
    ("NetCashProvidedByUsedInOperatingActivities", "duration", "经营活动现金流", True),
    ("PaymentsToAcquirePropertyPlantAndEquipment", "duration", "购置固定资产", True),
    ("NetCashProvidedByUsedInInvestingActivities", "duration", "投资活动现金流", True),
    ("NetCashProvidedByUsedInFinancingActivities", "duration", "筹资活动现金流", True),
    ("PaymentsForRepurchaseOfCommonStock", "duration", "股份回购", True),
    ("PaymentsOfDividends", "duration", "支付股利", True),
    # ---- 资产负债表（时点型：注意没有 start 字段）----
    ("Assets", "instant", "总资产", True),
    ("Liabilities", "instant", "总负债", True),
    ("StockholdersEquity", "instant", "股东权益", True),
    ("AssetsCurrent", "instant", "流动资产", True),
    ("LiabilitiesCurrent", "instant", "流动负债", True),
    ("CashAndCashEquivalentsAtCarryingValue", "instant", "现金及现金等价物", True),
    ("MarketableSecuritiesCurrent", "instant", "流动有价证券", True),
    ("LongTermDebtNoncurrent", "instant", "长期债务", True),
    ("PropertyPlantAndEquipmentNet", "instant", "固定资产净额", True),
    # 坑 6：Meta 等公司 2019 年起改用「固定资产 + 融资租赁使用权资产」合并标签，
    #       旧的 PropertyPlantAndEquipmentNet 只在早年有值 —— 两个都查才不会断档。
    ("PropertyPlantAndEquipmentAndFinanceLeaseRightOfUseAssetAfterAccumulatedDepreciationAndAmortization",
     "instant", "固定资产及融资租赁使用权资产净额", True),
    ("Goodwill", "instant", "商誉", True),
]

SCALES = {"raw": 1.0, "mn": 1e6, "yi": 1e8}
SCALE_LABEL = {"raw": "美元", "mn": "百万美元", "yi": "亿美元"}


class _Tee(object):
    """同时写多个流（--log：控制台 + UTF-8 文件，绕开 PowerShell 重定向乱码）"""

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


# ---------------------------------------------------------------- 网络

def http_get_bytes(url, retries=3, timeout=60):
    """带 UA 的 GET，返回 bytes。分块读 + 整份重试，规避 IncompleteRead。

    坑：某些网络环境（公司代理 / TLS 中间设备）会在少数连接上抛
    CERTIFICATE_VERIFY_FAILED，重试同一 context 永远失败。因此 SSL 相关异常
    自动降级为「不校验证书」重试一次，不影响数据正确性。
    """
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
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise                      # 标签不存在：上层直接跳过，不重试
            last = e
            print("   ! 第 %d 次失败：%s，2s 后重试" % (i + 1, e))
            time.sleep(2)
        except Exception as e:              # noqa: BLE001
            last = e
            print("   ! 第 %d 次失败：%s，2s 后重试" % (i + 1, e))
            time.sleep(2)
            if isinstance(e, ssl.SSLError) or (
                    isinstance(e, OSError) and "SSL" in str(e)):
                try:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    req = urllib.request.Request(url, headers={"User-Agent": UA})
                    buf = b""
                    with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
                        while True:
                            chunk = r.read(65536)
                            if not chunk:
                                break
                            buf += chunk
                    return buf
                except Exception:           # noqa: BLE001
                    pass
    raise RuntimeError("请求失败 %s ：%s" % (url, last))


def http_get_json(url):
    return json.loads(http_get_bytes(url).decode("utf-8", errors="replace"))


def pick_units(concept_json):
    """companyconcept 返回 {"units": {"USD": [...], "USD/shares": [...]}}。

    EPS 的单位是 USD/shares，其余多为 USD；取第一个非空 unit 兜底。
    """
    units = concept_json.get("units") or {}
    for k in ("USD", "USD/shares"):
        if units.get(k):
            return k, units[k]
    for k, v in units.items():
        if v:
            return k, v
    return None, []


# ---------------------------------------------------------------- 抽取

def collect(facts, kind, fiscal_ends=None, form_re=None):
    """从一个 tag 的 facts 列表里抽「年度值」。

    返回 {财年(int): {"end": 期末日, "val": 数值, "filed": 申报日,
                       "spans": {(start, end): [(filed, val, accn), ...]}}}

    kind="duration" → 需 start+end，且期间长度 330–400 天（兼容非 12 月财年）
    kind="instant"  → **只看 end**（时点型科目没有 start，见文件头坑 1）
    fiscal_ends     → 已知财年期末日集合，用于给 instant 值筛掉季末时点

    出表用的 val/filed 取**最新申报值**（坑 4：同一财年被后续年报重复披露时，
    旧值是未重述前的数）；同时把该期间的全部观测存进 spans —— 同一期间被多份年报
    披露 = 天然的交叉验证点，交给 cross_verify() 比对（坑 7）。
    """
    out = {}
    for f in facts:
        form = f.get("form") or ""
        if form_re and not form_re.match(form):
            continue
        end = f.get("end")
        if not end:
            continue
        start = f.get("start") if kind == "duration" else None

        if kind == "duration":
            if not start:
                continue
            try:
                span = (date.fromisoformat(end) - date.fromisoformat(start)).days
            except ValueError:
                continue
            if not (330 <= span <= 400):
                continue                  # 只保留约一年的期间，滤掉季度 / 半年
        else:
            # 时点型：优先对齐已知财年期末日；没有集合时（自定义标签）退回「财年末时点」
            if fiscal_ends:
                if end not in fiscal_ends:
                    continue
            elif (f.get("fp") or "") != "FY":
                continue

        # 财年 key 用 end 年份：同一 10-K 里的三年对比数据 fy 字段相同，
        # 用它当 key 会互相覆盖（见文件头坑 2）
        fy = int(end[:4])
        filed = f.get("filed") or ""
        rec = out.get(fy)
        if rec is None:
            rec = {"end": end, "val": None, "filed": "", "spans": {}}
            out[fy] = rec
        # 记录该期间的全部观测（同期间被多份年报披露 = 重叠年份 = 交叉验证点）
        rec["spans"].setdefault((start or "", end), []).append(
            (filed, f.get("val"), f.get("accn") or ""))
        # 出表用最新申报值
        if filed > rec["filed"]:
            rec["val"] = f.get("val")
            rec["filed"] = filed
            rec["end"] = end
    return out


def cross_verify(durations, years, scale):
    """重叠年份交叉验证：同一期间被多份年报重复披露 → 比对数值是否一致。

    为什么必须做：一份年报会同时披露前 2–3 年数据，所以每个财年至少在后续两份
    年报里各出现一次 —— 这是**免费的交叉验证点**。两次申报值不同 = 公司做了
    **重述（restatement）**或改了科目口径，是必须写进报告的重大信号。
    本脚本此前「静默取最新值」，会把重述悄悄抹平（见文件头坑 7）。

    返回 (lines, n_periods, conflicts)
      n_periods  可交叉验证的「财年×科目×期间」个数（被 ≥2 份年报披露过）
      conflicts  [(tag, label, year, key, obs, is_money), ...]
    """
    conflicts = []
    n_periods = 0
    for tag, (label, is_money, vals) in durations.items():
        for y in years:
            rec = vals.get(y)
            if not rec:
                continue
            for key, obs in (rec.get("spans") or {}).items():
                seen = [v for _f, v, _a in obs if v is not None]
                if len(seen) < 2:
                    continue
                n_periods += 1
                uniq = []
                for v in seen:
                    if not any(abs(v - u) <= 1e-6 * max(1.0, abs(u)) for u in uniq):
                        uniq.append(v)
                if len(uniq) > 1:
                    conflicts.append((tag, label, y, key, obs, is_money))

    lines = ["## 重叠年份交叉验证（同一期间在不同年报中的重复披露）", ""]
    if n_periods == 0:
        lines.append("> ⚠️ 本次**没有可交叉验证的期间**——可能只拉到单一年报，"
                     "或 `--form` 过滤过严。**这不等于数据没问题，只等于没验到**；"
                     "建议补齐多份年报后重跑。")
        lines.append("")
        return lines, 0, []

    lines.append("可交叉验证区间：**%d 个**「财年 × 科目」（每个都被 ≥2 份年报披露过）" % n_periods)
    lines.append("")
    if not conflicts:
        lines.append("> ✅ **%d 个区间全部一致** —— 无重述迹象（同一数字在后续年报里被原样重申）。" % n_periods)
    else:
        lines.append("> 🔴 **发现 %d 处不一致** —— 同一期间在不同年报里数字不同，"
                     "含义是**重述（restatement）或科目口径变更**，须查明原因后写进报告：" % len(conflicts))
        lines.append("")
        lines.append("| 财年 | 科目 | 期间 | 早期申报 | 后期申报 | 差异 |")
        lines.append("|---|---|---|---|---|---|")
        for tag, label, y, key, obs, is_money in conflicts:
            ordered = sorted([o for o in obs if o[1] is not None], key=lambda o: o[0])
            old, new = ordered[0], ordered[-1]
            diff = new[1] - old[1]
            pct = ("%.2f%%" % (diff / old[1] * 100)) if old[1] else "—"
            lines.append("| %d | %s | %s | %s（%s） | %s（%s） | %s（%s） |" % (
                y, label, key[1],
                fmt(old[1], scale, is_money), old[0],
                fmt(new[1], scale, is_money), new[0],
                fmt(diff, scale, is_money) if is_money else ("%.2f" % diff), pct))
        lines.append("")
        lines.append("> 常见成因：① 会计差错更正（重述）；② 科目重分类（如把某费用并入另一行）；"
                     "③ 并购后追溯调整；④ 财年/合并范围变更。**不要默认最新值就对**——"
                     "回年报原文看公司怎么解释的。")
    lines.append("")
    return lines, n_periods, conflicts


def fmt(v, scale, is_money):
    if v is None:
        return "—"
    if not is_money:
        return "%.2f" % v
    if scale == "raw":
        return "{:,.0f}".format(v)
    return ("{:,.0f}" if scale == "mn" else "{:,.2f}").format(v / SCALES[scale])


def main():
    global UA                      # 必须在任何对 UA 的引用之前声明

    ap = argparse.ArgumentParser(
        description="SEC XBRL 多年财务序列抓取（企业分析技能 · 分支 C 美股）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例：\n"
               "  %(prog)s 1326801 --scale yi --from 2018\n"
               "  %(prog)s 1737806 --form 20-F --tag Revenues,NetIncomeLoss",
    )
    ap.add_argument("cik", help="SEC CIK（可带前导零，如 1326801 / 0001326801）")
    ap.add_argument("--taxonomy", default="us-gaap",
                    help="XBRL 分类标准，默认 us-gaap（IFRS 报表的 FPI 可试 ifrs-full）")
    ap.add_argument("--tag", default=None,
                    help="自定义标签（英文名，逗号分隔），给出后忽略默认套装")
    ap.add_argument("--form", default="10-K,20-F,40-F",
                    help="接受的表单类型，逗号分隔（默认 10-K,20-F,40-F，自动兼容 /A 修订版）")
    ap.add_argument("--from", dest="fy_from", type=int, default=None, help="起始财年（含）")
    ap.add_argument("--to", dest="fy_to", type=int, default=None, help="结束财年（含）")
    ap.add_argument("--scale", choices=["raw", "mn", "yi"], default="mn",
                    help="金额单位：raw=美元 / mn=百万美元（默认）/ yi=亿美元")
    ap.add_argument("--json", dest="json_out", default=None,
                    help="把原始值（未换算）落成 JSON，便于二次加工")
    ap.add_argument("--log", default=None, help="同时把输出写入 UTF-8 文件")
    ap.add_argument("--sleep", type=float, default=0.2,
                    help="每个标签之间的间隔秒数（SEC 限速约 10 req/s），默认 0.2")
    ap.add_argument("--ua", default=UA, help="自定义 User-Agent（建议留真实邮箱）")
    ap.add_argument("--no-verify", action="store_true",
                    help="跳过「重叠年份交叉验证」（默认执行；验证本身不额外发请求）")
    args = ap.parse_args()

    UA = args.ua

    if args.log:
        sys.stdout = _Tee(sys.stdout, open(args.log, "w", encoding="utf-8", errors="replace"))
        sys.stderr = sys.stdout

    cik = re.sub(r"\D", "", args.cik) or "0"
    cik = cik.lstrip("0") or "0"
    form_re = re.compile(
        r"^(?:" + "|".join(re.escape(s.strip()) + r"(?:/A)?" for s in args.form.split(",")
                           if s.strip()) + r")$")

    if args.tag:
        want = [t.strip() for t in args.tag.split(",") if t.strip()]
        known = {t[0]: t for t in DEFAULT_TAGS}
        tags = []
        for t in want:
            if t in known:
                tags.append(known[t])
            else:
                # 类型未知：标 auto，运行期先试期间型，无值再按时点型解析
                tags.append((t, "auto", t, True))
    else:
        tags = DEFAULT_TAGS

    print("== SEC XBRL 年度序列：CIK %s（%s）==" % (cik, args.taxonomy))
    print("   表单：%s   单位：%s   标签：%d 个\n" % (args.form, SCALE_LABEL[args.scale], len(tags)))

    # ---- 第一步：逐个拉取 ----
    raw, entity = {}, None
    for tag, kind, label, is_money in tags:
        url = CONCEPT % (int(cik), args.taxonomy, tag)
        try:
            j = http_get_json(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue                  # 该公司不用这个标签，正常跳过
            print("   ! %s 抓取失败：%s" % (tag, e))
            continue
        except Exception as e:              # noqa: BLE001
            print("   ! %s 抓取失败：%s" % (tag, e))
            continue
        if entity is None:
            entity = j.get("entityName")
        unit_key, facts = pick_units(j)
        if not facts:
            continue
        raw[tag] = (kind, label, is_money, facts, unit_key)
        print("   + %-22s %-14s %d 条 fact" % (tag, label, len(facts)))
        time.sleep(args.sleep)

    if not raw:
        print("\n!! 未取到任何数据。检查 CIK / 表单类型 / taxonomy 是否正确。")
        return 1

    print("\n== 实体：%s ==" % (entity or "(未知)"))

    # ---- 第二步：先处理期间型，收集财年期末日 ----
    durations, instants, kind_of = {}, {}, {}
    fiscal_ends = set()
    deferred = []
    for tag, (kind, label, is_money, facts, unit_key) in raw.items():
        if kind == "auto":
            vals = collect(facts, "duration", form_re=form_re)
            if vals:
                durations[tag] = (label, is_money, vals)
                kind_of[tag] = "duration"
                fiscal_ends |= {v["end"] for v in vals.values()}
            else:
                deferred.append((tag, label, is_money, facts))
            continue
        vals = collect(facts, kind, form_re=form_re)
        if kind == "duration":
            durations[tag] = (label, is_money, vals)
            kind_of[tag] = "duration"
            fiscal_ends |= {v["end"] for v in vals.values()}
        else:
            instants[tag] = (kind, label, is_money, facts, unit_key)

    # 自定义标签若期间型解析不出年度值，按「时点型」再试一次
    for tag, label, is_money, facts in deferred:
        instants[tag] = ("instant", label, is_money, facts, None)

    # ---- 第三步：时点型按财年期末日过滤（坑 1：它没有 start 字段）----
    for tag, (kind, label, is_money, facts, unit_key) in instants.items():
        vals = collect(facts, "instant", fiscal_ends=fiscal_ends, form_re=form_re)
        durations[tag] = (label, is_money, vals)
        kind_of[tag] = "instant"

    # ---- 第四步：汇总财年范围、输出 ----
    years = set()
    for _label, _is_money, vals in durations.values():
        years |= {y for y in vals if (args.fy_from is None or y >= args.fy_from)
                  and (args.fy_to is None or y <= args.fy_to)}
    if not years:
        print("\n!! 过滤后无数据（检查 --from / --to 是否写反）。")
        return 1
    years = sorted(years, reverse=True)          # 最新财年在最左（强制规则）

    print("财年范围：%d–%d（%d 年）\n" % (min(years), max(years), len(years)))

    groups = [("利润表 / 现金流量表（期间型）",
               [t for t in durations if kind_of.get(t) == "duration"]),
              ("资产负债表（时点型，取财年末）",
               [t for t in durations if kind_of.get(t) == "instant"])]

    out_lines = []
    for gname, gt in groups:
        rows = [t for t in gt if any(
            y in durations[t][2] and durations[t][2][y]["val"] is not None
            for y in years)]
        if not rows:
            continue
        out_lines.append("### %s" % gname)
        out_lines.append("")
        out_lines.append("| 科目 | " + " | ".join(str(y) for y in years) + " |")
        out_lines.append("|---" * (len(years) + 1) + "|")
        for t in rows:
            label, is_money, vals = durations[t]
            cells = []
            for y in years:
                rec = vals.get(y)
                cells.append(fmt(rec["val"], args.scale, is_money) if rec else "—")
            out_lines.append("| %s | %s |" % (label, " | ".join(cells)))
        out_lines.append("")
        out_lines.append("> 单位：%s。数据来源：SEC XBRL companyconcept（与同一份 10-K 原文同源），"
                         "按财年期末日归档、同一财年取最新申报值。" % SCALE_LABEL[args.scale])
        out_lines.append("")

    print("\n".join(out_lines))

    # ---- 第四步 b：重叠年份交叉验证（坑 6：重复披露是免费的重述检测器）----
    verify_exit = 0
    if not args.no_verify:
        vlines, n_periods, conflicts = cross_verify(durations, years, args.scale)
        print("\n".join(vlines))
        if conflicts:
            verify_exit = 2                 # 有重述/口径变更：调用方须注意（非致命）

    # ---- 第五步：JSON 落盘（保留原始美元值）----
    if args.json_out:
        payload = {"cik": cik, "entity": entity, "taxonomy": args.taxonomy,
                   "form": args.form, "series": {}}
        for t, (label, is_money, vals) in durations.items():
            payload["series"][t] = {
                "label": label, "is_money": is_money,
                "kind": kind_of.get(t, "duration"),
                "values": {str(y): vals[y]["val"] for y in sorted(vals)
                           if (args.fy_from is None or y >= args.fy_from)
                           and (args.fy_to is None or y <= args.fy_to)},
                "period_end": {str(y): vals[y]["end"] for y in sorted(vals)
                               if (args.fy_from is None or y >= args.fy_from)
                               and (args.fy_to is None or y <= args.fy_to)},
            }
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=2)
        print("原始值已写入 JSON：%s" % args.json_out)

    print("说明：表中 `—` 表示该财年**该标签未在 XBRL 中出现**——可能是「真为 0」、"
          "「当年未使用此标签」或「公司改了科目名」，**不等于金额为零**，引用前须回年报原文确认。")
    print("提示：本脚本用于**建骨架序列**；报告中出现的每个关键数字仍须回年报原文核对。")
    if verify_exit:
        print("⚠️ 退出码 2（非致命）：重叠年份交叉验证发现不一致（重述 / 口径变更）——"
              "数据已正常输出，但须查明原因并写进报告。")
    return verify_exit


if __name__ == "__main__":
    sys.exit(main())
