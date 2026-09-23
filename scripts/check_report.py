# -*- coding: utf-8 -*-
"""
企业分析报告交付前自检（enterprise-analyst Step 3.5）

用法：
    python scripts/check_report.py <报告文件.html|报告文件.md> [--log 日志文件]

检查项（18 项，脚本内编号 [0]–[15]）：
    [0]    文件命名规范（{公司}_分析报告_{YYYYMMDD}.html）
    [1]    HTML 标签闭合
    [2]    表格列数一致性（表头 vs 各数据行）
           ⚠ 统计的是 <td> 标签个数、**不展开 colspan**，因此汇总行禁用 colspan；
             rowspan 已被正确补占位，可放心用。
    [2b]   数值列表头对齐（数值列 ⊇50% 带 num-c 时，表头 <th> 也必须带 num-c）
    [3]    canvas 与 Chart.js 注册配对（双向，含 aria-label）
    [4]    时间列排序规则（最新期间必须在最左；预测年也算期间）
    [5]    必备章节（**字面匹配**，如「结论」不算「总结」）
    [6]    数据来源 / 免责声明
    [7]    第 0 层硬伤核验痕迹（须写明审计意见，不得凭印象）
    [8]    常驻侧边目录（sticky TOC + 锚点配对 + 回到顶部锚点）
    [9]    产品用途与客户映射表（企业概况必备）
    [10]   行业地位与竞争格局（独立章节 + 至少命中 3 项信号）
    [10.5] 护城河四问与证据链（证据表 / 巨资测试 / 章末明确结论）
    [11]   反空值检查（num-c 单元格不得留空占位符）
    [12]   绝对化词扫描 —— 硬档（不可复制/完美/必然…）出现即 FAIL；
           软档（唯一/垄断/第一/领先…）同行内无数字且无出处标记则 WARN
    [13]   定性结论出处标注 —— 【源】/【推】/【判】合计须 ≥3 处；
           另附加提示护城河结论句附近是否有依据（WARN，不阻塞）
           [12][13] 规则详见 references/qualitative_discipline.md（2026-09-22 新增）
    [14]   高风险术语首现自解释 —— 【读者假设：第一次接触这家公司，且未必懂会计】
           Level 1/2/3、VIE、KAM、商誉、股份支付… 等术语出现时，首现处必须有中文解释，
           或全文存在「术语注解/名词解释」区块且该术语在区块内被定义。缺则 FAIL。
    [15]   英文缩写首现展开（提示级，不阻塞）—— 自动抽取全文 2–6 位大写缩写，
           首现处既无中文括注也无「英文全称（缩写）」形式的，列为提示。
           [14][15] 规则详见 references/qualitative_discipline.md 第八节（2026-09-23 新增）

退出码：0 = 全部通过；1 = 有 FAIL。

配套「报告写作前清单」见 references/pre_write_checklist.md —— **动笔前过一遍**，
让本自检一次通过，避免写完返工（2026-09-22 美股 Meta 报告首轮 19 项 FAIL、返工三轮的教训）。
"""
import re
import sys
from datetime import date
from pathlib import Path

# ---- 期间解析：把 "2026H1" / "2025" / "2024-12-31" / "2026/6/30" 转可比较 key ----
def period_key(tok: str):
    tok = tok.strip()
    m = re.match(r'^(20\d{2})\s*[-/]?\s*(\d{1,2})?\s*[-/]?\s*(\d{1,2})?$', tok)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2) or 0), int(m.group(3) or 0)
        return (y, mo, d, 1)          # 具体日期
    m = re.match(r'^(20\d{2})\s*(H[12]|上半年|下半年)$', tok)
    if m:
        y, half = int(m.group(1)), m.group(2)
        return (y, 6 if half in ('H1', '上半年') else 12, 0, 2)   # 半年 > 全年
    m = re.match(r'^(20\d{2})\s*[年]?$', tok)
    if m:
        return (int(m.group(1)), 0, 0, 0)                          # 全年
    m = re.match(r'^(20\d{2})E$', tok)
    if m:
        return (int(m.group(1)), 0, 0, 3)                          # 预测年
    return None

# 表头里常混有非期间 token（如"同比""说明"），只抽取可识别的期间
PERIOD_RE = re.compile(r'20\d{2}(?:\s*[-/]\s*\d{1,2}(?:\s*[-/]\s*\d{1,2})?|\s*(?:H[12]|年上半年|下半年|年|E))?')

FAILED = []

def fail(msg):
    FAILED.append(msg)

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


