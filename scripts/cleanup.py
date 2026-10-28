#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
cleanup.py — enterprise-analyst 分析收尾的中间文件清理（v2 · 2026-10-28 重写）

用途：分析完成后清掉「过程性中间文件」，只留「财报原文 + 最终报告」。

v1 → v2 的三处修正
  起因：2026-10-28 网易报告交付时，工作目录残留 94 MB / 60+ 文件，
        其中 25 个 .txt 转换件（16.5 MB）、3 份下载日志、3 个临时脚本。
        即使当时跑了 v1，这些文件也一个都删不掉——不是执行问题，是判据问题。

  1. **递归扫描子目录**：v1 只 os.listdir(顶层)，_src/ 下的 25 个 .txt 整体漏掉。
  2. **判据改为「扩展名优先」**：.pdf/.htm/.html 一律保留；.txt 只要同目录存在
     同名原文，即判为「可重新生成的转换件」。v1 的 _KEEP_HINTS 含 "20-f"，
     而转换件文件名是 20F_xxx.txt，先命中保留词就 return False —— 永远删不掉
     和原文同前缀的转换件。
  3. **--dirs 删目录前先查内容**：目录内只要还有受保护文件就拒绝删除。
     v1 直接 shutil.rmtree，能连财报原文一起删。

判定顺序（短路，先命中先生效，见 classify()）：
  A. 扩展名 ∈ {.pdf,.htm,.html,.xhtml,.mhtml}            → 保留（原文 / 报告）
  B. 扩展名 ∈ {.txt,.json,.log,.csv} 且同目录有同名原文  → 删除（转换件）
  C. 文件名命中 _KEEP_HINTS                              → 保留（用户数据 / 报告）
  D. 文件名以 `_` 开头                                   → 删除（临时脚本 / 日志）
  E. 文件名命中 _DELETE_HINTS                            → 删除
  F. 其余                                                → 保留（非中间文件，不动）

默认 dry-run（只列不删），必须 --apply 才真正删除。

用法：
    <python> scripts/cleanup.py <工作目录> --check        # 门禁模式：有残留返回 3
    <python> scripts/cleanup.py <工作目录> --dry-run      # 看清单（默认）
    <python> scripts/cleanup.py <工作目录> --apply
    <python> scripts/cleanup.py <工作目录> --apply --files a.txt,b.log
    <python> scripts/cleanup.py <工作目录> --apply --dirs _tmp
    <python> scripts/cleanup.py <工作目录> --dry-run --maxdepth 3
    <python> scripts/cleanup.py <工作目录> --apply --keep 重要.txt

