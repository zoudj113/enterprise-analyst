"""
Chinese Financial PDF Analysis Toolkit
=======================================

A reusable toolkit for extracting, scanning, and parsing Chinese financial
PDF documents (prospectuses, annual reports, 10-K equivalents, etc.).

Quick start:
    from chinese_finance_pdf import ChinesePDFExtractor, FinancialScanner, FinancialParser

    extractor = ChinesePDFExtractor("招股说明书.pdf")
    pages = extractor.extract_all()

    scanner = FinancialScanner(pages)
    classified = scanner.scan_and_classify()

    parser = FinancialParser(classified)
    metrics = parser.parse_all("招股说明书.pdf")

    # Access structured data
    print(metrics.gross_margin)  # {'2022': 0.688, '2023': 0.658, '2024': 0.673}
    print(metrics.revenue)      # {'2022': 4131.1, '2023': 2662.1, '2024': 10056.9}

CLI usage:
    python -m chinese_finance_pdf scan "招股说明书.pdf"
    python -m chinese_finance_pdf analyze "招股说明书.pdf" --output report.md
    python -m chinese_finance_pdf extract "招股说明书.pdf" --pages 290-350
    python -m chinese_finance_pdf tables "招股说明书.pdf" --pages 290-300
"""

from .extractor import ChinesePDFExtractor
from .scanner import FinancialScanner
from .parser import FinancialParser
from .models import (
    FinancialDocument,
    FinancialMetrics,
    ExtractedTable,
    PageInfo,
    FinancialSection,
    ExtractionBackend,
)
from .output import MarkdownOutput, JSONOutput, CSVOutput

__version__ = "1.0.0"

__all__ = [
    # Core classes
    "ChinesePDFExtractor",
    "FinancialScanner",
    "FinancialParser",
    # Data models
    "FinancialDocument",
    "FinancialMetrics",
    "ExtractedTable",
    "PageInfo",
    "FinancialSection",
    "ExtractionBackend",
    # Output formatters
    "MarkdownOutput",
    "JSONOutput",
    "CSVOutput",
]
