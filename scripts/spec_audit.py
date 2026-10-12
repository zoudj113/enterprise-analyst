# -*- coding: utf-8 -*-
"""
规范符合度审计（enterprise-analyst Step 3.6，交付前必跑）

用途：回答一个 check_report.py **回答不了**的问题——
      「报告是否把 references/ 下每个规范文件要求的产出物都做出来了？」

与 check_report.py 的分工（**两者都必须跑，不可互相替代**）：
    check_report.py   格式 lint    标签闭合 / 表格列数 / 期间排序 / 用词纪律 / 缩写展开 …
                                    它能保证「报告是合法的 HTML 且写法合规」，
                                    **但它匹配的是字符串，不是规范本身**——
                                    一份缺独立估值章、6.1 没做五类压缩的报告同样能全绿。
    spec_audit.py     规范审计    结构完整性与内容覆盖：某个规范文件要求的那张表、
                                    那个小节、那个结论句，是否真的存在于报告里。

用法：
    <python> scripts/spec_audit.py <报告文件.html|报告文件.md> [--log 日志文件] [--strict]

产出：
    ① 逐项检查结果（FAIL / WARN / OK），失败项给出「在哪个规范文件的哪一节 + 怎么补」；
    ② **规范覆盖率表**：references/*.md 每个文件一行，标明本脚本如何校验它；
    ③ 元检查：references/ 下若出现未纳入本审计表的新规范文件 → FAIL（防止规范加了、审计漏了）。

退出码：0 = 无 FAIL（可交付）；1 = 有 FAIL。

维护约定（重要）：
    新增 references/*.md 时，**必须**同时在下方 SPEC_FILES 里登记，并尽量为其加上机器可查的
    检查项（CHECKS）。若只登记不加检查项，会以 WARN「无机器校验路径」暴露出来，
    提醒人工在报告里逐条对照该规范。
"""
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
REFS_DIR = SKILL_DIR / "references"        # 相对脚本定位，跨机器可移植，勿写绝对路径

# ---------------------------------------------------------------------------
# 规范文件登记表：references/*.md → 校验路径
#   auto       由本脚本的 CHECKS 机器校验（spec 字段指向本文件）
#   delegated  由 check_report.py 校验（格式 / 用词层），本脚本不重复
#   alias      与另一个文件的检查项合并校验（如两种股权图方案二选一）
#   index      装载索引入口，本身不产出报告内容
#   manual     无机器校验路径，须人工逐条对照（会以 WARN 暴露）
# ---------------------------------------------------------------------------
SPEC_FILES = {
    "SPEC_INDEX.md":
        ("index", "规范索引台账：Step 0.5 的装载入口，本身不产出报告内容"),
    "pre_write_checklist.md":
        ("delegated", "写作前清单：规则已操作化进 check_report.py 全部检查块，本脚本不重复"),
    "qualitative_discipline.md":
        ("delegated", "定性用词纪律：由 check_report.py [12] 绝对化词 / [13] 出处标注 / [14][15] 术语校验"),
    "html_report_template.md":
        ("delegated", "HTML 骨架与版式：由 check_report.py [0]–[8]、[11]、[16]、[18] 校验"),
    "enterprise_analyst_prompt.md":
        ("auto", "章节骨架完整性：见 GEN-1 / GEN-2"),
    "simple_balance_sheet.md":
        ("auto", "简易合并资产负债表 + 三专项 + 营运资本效率：见 SB-*"),
    "industry_competitive_landscape.md":
        ("auto", "行业地位：自给率 / 成本曲线定位：见 ICL-*"),
    "moat_framework.md":
        ("auto", "护城河前置门槛 / 四问 / 巨资测试：见 MOAT-*"),
    "risk_checklist.md":
        ("auto", "风险清单三层结构 + 10 项必查 + 监测表：见 RISK-*"),
    "forensic_risk_layer.md":
        ("auto", "第 0 层硬伤核验 + 造假红旗结论 + 获现率类取证指标：见 RISK-1 / RISK-5 / RISK-6"),
    "attribution_analysis.md":
        ("auto", "经营变动归因：见 ATTR-*"),
    "product_downstream_map.md":
        ("auto", "产品用途与下游客户映射表：见 PDM-1"),
    "equity_structure_ascii.md":
        ("auto", "股权架构图（ASCII 分支）：见 EQ-1"),
    "equity_structure_mermaid.md":
        ("alias", "股权架构图（Mermaid 分支）：与 ASCII 分支二选一，由 EQ-1 一并校验"),
}

# ---------------------------------------------------------------------------
# 基础工具
# ---------------------------------------------------------------------------
FAILED, WARNED = [], []


