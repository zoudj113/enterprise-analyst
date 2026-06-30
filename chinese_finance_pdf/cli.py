"""
Command-line interface for the Chinese financial PDF analysis toolkit.

Usage:
  python -m chinese_finance_pdf scan <pdf_path>
  python -m chinese_finance_pdf extract <pdf_path> [--pages 1-50,100-150]
  python -m chinese_finance_pdf analyze <pdf_path> [--output report.md]
  python -m chinese_finance_pdf tables <pdf_path> --pages 290-300
"""

import argparse
import sys
from pathlib import Path

import re

from .extractor import ChinesePDFExtractor
from .scanner import FinancialScanner
from .parser import FinancialParser
from .models import ExtractionBackend, FinancialDocument
from .output import MarkdownOutput, JSONOutput, CSVOutput


def _parse_page_ranges(pages_str: str) -> list[int]:
    """Parse page range strings like '1-50,100-150' into a flat list."""
    pages: list[int] = []
    for part in pages_str.split(','):
        part = part.strip()
        if '-' in part:
            a, b = part.split('-', 1)
            pages.extend(range(int(a), int(b) + 1))
        else:
            pages.append(int(part))
    return sorted(set(pages))


def cmd_scan(args):
    """Scan a PDF and report which pages contain which financial sections."""
    backend = ExtractionBackend(args.backend)
    extractor = ChinesePDFExtractor(args.pdf_path, backend=backend)

    print(f"正在扫描: {args.pdf_path}")
    print(f"总页数: {extractor.get_page_count()}")
    print(f"提取引擎: {backend.value}\n")

    # Extract all pages (chunked for large PDFs)
    all_pages: list = []
    for chunk in extractor.extract_chunked(chunk_size=50):
        all_pages.extend(chunk)
        if args.verbose:
            print(f"  已提取 {len(all_pages)} 页...")

    # Scan and classify
    scanner = FinancialScanner(all_pages)
    scanner.scan_and_classify()

    # Output
    if args.output == "json":
        print(CSVOutput.pages_to_csv(all_pages))
    else:
        summary = scanner.get_section_summary()
        print(MarkdownOutput.format_section_summary(summary))

        # Also print financial data page ranges
        fin_pages = scanner.find_financial_pages(min_digit_count=30)
        if fin_pages:
            page_nums = sorted(p.page_number for p in fin_pages)
            print(f"\n**疑似财务数据页面** ({len(page_nums)}页):")
            # Group consecutive pages
            groups: list[list[int]] = []
            for pn in page_nums:
                if groups and pn == groups[-1][-1] + 1:
                    groups[-1].append(pn)
                else:
                    groups.append([pn])
            for g in groups:
                if len(g) == 1:
                    print(f"  - 第{g[0]}页")
                else:
                    print(f"  - 第{g[0]}-{g[-1]}页")


def cmd_extract(args):
    """Extract text from specific pages."""
    backend = ExtractionBackend(args.backend)
    extractor = ChinesePDFExtractor(args.pdf_path, backend=backend)

    if args.pages:
        page_numbers = _parse_page_ranges(args.pages)
    else:
        page_numbers = list(range(1, extractor.get_page_count() + 1))

    output_lines: list[str] = []
    for chunk_start in range(0, len(page_numbers), args.chunk_size):
        chunk_pages = page_numbers[chunk_start:chunk_start + args.chunk_size]
        for page_info in extractor.extract_pages(chunk_pages):
            output_lines.append(f"\n===== 第{page_info.page_number}页 =====")
            output_lines.append(page_info.text)

    result = "\n".join(output_lines)
    if args.output:
        Path(args.output).write_text(result, encoding='utf-8')
        print(f"已保存至: {args.output}")
    else:
        # Ensure UTF-8 output
        extractor._ensure_encoding()
        print(result)


