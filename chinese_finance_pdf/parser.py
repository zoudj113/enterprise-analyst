"""
Structured financial data parser.

Takes classified PageInfo objects and extracts structured
FinancialMetrics using regex-based multi-column line parsing
and pdfplumber table extraction.
"""

import re
from collections import Counter
from pathlib import Path

from .models import (
    PageInfo, ExtractedTable, FinancialSection, FinancialMetrics,
)
from .keywords import (
    YEAR_PATTERN, FISCAL_YEAR_HEADING_PATTERN, YEAR_COLUMNS_PATTERN
)


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
        """Use pdfplumber's table extraction on a specific page.

        Falls back to text-based line parsing if no bordered tables found."""
        import pdfplumber

        tables: list[ExtractedTable] = []
        with pdfplumber.open(pdf_path) as pdf:
            if page_number < 1 or page_number > len(pdf.pages):
                return tables
            page = pdf.pages[page_number - 1]

            # Try bordered table extraction first
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

            # Fallback: text-based multi-column line parsing
            if not tables:
                text = page.extract_text()
                if text:
                    parsed = self._parse_text_as_table(text, page_number)
                    if parsed:
                        tables.append(parsed)
        return tables

    def parse_all(self, pdf_path: str) -> FinancialMetrics:
        """
        Parse all classified sections and return a complete FinancialMetrics.

        This is the main entry point. It discovers fiscal years from the
        document and extracts available metrics from classified pages.
        """
        metrics = FinancialMetrics()

        # Discover fiscal years from financial statement pages only
        metrics.fiscal_years = self._detect_fiscal_years()

        # Parse income statement pages
        income_pages = [p for p in self.pages
                        if p.section_type == FinancialSection.INCOME_STATEMENT]
        if income_pages:
            self._parse_metrics_from_pages(metrics, income_pages)

        # Parse balance sheet pages
        bs_pages = [p for p in self.pages
                    if p.section_type == FinancialSection.BALANCE_SHEET]
        if bs_pages:
            self._parse_balance_sheet(metrics, bs_pages)

        # Parse cash flow pages
        cf_pages = [p for p in self.pages
                    if p.section_type == FinancialSection.CASH_FLOW]
        if cf_pages:
            self._parse_cash_flow(metrics, cf_pages)

        # Parse revenue breakdown pages
        rev_pages = [p for p in self.pages
                     if p.section_type == FinancialSection.REVENUE_BREAKDOWN]
        if rev_pages:
            self._parse_revenue_breakdown(metrics, rev_pages)

        # Extract tables from high-digit-count financial pages
        fin_pages = [p for p in self.pages
                     if p.section_type != FinancialSection.UNKNOWN
                     and p.digit_count >= 30]
        for page in fin_pages[:50]:  # Limit to avoid excessive I/O
            try:
                tables = self.extract_tables_from_page(page.page_number, pdf_path)
                for t in tables:
                    self._ingest_table(metrics, t)
            except Exception:
                pass

        return metrics

    # ── Year detection ─────────────────────────────────────────────────

    def _detect_fiscal_years(self) -> list[str]:
        """
        Detect fiscal years from the document's summary section.

        The most reliable fiscal year signal is in the document's overview/summary
        (usually first ~30 pages), where column headers like "2023年 2024年 2025年"
        appear above the key financial tables.

        Strategy:
        1. Scan ONLY pages 1-30 (summary section) for year column clusters
        2. Also check pages classified as INCOME_STATEMENT in top 30 pages
        3. Return the most frequent contiguous block of 2-4 years
        """
        col_year_counter: Counter = Counter()

        # Focus on summary pages (first 30) + early financial pages
        for page in self.pages[:30]:
            text = page.text

            # Look for year column clusters on the same line
            # e.g. "2023年        2024年        2025年"
            for line in text.split('\n'):
                for m in YEAR_COLUMNS_PATTERN.finditer(line):
                    years = [y.replace('年', '') for y in YEAR_PATTERN.findall(m.group(1))]
                    if 2 <= len(years) <= 5:
                        for y in years:
                            col_year_counter[y] += 3

            # Also check fiscal year headings
            for m in FISCAL_YEAR_HEADING_PATTERN.finditer(text):
                years = [y.replace('年', '') for y in YEAR_PATTERN.findall(m.group(1))]
                for y in years:
                    col_year_counter[y] += 5

        if not col_year_counter:
            return []

        # Find the best contiguous block of 2-4 years
        sorted_years = sorted(col_year_counter.keys())
        best_block: list[str] = []
        best_score = 0

        for i in range(len(sorted_years)):
            for j in range(i + 2, min(i + 5, len(sorted_years) + 1)):
                block = sorted_years[i:j]
                if all(int(block[k+1]) == int(block[k]) + 1 for k in range(len(block)-1)):
                    score = sum(col_year_counter.get(y, 0) for y in block)
                    # Bonus for being recent (2020+)
                    if int(block[0]) >= 2020:
                        score *= 2
                    if score > best_score:
                        best_score = score
                        best_block = block

        if not best_block:
            best_block = [y for y, _ in col_year_counter.most_common(3)]
            best_block.sort()

        return best_block

    # ── Multi-column line parsing ───────────────────────────────────────

    def _parse_multicolumn_line(
        self, line: str, years: list[str]
    ) -> dict[str, list[float | None]]:
        """
        Parse a line with the prospectus's multi-column number format.

        Format: "label ............ value1% value2% value3%"
        Where each year has an absolute value and optionally a percentage.

        Returns: {year: [absolute_value, percentage_or_None], ...}
        """
        result: dict[str, list[float | None]] = {}

        # Remove leading label (up to the dots or first number)
        # Find where the numbers start
        num_match = re.search(r'[\d,(（-]\s*[\d,]+', line)
        if not num_match:
            return result

        numbers_part = line[num_match.start():]

        # Extract all numbers from the numbers part
        # Pattern: optional parenthesized negative, then digits with commas
        all_numbers = []
        for m in re.finditer(
            r'([（(]\s*[\d,]+\.?\d*\s*[）)])|(-?[\d,]+\.?\d*)',
            numbers_part
        ):
            val_str = m.group(0)
            # Check if parenthesized (negative)
            is_neg = False
            if val_str.startswith('(') or val_str.startswith('（'):
                is_neg = True
                val_str = val_str[1:-1]
            val = self.clean_number(val_str)
            if val is not None:
                all_numbers.append(-val if is_neg else val)

        if not all_numbers:
            return result

        # Determine if there are percentages mixed in using heuristics
        n_years = len(years)
        n_vals = len(all_numbers)

        # Heuristic: detect (value, percentage) pairs pattern
        # Pairs mode when: (a) exactly 2N numbers, OR (b) odd-indexed values
        # are small (likely percentages)
        evens = [all_numbers[i] for i in range(0, n_vals, 2)]
        odds = [all_numbers[i] for i in range(1, n_vals, 2)]
        avg_odd = sum(abs(v) for v in odds) / len(odds) if odds else 0
        avg_even = sum(abs(v) for v in evens) / len(evens) if evens else 1
        looks_like_pairs = (
            odds and (avg_odd < 100 or avg_odd / max(avg_even, 1) < 0.5)
        )

        if n_vals >= n_years * 2:
            # Clear pairs: 2N numbers → (absolute, %) for each year
            for i, year in enumerate(years):
                idx = i * 2
                if idx + 1 < n_vals:
                    result[year] = [all_numbers[idx], all_numbers[idx + 1]]
                elif idx < n_vals:
                    result[year] = [all_numbers[idx], None]
        elif looks_like_pairs and n_vals >= 4:
            # e.g. 6 numbers for 4 years → 3 pairs mapped to first 3 years
            effective_years = min(n_years, n_vals // 2)
            for i in range(effective_years):
                year = years[i]
                idx = i * 2
                result[year] = [all_numbers[idx],
                                all_numbers[idx + 1] if idx + 1 < n_vals else None]
        elif n_vals >= n_years:
            # Just absolute values, one per year
            for i, year in enumerate(years):
                if i < n_vals:
                    result[year] = [all_numbers[i], None]
        else:
            # Fewer numbers than years: map what we can
            for i in range(min(n_years, n_vals)):
                result[years[i]] = [all_numbers[i], None]

        return result

    def _find_metric_in_text(
        self, text: str, labels: list[str], years: list[str]
    ) -> dict[str, dict[str, list[float | None]]]:
        """
        Search text for lines matching given labels and parse multi-column numbers.

        Returns: {label_key: {year: [value, percentage], ...}, ...}
        """
        results: dict[str, dict[str, list[float | None]]] = {}
        lines = text.split('\n')

        for line in lines:
            for label in labels:
                if label in line:
                    parsed = self._parse_multicolumn_line(line, years)
                    if parsed:
                        results[label] = parsed
                    break
        return results

    # ── Section parsers ─────────────────────────────────────────────────

    def _parse_metrics_from_pages(
        self, metrics: FinancialMetrics, pages: list[PageInfo]
    ) -> None:
        """Extract income statement metrics from classified pages.

        Prioritizes pages from the summary section (first 30 pages) and
        pages with higher digit counts (more complete financial data).
        """
        # Sort: summary pages first, then by digit_count descending
        sorted_pages = sorted(
            pages,
            key=lambda p: (
                0 if p.page_number <= 30 else 1,
                -p.digit_count
            )
        )
        all_text = "\n".join(p.text for p in sorted_pages)
        years = metrics.fiscal_years
        if not years:
            return

        # Track which metrics have been filled to avoid overwriting with worse data
        filled: set[str] = set()

        # Income statement metric labels to search for
        metric_labels = {
            'revenue': ['收入', '總收入'],
            'gross_profit': ['毛利'],
            'operating_profit': ['經營利潤', '經營利潤╱', '經營溢利'],
            'net_profit': ['年內利潤', '年內溢利', '淨利潤'],
            'finance_cost': ['融資成本', '財務成本'],
            'income_tax': ['所得稅'],
            'sales_expense': ['銷售開支', '銷售及分銷'],
            'admin_expense': ['一般及行政開支', '行政開支', '管理費用'],
            'rd_expense': ['研發成本', '研發開支', '研發費用'],
        }

        for line in all_text.split('\n'):
            line = line.strip()
            if not line or len(line) < 20:
                continue

            # Revenue
            if any(kw in line for kw in ['收入', '總收入']) and \
               not any(kw in line for kw in ['其他收入', '收入佔', '收入結構', '收入明細']):
                parsed = self._parse_multicolumn_line(line, years)
                if parsed and len(parsed) >= len(years) - 1 and 'revenue' not in filled:
                    rev_count = 0
                    for yr, vals in parsed.items():
                        if vals[0] is not None and vals[0] > 100:  # > 100 百万 to filter Q1
                            metrics.revenue[yr] = vals[0] / 1_000
                            rev_count += 1
                    if rev_count >= 2:
                        filled.add('revenue')

            # Gross profit
            if '毛利' in line and '毛利率' not in line:
                parsed = self._parse_multicolumn_line(line, years)
                if parsed and 'gross_profit' not in filled:
                    gp_count = 0
                    for yr, vals in parsed.items():
                        if vals[0] is not None and abs(vals[0]) > 100:
                            metrics.gross_profit[yr] = vals[0] / 1_000
                            gp_count += 1
                    if gp_count >= 2:
                        filled.add('gross_profit')

            # Gross margin
            if '毛利率' in line:
                parsed = self._parse_multicolumn_line(line, years)
                if parsed:
                    for yr, vals in parsed.items():
                        # Percentage might be in vals[0] or vals[1]
                        pct = vals[0] if vals[0] and vals[0] < 100 else \
                              (vals[1] if len(vals) > 1 and vals[1] and vals[1] < 100 else None)
                        if pct is not None:
                            metrics.gross_margin[yr] = pct / 100

            # Operating profit
            if any(kw in line for kw in ['經營利潤', '經營溢利']) and \
               '應佔' not in line:
                parsed = self._parse_multicolumn_line(line, years)
                if parsed and 'operating_profit' not in filled:
                    for yr, vals in parsed.items():
                        if vals[0] is not None:
                            metrics.operating_profit[yr] = vals[0] / 1_000
                    filled.add('operating_profit')

            # Net profit
            if any(kw in line for kw in ['年內利潤', '年內溢利', '淨利潤']) and \
               '應佔' not in line and '母公司' not in line:
                parsed = self._parse_multicolumn_line(line, years)
                if parsed and 'net_profit' not in filled:
                    for yr, vals in parsed.items():
                        if vals[0] is not None and abs(vals[0]) > 50:
                            metrics.net_profit[yr] = vals[0] / 1_000
                    filled.add('net_profit')

            # Sales expense ratio
            if any(kw in line for kw in ['銷售開支', '銷售及分銷']):
                parsed = self._parse_multicolumn_line(line, years)
                if parsed:
                    for yr, vals in parsed.items():
                        pct = vals[1] if len(vals) > 1 and vals[1] and vals[1] < 100 else None
                        if pct is not None:
                            metrics.sales_marketing_ratio[yr] = pct / 100

            # Admin expense ratio
            if any(kw in line for kw in ['一般及行政開支', '行政開支']):
                parsed = self._parse_multicolumn_line(line, years)
                if parsed:
                    for yr, vals in parsed.items():
                        pct = vals[1] if len(vals) > 1 and vals[1] and vals[1] < 100 else None
                        if pct is not None:
                            metrics.admin_expense_ratio[yr] = pct / 100

            # R&D expense ratio
            if any(kw in line for kw in ['研發成本', '研發開支']):
                parsed = self._parse_multicolumn_line(line, years)
                if parsed:
                    for yr, vals in parsed.items():
                        pct = vals[1] if len(vals) > 1 and vals[1] and vals[1] < 100 else None
                        if pct is not None:
                            metrics.rd_expense_ratio[yr] = pct / 100

    def _parse_balance_sheet(
        self, metrics: FinancialMetrics, pages: list[PageInfo]
    ) -> None:
        """Extract balance sheet metrics. Prioritizes summary pages."""
        sorted_pages = sorted(
            pages,
            key=lambda p: (0 if p.page_number <= 30 else 1, -p.digit_count)
        )
        all_text = "\n".join(p.text for p in sorted_pages)
        years = metrics.fiscal_years
        if not years:
            return

        for line in all_text.split('\n'):
            line = line.strip()
            if len(line) < 20:
                continue

            parsed = self._parse_multicolumn_line(line, years)
            if not parsed:
                continue

            assign = lambda field: [
                metrics.__setattr__(field,
                    {**getattr(metrics, field), yr: vals[0] / 1_000})
                for yr, vals in parsed.items() if vals[0] is not None
            ]

            if '資產總額' in line or '總資產' in line:
                assign('total_assets')
            elif '負債總額' in line or '總負債' in line:
                assign('total_liabilities')
            elif '權益總額' in line or '淨資產總額' in line or '資產淨額' in line:
                assign('total_equity')
            elif '現金及現金等價物' in line:
                assign('cash_and_equivalents')
            elif '存貨' in line and '合約成本' in line:
                assign('inventory')
            elif '貿易應收款項及應收票據' in line:
                assign('trade_receivables')
            elif '貿易應付款項及應付票據' in line:
                assign('trade_payables')

    def _parse_cash_flow(
        self, metrics: FinancialMetrics, pages: list[PageInfo]
    ) -> None:
        """Extract cash flow statement metrics. Prioritizes summary pages."""
        sorted_pages = sorted(
            pages,
            key=lambda p: (0 if p.page_number <= 30 else 1, -p.digit_count)
        )
        all_text = "\n".join(p.text for p in sorted_pages)
        years = metrics.fiscal_years
        if not years:
            return

        for line in all_text.split('\n'):
            line = line.strip()
            if len(line) < 20:
                continue

            parsed = self._parse_multicolumn_line(line, years)
            if not parsed:
                continue

            assign = lambda field: [
                metrics.__setattr__(field,
                    {**getattr(metrics, field), yr: vals[0] / 1_000})
                for yr, vals in parsed.items() if vals[0] is not None
            ]

            if '經營活動所得' in line or '經營活動現金' in line or '經營活動所得現金流量淨額' in line:
                assign('operating_cash_flow')
            elif '投資活動所用' in line or '投資活動現金' in line or '投資活動所用現金流量淨額' in line:
                assign('investing_cash_flow')
            elif '融資活動所得' in line or '融資活動現金' in line or '融資活動所得現金流量淨額' in line:
                assign('financing_cash_flow')

    def _parse_revenue_breakdown(
        self, metrics: FinancialMetrics, pages: list[PageInfo]
    ) -> None:
        """Extract revenue breakdown by product/business segment."""
        all_text = "\n".join(p.text for p in pages)
        years = metrics.fiscal_years
        if not years:
            return

        # Look for product revenue lines
        # Format: "产品名 ............... value% value% value%"
        segment_keywords = [
            '氯鹼', '碳三碳四', '濕電子', '電子級',
            '燒鹼', '環氧丙烷', 'MTBE',
            '環氧氯丙烷', '氯丙烯', '三氯乙烯', '四氯乙烯',
            '丙烷', '丙烯', '能源', '電力', '蒸汽',
            '化學品', '新材料',
        ]

        seen_categories: set[str] = set()

        for line in all_text.split('\n'):
            line = line.strip()
            if len(line) < 25:
                continue

            # Check if line looks like a product revenue line
            has_segment = any(kw in line for kw in segment_keywords)
            if not has_segment:
                continue

            # Skip lines that are clearly not revenue data
            if any(skip in line for skip in [
                '產能', '利用率', '下游', '說明', '預計', '複合年增長率',
                '由', '增長至', '增加至', '減少至', '達', '將達',
                'CAGR', '市場', '行業', '中國', '全球',
                '附註', '定義', '包括', '主要', '應用',
                '發明', '實用新型', '專利', '安全生產', '危險化學品',
                '董事', '副總裁', '總經理',
            ]):
                continue

            parsed = self._parse_multicolumn_line(line, years)
            if parsed and len(parsed) >= 1:
                # Check at least one value is substantial (> 1000 for 千元 units)
                max_val = max(
                    (abs(vals[0]) for vals in parsed.values() if vals[0] is not None),
                    default=0
                )
                if max_val < 1000:
                    continue

                # Extract the category name (part before the dots/numbers)
                name_match = re.match(r'^[－\-\s]*([^\d.]+?)[.\s]{4,}', line)
                if not name_match:
                    name_match = re.match(r'^([^\d]+?)\s+[\d,（(]', line)

                cat_name = name_match.group(1).strip() if name_match else line[:30].strip()
                # Clean up
                cat_name = cat_name.rstrip('.. .．。').strip()

                # Deduplicate by category name
                dedup_key = cat_name[:15]
                if dedup_key in seen_categories:
                    continue
                seen_categories.add(dedup_key)

                metrics.revenue_by_product.append({
                    "category": cat_name,
                    "values": [f"{parsed.get(yr, [None])[0]:,.0f}"
                              if parsed.get(yr) and parsed[yr][0] else "-"
                              for yr in years],
                    "page": pages[0].page_number if pages else 0,
                })

    def _parse_text_as_table(
        self, text: str, page_number: int
    ) -> ExtractedTable | None:
        """Try to parse plain text as a table using multi-column line heuristics."""
        lines = [l.strip() for l in text.split('\n') if l.strip()]

        # Find lines with consistent number patterns
        data_lines = []
        for line in lines:
            numbers = re.findall(r'[\d,]+\.?\d*', line)
            if len(numbers) >= 3:  # At least 3 numbers (for 3 years)
                data_lines.append(line)

        if len(data_lines) < 3:
            return None

        # Build a pseudo-table
        headers = ["项目"]
        # Try to detect years from the text
        year_matches = YEAR_PATTERN.findall(text)
        if year_matches:
            headers.extend(year_matches[:6])  # Max 6 year columns
        else:
            headers.extend(["数值1", "数值2", "数值3"])

        rows = []
        for line in data_lines[:30]:  # Limit rows
            # Split on multiple dots or large whitespace
            parts = re.split(r'\.{3,}|\s{3,}', line)
            if len(parts) >= 2:
                rows.append([p.strip() for p in parts])

        if not rows:
            return None

        return ExtractedTable(
            page_number=page_number,
            headers=headers,
            rows=rows,
        )

    # ── Table ingestion ─────────────────────────────────────────────────

    def _ingest_table(
        self,
        metrics: FinancialMetrics,
        table: ExtractedTable,
    ) -> None:
        """
        Try to ingest a table into metrics.

        Generic approach: identify financial metric rows by keyword matching
        in the first column, and extract numbers from subsequent columns.
        """
        header_text = " ".join(table.headers)
        years = metrics.fiscal_years

        # Detect if this is a revenue/product breakdown table
        is_revenue_table = any(
            kw in header_text
            for kw in ['產品', '收入', '類別', '类别', '板块', '板塊', '分部']
        )

        # Detect if it's a financial statement table
        is_financial_table = any(
            kw in header_text
            for kw in ['人民幣', '人民币', '千元', '百萬', '百万', '佔收入', '占收入', '%']
        )

        for row in table.rows:
            if len(row) < 2:
                continue

            label = row[0].strip() if row[0] else ""
            values = row[1:]

            if is_revenue_table and label:
                metrics.revenue_by_product.append({
                    "category": label,
                    "values": values[:len(years)] if years else values,
                    "page": table.page_number,
                })
            elif is_financial_table and label:
                # Store as cost component or expense item
                if any(kw in label for kw in ['成本', '費用', '開支', '支出']):
                    metrics.cost_components.append({
                        "category": label,
                        "values": values[:len(years)] if years else values,
                        "page": table.page_number,
                    })

    # ── Utility ─────────────────────────────────────────────────────────

    @staticmethod
    def clean_number(value: str) -> float | None:
        """
        Clean Chinese-formatted numbers to Python float.

        Handles:
        - Parenthesized negatives: (1,234.5) → -1234.5
        - Chinese commas: 12,345.6 → 12345.6
        - Full-width characters
        - Percentage suffixes: 68.8% → 68.8 (caller should /100 if needed)
        """
        if not value:
            return None
        s = str(value).strip()
        s = s.replace('　', ' ').replace('\xa0', ' ')

        # Detect parenthesized negative
        is_negative = False
        if s.startswith('(') and s.endswith(')'):
            is_negative = True
            s = s[1:-1]
        elif s.startswith('（') and s.endswith('）'):
            is_negative = True
            s = s[1:-1]

        s = s.replace(',', '').replace('，', '').replace(' ', '')
        s = s.replace('%', '')

        # Full-width to half-width
        fw_map = str.maketrans(
            '０１２３４５６７８９．－',
            '0123456789.-'
        )
        s = s.translate(fw_map)

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
            m = re.search(
                rf'{year}.*?([\d,]+\.?\d*)',
                text
            )
            if m:
                results[year] = m.group(1)
        return results
