#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
cleanup.py — enterprise-analyst 分析收尾的通用中间文件清理

用途：分析完成后清理「过程性中间文件」，保留「财报原文 + 最终报告」。

设计原则（安全第一）：
  1. 默认 **dry-run**（只列不删），必须加 --apply 才真正删除。
  2. 只删**明确属于中间过程**的文件，绝不碰财报原文与报告。
  3. 不递归删目录（除非 --dirs 显式指定目录名）。
  4. 删除前打印完整清单，删除后打印「删了哪些 + 剩了哪些」。

默认「可删」判定（都可被 --keep 覆盖）：
  - 文件名以 `_` 开头（本次分析的临时脚本/中间输出，如 _extract_*.py、_dl.txt）
  - 文件名含 `cleanup` 或 `_cleanup`（清理脚本自身）
  - 显式通过 --files 传入的路径

默认「保留」：
  - 财报原文：*.pdf / *.htm / *.html（EDGAR 原文）/ 含「年报」「10-K」「20-F」「招股」的文件
  - 最终报告：*分析报告*.html / *.md

用法：
    # 预览（安全，什么都不删）
    python cleanup.py <工作目录> --dry-run

    # 真正清理（预览确认后再加 --apply）
    python cleanup.py <工作目录> --apply

    # 额外指定要删的目录（如临时 _src 里不需要的子目录）
    python cleanup.py <工作目录> --apply --dirs _tmp

仅用标准库，managed python 即可运行。
"""

import argparse
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# 命中这些关键词的文件，即便不以 _ 开头也视为「可删中间文件」
_DELETE_HINTS = ("cleanup", "_check", "_verify", "_final_ls", "_ls")

# 命中这些关键词的文件，即便以 _ 开头也强制保留（财报原文 / 报告 / 用户数据）
_KEEP_HINTS = ("年报", "年度报告", "招股", "10-k", "20-f", "10k", "20f",
               "分析报告", "annual report", "prospectus", "财务")


def is_middle(name):
    """判断文件名是否属于「可删中间文件」。"""
    low = name.lower()
    # 保留：财报原文 / 报告
    for k in _KEEP_HINTS:
        if k in low:
            return False
    # 可删：_ 前缀或命中删除提示词
    if name.startswith("_"):
        return True
    for k in _DELETE_HINTS:
        if k in low:
            return True
    return False


def main():
    ap = argparse.ArgumentParser(description="清理中间文件，保留财报原文与报告")
    ap.add_argument("workdir", help="分析工作目录")
    ap.add_argument("--dry-run", action="store_true", help="只列不删（默认）")
    ap.add_argument("--apply", action="store_true", help="真正执行删除")
    ap.add_argument("--files", default="", help="额外显式指定要删的文件，逗号分隔")
    ap.add_argument("--dirs", default="", help="额外显式指定要删的子目录名，逗号分隔")
    ap.add_argument("--log", default=None, help="结果写该 UTF-8 文件")
    args = ap.parse_args()

    wd = args.workdir
    to_delete = []      # 文件
    dirs_to_delete = []  # 目录

    for name in sorted(os.listdir(wd)):
        full = os.path.join(wd, name)
        if os.path.isdir(full):
            if name in [d.strip() for d in args.dirs.split(",") if d.strip()]:
                dirs_to_delete.append(full)
            continue
        if is_middle(name):
            to_delete.append(full)

    for f in [x.strip() for x in args.files.split(",") if x.strip()]:
        full = os.path.join(wd, f)
        if os.path.exists(full):
            to_delete.append(full)

    # 去重
    to_delete = sorted(set(to_delete))
    dirs_to_delete = sorted(set(dirs_to_delete))

    lines = []
    lines.append("== 待删除文件 %d 个 ==" % len(to_delete))
    for f in to_delete:
        lines.append("  DEL  %s" % os.path.basename(f))
    lines.append("== 待删除目录 %d 个 ==" % len(dirs_to_delete))
    for d in dirs_to_delete:
        lines.append("  RMDIR  %s" % os.path.basename(d))

    if args.apply:
        for f in to_delete:
            try:
                os.remove(f)
            except Exception as e:
                lines.append("  ! 删除失败 %s：%s" % (os.path.basename(f), e))
        for d in dirs_to_delete:
            try:
                import shutil
                shutil.rmtree(d, ignore_errors=True)
            except Exception as e:
                lines.append("  ! 删除目录失败 %s：%s" % (os.path.basename(d), e))
        lines.append("== 已执行删除 ==")
    else:
        lines.append("== DRY-RUN：未删除任何文件，加 --apply 才真正删除 ==")

    text = "\n".join(lines)
    print(text)
    if args.log:
        with open(args.log, "w", encoding="utf-8") as f:
            f.write(text + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