def main():
    argv = sys.argv[1:]
    if not argv:
        print(__doc__)
        return 1

    # --log <file>：输出同时写入 UTF-8 文件（PowerShell 重定向中文会乱码）
    log_path = None
    if "--log" in argv:
        i = argv.index("--log")
        if i + 1 < len(argv):
            log_path = argv[i + 1]
            del argv[i:i + 2]
    if not argv:
        print(__doc__)
        return 1
    if log_path:
        sys.stdout = _Tee(sys.stdout, open(log_path, "w", encoding="utf-8", errors="replace"))
        sys.stderr = sys.stdout

    path = Path(argv[0])
    if not path.exists():
        print(f"文件不存在: {path}")
        return 1
    html = path.read_text(encoding='utf-8')
    is_html = path.suffix.lower() == '.html'
    print(f"检查: {path.name}  ({len(html):,} 字符, {'HTML' if is_html else 'Markdown'})\n")

    # ---------- 0. 文件命名规范 ----------
    print("[0] 文件命名规范")
    NAME_RE = re.compile(r'^(.+?)_分析报告_(\d{8})(?:_v(\d+))?\.(html|md)$')
    nm = NAME_RE.match(path.name)
    if not nm:
        fail(f"文件名不符合规范，应为 {{公司简称}}_分析报告_{{YYYYMMDD}}.html ，实际为 {path.name}")
        print(f"    FAIL {path.name}")
    else:
        ext_ok = (path.suffix.lower().lstrip('.') == nm.group(4))
        today = date.today().strftime('%Y%m%d')
        if not ext_ok:
            fail(f"文件扩展名与命名不一致: {path.name}")
            print(f"    FAIL 扩展名不一致")
        print(f"    OK 公司={nm.group(1)} 日期={nm.group(2)} 版本={nm.group(3) or '1'} 格式={nm.group(4)}")
        if nm.group(2) != today:
            print(f"    注意 文件名日期 {nm.group(2)} 与今天 {today} 不同（若是重生成旧报告可忽略）")
        if path.suffix.lower() == '.md':
            print("    注意 Markdown 为可选格式，默认应输出 HTML")

    if is_html:
        print("[1] HTML 标签闭合")
        tags = ['table','thead','tbody','tfoot','tr','th','td','div','script',
                'h2','h3','h4','footer','nav','canvas','aside']
        for t in tags:
            o = len(re.findall(r'<' + t + r'[\s>]', html))
            c = len(re.findall(r'</' + t + r'>', html))
            if o != c:
                fail(f"<{t}> 标签不闭合: open={o} close={c}")
                print(f"    FAIL <{t}>: open={o} close={c}")
        print(f"    OK 检查了 {len(tags)} 类标签")

    # ---------- 2. 表格列数一致性 ----------
    print("\n[2] 表格列数一致性")
    if is_html:
        tables = re.findall(r'<table>([\s\S]*?)</table>', html)
    else:
        blocks, cur = [], []
        for ln in html.splitlines():
            if ln.strip().startswith('|'):
                cur.append(ln)
            elif cur:
                blocks.append('\n'.join(cur)); cur = []
        if cur: blocks.append('\n'.join(cur))
        tables = blocks

    def cells(row: str):
        if is_html:
            return len(re.findall(r'<t[dh][\s>]', row))
        return len([c for c in row.strip().strip('|').split('|')])

    def row_layout(rows):
        """逐行返回 [(col, attrs)]，正确处理 rowspan / colspan 的跨行跨列占位。

        行内被上方 rowspan 占据的列会补一个占位单元，因此返回列表的长度即该行的
        「视觉列数」——用于列数一致性检查，避免把合法的 rowspan 误判为列数缺失。
        """
        pending = {}          # col -> (剩余占据行数, attrs)
        out = []
        for r in rows:
            occ = {c: a for c, (rem, a) in pending.items() if rem > 0}
            placed = [(c, a) for c, a in sorted(occ.items())]
            nxt = {c: (rem - 1, a) for c, (rem, a) in pending.items() if rem - 1 > 0}
            col = 0
            for cm in re.finditer(r'<td([^>]*)>', r):
                attrs = cm.group(1)
                while col in occ:
                    col += 1
                rm_ = re.search(r'rowspan\s*=\s*"(\d+)"', attrs)
                sm_ = re.search(r'colspan\s*=\s*"(\d+)"', attrs)
                rs = int(rm_.group(1)) if rm_ else 1
                cs = int(sm_.group(1)) if sm_ else 1
                placed.append((col, attrs))
                if rs > 1:
                    for k in range(cs):
                        nxt[col + k] = (rs - 1, attrs)
                col += cs
            pending = nxt
            out.append(placed)
        return out

    def body_rows(tb):
        """取表格正文行（排除含 <th> 的表头行）。"""
        return [r for r in re.findall(r'<tr[^>]*>([\s\S]*?)</tr>', tb)
                if not re.search(r'<th[\s>]', r)]

    print(f"    共 {len(tables)} 张表")
    for i, tb in enumerate(tables, 1):
        if is_html:
            head_m = re.search(r'<thead>[\s\S]*?</thead>', tb)
            if not head_m:
                continue
            head_n = len(re.findall(r'<th[\s>]', head_m.group(0)))
            rows = body_rows(tb)
            layout = row_layout(rows)
            bad = [len(pl) for pl in layout if len(pl) and len(pl) != head_n]
        else:
            lines = [l for l in tb.splitlines() if l.strip().startswith('|')]
            if len(lines) < 2:
                continue
            head_n = cells(lines[0])
            rows = lines[2:]  # 跳过表头 + 分隔行
            bad = []
            for r in rows:
                n = cells(r)
                if n and n != head_n:
                    bad.append(n)
        if bad:
            fail(f"表 #{i} 列数不一致: 表头 {head_n} 列，异常行 {sorted(set(bad))}")
            print(f"    FAIL 表 #{i}: 表头 {head_n} 列，异常 {bad}")

    # ---------- 2b. 数值列表头对齐 ----------
    # 数值列（td 带 num-c 占比 ≥50%）的 <th> 也必须带 num-c，
    # 否则表头左对齐 + 数据右对齐，视觉上既不居中也不对齐。
    print("\n[2b] 数值列表头对齐")
    aligned_bad = 0
    if is_html:
        for i, tb in enumerate(tables, 1):
            thead_m = re.search(r'<thead>([\s\S]*?)</thead>', tb)
            if not thead_m:
                continue
            th_flags = []
            for thm in re.finditer(r'<th([^>]*)>([\s\S]*?)</th>', thead_m.group(1)):
                attrs = thm.group(1)
                span = 1
                sm = re.search(r'colspan\s*=\s*"(\d+)"', attrs)
                if sm:
                    span = int(sm.group(1))
                th_flags.extend(['num-c' in attrs] * span)
            counts = {}
            for placed in row_layout(body_rows(tb)):
                for col, attrs in placed:
                    slot = counts.setdefault(col, [0, 0])
                    slot[0] += 1
                    if 'num-c' in attrs:
                        slot[1] += 1
            for col, (total, num) in counts.items():
                if total and num / total >= 0.5 and col < len(th_flags) and not th_flags[col]:
                    aligned_bad += 1
                    fail(f"表 #{i} 第 {col + 1} 列为数值列，但表头 <th> 缺 num-c（与右对齐数据错位）")
        if aligned_bad:
            print(f"    FAIL {aligned_bad} 个数值列表头未右对齐")
        else:
            print(f"    OK 全部数值列表头与数据对齐")

    # ---------- 3. canvas 注册 ----------
    if is_html:
        print("\n[3] canvas 与图表注册")
        canvases = re.findall(r'<canvas id="([^"]+)"', html)
        registered = re.findall(r"getElementById\('([^']+)'\)", html)
        missing = [c for c in canvases if c not in registered]
        orphan = [r for r in registered if r not in canvases]
        if missing:
            fail(f"canvas 未注册: {missing}")
        if orphan:
            fail(f"注册了不存在的 canvas: {orphan}")
        print(f"    canvas {len(canvases)} 个, 注册 {len(registered)} 个 -> {'OK' if not (missing or orphan) else 'FAIL'}")

        # aria-label 可访问性
        no_aria = [c for c, blk in
                   ((c, re.search(r'<canvas id="' + re.escape(c) + r'"([^>]*)>', html)) for c in canvases)
                   if blk and 'aria-label' not in blk.group(1)]
        if no_aria:
            fail(f"canvas 缺 aria-label: {no_aria}")
            print(f"    FAIL 缺 aria-label: {no_aria}")

    # ---------- 4. 时间列排序规则 ----------
    print("\n[4] 时间列排序规则（最新期间必须在最左）")
    checked = 0
    if is_html:
        rows_iter = re.findall(r'<thead>[\s\S]*?</thead>', html)
    else:
        rows_iter = [l for l in html.splitlines()
                     if l.strip().startswith('|') and '---' not in l][:1]
        rows_iter = []

    def header_tokens(h):
        if is_html:
            items = re.findall(r'<th[^>]*>([\s\S]*?)</th>', h)
        else:
            items = [c for c in h.strip().strip('|').split('|')]
        out = []
        for it in items:
            txt = re.sub(r'<[^>]*>', '', it).strip()
            m = PERIOD_RE.search(txt)
            if m:
                out.append(m.group(0).strip().replace(' ', ''))
        return out

    headers = rows_iter if is_html else []
    for h in headers:
        keys = [(t, period_key(t)) for t in header_tokens(h)]
        keys = [(t, k) for t, k in keys if k]
        if len(keys) < 2:
            continue
        # 区分两种表头形态：
        #   ① 单一期间序列（无重复期间）→ 必须整体严格降序
        #   ② 多指标组并列 / 左右双栏（存在重复期间）→ 按"出现重复"分段，逐段校验降序
        keys_seq = [k for _, k in keys]
        has_dup = len(set(keys_seq)) != len(keys_seq)
        if has_dup:
            segments, cur = [], []
            for t, k in keys:
                if cur and k >= cur[-1][1]:
                    segments.append(cur); cur = []
                cur.append((t, k))
            if cur:
                segments.append(cur)
        else:
            segments = [keys]
        checked += 1
        for seg in segments:
            if len(seg) < 2:
                continue
            seq = [k for _, k in seg]
            desc = all(seq[i] >= seq[i + 1] for i in range(len(seq) - 1))
            if not desc:
                fail(f"时间列未按「最新在最左」排列: {[t for t, _ in seg]}")
                print(f"    FAIL {' > '.join(t for t, _ in seg)}")
                break
    if FAILED and any('时间列' in f for f in FAILED):
        pass
    timed_fail = any('时间列' in f for f in FAILED)
    print(f"    检查了 {checked} 张含期间表头的表格 -> {'FAIL' if timed_fail else 'OK'}")

    # 图表 X 轴方向
    if is_html:
        for lm in re.finditer(r"labels\s*:\s*\[([^\]]*)\]", html):
            raw = lm.group(1)
            items = re.findall(r"'([^']+)'|\"([^\"]+)\"", raw)
            items = [a or b for a, b in items]
            ks = [(t, period_key(t)) for t in items]
            ks = [(t, k) for t, k in ks if k]
            if len(ks) >= 3:
                seq = [k for _, k in ks]
                desc = all(seq[i] >= seq[i + 1] for i in range(len(seq) - 1))
                asc = all(seq[i] <= seq[i + 1] for i in range(len(seq) - 1))
                if not desc and asc:
                    print(f"    注意 chart labels 为升序: {[t for t, _ in ks]} "
                          f"（若是瀑布图属豁免，否则应翻转）")

    # ---------- 5. 必备章节 ----------
    print("\n[5] 必备章节")
    required = {
        '企业概况': ['企业概况'],
        '股权架构': ['股权架构', '股权结构'],
        '融资与分红': ['融资', '分红'],
        '核心财务指标': ['核心财务指标', '财务概要'],
        '资产负债表分析': ['资产负债表', '简易合并资产负债表'],
        '经营数据分析': ['经营数据分析', '经营情况'],
        '护城河': ['护城河'],
        '风险预警': ['风险预警', '风险扫描'],
        '总结': ['总结'],
    }
    for name, kws in required.items():
        hit = any(k in html for k in kws)
        if not hit:
            fail(f"缺少章节: {name}")
        print(f"    {'OK ' if hit else 'FAIL'} {name}")

    # ---------- 6. 数据来源与免责 ----------
    print("\n[6] 数据来源 / 免责声明")
    has_src = bool(re.search(r'数据来源|资料来源', html))
    has_disc = bool(re.search(r'免责声明|不构成.{0,6}投资建议', html))
    if not has_src:
        fail("报告末尾缺数据来源")
    if not has_disc:
        fail("报告缺免责声明")
    print(f"    {'OK ' if has_src else 'FAIL'} 数据来源")
    print(f"    {'OK ' if has_disc else 'FAIL'} 免责声明")

    # ---------- 7. 第 0 层硬伤核验痕迹 ----------
    print("\n[7] 第 0 层硬伤核验")
    has_audit = bool(re.search(r'审计|核数师|会计师事务所', html))
    # 「一票否决」只需留痕：允许写"无触发"，禁止只字不提
    if not has_audit:
        fail("未发现第 0 层硬伤核验痕迹：报告须写明审计意见类型（如 标准无保留 / 保留 / 无法表示意见）")
        print("    FAIL 缺审计意见核验 — 不得凭印象写，须回原文核实")
    else:
        print("    OK 已提及审计意见 / 核数师")

    # ---------- 8. 常驻侧边目录 ----------
    if is_html:
        print("\n[8] 常驻侧边目录")
        ok_layout = bool(re.search(r'class="layout"', html))
        ok_side = bool(re.search(r'<aside class="sidebar"', html))
        ok_sticky = bool(re.search(r'\.sidebar\s*\{[^}]*position\s*:\s*sticky', html, re.S))
        ok_content = bool(re.search(r'class="content"', html))
        ok_minw = bool(re.search(r'\.content\s*\{[^}]*min-width\s*:\s*0', html, re.S))
        for label, val in [('两栏 layout', ok_layout), ('aside.sidebar', ok_side),
                           ('sidebar sticky', ok_sticky), ('div.content', ok_content),
                           ('content min-width:0', ok_minw)]:
            if not val:
                fail(f"常驻目录缺失要素: {label}")
            print(f"    {'OK ' if val else 'FAIL'} {label}")

        # 锚点配对
        anchors = re.findall(r'<a href="#([^"]+)"', html)
        ids = set(re.findall(r'id="([^"]+)"', html))
        toc_anchors = [a for a in anchors if re.match(r'^s\d+$', a)]
        dead = [a for a in toc_anchors if a not in ids]
        if dead:
            fail(f"目录锚点无对应 id: {dead}")
        h2_ids = re.findall(r'<h2 id="([^"]+)"', html)
        miss = [i for i in h2_ids if i not in toc_anchors]
        if miss:
            fail(f"章节未进目录: {miss}")
        if not toc_anchors:
            fail("目录里没有任何章节锚点")
        print(f"    目录条目 {len(set(toc_anchors))} 个 / h2 章节 {len(h2_ids)} 个"
              f" -> {'OK' if not (dead or miss) else 'FAIL'}")

        if '<header id="top">' not in html:
            fail('缺 <header id="top">（回到顶部锚点）')
            print("    FAIL 回到顶部锚点")
        else:
            print("    OK 回到顶部锚点")

        if 'classList.toggle(\'active\'' in html:
            print("    OK 滚动高亮脚本")
        else:
            print("    注意 未发现滚动高亮脚本（建议添加）")

    # ---------- 9. 产品用途与客户映射 ----------
    print("\n[9] 产品用途与客户映射（企业概况必备）")
    # 表头含五要素任一列，才认作已建映射表（避免"客户"二字在风险章节出现就算通过）
    has_map = bool(re.search(r'<th[^>]*>\s*(工业用途|直接客户|终端行业|下游客户)', html)) \
        or bool(re.search(r'\|\s*(工业用途|直接客户|终端行业|下游客户)\s*\|', html))
    if not has_map:
        fail("缺「产品 → 用途 → 客户」映射表：企业概况的「主要产品」须配五要素表"
             "（产品 / 是什么 / 工业用途 / 直接客户 / 终端行业），禁止只罗列产品名。"
             "模板见 references/product_downstream_map.md")
    print(f"    {'OK ' if has_map else 'FAIL'} 映射表表头（工业用途 / 直接客户 / 终端行业）")

    # ---------- 10. 行业地位与竞争格局 ----------
    print("\n[10] 行业地位与竞争格局（独立章节）")
    # 标题里常含 <span class="num">二</span> 等内联标签，须取整段 h2 再匹配
    h2_titles = re.findall(r'<h2[^>]*>([\s\S]*?)</h2>', html)
    has_sec = any(re.search(r'行业地位|竞争格局', re.sub(r'<[^>]+>', '', t)) for t in h2_titles) \
        or bool(re.search(r'^#{1,3}\s*.*(行业地位|竞争格局)', html, re.M))
    if not has_sec:
        fail("缺「行业地位与竞争格局」章节：必须有独立章节回答「行业多大、对手是谁、凭什么赚钱」。"
             "规范见 references/industry_competitive_landscape.md")
    print(f"    {'OK ' if has_sec else 'FAIL'} 独立章节标题")

    signals = {
        "行业规模/市场规模": r'市场规模|行业规模',
        "竞争格局/对手/梯队": r'竞争对手|竞争格局|第一梯队|第二梯队',
        "资源自给率": r'自给率',
        "单位成本/成本曲线": r'完全成本|单位成本|吨成本|成本曲线',
        "市占率/份额": r'市占率|市场份额|占全国|占全球',
    }
    hit = [k for k, pat in signals.items() if re.search(pat, html)]
    for k in signals:
        print(f"    {'OK ' if k in hit else '--  '} {k}")
    if len(hit) < 3:
        fail("行业地位章节内容不足：至少需覆盖「行业规模、竞争格局、自给率、成本曲线、市占率」中的 3 项，"
             f"当前仅 {len(hit)} 项（{('、'.join(hit)) or '无'}）")

    # ---------- 10.5 护城河四问与证据链 ----------
    # 唐朝四问法（2026-09 升级）：有就是有，没有就是没有。
    # 三项硬检查：巨资测试（④问）、证据表表头、章末明确结论。
    print("\n[10.5] 护城河四问与证据链")
    pat_th_evd = re.compile(r'<th[^>]*>\s*(财报证据|量化证据|证据链?)\s*(?:<|\|)')
    pat_md_evd = re.compile(r'\|\s*(财报证据|量化证据|证据链?)\s*\|')
    has_evd = bool(pat_th_evd.search(html)) or bool(pat_md_evd.search(html))
    has_test = bool(re.search(r'巨资测试|巴菲特测试|挟巨资|10\s*亿美元|100\s*亿美元|10\s*亿美金|100\s*亿美金', html))
    has_concl = bool(re.search(r'未发现.{0,10}护城河|护城河.{0,16}(宽阔|较深|较浅|狭窄|不存在|存疑|未发现)', html))
    if not has_evd:
        fail("护城河章节缺「证据表」：每条护城河主张必须配财报可验证的量化证据，"
             "证据不足的类别明确写「无」。版式见 references/moat_framework.md")
    if not has_test:
        fail("护城河章节缺「巨资测试」（④问）：须回答「假设同行/产业巨头挟巨资进攻，"
             "公司能否保住乃至扩张市场份额」（巴菲特：给 10 亿/100 亿美元能否伤着这家公司）")
    if not has_concl:
        fail("护城河章节缺明确结论句：须写「护城河为宽阔/较深/较浅/狭窄/未发现，"
             "核心支撑是 X（证据 Y），最大威胁是 Z」——「未发现护城河」也是合格结论")
    for label, val in [('证据表（财报证据列）', has_evd), ('巨资测试（④问）', has_test),
                       ('章末明确结论', has_concl)]:
        print(f"    {'OK ' if val else 'FAIL'} {label}")

    # ---------- 11. 反空值检查（数据不得丢失） ----------
    # 数值单元格（class 含 num-c 的 td/th）不得出现空占位符（— / - / null / N/A / 空串）。
    # 但凡留空，必须能给出「原始数据确未披露」的正当理由，由写报告者人工确认后逐条豁免。
    # 本检查只告警不豁免：把每个空值列出来逼人复核，杜绝「该有数却留空」。
    print("\n[11] 反空值检查（数据不得留空）")
    if is_html:
        PLACEHOLDER = re.compile(r'(^|\s)[—–-]{1,3}(\s|$)')
        EMPTY_TD = re.compile(r'<td([^>]*)>\s*(?:<[^>]+>\s*)*</td>')
        blanks = []
        for i, tb in enumerate(tables, 1):
            for tdm in re.finditer(r'<t[dh]([^>]*)>([\s\S]*?)</t[dh]>', tb):
                attrs, content = tdm.group(1), tdm.group(2)
                if 'num-c' not in attrs and 'num-c' not in attrs:
                    # 仅检查数值列
                    pass
                if 'num-c' not in attrs:
                    continue
                txt = re.sub(r'<[^>]*>', '', content).strip()
                if txt == '' or txt in ('—', '-', '--', '——', 'null', 'N/A', 'NA', 'n/a', '无', '未披露'):
                    blanks.append((i, txt if txt else '(空)'))
        if blanks:
            # 汇总去重
            uniq = {}
            for i, v in blanks:
                uniq.setdefault(i, []).append(v)
            for i in sorted(uniq):
                fail(f"表 #{i} 存在空值单元格 {len(uniq[i])} 处: {uniq[i][:8]}")
                print(f"    FAIL 表 #{i}: 空值 {len(uniq[i])} 处，示例 {uniq[i][:8]}")
        if not blanks:
            print("    OK 数值列无空占位符")
    else:
        print("    --  Markdown 模式：请人工检查表格无空值")

    # ---------- 12. 绝对化词扫描（定性用词纪律）----------
    # 规则源：references/qualitative_discipline.md 第五节
    print("\n[12] 绝对化词扫描（定性用词纪律）")
    if is_html:
        _body = re.sub(r'<(script|style)[\s\S]*?</\1>', ' ', html, flags=re.I)
        _body = re.sub(r'<[^>]*>', ' ', _body)
    else:
        _body = re.sub(r'```[\s\S]*?```', ' ', html)      # Markdown：去掉代码块
    _body = _body.replace('&nbsp;', ' ')
    _lines = _body.splitlines()

    # 硬档：财务分析语境下无正当用途 —— 出现即 FAIL
    HARD_WORDS = ("不可复制", "不可撼动", "完美", "无可挑剔", "极致", "极佳", "必然",
                  "永远", "No.1", "NO.1", "零风险", "稳赚", "绝对领先", "无可比拟",
                  "独一无二", "100%确定")
    # 软档：可用但须有代价 —— 同行内有数字或出处标记即豁免，否则 WARN
    # 词表只收「高置信营销词组」：单字与泛词（最/全部/第一/领先）误报过多已剔除，
    # 例如「绝对值」「第一问」「第一梯队」「影响最大」都是正常表述。
    SOFT_WORDS = ("唯一", "垄断", "龙头", "领先地位", "绝对优势", "绝对领先",
                  "全球第一", "行业第一", "全国第一", "排名第一", "世界第一",
                  "最强", "最优", "最佳", "最先进", "最具", "霸主", "王者", "天花板")
    EVIDENCE_RE = re.compile(r'[0-9]|【源】|【推】|【判】|【公司自述】')
    # 「唯一」在股权/法律语境下是事实描述（如"Class B 股的唯一控制人"），不算营销词
    SOFT_EXEMPT_RE = re.compile(r'唯一(?:的)?(?:控制人|股东|持有人|表决权|投票权|真源|法定)')


    hard_hits, soft_hits = [], []
    for _ln, _t in enumerate(_lines, 1):
        _t = _t.strip()
        if not _t:
            continue
        for _w in HARD_WORDS:
            if _w in _t:
                hard_hits.append((_ln, _w, _t[:70]))
        for _w in SOFT_WORDS:
            if _w in _t and not EVIDENCE_RE.search(_t) and not SOFT_EXEMPT_RE.search(_t):
                soft_hits.append((_ln, _w, _t[:70]))

    if hard_hits:
        for _ln, _w, _t in hard_hits[:12]:
            fail(f"[12] 硬档绝对化词「{_w}」（行 {_ln}）：{_t}")
            print(f"    FAIL 行 {_ln} 「{_w}」: {_t}")
        if len(hard_hits) > 12:
            print(f"    ...另有 {len(hard_hits) - 12} 处")
        print("    解法：硬档词无豁免路径，拆成可验证的句子（见 qualitative_discipline.md 第六节）")
    else:
        print("    OK 无硬档绝对化词")
    if soft_hits:
        print(f"    注意 软档词 {len(soft_hits)} 处同行内既无数字也无出处标记（不阻塞交付，建议补）：")
        for _ln, _w, _t in soft_hits[:8]:
            print(f"        行 {_ln} 「{_w}」: {_t}")
    else:
        print("    OK 软档词均有数字/出处支撑")

    # ---------- 13. 定性结论出处标注 ----------
    # 规则源：references/qualitative_discipline.md 第三、八节
    print("\n[13] 定性结论出处标注（【源】/【推】/【判】）")
    _marks = {}
    for _m in ("【源】", "【推】", "【判】", "【疑】", "【公司自述】"):
        _c = _body.count(_m)
        if _c:
            _marks[_m] = _c
    _total = sum(_marks.values())
    _detail = "  ".join(f"{k}×{v}" for k, v in _marks.items()) or "(无)"
    if _total < 3:
        fail(f"[13] 定性结论出处标记仅 {_total} 处（要求 ≥3）：{_detail} —— 见 qualitative_discipline.md")
        print(f"    FAIL {_total} 处（要求 ≥3）  {_detail}")
        print("    解法：护城河 / 竞争格局 / 风险成因等关键定性句挂【源】/【推】/【判】")
    else:
        print(f"    OK {_total} 处  {_detail}")
    # 附加（WARN，不 FAIL）：护城河章末结论句附近应有出处或量化依据
    _mo = re.search(r'护城河[^。；\n]{0,16}(?:宽阔|较深|较浅|狭窄|不存在|存疑|未发现)', _body)
    if _mo:
        _seg = _body[max(0, _mo.start() - 100): _mo.end() + 220]
        if not EVIDENCE_RE.search(_seg):
            print("    注意 护城河结论句附近未见出处标记或量化依据，建议补（第四节「公司自述打折」）")

    # ---------- 14. 高风险术语是否给出定义（读者假设：外行）----------
    # 规则源：references/qualitative_discipline.md 第八节
    # 教训：2026-09-23 Amazon 报告写「Level 3 主观估值」，读者追问「这是什么意思、你从哪里找来的」
    print("\n[14] 高风险术语是否给出定义（读者假设：外行）")
    JARGON = ("Level 1", "Level 2", "Level 3",
              "VIE", "可变利益实体", "KAM", "关键审计事项",
              "DLOM", "AOCI", "ASC 820", "ASC 606", "ASC 842",
              "Non-GAAP", "净现金转换周期", "剩余履约义务", "未确认履约义务")

    def _term_defined(_t):
        # 定义式①：术语后紧跟冒号/等号/破折号，且其后有实质内容（中文或 ≥4 字母英文）
        for _m in re.finditer(re.escape(_t) + r'\s*(?:[:：=＝]|——|—)\s*(.{4,140})', _body):
            if re.search(r'[\u4e00-\u9fff]|[A-Za-z]{4,}', _m.group(1)):
                return True
        # 定义式②：术语后紧跟中文括注，且括注 ≥6 字
        if re.search(re.escape(_t) + r'\s*[（(][^）)]{6,}[）)]', _body):
            return True
        # 定义式③：「全称（术语…）」形式
        #   如「美国会计准则（ASC 820）」「关键审计事项（KAM，Key Audit Matter）」
        if re.search(r'[A-Za-z0-9\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff .&\-]{1,40}'
                     r'[（(]\s*' + re.escape(_t), _body):
            return True
        return False

    _j_hit = [_t for _t in JARGON if _t in _body]
    _j_miss = [_t for _t in _j_hit if not _term_defined(_t)]
    if _j_miss:
        fail("[14] 高风险术语全文无定义式说明：" + "、".join(_j_miss)
             + " —— 见 qualitative_discipline.md 第八节")
        print("    FAIL %d 个：%s" % (len(_j_miss), "、".join(_j_miss)))
        print("    解法①：首现处给「英文原文 + 中文直译 + 本案为何适用」")
        print("    解法②：集中加「术语注解」区块，每条写成「术语：中文解释（附原文引述）」")
    elif _j_hit:
        print("    OK 命中 %d 个高风险术语，均有定义式说明：%s" % (len(_j_hit), "、".join(_j_hit)))
    else:
        print("    OK 未出现高风险术语")

    # ---------- 15. 英文缩写首现是否展开（提示级，不阻塞交付）----------
    print("\n[15] 英文缩写首现展开检查（提示）")
    ACR_WL = {
        "SEC", "IPO", "CEO", "CFO", "COO", "CTO", "AI", "ML", "LLM", "GPU", "CPU", "IT",
        "US", "USA", "UK", "EU", "HTML", "PDF", "URL", "API", "ID", "OK",
        "Q1", "Q2", "Q3", "Q4", "H1", "H2", "FY", "YTD", "QOQ", "YOY", "LTM", "CAGR",
        "EPS", "PE", "PB", "PS", "ROE", "ROA", "ROIC", "TTM", "EBIT", "EBITDA",
        "GAAP", "IFRS", "ADR", "ETF", "GDP", "CPI", "PMI", "FDI", "M&A",
        "USD", "RMB", "CNY", "HKD", "EUR", "JPY", "B2B", "B2C",
        "SaaS", "PaaS", "IaaS", "KPI", "NA", "TBD", "ARR", "GMV", "DAU", "MAU", "ARPU",
    }
    _acr = {}
    for _m in re.finditer(r'(?<![A-Za-z0-9&])([A-Z][A-Z&]{1,5})(?![A-Za-z0-9])', _body):
        _t = _m.group(1)
        if _t in ACR_WL:
            continue
        _acr.setdefault(_t, _m.start())
    _unexp = []
    for _t, _i in sorted(_acr.items(), key=lambda kv: kv[1]):
        _seg = _body[max(0, _i - 120): _i + 160]
        # 交易所前缀后的代码（如 NASDAQ: AMZN）视为自解释
        if re.search(r'(?:NASDAQ|NYSE|AMEX|SSE|SZSE|SEHK|HKEX|TSX|LSE|TSE|Ticker|代码)'
                     r'\s*[:：]\s*$', _body[max(0, _i - 16): _i]):
            continue
        # 紧邻中文括注（任意长度）即视为已说明
        if re.search(r'[（(][^）)]*[\u4e00-\u9fff][^）)]*[）)]', _seg):
            continue
        # 「全称（缩写）」形式：如「美国联邦贸易委员会（FTC）」「Amazon.com（AMZN）」
        if re.search(r'[A-Za-z0-9\u4e00-\u9fff][A-Za-z0-9\u4e00-\u9fff .&\-]{1,40}'
                     r'[（(]\s*' + re.escape(_t), _body):
            continue
        # 「英文全称（缩写）」形式
        if re.search(r'[A-Z][A-Za-z]+(?:\s+[A-Za-z&.]+){1,6}\s*[（(]\s*'
                     + re.escape(_t) + r'\s*[）)]', _body[max(0, _i - 220): _i + 40]):
            continue
        # 定义式写法（缩写：中文解释）
        if re.search(re.escape(_t) + r'\s*[:：—]\s*\S', _body):
            continue
        _unexp.append(_t)
    if _unexp:
        print("    注意 %d 个缩写首现处未见中文解释或英文全称（不阻塞交付）：" % len(_unexp))
        print("         " + "、".join(_unexp[:20]) + ("…" if len(_unexp) > 20 else ""))
        print("    建议：外行读者未必认得，首现处补「英文全称（缩写）」或中文括注")
    else:
        print("    OK 未发现未解释的英文缩写")

    # ---------- 汇总 ----------
    print("\n" + "=" * 56)
    if not FAILED:
        print("全部检查通过 —— 可以交付")
        return 0
    print(f"发现 {len(FAILED)} 个问题：")
    for f in FAILED:
        print(f"  - {f}")
    return 1


if __name__ == '__main__':
    sys.exit(main())