def fail(msg):
    FAILED.append(msg)


def warn(msg):
    WARNED.append(msg)


def read_report(path: Path):
    raw = path.read_text(encoding="utf-8", errors="replace")
    is_html = path.suffix.lower() in (".html", ".htm")
    return raw, is_html


ENT = [("&nbsp;", " "), ("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
       ("&quot;", '"'), ("&#39;", "'"), ("&mdash;", "—"), ("&middot;", "·")]


def plain(s: str) -> str:
    """HTML → 纯文本（保留单元格分隔符，便于逐格判断）"""
    s = re.sub(r"<script.*?</script>", " ", s, flags=re.S | re.I)
    s = re.sub(r"<style.*?</style>", " ", s, flags=re.S | re.I)
    s = re.sub(r"</t[hd]>", " | ", s, flags=re.I)
    s = re.sub(r"</tr>", "\n", s, flags=re.I)
    s = re.sub(r"<[^>]+>", " ", s)
    for a, b in ENT:
        s = s.replace(a, b)
    return re.sub(r"[ \t\u00a0]+", " ", s)


def has(text: str, *kws) -> bool:
    """任一关键词命中"""
    return any(k in text for k in kws)


def has_all(text: str, *kws) -> bool:
    return all(k in text for k in kws)


PERIOD_TOK = re.compile(
    r"20\d{2}\s*(?:[-/]\s*\d{1,2}(?:\s*[-/]\s*\d{1,2})?|年(?:\s*\d{1,2}\s*月)?|"
    r"\s*(?:H[12]|上半年|下半年|Q[1-4])|E|年)?"
)


def periods(text: str):
    return PERIOD_TOK.findall(text)


# ---- 标题与章节切分（**层级敏感**）----
# 教训：规范要求的小节（如 6.1 简易合并资产负债表）常是 <h3>，只按 <h2> 切章会
# 让「按标题定位小节」整体失效、并产生假 FAIL。故按 2–4 级统一切块，
# 命中某标题时，其内容 = 到下一个 **同级或更高级** 标题之前的全部（含子小节）。
def _marks(raw: str, is_html: bool):
    """→ [(start, end, level, title)]"""
    if is_html:
        pat = re.compile(r"<h([2-4])[^>]*>(.*?)</h\1\s*>", re.S | re.I)
        return [(m.start(), m.end(), int(m.group(1)), plain(m.group(2)).strip())
                for m in pat.finditer(raw)]
    pat = re.compile(r"^(#{2,4})[ \t]+(.+?)[ \t]*$", re.M)
    return [(m.start(), m.end(), len(m.group(1)), m.group(2).strip())
            for m in pat.finditer(raw)]


def sections(raw: str, is_html: bool, max_level=4):
    """→ [(title, level, text)]，text 含该标题下的全部子小节"""
    marks = [m for m in _marks(raw, is_html) if m[2] <= max_level]
    out = []
    for i, (s, e, lv, title) in enumerate(marks):
        end = len(raw)
        for s2, e2, lv2, _t2 in marks[i + 1:]:
            if lv2 <= lv:
                end = s2
                break
        out.append((title, lv, raw[e:end]))
    return out


def chapters(raw: str, is_html: bool):
    """顶层章节（HTML h2 / MD ##）→ [(title, text)]"""
    return [(t, body) for t, lv, body in sections(raw, is_html, max_level=2)
            if lv == 2]


def chapter(raw, is_html, *kws):
    """按关键词找顶层章节 → (title, text)；找不到返回 ('', '')"""
    for t, body in chapters(raw, is_html):
        if has(t, *kws):
            return t, body
    return "", ""


def headlines(raw: str, is_html: bool):
    """全部标题纯文本（h2–h4），用于「有没有这个标题」类判断"""
    return [m[3] for m in _marks(raw, is_html)]


def sec(raw, is_html, *kws, level=None):
    """按关键词定位小节（含其子小节）→ (title, text)；找不到 ('', '')"""
    for t, lv, body in sections(raw, is_html):
        if (level is None or lv == level) and has(t, *kws):
            return t, body
    return "", ""


def sec_join(raw, is_html, *kws, level=None):
    """命中所有小节（含子小节）的纯文本拼接"""
    return " ".join(plain(body) for t, lv, body in sections(raw, is_html)
                    if (level is None or lv == level) and has(t, *kws))


def headings(raw: str, is_html: bool):
    """兼容别名：全部标题纯文本"""
    return headlines(raw, is_html)


# ---- 表格提取：统一 HTML / Markdown → [[cell, ...], ...] ----
def tables(raw: str, is_html: bool):
    out = []
    if is_html:
        for tb in re.finditer(r"<table.*?</table>", raw, re.S | re.I):
            rows = []
            for tr in re.finditer(r"<tr.*?</tr>", tb.group(0), re.S | re.I):
                cells = [plain(c.group(1)).strip()
                         for c in re.finditer(r"<t[hd][^>]*>(.*?)</t[hd]>", tr.group(0), re.S | re.I)]
                if cells:
                    rows.append(cells)
            if rows:
                out.append(rows)
    else:
        cur = []
        for line in raw.split("\n"):
            if line.strip().startswith("|") and line.strip().endswith("|"):
                cells = [c.strip() for c in line.strip().strip("|").split("|")]
                if set("".join(cells)) <= set("-: "):      # 分隔行
                    continue
                cur.append(cells)
            elif cur:
                out.append(cur)
                cur = []
        if cur:
            out.append(cur)
    return out


def rows_of(tb):
    """数据行（去掉表头行）"""
    return tb[1:] if len(tb) > 1 else []


def numeric_ratio(cells):
    if not cells:
        return 0.0
    n = sum(1 for c in cells if re.search(r"\d", c))
    return n / len(cells)


def find_table(raw, is_html, chap_kws, header_kws, min_rows=1):
    """在指定章节（含子小节）里找表头命中 header_kws、数据行 ≥ min_rows 的表
    → (表, 章节标题)。章节内找不到时退化为全报告搜索，避免因标题措辞不同而假 FAIL。"""
    t, body = sec(raw, is_html, *chap_kws)
    for scope in ([body, raw] if body else [raw]):
        for tb in tables(scope, is_html):
            head = " ".join(tb[0])
            if has(head, *header_kws) and len(rows_of(tb)) >= min_rows:
                return tb, t
    return None, t


def balance_table(raw, is_html):
    """定位「简易合并资产负债表」的左右并排主表（表头含两组期间列）。
    SB-* 一律以**该表的行标签**为判据 —— 不用小节正文的散见用词，
    否则「小节别处提了一句类现金」就能骗过检查（2026-10 故障注入实测暴露）。"""
    _, body = sec(raw, is_html, "简易合并资产负债表", "简易资产负债表")
    for tb in tables(body or raw, is_html):
        head = " ".join(tb[0])
        if has(head, "资产", "负债及权益", "负债和所有者权益") and len(periods(head)) >= 4:
            return tb
    return None


def _labels(tb):
    """表内全部单元格文本（去空白），用于标签类判断"""
    return [c.strip() for r in tb for c in r if c.strip()]


def _missing_labels(tb, kws):
    """返回**未出现**的标签（判据：表内存在以该标签开头的单元格）"""
    return [k for k in kws if not any(c.startswith(k) for c in _labels(tb))]


def sec_text(raw, is_html, *kws):
    """命中关键词的小节（含其全部子小节）纯文本；找不到时回退全文"""
    txt = sec_join(raw, is_html, *kws)
    return txt if txt.strip() else (plain(raw) if is_html else raw)


# ===========================================================================
# 检查项
# ===========================================================================
CHECKS = []


def check(cid, spec, sev, title):
    def deco(fn):
        CHECKS.append(dict(id=cid, spec=spec, sev=sev, title=title, fn=fn))
        return fn
    return deco


# ---------------- 1. 简易合并资产负债表（simple_balance_sheet.md） ----------------
@check("SB-1", "simple_balance_sheet.md", "FAIL", "简易合并资产负债表 · 存在")
def _(raw, is_html):
    hs = headings(raw, is_html)
    hit = [h for h in hs if has(h, "简易合并资产负债表", "简易资产负债表")]
    if not hit:
        return False, "未发现「简易合并资产负债表」小节标题（SKILL.md 第 6 步第 6 项要求必做）", ""
    return True, f"命中小节：{hit[0]}", hit[0]


@check("SB-2", "simple_balance_sheet.md", "FAIL", "资产五类标签（类现金/投资资产/应收款项/经营资产/其他资产）")
def _(raw, is_html):
    tb = balance_table(raw, is_html)
    if tb is None:
        return False, "找不到左右并排的资产负债表主表（见 SB-4）", ""
    need = ["类现金", "投资资产", "应收款项", "经营资产"]
    miss = _missing_labels(tb, need)
    if miss:
        return False, ("主表行标签未做五类压缩，缺：" + "、".join(miss) +
                       "。规范要求把原始科目归并成这五类，**不是逐行列示报表科目**"), ""
    if _missing_labels(tb, ["其他资产"]):
        warn("SB-2 资产五类中「其他资产」行未出现（为 0 时请显式写 0，不要省略）")
    return True, f"主表五类标签齐全（共 {len(rows_of(tb))} 行）", ""


@check("SB-3", "simple_balance_sheet.md", "FAIL", "负债及权益四类标签（有息负债/经营性负债/其他负债/净资产）")
def _(raw, is_html):
    tb = balance_table(raw, is_html)
    if tb is None:
        return False, "找不到左右并排的资产负债表主表（见 SB-4）", ""
    miss = _missing_labels(tb, ["有息负债", "经营性负债", "净资产"])
    if miss:
        return False, "主表行标签缺：" + "、".join(miss), ""
    if _missing_labels(tb, ["其他负债"]):
        warn("SB-3 「其他负债」行未出现（为 0 时请显式写 0）")
    return True, "主表四类标签齐全", ""


@check("SB-4", "simple_balance_sheet.md", "FAIL", "左右并排版式（同一表头含两组期间列）")
def _(raw, is_html):
    _, body = sec(raw, is_html, "简易合并资产负债表", "简易资产负债表")
    if not body:
        return False, "找不到该小节，无法校验版式", ""
    tb = balance_table(raw, is_html)
    if tb is None:
        return False, ("该小节的表格不是「资产 | 左期间列… ‖ 负债及权益 | 右期间列…」的左右并排结构；"
                       "规范要求两侧平账、最新期间在最左"), ""
    return True, f"左右并排（表头含 {len(periods(' '.join(tb[0])))} 个期间 token）", ""


@check("SB-5", "simple_balance_sheet.md", "FAIL", "平账行（资产合计 / 负债及权益合计）")
def _(raw, is_html):
    tb = balance_table(raw, is_html)
    if tb is None:
        return False, "找不到主表，无法校验平账行", ""
    cs = _labels(tb)
    a = any(c.startswith("资产合计") or c.startswith("资产总计") for c in cs)
    b = any(c.startswith(x) for c in cs for x in
            ("负债及权益合计", "负债和所有者权益合计", "负债及股东权益合计", "负债及所有者权益合计"))
    if a and b:
        return True, "主表两侧合计行齐全", ""
    return False, f"主表缺合计行：资产侧={a} 负债权益侧={b}", ""


@check("SB-6", "simple_balance_sheet.md", "WARN", "至少两期对照")
def _(raw, is_html):
    tb = balance_table(raw, is_html)
    n = len(periods(" ".join(tb[0]))) if tb else 0
    if n >= 2:
        return True, f"{n} 个期间 token（≥2 期）", ""
    return False, "未识别到 ≥2 期对照，请确认列了最新一期与上期", ""


@check("SB-7", "simple_balance_sheet.md", "FAIL", "科目归类口径映射表")
def _(raw, is_html):
    hit = [h for h in headlines(raw, is_html) if has(h, "归类", "口径")]
    if hit:
        return True, f"命中小节：{hit[0]}", hit[0]
    return False, ("缺「归类口径映射表」：须逐条说明原始科目 → 五类/四类的归属，"
                   "否则读者无法复核压缩是否失真（规范 simple_balance_sheet.md 必做）"), ""


@check("SB-8", "simple_balance_sheet.md", "FAIL", "应收账款 / 合同负债 / 有息负债三项专项")
def _(raw, is_html):
    hs = headings(raw, is_html)
    miss = [k for k in ("应收账款", "合同负债", "有息负债")
            if not any(k in h and has(h, "专项", "明细", "拆解", "分析") for h in hs)]
    if miss:
        return False, ("缺专项小节：" + "、".join(miss) +
                       "。规范要求三者各做一节（账龄表 / 预收款结构 / 借款构成）"), ""
    return True, "三项专项小节齐全", ""


@check("SB-9", "simple_balance_sheet.md", "FAIL", "营运资本效率（周转天数 / 现金转换周期 / 净现金）")
def _(raw, is_html):
    t = plain(raw) if is_html else raw
    ccc = has(t, "现金转换周期", "CCC")
    days = has(t, "周转天数", "周转率")
    cash = has(t, "净现金")
    if ccc and days and cash:
        return True, "周转天数 + CCC + 净现金齐全", ""
    return False, f"缺项：周转天数={days} CCC={ccc} 净现金={cash}", ""


# ---------------- 2. 行业竞争格局（industry_competitive_landscape.md） ----------------
@check("ICL-1", "industry_competitive_landscape.md", "FAIL", "关键资源自给率")
def _(raw, is_html):
    hs = headings(raw, is_html)
    if any("自给率" in h for h in hs) or "自给率" in plain(raw):
        return True, "有「自给率」小节或指标", ""
    return False, ("缺「关键资源自给率」：须说明原料/耗材自供比例，或用成本占比反证自给程度"
                   "（industry_competitive_landscape.md 必做七段之一）"), ""


@check("ICL-2", "industry_competitive_landscape.md", "FAIL", "单位成本在成本曲线上的定位")
def _(raw, is_html):
    t = plain(raw) if is_html else raw
    if has(t, "成本曲线", "成本结构", "单位成本"):
        return True, "有成本结构 / 成本曲线定位内容", ""
    return False, "缺「单位成本 / 成本曲线定位」：须给定成本结构表或代理指标（能耗、良率、规模）", ""


# ---------------- 3. 护城河（moat_framework.md） ----------------
@check("MOAT-1", "moat_framework.md", "FAIL", "前置门槛（历史 ROE 是否够高）")
def _(raw, is_html):
    t = plain(raw) if is_html else raw
    if ("ROE" in t or "净资产收益率" in t) and has(t, "前置门槛", "门槛", "前置"):
        return True, "有前置门槛结论（ROE 对比）", ""
    return False, ("缺「前置门槛」：护城河章节开头必须先给一句前置结论——近 5 年 ROE 与经营现金流/净利润"
                   "是否达到门槛，否则谈不上护城河（moat_framework.md 硬要求）"), ""


@check("MOAT-2", "moat_framework.md", "FAIL", "唐朝「四问」逐条回答")
def _(raw, is_html):
    t = sec_text(raw, is_html, "护城河")
    if not t:
        t = plain(raw) if is_html else raw
    qs = ["靠什么赚钱", "为什么", "为何", "巨资"]
    hit = sum(1 for q in ("靠什么赚钱", "客户", "资本", "巨资") if q in t)
    if "四问" in t and hit >= 3:
        return True, "四问逐条回答齐全", ""
    return False, ("缺「四问」逐条回答（① 靠什么赚钱 ② 客户为何选它 ③ 为何其他资本没抢 ④ 巨资测试）；"
                   "仅有证据表不算完成四问"), ""


@check("MOAT-3", "moat_framework.md", "FAIL", "巨资测试")
def _(raw, is_html):
    t = plain(raw) if is_html else raw
    if "巨资测试" in t:
        return True, "有巨资测试", ""
    return False, "缺「巨资测试」（给对手足够资金能否攻破）", ""


# ---------------- 4. 风险（risk_checklist.md / forensic_risk_layer.md） ----------------
@check("RISK-1", "forensic_risk_layer.md", "FAIL", "第 0 层硬伤核验（一票否决层）")
def _(raw, is_html):
    t = sec_text(raw, is_html, "风险")
    if not t:
        t = plain(raw) if is_html else raw
    if not has(t, "第 0 层", "第0层", "硬伤"):
        return False, ("风险章缺「第 0 层硬伤核验」：8 项（审计意见 / 关键审计事项 / 审计师变更 / "
                       "控股股东质押 / 监管问询与做空 / 推迟刊发 / 内部人减持 / 离岸主体畸高）"
                       "须逐条留痕，无触发时压缩为一句明确结论"), ""
    keys = ["审计意见", "关键审计事项", "审计师", "核数师", "质押", "问询", "刊发", "减值", "离岸"]
    hit = sum(1 for k in keys if k in t)
    if hit >= 4 or has(t, "均未触发", "无触发", "全部未触发"):
        return True, f"第 0 层已写，命中 {hit} 项线索", ""
    return False, f"第 0 层内容过薄（仅命中 {hit} 项线索），未逐条留痕也未声明「均未触发」", ""


@check("RISK-2", "risk_checklist.md", "FAIL", "企业自身 10 项必查")
def _(raw, is_html):
    t = sec_text(raw, is_html, "风险")
    if not t:
        return False, "找不到风险章节", ""
    keys = {"关联交易": "关联交易", "客户/供应商集中度": "集中度",
            "存贷双高": "存贷双高", "毛利率": "毛利率", "应收账款背离": "应收",
            "商誉减值": "商誉", "非经营利润占比": "非经常", "少数股东分流": "少数股东",
            "业绩骤降": "下滑", "资本配置": "分红"}
    miss = [n for n, k in keys.items() if k not in t]
    if len(miss) > 4:
        return False, f"10 项必查覆盖不足，未见：{'、'.join(miss)}", ""
    if miss:
        warn("RISK-2 未在风险章发现的必查项（若确不适用请在文中写明「不适用」）：" + "、".join(miss))
    return True, f"命中 {len(keys) - len(miss)}/10 项", ""


@check("RISK-3", "risk_checklist.md", "FAIL", "关键数据异常变动监测表（≥10 项量化对照）")
def _(raw, is_html):
    tb, sec = find_table(raw, is_html, ["风险"], ["监测", "异常", "变动", "指标"], min_rows=10)
    if tb and numeric_ratio([c for r in rows_of(tb) for c in r]) >= 0.4:
        return True, f"监测表 {len(rows_of(tb))} 行量化对照（章节：{sec}）", sec
    best = max((len(rows_of(t)) for t in tables(raw, is_html)), default=0)
    return False, (f"未找到表头含「监测/异常/变动/指标」且数据行 ≥10 的量化对照表"
                   f"（全报告最长表为 {best} 行）。规范要求逐项给出多期数字对照"), ""


@check("RISK-4", "risk_checklist.md", "FAIL", "外部环境与治理层面")
def _(raw, is_html):
    t = sec_text(raw, is_html, "风险")
    if has(t, "外部环境", "治理层面", "外部风险", "治理"):
        return True, "有外部环境 / 治理层面小节", ""
    return False, "风险章缺「外部环境与治理层面」小节（三层结构的第三层）", ""


@check("RISK-5", "forensic_risk_layer.md", "FAIL", "章末「是否存在财务造假红旗」明确结论")
def _(raw, is_html):
    t = plain(raw) if is_html else raw
    if not has(t, "造假红旗", "财务造假"):
        return False, "全文无「财务造假红旗」结论句——风险章末尾必须给出明确判断", ""
    if re.search(r"(不存在|未发现|没有|无)[^。；\n]{0,12}(造假红旗|财务造假)", t) or \
       re.search(r"(存在|发现)[^。；\n]{0,12}(造假红旗|财务造假)", t):
        return True, "已给出明确结论", ""
    return False, "提到「造假红旗」但未给出「存在 / 不存在」的明确判断", ""


@check("RISK-6", "forensic_risk_layer.md", "FAIL", "取证指标（核心利润获现率 / 销售收现比）")
def _(raw, is_html):
    t = plain(raw) if is_html else raw
    if has(t, "获现率", "销售收现比", "现金流量肖像"):
        return True, "有获现率 / 收现比类取证指标", ""
    return False, "缺取证指标（核心利润获现率 / 销售收现比），无法判断利润含金量", ""


# ---------------- 5. 估值章 ----------------
@check("VAL-1", "enterprise_analyst_prompt.md", "FAIL", "独立「市场定价与估值」章")
def _(raw, is_html):
    for t, _ in chapters(raw, is_html):
        if has(t, "估值", "市场定价", "定价与估值"):
            return True, f"独立章节：{t}", t
    return False, ("缺独立「市场定价与估值」章。估值不能只散落在总结里——"
                   "须独立成章，含两地价格、市值、PE/PB、股息率、区间、AH 溢价、同业对照"), ""


@check("VAL-2", "enterprise_analyst_prompt.md", "FAIL", "估值章必备读数")
def _(raw, is_html):
    t = sec_text(raw, is_html, "估值", "市场定价")
    if not t:
        return False, "找不到估值章", ""
    need = {"市盈率/PE": ("市盈率", "PE"), "市净率/PB": ("市净率", "PB"),
            "股息率": ("股息率",), "市值": ("市值",), "52 周区间": ("52 周", "52周")}
    miss = [n for n, ks in need.items() if not has(t, *ks)]
    if miss:
        return False, "估值章缺读数：" + "、".join(miss), ""
    return True, "PE / PB / 股息率 / 市值 / 52 周区间齐全", ""


@check("VAL-3", "enterprise_analyst_prompt.md", "FAIL", "A+H 两地价差（AH 溢价）")
def _(raw, is_html):
    t = plain(raw) if is_html else raw
    if not has(t, "H 股", "H股", "港股", ".HK"):
        return True, "非两地上市公司，跳过", ""
    if not has(t, "AH 溢价", "AH溢价", "A/H", "A 股溢价"):
        return False, ("两地上市但未写 AH 溢价：须给出价差计算，并**明确方向**——"
                       "「A 股相对 H 股溢价 X%」与行情页面的负号含义相反，是最易误读处"), ""
    return True, "有 AH 溢价及其方向说明", ""


@check("VAL-4", "enterprise_analyst_prompt.md", "WARN", "同业估值对照")
def _(raw, is_html):
    t = sec_text(raw, is_html, "估值", "市场定价")
    if has(t, "同业", "可比", "行业均值", "竞品"):
        return True, "有同业估值对照", ""
    return False, "估值章缺同业估值对照，读者无法判断贵贱是公司特有还是行业普遍", ""


# ---------------- 6. 其他规范文件 ----------------
@check("PDM-1", "product_downstream_map.md", "FAIL", "产品用途与下游客户映射表")
def _(raw, is_html):
    for tb in tables(raw, is_html):
        head = " ".join(tb[0])
        if has(head, "工业用途", "直接客户", "终端行业", "下游客户"):
            return True, "映射表表头齐全", ""
    return False, "缺产品用途与下游客户映射表（企业概况必备，五要素表头）", ""


@check("EQ-1", "equity_structure_ascii.md", "FAIL", "股权架构图（ASCII 图或 Mermaid）")
def _(raw, is_html):
    t = plain(raw) if is_html else raw
    ascii_box = any(ch in t for ch in "┌└├│─┐┘┤")
    if has(t, "股权架构", "股权结构") and (ascii_box or "mermaid" in raw.lower() or "flowchart" in raw.lower()):
        return True, "有股权架构图", ""
    return False, "缺股权架构图（ASCII Art 或 Mermaid 任一，见 equity_structure_ascii.md）", ""


@check("ATTR-1", "attribution_analysis.md", "WARN", "经营变动归因（±10% 项的四件套）")
def _(raw, is_html):
    t = plain(raw) if is_html else raw
    if has(t, "归因", "四件套", "连环替代", "量价", "拆分"):
        return True, "有归因内容", ""
    return False, "未见经营变动归因（±10% 变动的量价拆分 / 四件套），若本期无超阈值项可忽略", ""


@check("GEN-1", "enterprise_analyst_prompt.md", "WARN", "术语注解表仅收行业专有名词")
def _(raw, is_html):
    hs = headings(raw, is_html)
    if not any(has(h, "术语", "名词解释") for h in hs):
        return True, "无术语表（可接受）", ""
    tb, _ = find_table(raw, is_html, ["术语", "名词解释"], ["术语", "含义", "解释", "说明"], min_rows=1)
    if tb is None:
        return True, "术语以正文段落形式给出", ""
    n = len(rows_of(tb))
    if n > 6:
        return False, (f"术语表 {n} 条，偏多。用户硬规则：术语表只收**行业专有名词**（原料/工艺/产品形态，"
                       f"通常 0–5 条），会计/金融通用词（FVTPL、Non-IFRS、市盈率、合约负债…）"
                       f"一律移出、在正文首现处就地解释"), ""
    return True, f"术语表 {n} 条，符合「仅收行业专有名词」", ""


@check("GEN-2", "enterprise_analyst_prompt.md", "FAIL", "编号章节骨架完整（企业概况→…→总结）")
def _(raw, is_html):
    h2s = [t for t, _ in chapters(raw, is_html)]
    need = {"企业概况": ("概况", "速览", "公司简介"),
            "行业地位与竞争格局": ("行业", "竞争"),
            "股权架构": ("股权",),
            "融资与分红": ("融资", "分红"),
            "核心财务指标": ("财务指标", "财务概要", "财务数据"),
            "资产负债表分析": ("资产负债表", "资产负债"),
            "经营数据分析": ("经营数据", "经营情况", "经营分析"),
            "护城河研判": ("护城河",),
            "风险预警清单": ("风险",),
            "市场定价与估值": ("估值", "市场定价"),
            "总结": ("总结", "结论")}
    miss = [n for n, ks in need.items() if not any(has(t, *ks) for t in h2s)]
    if len(h2s) < 10:
        return False, f"顶层章节仅 {len(h2s)} 个，骨架不完整（SKILL.md 要求 11 个编号章 + 前言速览）", ""
    if len(miss) > 2:
        return False, "缺顶层章节：" + "、".join(miss), ""
    if miss:
        warn("GEN-2 未匹配到顶层章节（命名不同请人工确认）：" + "、".join(miss))
    return True, f"顶层章节 {len(h2s)} 个，骨架齐全", ""


@check("GEN-3", "enterprise_analyst_prompt.md", "FAIL", "现金流量表分析（可并入其他章，但必须有）")
def _(raw, is_html):
    t = plain(raw) if is_html else raw
    need = {"经营现金流": ("经营活动产生的现金流量净额", "经营活动现金流", "经营现金流"),
            "现金流与利润的匹配": ("获现率", "现金流肖像", "现金含量", "净现比")}
    miss = [n for n, ks in need.items() if not has(t, *ks)]
    if miss:
        return False, "缺现金流量维度：" + "、".join(miss), ""
    return True, "经营现金流与利润匹配度分析齐全", ""


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1
    log_path = None
    if "--log" in argv:
        i = argv.index("--log")
        if i + 1 < len(argv):
            log_path = argv[i + 1]
            del argv[i:i + 2]
    argv = [a for a in argv if a != "--strict"]
    if not argv:
        print(__doc__)
        return 1

    path = Path(argv[0])
    if not path.exists():
        print(f"文件不存在: {path}")
        return 1
    raw, is_html = read_report(path)

    import io
    streams = [sys.stdout]
    fh = None
    if log_path:
        fh = open(log_path, "w", encoding="utf-8")
        streams.append(fh)

    class Tee:
        def write(self, s):
            for st in streams:
                try:
                    st.write(s)
                except Exception:
                    pass

        def flush(self):
            for st in streams:
                try:
                    st.flush()
                except Exception:
                    pass

    out = Tee()
    out.write(f"规范符合度审计: {path.name}  ({len(raw):,} 字符, "
              f"{'HTML' if is_html else 'Markdown'})\n")
    out.write("=" * 62 + "\n")

    # 按规范文件分组输出（同一规范的检查项聚在一起，不被别的规范切断）
    order = []
    for c in CHECKS:
        if c["spec"] not in order:
            order.append(c["spec"])
    for spec in order:
        out.write(f"\n规范文件: {spec}\n")
        for c in [x for x in CHECKS if x["spec"] == spec]:
            try:
                ok, msg, where = c["fn"](raw, is_html)
            except Exception as e:                  # 检查项自身出错不应静默
                ok, msg, where = False, f"检查项执行异常: {e}", ""
            tag = "OK  " if ok else ("FAIL" if c["sev"] == "FAIL" else "WARN")
            if not ok:
                (fail if c["sev"] == "FAIL" else warn)(f"[{c['id']}] {c['title']} — {msg}")
            out.write(f"  [{c['id']:<7}] {tag:<4} {c['title']}\n")
            out.write(f"             {msg}\n")

    # ---- 覆盖率表：references/ 下的文件是否都纳入审计 ----
    out.write("\n" + "=" * 62 + "\n规范覆盖率表（references/*.md）\n" + "=" * 62 + "\n")
    if REFS_DIR.is_dir():
        disk = sorted(p.name for p in REFS_DIR.glob("*.md"))
        for name in disk:
            ent = SPEC_FILES.get(name)
            if ent is None:
                fail(f"references/{name} 未登记进 spec_audit.py 的 SPEC_FILES —— "
                     f"规范新增了但审计没跟上，无法保证它被遵守")
                out.write(f"  ✗ {name:<38} 未登记（审计表需更新）\n")
                continue
            kind, desc = ent
            n_chk = sum(1 for c in CHECKS if c["spec"] == name)
            if kind == "auto" and n_chk == 0:
                warn(f"references/{name} 登记为 auto 但无任何检查项")
            mark = {"auto": "机器校验", "delegated": "交由 check_report.py",
                    "alias": "与同类项合并校验", "index": "装载入口（不产出内容）",
                    "manual": "人工对照"}[kind]
            out.write(f"  ✔ {name:<38} {mark:<20} {n_chk} 项\n")
            out.write(f"      {desc}\n")
        extra = [k for k in SPEC_FILES if k not in disk]
        for k in extra:
            warn(f"SPEC_FILES 登记了 references/{k}，但磁盘上不存在该文件")
        out.write(f"\n  合计：磁盘 {len(disk)} 个规范文件 / 登记 {len(SPEC_FILES)} 个 / "
                  f"机器检查项 {len(CHECKS)} 条\n")
    else:
        out.write(f"  （未找到规范目录 {REFS_DIR}，跳过覆盖率检查）\n")

    out.write("\n" + "=" * 62 + "\n")
    if FAILED:
        out.write(f"规范符合度：不通过，{len(FAILED)} 项未达标\n")
        for f in FAILED:
            out.write(f"  - {f}\n")
    else:
        out.write("规范符合度：全部通过 —— 可与 check_report.py 的格式 lint 结果一并交付\n")
    if WARNED:
        out.write(f"\n提示 {len(WARNED)} 项（不阻塞，但建议逐条确认）：\n")
        for w in WARNED:
            out.write(f"  - {w}\n")
    out.write("\n下一步：check_report.py 通过 **且** 本脚本通过，才可进入 Step 3.8 回传与交付。\n")
    out.flush()
    if fh:
        fh.close()
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
