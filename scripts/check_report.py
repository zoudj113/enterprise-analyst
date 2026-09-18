# -*- coding: utf-8 -*-
"""
企业分析报告交付前自检（enterprise-analyst Step 3.5）

用法：
    python scripts/check_report.py <报告文件.html|报告文件.md>

检查项：
    0. 文件命名规范（{公司}_分析报告_{YYYYMMDD}.html）
    1. HTML 标签闭合
    2. 表格列数一致性（表头 vs 各数据行）
    3. canvas 与 Chart.js 注册配对
    4. 时间列排序规则（最新期间必须在最左）
    5. 必备章节
    6. 免责声明 / 数据来源
    7. 第 0 层硬伤核验痕迹（须写明审计意见，不得凭印象）
    8. 常驻侧边目录（sticky TOC + 锚点配对 + 滚动高亮）

退出码：0 = 全部通过；1 = 有 FAIL。
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

def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    path = Path(sys.argv[1])
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

    print(f"    共 {len(tables)} 张表")
    for i, tb in enumerate(tables, 1):
        if is_html:
            head_m = re.search(r'<thead>[\s\S]*?</thead>', tb)
            if not head_m:
                continue
            head_n = len(re.findall(r'<th[\s>]', head_m.group(0)))
            rows = re.findall(r'<tr>([\s\S]*?)</tr>', tb)
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
            for rm in re.finditer(r'<tr[^>]*>([\s\S]*?)</tr>', tb):
                row = rm.group(1)
                if re.search(r'<th[\s>]', row):
                    continue
                col = 0
                for cm2 in re.finditer(r'<td([^>]*)>', row):
                    span = 1
                    sm2 = re.search(r'colspan\s*=\s*"(\d+)"', cm2.group(1))
                    if sm2:
                        span = int(sm2.group(1))
                    slot = counts.setdefault(col, [0, 0])
                    slot[0] += 1
                    if 'num-c' in cm2.group(1):
                        slot[1] += 1
                    col += span
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
