"""
Structured output formatters.

Converts FinancialMetrics and FinancialDocument into:
- Markdown tables (for skill analysis reports)
- JSON (for programmatic consumption)
- CSV (for spreadsheet analysis)
"""

import json
import csv
import io
from dataclasses import asdict

from .models import FinancialMetrics, FinancialDocument, PageInfo


class MarkdownOutput:
    """Formats FinancialMetrics into Markdown tables."""

    @staticmethod
    def format_metrics_summary(metrics: FinancialMetrics) -> str:
        """Generate a core financial metrics summary table."""
        years = metrics.fiscal_years
        if not years:
            return "*No fiscal years detected.*"

        lines = ["## 核心财务指标\n"]
        lines.append("| 指标 | " + " | ".join(f"{y}年" for y in years) + " |")
        lines.append("|------|" + "|".join(":------:" for _ in years) + "|")

        def row(label: str, data: dict, fmt: str = ".1f"):
            vals = []
            for y in years:
                v = data.get(y)
                if v is None:
                    vals.append("-")
                else:
                    vals.append(f"{v:{fmt}}")
            lines.append(f"| {label} | " + " | ".join(vals) + " |")

        row("收入（百万元）", metrics.revenue)
        row("毛利（百万元）", metrics.gross_profit)
        row_margin = "| 毛利率 | " + " | ".join(
            f"{metrics.gross_margin.get(y, 0)*100:.1f}%" if metrics.gross_margin.get(y) else "-"
            for y in years
        ) + " |"
        lines.append(row_margin)
        row("经营利润（百万元）", metrics.operating_profit)
        row("净利润（百万元）", metrics.net_profit)
        row("经调整净利润（百万元）", metrics.adjusted_net_profit)
        row("总资产（百万元）", metrics.total_assets)
        row("现金及等价物（百万元）", metrics.cash_and_equivalents)
        row("存货（百万元）", metrics.inventory)
        row("经营性现金流（百万元）", metrics.operating_cash_flow)

        return "\n".join(lines)

    @staticmethod
    def format_revenue_breakdown(metrics: FinancialMetrics) -> str:
        """Format revenue by product/channel as a Markdown table."""
        if not metrics.revenue_by_product:
            return ""

        lines = ["## 收入结构\n"]
        for entry in metrics.revenue_by_product:
            cat = entry.get("category", "")
            vals = entry.get("values", [])
            if cat and vals:
                lines.append(f"- **{cat}**: " + " | ".join(vals))
        return "\n".join(lines)

    @staticmethod
    def format_document_summary(doc: FinancialDocument) -> str:
        """Format document metadata summary."""
        lines = [
            f"**PDF文件**: {doc.pdf_path}",
            f"**总页数**: {doc.total_pages}",
            f"**提取引擎**: {doc.extraction_backend.value}",
            f"**已提取页数**: {len(doc.pages)}",
        ]
        return "\n".join(lines)

    @staticmethod
    def format_section_summary(summary: dict[str, list[int]]) -> str:
        """Format section-to-pages mapping."""
        lines = ["## 章节页面映射\n"]
        for section_name, page_nums in summary.items():
            pages_str = ", ".join(str(p) for p in page_nums[:10])
            if len(page_nums) > 10:
                pages_str += f" ... (共{len(page_nums)}页)"
            lines.append(f"- **{section_name}**: {pages_str}")
        return "\n".join(lines)

    @staticmethod
    def format_report_stub(metrics: FinancialMetrics) -> str:
        """
        Generate an analysis report stub following the skill's 4-step format:
        1. 企业概况
        2. 核心指标表
        3. 竞争力分析（待填充）
        4. 风险预警点（待填充）
        """
        lines = [
            "# 企业财务分析报告（自动生成基础数据）",
            "",
            "## 一、企业概况",
            "",
            "*(根据PDF文本内容手动/LLM填充)*",
            "",
            MarkdownOutput.format_metrics_summary(metrics),
            "",
            MarkdownOutput.format_revenue_breakdown(metrics),
            "",
            "## 三、竞争力分析（护城河）",
            "",
            "*(待分析)*",
            "",
            "## 四、风险预警点",
            "",
            "*(待识别)*",
        ]
        return "\n".join(lines)


class JSONOutput:
    """Machine-readable JSON output."""

    @staticmethod
    def to_json(metrics: FinancialMetrics, indent: int = 2) -> str:
        """Serialize FinancialMetrics to JSON string."""
        d = JSONOutput.to_dict(metrics)
        return json.dumps(d, ensure_ascii=False, indent=indent, default=str)

    @staticmethod
    def to_dict(metrics: FinancialMetrics) -> dict:
        """Convert FinancialMetrics to plain dict."""
        d = asdict(metrics)
        # Remove empty source_texts to keep JSON lean
        d.pop('source_texts', None)
        return d


class CSVOutput:
    """CSV export for spreadsheet analysis."""

    @staticmethod
    def metrics_to_csv(metrics: FinancialMetrics) -> str:
        """Export key metrics as CSV string."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        years = metrics.fiscal_years

        writer.writerow(["指标"] + [f"{y}年" for y in years])

        numeric_fields = [
            ("收入", metrics.revenue),
            ("毛利", metrics.gross_profit),
            ("毛利率", metrics.gross_margin),
            ("经营利润", metrics.operating_profit),
            ("净利润", metrics.net_profit),
            ("经调整净利润", metrics.adjusted_net_profit),
            ("总资产", metrics.total_assets),
            ("总负债", metrics.total_liabilities),
            ("权益总额", metrics.total_equity),
            ("现金及等价物", metrics.cash_and_equivalents),
            ("存货", metrics.inventory),
            ("经营性现金流", metrics.operating_cash_flow),
            ("投资性现金流", metrics.investing_cash_flow),
            ("融资性现金流", metrics.financing_cash_flow),
        ]

        for label, data in numeric_fields:
            row_vals = [label]
            for y in years:
                v = data.get(y)
                row_vals.append(f"{v:.2f}" if v is not None else "")
            writer.writerow(row_vals)

        return buf.getvalue()

    @staticmethod
    def pages_to_csv(pages: list[PageInfo]) -> str:
        """Export page classification results as CSV."""
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["页码", "章节类型", "置信度", "字符数", "数字数", "关键词命中"])

        for p in pages:
            writer.writerow([
                p.page_number,
                p.section_type.value,
                f"{p.confidence_score:.2f}",
                p.char_count,
                p.digit_count,
                ";".join(p.keyword_hits[:5]),
            ])

        return buf.getvalue()
