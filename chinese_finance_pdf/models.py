"""
Data models for the Chinese financial PDF analysis toolkit.

Uses dataclasses for type-safe, structured representation of
extracted pages, tables, documents, and financial metrics.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ExtractionBackend(Enum):
    PDFPLUMBER = "pdfplumber"
    PYPDF2 = "pypdf2"


class FinancialSection(Enum):
    INCOME_STATEMENT = "income_statement"
    BALANCE_SHEET = "balance_sheet"
    CASH_FLOW = "cash_flow"
    REVENUE_BREAKDOWN = "revenue_breakdown"
    COST_STRUCTURE = "cost_structure"
    MARGIN_ANALYSIS = "margin_analysis"
    BUSINESS_OVERVIEW = "business_overview"
    RISK_FACTORS = "risk_factors"
    EQUITY_STRUCTURE = "equity_structure"
    EXPENSES = "expenses"
    UNKNOWN = "unknown"


@dataclass
class PageInfo:
    """Metadata about a single extracted PDF page."""
    page_number: int           # 1-based
    text: str
    char_count: int = 0
    digit_count: int = 0
    section_type: FinancialSection = FinancialSection.UNKNOWN
    keyword_hits: list[str] = field(default_factory=list)
    confidence_score: float = 0.0

    def __post_init__(self):
        if self.char_count == 0:
            self.char_count = len(self.text)
        if self.digit_count == 0:
            self.digit_count = sum(c.isdigit() for c in self.text)


@dataclass
class ExtractedTable:
    """A table extracted from a PDF page."""
    page_number: int
    headers: list[str]
    rows: list[list[str]]
    section_type: FinancialSection = FinancialSection.UNKNOWN
    raw_cells: list[list[str | None]] = field(default_factory=list)


@dataclass
class FinancialDocument:
    """The complete extracted financial document."""
    pdf_path: str
    total_pages: int
    pages: list[PageInfo] = field(default_factory=list)
    tables: list[ExtractedTable] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    extraction_backend: ExtractionBackend = ExtractionBackend.PDFPLUMBER


@dataclass
class FinancialMetrics:
    """
    Key financial metrics extracted and structured.

    All numeric values are in RMB 百万元 (millions) unless noted.
    Dictionary keys are fiscal year strings like "2022", "2023", "2024".
    """
    # ── Top-line metrics ──────────────────────────────────────────
    revenue: dict[str, float | None] = field(default_factory=dict)
    revenue_yoy: dict[str, float | None] = field(default_factory=dict)
    gross_profit: dict[str, float | None] = field(default_factory=dict)
    gross_margin: dict[str, float | None] = field(default_factory=dict)
    operating_profit: dict[str, float | None] = field(default_factory=dict)
    net_profit: dict[str, float | None] = field(default_factory=dict)
    adjusted_net_profit: dict[str, float | None] = field(default_factory=dict)
    adjusted_net_margin: dict[str, float | None] = field(default_factory=dict)

    # ── Balance sheet ─────────────────────────────────────────────
    total_assets: dict[str, float | None] = field(default_factory=dict)
    total_liabilities: dict[str, float | None] = field(default_factory=dict)
    total_equity: dict[str, float | None] = field(default_factory=dict)
    cash_and_equivalents: dict[str, float | None] = field(default_factory=dict)
    inventory: dict[str, float | None] = field(default_factory=dict)
    trade_receivables: dict[str, float | None] = field(default_factory=dict)
    trade_payables: dict[str, float | None] = field(default_factory=dict)

    # ── Cash flow ─────────────────────────────────────────────────
    operating_cash_flow: dict[str, float | None] = field(default_factory=dict)
    investing_cash_flow: dict[str, float | None] = field(default_factory=dict)
    financing_cash_flow: dict[str, float | None] = field(default_factory=dict)

    # ── Breakdowns (list of dicts keyed by category) ──────────────
    revenue_by_product: list[dict[str, Any]] = field(default_factory=list)
    revenue_by_channel: list[dict[str, Any]] = field(default_factory=list)
    cost_components: list[dict[str, Any]] = field(default_factory=list)
    expense_breakdown: list[dict[str, Any]] = field(default_factory=list)

    # ── Expense ratios ────────────────────────────────────────────
    sales_marketing_ratio: dict[str, float | None] = field(default_factory=dict)
    admin_expense_ratio: dict[str, float | None] = field(default_factory=dict)
    rd_expense_ratio: dict[str, float | None] = field(default_factory=dict)

    # ── Efficiency metrics ────────────────────────────────────────
    inventory_turnover_days: dict[str, float | None] = field(default_factory=dict)
    receivables_turnover_days: dict[str, float | None] = field(default_factory=dict)

    # ── Metadata ──────────────────────────────────────────────────
    fiscal_years: list[str] = field(default_factory=list)
    currency_unit: str = "人民币百万元"
    source_texts: dict[str, str] = field(default_factory=dict)