仅用标准库，managed python 即可运行；不写死任何机器路径。
"""

import argparse
import os
import shutil
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 原文扩展名：命中即保留，不再进入任何删除判定
ORIGINAL_EXTS = {".pdf", ".htm", ".html", ".xhtml", ".mhtml"}

# 可派生的转换件扩展名：同目录若有同名原文 → 判为可删
DERIVED_EXTS = {".txt", ".json", ".log", ".csv"}

# 即便不以 _ 开头也保留的关键词（用户数据 / 报告本体）
KEEP_HINTS = ("分析报告", "年报", "年度报告", "招股", "annual report", "prospectus")

# 即便不以 _ 开头也删除的关键词
DELETE_HINTS = ("cleanup", "_check", "_verify", "_final_ls")


def human(n):
    """字节数转可读字符串。"""
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            if unit == "B":
                return "%d B" % n
            return "%.1f %s" % (n, unit)
        n /= 1024.0
    return "%.1f GB" % n


def classify(name, siblings_low):
    """判断单个文件去留。返回 (是否删除, 理由)。

    siblings_low 是**同目录**其他文件名的小写集合，用于识别「同目录有同名原文」。
    """
    low = name.lower()
    stem, ext = os.path.splitext(name)
    ext = ext.lower()

    # A. 原文 / 报告本体，永远保留
    if ext in ORIGINAL_EXTS:
        return (False, "原文/报告 %s" % ext)

    # B. 派生转换件：同目录存在同名原文 → 可重新生成，删
    if ext in DERIVED_EXTS:
        for oe in ORIGINAL_EXTS:
            if (stem + oe).lower() in siblings_low:
                return (True, "转换件（同目录有 %s%s）" % (stem, oe))

    # C. 保留词（用户提供的原始资料、报告成品）
    for k in KEEP_HINTS:
        if k in low:
            return (False, "保留词「%s」" % k)

    # D. 临时脚本 / 日志
    if name.startswith("_"):
        return (True, "临时文件（_ 前缀）")

    # E. 其他临时产物
    for k in DELETE_HINTS:
        if k in low:
            return (True, "临时文件（命中 %s）" % k)

    # F. 不认识的，不动
    return (False, "非中间文件")


def scan(wd, maxdepth, recurse):
    """遍历工作目录，返回 (待删列表, 保留列表)，元素为 (绝对路径, 相对路径, 理由, 字节数)。"""
    to_del, kept = [], []
    for dirpath, dirnames, filenames in os.walk(wd):
        rel = os.path.relpath(dirpath, wd)
        depth = 0 if rel == "." else rel.count(os.sep) + 1

        # 控制递归深度
        if not recurse or depth >= maxdepth:
            dirnames[:] = []

        # 跳过版本控制与工作区元数据目录，避免误伤
        dirnames[:] = [d for d in dirnames if d not in (".git", ".workbuddy", "node_modules")]

        siblings_low = {f.lower() for f in filenames}
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            if not os.path.isfile(full):
                continue
            act, why = classify(name, siblings_low)
            try:
                size = os.path.getsize(full)
            except OSError:
                size = 0
            rp = os.path.relpath(full, wd)
            (to_del if act else kept).append((full, rp, why, size))
    return to_del, kept


def group_by_reason(items):
    """按理由归组，用于输出。"""
    groups = {}
    for full, rp, why, size in items:
        key = why.split("（")[0]
        groups.setdefault(key, []).append((full, rp, why, size))
    return groups


def dir_guard(wd, dirname):
    """删除目录前的保护检查：返回 (是否可删, 受保护文件列表)。"""
    full = os.path.join(wd, dirname)
    if not os.path.isdir(full):
        return (False, [])
    protected = []
    for dp, dn, fn in os.walk(full):
        siblings_low = {f.lower() for f in fn}
        for n in fn:
            act, _ = classify(n, siblings_low)
            if not act:
                protected.append(os.path.join(dp, n))
    return (len(protected) == 0, protected)


def main():
    ap = argparse.ArgumentParser(
        description="清理中间文件，保留财报原文与报告（默认 dry-run）"
    )
    ap.add_argument("workdir", help="分析工作目录")
    ap.add_argument("--dry-run", action="store_true", help="只列不删（默认行为）")
    ap.add_argument("--check", action="store_true",
                    help="门禁模式：存在残留中间文件时返回 3（交付前校验用），不删任何文件")
    ap.add_argument("--apply", action="store_true", help="真正执行删除")
    ap.add_argument("--files", default="", help="额外显式指定要删的文件（相对 workdir，逗号分隔）")
    ap.add_argument("--dirs", default="", help="额外显式指定要删的子目录名（逗号分隔）")
    ap.add_argument("--keep", default="", help="强制保留的文件名或相对路径（逗号分隔），优先级最高")
    ap.add_argument("--maxdepth", type=int, default=9, help="递归最大深度，默认 9")
    ap.add_argument("--no-recurse", action="store_true", help="只看顶层，不递归子目录")
    ap.add_argument("--force-dir", action="store_true", help="即使目录内有受保护文件也删除（危险）")
    ap.add_argument("--log", default=None, help="结果写入该 UTF-8 文件")
    args = ap.parse_args()

    wd = args.workdir
    if not os.path.isdir(wd):
        print("!! 目录不存在：%s" % wd)
        return 2
    if args.check and args.apply:
        print("!! --check 与 --apply 不能同时使用（检查模式不删任何文件）")
        return 2

    keep_set = set()
    for x in [i.strip() for i in args.keep.split(",") if i.strip()]:
        keep_set.add(x.replace("\\", "/").lower())
        keep_set.add(os.path.basename(x).lower())

    to_del, kept = scan(wd, args.maxdepth, not args.no_recurse)

    # 强制保留过滤
    if keep_set:
        rest = []
        for item in to_del:
            full, rp, why, size = item
            if rp.replace("\\", "/").lower() in keep_set or os.path.basename(full).lower() in keep_set:
                kept.append((full, rp, "用户指定保留（--keep）", size))
            else:
                rest.append(item)
        to_del = rest

    # 显式 --files
    seen = {os.path.normcase(x[0]) for x in to_del}
    for x in [i.strip() for i in args.files.split(",") if i.strip()]:
        full = os.path.join(wd, x)
        if os.path.isfile(full) and os.path.normcase(full) not in seen:
            to_del.append((full, os.path.relpath(full, wd), "显式指定（--files）", os.path.getsize(full)))
            seen.add(os.path.normcase(full))

    to_del.sort(key=lambda t: t[1])
    kept.sort(key=lambda t: t[1])

    del_bytes = sum(t[3] for t in to_del)

    # 门禁模式：交付前校验。「Step 4 有没有做」由此变成可用退出码判定的问题，而不是靠自觉。
    if args.check:
        if to_del:
            print("== FAIL：仍有 %d 个中间文件未清理 / %s —— Step 4 未完成 ==" % (len(to_del), human(del_bytes)))
            for full, rp, why, size in to_del[:20]:
                print("   DEL  %-58s %s" % (rp, why))
            if len(to_del) > 20:
                print("   ... 其余 %d 个省略，跑 --dry-run 看全量" % (len(to_del) - 20))
            print("修复：<python> scripts/cleanup.py <工作目录> --apply")
            return 3
        print("== PASS：未发现残留中间文件（保留 %d 个）—— Step 4 已完成 ==" % len(kept))
        return 0

    lines = []
    lines.append("== 扫描目录 ==")
    lines.append("  %s%s" % (os.path.abspath(wd), "（仅顶层）" if args.no_recurse else "（递归，maxdepth=%d）" % args.maxdepth))
    lines.append("")

    lines.append("== 待删除 %d 个 / %s ==" % (len(to_del), human(del_bytes)))
    for key, items in sorted(group_by_reason(to_del).items(), key=lambda kv: -sum(t[3] for t in kv[1])):
        sub = sum(t[3] for t in items)
        lines.append("  [%s] %d 个 / %s" % (key, len(items), human(sub)))
        for full, rp, why, size in items:
            lines.append("    DEL  %-62s %10s" % (rp, human(size)))
    if not to_del:
        lines.append("  （无）")
    lines.append("")

    lines.append("== 保留 %d 个 ==" % len(kept))
    for full, rp, why, size in kept:
        lines.append("    KEEP %-62s %10s  %s" % (rp, human(size), why))
    lines.append("")

    # 目录处理
    dirs = [d.strip() for d in args.dirs.split(",") if d.strip()]
    if dirs:
        lines.append("== 目录处理 ==")
        for d in dirs:
            ok, protected = dir_guard(wd, d)
            if ok:
                lines.append("  RMDIR %s（目录内已无受保护文件）" % d)
            elif args.force_dir:
                lines.append("  RMDIR %s（--force-dir 强制，含 %d 个受保护文件）" % (d, len(protected)))
            else:
                lines.append("  拒绝删除目录 %s：内部还有 %d 个受保护文件，如：" % (d, len(protected)))
                for p in protected[:5]:
                    lines.append("      KEEP %s" % os.path.relpath(p, wd))
                lines.append("      确需整目录删除请加 --force-dir")
        lines.append("")

    if args.apply:
        failed = 0
        for full, rp, why, size in to_del:
            try:
                os.remove(full)
            except OSError as e:
                lines.append("  ! 删除失败 %s：%s" % (rp, e))
                failed += 1
        for d in dirs:
            full = os.path.join(wd, d)
            ok, _ = dir_guard(wd, d)
            if ok or args.force_dir:
                shutil.rmtree(full, ignore_errors=True)
                lines.append("  RMDIR 已删除 %s" % d)
        lines.append("== 已执行删除：成功 %d 个，失败 %d 个，释放 %s ==" % (len(to_del) - failed, failed, human(del_bytes)))
    else:
        lines.append("== DRY-RUN：未删除任何文件。确认清单无误后加 --apply ==")

    text = "\n".join(lines)
    print(text)
    if args.log:
        with open(args.log, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
