# -*- coding: utf-8 -*-
"""
ima 长文档预处理：清洗 + 关键词行号索引（enterprise-analyst Step 1）

解决两个问题：
  1. fetch_media_content 落地的 .txt 常被 JSON 包裹/转义，直接 Read 全是噪声；
  2. 年报全文上万行，禁止整份 Read —— 必须先拿到「关键词 → 行号」索引，
     再用 Read(offset=行号-N, limit=...) 精确定位切片。

用法：
    python scripts/ima_doc_prepare.py <原始.txt> [-o 输出目录] [-k 关键词文件]
    python scripts/ima_doc_prepare.py <目录>            # 批量，推荐（避开中文名传参问题）

产出（默认写在源文件同目录）：
    {原名}_clean.md      清洗后的纯文本（Markdown，可直接 Grep / 切片 Read）
    {原名}_index.txt     关键词 → 行号索引，形如「营业收入: 312, 887, 1502 ...」

关键词文件：每行一个关键词，缺省时用内置财报关键词表。

依赖：仅标准库。Windows 下用
    C:\\Users\\zx\\.workbuddy\\binaries\\python\\versions\\3.13.12\\python.exe
"""
import argparse
import json
import os
import re
import sys

DEFAULT_KEYWORDS = [
    "营业收入", "营业成本", "毛利率", "净利润", "归属于上市公司股东的净利润",
    "扣除非经常性损益", "加权平均净资产收益率", "每股收益", "经营活动产生的现金流量净额",
    "投资活动产生的现金流量净额", "筹资活动产生的现金流量净额",
    "货币资金", "交易性金融资产", "应收账款", "应收款项融资", "预付款项",
    "其他应收款", "存货", "合同负债", "合同资产", "固定资产", "在建工程",
    "无形资产", "商誉", "长期股权投资", "其他权益工具投资", "递延所得税资产",
    "短期借款", "长期借款", "应付票据", "应付账款", "租赁负债",
    "资产减值损失", "信用减值损失", "资产处置收益", "其他收益", "投资收益",
    "管理费用", "销售费用", "财务费用", "研发费用", "税金及附加", "所得税费用",
    "少数股东损益", "少数股东权益", "未分配利润",
    "审计意见", "关键审计事项", "会计师事务所", "内部控制",
    "利润分配", "现金分红", "每10股", "募集资金",
    "关联交易", "关联方", "控股股东", "实际控制人", "质押",
    "生产量", "销售量", "库存量", "产能", "产量",
    "主要子公司", "分部", "前五名客户", "前五名供应商",
    "风险", "诉讼", "担保", "承诺",
]


def _deep_text(obj, depth=0):
    """从解析后的 JSON 对象里挑出正文：优先常见字段名，否则取最长字符串。"""
    if depth > 6:
        return None
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        for key in ("content", "text", "markdown", "result", "data", "body", "page_content"):
            if key in obj and isinstance(obj[key], str):
                return obj[key]
        best = None
        for v in obj.values():
            t = _deep_text(v, depth + 1)
            if t and (best is None or len(t) > len(best)):
                best = t
        return best
    if isinstance(obj, list):
        best = None
        for v in obj:
            t = _deep_text(v, depth + 1)
            if t and (best is None or len(t) > len(best)):
                best = t
        return best
    return None


def load_text(path):
    raw = open(path, encoding="utf-8", errors="replace").read()
    s = raw.strip()
    # 情形一：JSON 对象/数组包裹
    if s[:1] in "{[":
        try:
            t = _deep_text(json.loads(s))
            if t:
                return t
        except Exception:
            pass
    # 情形二：JSON 字符串包裹（带 \n \" 转义）
    if s[:1] == '"':
        try:
            return json.loads(s)
        except Exception:
            pass
    # 情形三：纯文本但残留字面转义
    if "\\n" in raw or '\\"' in raw:
        return raw.replace("\\n", "\n").replace('\\"', '"').replace("\\t", "\t")
    return raw


def build_index(lines, keywords, max_hits=25):
    out = []
    for kw in keywords:
        hits = [i + 1 for i, ln in enumerate(lines) if kw in ln]
        if not hits:
            continue
        shown = ", ".join(str(h) for h in hits[:max_hits])
        more = " ...(共%d处)" % len(hits) if len(hits) > max_hits else ""
        out.append("%s: %s%s" % (kw, shown, more))
    return out


def process_one(src, outdir, kws, max_hits):
    """处理单个文件，返回 (clean_path, index_path, 行数, 命中数)"""
    text = load_text(src)
    lines = text.splitlines()
    base = os.path.splitext(os.path.basename(src))[0]

    clean_path = os.path.join(outdir, base + "_clean.md")
    with open(clean_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)

    index_path = os.path.join(outdir, base + "_index.txt")
    idx = build_index(lines, kws, max_hits)
    with open(index_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("源文件: %s\n总行数: %d\n命中关键词: %d\n%s\n"
                % (os.path.basename(src), len(lines), len(idx), "-" * 40))
        f.write("\n".join(idx) + "\n")

    print("清洗 -> %s (%d 行, %d 字符)" % (clean_path, len(lines), len(text)))
    print("索引 -> %s (%d 个关键词命中)" % (index_path, len(idx)))
    return clean_path, index_path, len(lines), len(idx)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="原始 .txt，或**目录**（批量处理目录下所有 .txt）")
    ap.add_argument("-o", "--outdir", default=None, help="输出目录，默认与源文件/目录相同")
    ap.add_argument("-k", "--keywords", default=None, help="关键词文件，每行一个")
    ap.add_argument("--max-hits", type=int, default=25)
    ap.add_argument("--pattern", default="*.txt",
                    help="目录模式下的文件匹配式（默认 *.txt）")
    ap.add_argument("--skip-clean", action="store_true",
                    help="目录模式下跳过已产出 _clean.md 的源文件")
    args = ap.parse_args()

    src = os.path.abspath(args.src)
    if not os.path.exists(src):
        print("路径不存在: %s" % src)
        return 1

    kws = DEFAULT_KEYWORDS
    if args.keywords and os.path.exists(args.keywords):
        kws = [l.strip() for l in open(args.keywords, encoding="utf-8") if l.strip()]

    # 目录模式：避开 Windows/PowerShell 传中文文件名的编码问题
    if os.path.isdir(src):
        outdir = args.outdir or src
        os.makedirs(outdir, exist_ok=True)
        import glob
        files = [p for p in sorted(glob.glob(os.path.join(src, args.pattern)))
                 if not os.path.basename(p).startswith("_")
                 and not p.endswith("_clean.md")]
        if args.skip_clean:
            files = [p for p in files
                     if not os.path.exists(os.path.join(
                         outdir,
                         os.path.splitext(os.path.basename(p))[0] + "_clean.md"))]
        if not files:
            print("目录下无匹配的 .txt: %s" % src)
            return 1
        print("目录模式：%d 个文件" % len(files))
        ok = 0
        for p in files:
            try:
                process_one(p, outdir, kws, args.max_hits)
                ok += 1
            except Exception as e:
                print("  [ERR] %s -> %r" % (os.path.basename(p), e))
        print("完成 %d/%d" % (ok, len(files)))
        return 0 if ok else 1

    outdir = args.outdir or os.path.dirname(src)
    os.makedirs(outdir, exist_ok=True)
    process_one(src, outdir, kws, args.max_hits)
    return 0


if __name__ == "__main__":
    sys.exit(main())