def cmd_analyze(args):
    """Full analysis pipeline: scan -> classify -> parse -> output."""
    backend = ExtractionBackend(args.backend)
    extractor = ChinesePDFExtractor(args.pdf_path, backend=backend)

    print(f"正在分析: {args.pdf_path}")
    print(f"总页数: {extractor.get_page_count()}\n")

    # Step 1: Extract all pages
    all_pages: list = []
    for chunk in extractor.extract_chunked(chunk_size=50):
        all_pages.extend(chunk)

    # Step 2: Scan and classify
    scanner = FinancialScanner(all_pages)
    scanner.scan_and_classify()
    summary = scanner.get_section_summary()

    print("检测到的章节:")
    for section, pnums in summary.items():
        print(f"  {section}: {len(pnums)}页 (第{pnums[0]}-{pnums[-1]}页)")

    # Step 3: Parse financial data
    parser = FinancialParser(all_pages)
    metrics = parser.parse_all(args.pdf_path)
    metrics.fiscal_years = sorted(set(
        y for p in all_pages
        for y in [m.group(1) for m in __import__('re').finditer(r'(20\d{2})年', p.text)]
    ))

    # Step 4: Output
    if args.format == "json":
        output = JSONOutput.to_json(metrics)
    else:
        output = MarkdownOutput.format_document_summary(
            __import__('.models', fromlist=['FinancialDocument']).FinancialDocument(
                pdf_path=args.pdf_path,
                total_pages=extractor.get_page_count(),
                pages=all_pages,
                extraction_backend=backend,
            )
        )
        output += "\n\n"
        output += MarkdownOutput.format_section_summary(summary)
        output += "\n\n"
        output += MarkdownOutput.format_report_stub(metrics)

    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
        print(f"\n报告已保存至: {args.output}")
    else:
        extractor._ensure_encoding()
        print("\n" + output)


def cmd_tables(args):
    """Extract tables from specific pages."""
    if not args.pages:
        print("错误: --pages 参数为必选项", file=sys.stderr)
        sys.exit(1)

    page_numbers = _parse_page_ranges(args.pages)
    parser = FinancialParser([])  # pages not needed for table extraction

    all_tables: list = []
    for pn in page_numbers:
        tables = parser.extract_tables_from_page(pn, args.pdf_path)
        all_tables.extend(tables)
        print(f"第{pn}页: 提取 {len(tables)} 个表格")

    if not all_tables:
        print("未提取到任何表格。")
        return

    # Format output
    if args.format == "json":
        output = json.dumps(
            [{"page": t.page_number, "headers": t.headers, "rows": t.rows}
             for t in all_tables],
            ensure_ascii=False, indent=2
        )
    elif args.format == "csv":
        # Output first table as CSV
        t = all_tables[0]
        import csv, io
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(t.headers)
        w.writerows(t.rows)
        output = buf.getvalue()
    else:
        lines: list[str] = []
        for t in all_tables:
            lines.append(f"\n### 第{t.page_number}页表格\n")
            lines.append("| " + " | ".join(t.headers) + " |")
            lines.append("|" + "|".join("---" for _ in t.headers) + "|")
            for row in t.rows:
                lines.append("| " + " | ".join(row) + " |")
        output = "\n".join(lines)

    if args.output:
        Path(args.output).write_text(output, encoding='utf-8')
        print(f"已保存至: {args.output}")
    else:
        print(output)


def main():
    parser = argparse.ArgumentParser(
        prog="chinese-finance-pdf",
        description="中文财务PDF分析工具包",
    )
    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # scan
    sp = subparsers.add_parser("scan", help="扫描PDF，识别财务报表章节位置")
    sp.add_argument("pdf_path", type=str, help="PDF文件路径")
    sp.add_argument("--backend", choices=["pdfplumber", "pypdf2"], default="pdfplumber")
    sp.add_argument("--output", choices=["text", "json"], default="text")
    sp.add_argument("--verbose", "-v", action="store_true")

    # extract
    ep = subparsers.add_parser("extract", help="提取指定页面的文本")
    ep.add_argument("pdf_path", type=str, help="PDF文件路径")
    ep.add_argument("--pages", type=str, help="页码范围，如 '1-50,100-150'")
    ep.add_argument("--backend", choices=["pdfplumber", "pypdf2"], default="pdfplumber")
    ep.add_argument("--output", type=str, help="输出文件路径")
    ep.add_argument("--chunk-size", type=int, default=50)

    # analyze
    ap = subparsers.add_parser("analyze", help="全流程分析")
    ap.add_argument("pdf_path", type=str, help="PDF文件路径")
    ap.add_argument("--backend", choices=["pdfplumber", "pypdf2"], default="pdfplumber")
    ap.add_argument("--output", type=str, help="输出报告文件路径")
    ap.add_argument("--format", choices=["markdown", "json"], default="markdown")

    # tables
    tp = subparsers.add_parser("tables", help="提取指定页面的表格")
    tp.add_argument("pdf_path", type=str, help="PDF文件路径")
    tp.add_argument("--pages", type=str, required=True, help="页码范围")
    tp.add_argument("--output", type=str, help="输出文件路径")
    tp.add_argument("--format", choices=["markdown", "csv", "json"], default="markdown")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    handlers = {
        "scan": cmd_scan,
        "extract": cmd_extract,
        "analyze": cmd_analyze,
        "tables": cmd_tables,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
