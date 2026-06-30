"""
Financial section auto-detection for Chinese PDF documents.

Scans extracted pages and classifies them into FinancialSection types
using a two-pass approach:
  1. Fast pre-filter: digit count threshold (eliminates text-only pages)
  2. Keyword scoring: match against categorized keyword dictionaries
"""

from .keywords import FINANCIAL_KEYWORDS, ALL_FINANCIAL_KEYWORDS, MIN_FINANCIAL_DIGIT_THRESHOLD
from .models import PageInfo, FinancialSection


class FinancialScanner:
    """
    Scans PDF pages to identify and classify financial statement sections.

    Usage:
        scanner = FinancialScanner(pages)
        classified_pages = scanner.scan_and_classify()
        income_pages = scanner.find_section_pages(FinancialSection.INCOME_STATEMENT)
    """

    def __init__(self, pages: list[PageInfo]):
        self.pages = pages
        self._section_map: dict[str, FinancialSection] = {
            "income_statement": FinancialSection.INCOME_STATEMENT,
            "balance_sheet": FinancialSection.BALANCE_SHEET,
            "cash_flow": FinancialSection.CASH_FLOW,
            "revenue_breakdown": FinancialSection.REVENUE_BREAKDOWN,
            "cost_structure": FinancialSection.COST_STRUCTURE,
            "gross_margin": FinancialSection.MARGIN_ANALYSIS,
            "business_overview": FinancialSection.BUSINESS_OVERVIEW,
            "risk_factors": FinancialSection.RISK_FACTORS,
            "equity_structure": FinancialSection.EQUITY_STRUCTURE,
            "expenses": FinancialSection.EXPENSES,
        }

    # ── Public API ─────────────────────────────────────────────────────

    def classify_page(self, page: PageInfo) -> PageInfo:
        """
        Classify a single page into a FinancialSection based on keyword scoring.

        Algorithm:
        1. For each section, count keyword hits and normalize by section size
        2. Use digit density as confidence adjuster
        3. Pick highest-scoring section above threshold
        """
        if not page.text or len(page.text.strip()) < 20:
            return page

        digit_density = page.digit_count / max(page.char_count, 1)
        best_section = FinancialSection.UNKNOWN
        best_score = 0.0
        best_hits: list[str] = []

        for section_key, keywords in FINANCIAL_KEYWORDS.items():
            hits = [kw for kw in keywords if kw in page.text]
            if not hits:
                continue
            # Normalized score: hit ratio * section weight
            hit_ratio = len(hits) / len(keywords)
            # Boost score for pages with high digit density (financial tables)
            score = hit_ratio * (1.0 + digit_density * 3)
            if score > best_score:
                best_score = score
                best_section = self._section_map[section_key]
                best_hits = hits

        # Confidence threshold: require at least 2 keyword hits or digit density > 2%
        if best_section != FinancialSection.UNKNOWN and (
            len(best_hits) >= 2 or digit_density > 0.02
        ):
            page.section_type = best_section
            page.keyword_hits = best_hits
            page.confidence_score = min(best_score, 1.0)
        else:
            # Still mark as financial page if digit-heavy
            if page.digit_count >= MIN_FINANCIAL_DIGIT_THRESHOLD:
                page.confidence_score = min(digit_density * 10, 0.5)

        return page

    def scan_and_classify(self) -> list[PageInfo]:
        """Classify all pages in the document. Returns updated list."""
        for page in self.pages:
            self.classify_page(page)
        return self.pages

    def find_section_pages(
        self,
        section: FinancialSection,
        min_confidence: float = 0.0,
    ) -> list[PageInfo]:
        """Return all pages classified as a given section type."""
        return [
            p for p in self.pages
            if p.section_type == section and p.confidence_score >= min_confidence
        ]

    def find_financial_pages(self, min_digit_count: int = 30) -> list[PageInfo]:
        """
        Fast pre-filter: return pages likely containing financial data
        based on digit count heuristic. Does not require full classification.
        """
        return [p for p in self.pages if p.digit_count >= min_digit_count]

    def get_section_summary(self) -> dict[str, list[int]]:
        """
        Return a summary of which pages contain which sections.

        Example:
            {"income_statement": [290, 291, ...], "balance_sheet": [295, ...]}
        """
        summary: dict[str, list[int]] = {}
        for page in self.pages:
            if page.section_type != FinancialSection.UNKNOWN:
                key = page.section_type.value
                summary.setdefault(key, []).append(page.page_number)
        return summary

    @staticmethod
    def score_page_for_financial_data(page: PageInfo) -> float:
        """
        Score a page 0-1 for how likely it contains structured financial data.
        Composite: digit density + keyword density.
        """
        if page.char_count == 0:
            return 0.0
        digit_density = page.digit_count / page.char_count
        kw_hits = sum(
            1 for kw in ALL_FINANCIAL_KEYWORDS if kw in page.text
        )
        kw_density = kw_hits / max(page.char_count / 100, 1)
        score = min(digit_density * 8 + kw_density * 0.5, 1.0)
        return score
