#!/usr/bin/env python3
"""
PDF 财报文本提取脚本（通用版）
使用 PyMuPDF (pymupdf) 从中文 PDF 中提取可读文本，保存为 UTF-8 编码的 TXT 文件。

用法:
    python extract_pdf_text.py <pdf_dir> <output_dir> [--files file1.pdf file2.pdf ...]

若不指定 --files，则自动处理 pdf_dir 下的所有 PDF 文件。
"""

import pymupdf
import os
import argparse
import sys


def extract_pdf_to_text(pdf_path: str, txt_path: str) -> dict:
    """
    提取单个 PDF 的文本内容并保存为 TXT 文件。

    参数:
        pdf_path: PDF 文件完整路径
        txt_path: 输出 TXT 文件完整路径

    返回:
        包含 pages, chars, sample 的字典
    """
    result = {"pages": 0, "chars": 0, "sample": "", "error": None}

    try:
        doc = pymupdf.open(pdf_path)
        num_pages = len(doc)
        result["pages"] = num_pages

        full_text = []
        for i in range(num_pages):
            page = doc[i]
            text = page.get_text()
            full_text.append(f"--- Page {i+1} ---\n{text}")

        content = "\n".join(full_text)
        result["chars"] = len(content)
        result["sample"] = content[500:1000] if len(content) > 1000 else content

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(content)

        print(f"  ✓ 提取成功: {num_pages} 页, {len(content)} 字符")
        print(f"  → 已保存: {txt_path}")

    except Exception as e:
        result["error"] = str(e)
        print(f"  ✗ 提取失败: {e}")
        import traceback
        traceback.print_exc()

    return result


def main():
    parser = argparse.ArgumentParser(
        description="使用 PyMuPDF 从 PDF 中提取文本（通用版，支持中文财报）"
    )
    parser.add_argument("pdf_dir", help="PDF 文件所在目录（支持中文路径）")
    parser.add_argument("output_dir", help="文本文件输出目录")
    parser.add_argument(
        "--files",
        nargs="+",
        help="指定要处理的 PDF 文件名（含 .pdf 后缀），不指定则处理目录下所有 PDF",
    )
    args = parser.parse_args()

    pdf_dir = os.path.abspath(args.pdf_dir)
    output_dir = os.path.abspath(args.output_dir)

    # 确保输出目录存在
    os.makedirs(output_dir, exist_ok=True)

    # 确定要处理的文件列表
    if args.files:
        pdf_files = args.files
    else:
        pdf_files = [f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")]
        pdf_files.sort()  # 按文件名排序

    if not pdf_files:
        print(f"⚠️  在 {pdf_dir} 中未找到任何 PDF 文件")
        sys.exit(1)

    print(f"PDF 目录  : {pdf_dir}")
    print(f"输出目录  : {output_dir}")
    print(f"待处理文件: {len(pdf_files)} 个")
    print("-" * 60)

    results = []
    for fname in pdf_files:
        pdf_path = os.path.join(pdf_dir, fname)
        txt_fname = fname.replace(".pdf", "_pymupdf.txt").replace(".PDF", "_pymupdf.txt")
        txt_path = os.path.join(output_dir, txt_fname)

        print(f"\n处理: {fname}")
        print(f"  路径: {pdf_path}")
        print(f"  存在: {os.path.exists(pdf_path)}")

        if not os.path.exists(pdf_path):
            print(f"  ⚠️  文件不存在，跳过")
            continue

        result = extract_pdf_to_text(pdf_path, txt_path)
        result["filename"] = fname
        results.append(result)

    # 汇总
    print("\n" + "=" * 60)
    print("提取汇总:")
    success = sum(1 for r in results if r["error"] is None)
    print(f"  成功: {success}/{len(results)}")
    for r in results:
        if r["error"]:
            print(f"  ✗ {r['filename']}: {r['error']}")
        else:
            print(f"  ✓ {r['filename']}: {r['pages']} 页, {r['chars']} 字符")
    print("=" * 60)


if __name__ == "__main__":
    main()
