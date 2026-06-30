"""
Structured financial data parser.

Takes classified PageInfo objects and attempts to extract structured
FinancialMetrics using pdfplumber's table extraction and regex fallbacks.
"""

import re
from pathlib import Path

from .models import (
    PageInfo, ExtractedTable, FinancialSection, FinancialMetrics,
)
from .keywords import YEAR_PATTERN


class FinancialParser:
    """
    Parses classified pages into structured FinancialMetrics.

    Usage:
        parser = FinancialParser(pages)
        metrics = parser.parse_all("path/to/pdf.pdf")
    """

    def __init__(self, pages: list[PageInfo]):
        self.pages = pages

    # ── Public API ─────────────────────────────────────────────────────

    def extract_tables_from_page(
        self,
        page_number: int,
        pdf_path: str,
    ) -> list[ExtractedTable]:
        """Use pdfplumber's table extraction on a specific page."""
        import pdfplumber

        tables: list[ExtractedTable] = []
        with pdfplumber.open(pdf_path) as pdf:
            if page_number < 1 or page_number > len(pdf.pages):
                return tables
            page = pdf.pages[page_number - 1]
            raw_tables = page.extract_tables()
            for raw in raw_tables:
                if not raw or len(raw) < 2:
                    continue
                headers = [str(c) if c else "" for c in raw[0]]
                rows = [[str(c) if c else "" for c in r] for r in raw[1:]]
                tables.append(ExtractedTable(
                    page_number=page_number,
                    headers=headers,
                    rows=rows,
                    raw_cells=raw,
                ))
        return tables

    def parse_all(self, pdf_path: str) -> FinancialMetrics:
        """
        Parse all classified sections and return a complete FinancialMetrics.

        This is the main entry point. It discovers fiscal years from the
        document and extracts available metrics from classified pages.
        """
        metrics = FinancialMetrics()

        # Discover fiscal years from the document
        metrics.fiscal_years = self._detect_fiscal_years()

        # Parse each section
        income_pages = [p for p in self.pages
                        if p.section_type == FinancialSection.INCOME_STATEMENT]
        if income_pages:
            self._parse_metrics_from_pages(metrics, income_pages)

        # Extract tables from financial pages
        fin_pages = [p for p in self.pages
                     if p.section_type != FinancialSection.UNKNOWN
                     and p.digit_count >= 30]
        for page in fin_pages:
            try:
                tables = self.extract_tables_from_page(page.page_number, pdf_path)
                for t in tables:
                    self._ingest_table(metrics, t)
            except Exception:
                pass  # skip unparseable pages

        return metrics

    # ── Internal helpers ────────────────────────────────────────────────

    def _detect_fiscal_years(self) -> list[str]:
        """Detect which fiscal years are present in the document."""
        years: set[str] = set()
        for page in self.pages:
            found = YEAR_PATTERN.findall(page.text)
            years.update(y.replace('年', '') for y in found)
        return sorted(years, reverse=True)

    def _parse_metrics_from_pages(
        self,
        metrics: FinancialMetrics,
        pages: list[PageInfo],
    ) -> None:
        """Extract key metrics from page text using regex patterns."""
        all_text = "\n".join(p.text for p in pages)

        years = metrics.fiscal_years
        for year in years:
            # Revenue
            m = re.search(
                rf'收入.*?{year}.*?([\d,]+\.?\d*)\s*(?:百萬|百万|億元|亿元)',
                all_text
            )
            if not m:
                m = re.search(rf'總計.*?{year}.*?([\d,]+\.?\d*)', all_text)
            if m:
                metrics.revenue[year] = self.clean_number(m.group(1))

            # Gross margin
            m = re.search(
                rf'毛利率.*?{year}.*?([\d,]+\.?\d*)\s*%',
                all_text
            )
            if m:
                metrics.gross_margin[year] = float(m.group(1)) / 100

            # Net profit
            m = re.search(
                rf'(?:淨利潤|淨虧損|年內利潤|年內虧損).*?{year}.*?([\d,]+\.?\d*)',
                all_text
            )
            if m:
                val = self.clean_number(m.group(1))
                # Check if it's a loss (parenthesized)
                context = all_text[max(0, m.start()-50):m.end()]
                sign = -1 if any(kw in context for kw in ['虧損', '亏损']) else 1
                metrics.net_profit[year] = val * sign

    def _ingest_table(
        self,
        metrics: FinancialMetrics,
        table: ExtractedTable,
    ) -> None:
        """Try to ingest a pdfplumber table into metrics."""
        # Store as revenue breakdown if it looks like one
        header_text = " ".join(table.headers)
        if any(kw in header_text for kw in ['產品', '类别', '玩具', '文具']):
            for row in table.rows:
                if len(row) >= 3:
                    metrics.revenue_by_product.append({
                        "category": row[0],
                        "values": row[1:],
                        "page": table.page_number,
                    })

    @staticmethod
    def clean_number(value: str) -> float | None:
        """
        Clean Chinese-formatted numbers to Python float.

        Handles:
        - Parenthesized negatives: (1,234.5) → -1234.5
        - Chinese commas: 12,345.6 → 12345.6
        - Full-width characters
        - Percentage suffixes: 68.8% → 0.688
        """
        if not value:
            return None
        s = str(value).strip()
        # Remove full-width spaces
        s = s.replace('　', ' ').replace('\xa0', ' ')
        # Detect parenthesized negative
        is_negative = False
        if s.startswith('(') and s.endswith(')'):
            is_negative = True
            s = s[1:-1]
        elif s.startswith('（') and s.endswith('）'):
            is_negative = True
            s = s[1:-1]
        # Remove commas and spaces
        s = s.replace(',', '').replace('，', '').replace(' ', '')
        # Remove percentage sign
        s = s.replace('%', '')
        # Convert full-width digits to half-width
        fullwidth_map = str.maketrans(
            '０１２３４５６７８９．－',
            '0123456789.-'
        )
        s = s.translate(fullwidth_map)
        try:
            val = float(s)
        except ValueError:
            return None
        return -val if is_negative else val

    @staticmethod
    def extract_yearly_values(
        text: str,
        years: list[str],
    ) -> dict[str, str]:
        """
        Extract values associated with specific years from text.

        Finds number tokens near year references in the text.
        """
        results: dict[str, str] = {}
        for year in years:
            # Find year reference and next number
            m = re.search(
                rf'{year}.*?([\d,]+\.?\d*)',
                text
            )
            if m:
                results[year] = m.group(1)
        return results
