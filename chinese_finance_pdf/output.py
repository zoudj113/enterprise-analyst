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
            return "*未检测到财务年度。*\n"

        lines = ["## 核心财务指标\n"]
        lines.append("| 指标 | " + " | ".join(f"{y}年" for y in years) + " |")
        lines.append("|------|" + "|".join(":------:" for _ in years) + "|")

        def row(label: str, data: dict, fmt: str = ".1f", unit: str = "", pct: bool = False):
            vals = []
            for y in years:
                v = data.get(y)
                if v is None:
                    vals.append("-")
                elif pct:
                    vals.append(f"{v*100:{'.1f' if fmt == '.1f' else fmt}}%")
                else:
                    vals.append(f"{v:{fmt}}{unit}")
            lines.append(f"| {label} | " + " | ".join(vals) + " |")

        row("营业收入（百万元）", metrics.revenue)
        row("毛利（百万元）", metrics.gross_profit)
        row("毛利率", metrics.gross_margin, pct=True)
        row("经营利润（百万元）", metrics.operating_profit)
        row("净利润（百万元）", metrics.net_profit)
        row("经调整净利润（百万元）", metrics.adjusted_net_profit)
        row("总资产（百万元）", metrics.total_assets)
        row("总负债（百万元）", metrics.total_liabilities)
        row("权益总额（百万元）", metrics.total_equity)
        row("现金及等价物（百万元）", metrics.cash_and_equivalents)
        row("存货（百万元）", metrics.inventory)
        row("应收款项（百万元）", metrics.trade_receivables)
        row("应付款项（百万元）", metrics.trade_payables)
        row("经营现金流（百万元）", metrics.operating_cash_flow)
        row("投资现金流（百万元）", metrics.investing_cash_flow)
        row("融资现金流（百万元）", metrics.financing_cash_flow)
        row("销售费用率", metrics.sales_marketing_ratio, pct=True)
        row("管理费用率", metrics.admin_expense_ratio, pct=True)
        row("研发费用率", metrics.rd_expense_ratio, pct=True)

        # Calculate and add derived metrics
        lines.append("")
        lines.append("### 衍生指标\n")
        lines.append("| 指标 | " + " | ".join(f"{y}年" for y in years) + " |")
        lines.append("|------|" + "|".join(":------:" for _ in years) + "|")

        # Net margin
        net_margin_vals = []
        for y in years:
            rev = metrics.revenue.get(y)
            np_ = metrics.net_profit.get(y)
            if rev and np_ and rev > 0:
                net_margin_vals.append(f"{np_/rev*100:.1f}%")
            else:
                net_margin_vals.append("-")
        lines.append("| 净利率 | " + " | ".join(net_margin_vals) + " |")

        # ROE
        roe_vals = []
        for y in years:
            np_ = metrics.net_profit.get(y)
            eq = metrics.total_equity.get(y)
            if np_ and eq and eq > 0:
                roe_vals.append(f"{np_/eq*100:.1f}%")
            else:
                roe_vals.append("-")
        lines.append("| ROE | " + " | ".join(roe_vals) + " |")

        # ROA
        roa_vals = []
        for y in years:
            np_ = metrics.net_profit.get(y)
            ta = metrics.total_assets.get(y)
            if np_ and ta and ta > 0:
                roa_vals.append(f"{np_/ta*100:.1f}%")
            else:
                roa_vals.append("-")
        lines.append("| ROA | " + " | ".join(roa_vals) + " |")

        # Debt ratio
        debt_vals = []
        for y in years:
            tl = metrics.total_liabilities.get(y)
            ta = metrics.total_assets.get(y)
            if tl and ta and ta > 0:
                debt_vals.append(f"{tl/ta*100:.1f}%")
            else:
                debt_vals.append("-")
        lines.append("| 资产负债率 | " + " | ".join(debt_vals) + " |")

        # OCF/NP ratio (profit quality)
        ocf_np_vals = []
        for y in years:
            ocf = metrics.operating_cash_flow.get(y)
            np_ = metrics.net_profit.get(y)
            if ocf and np_ and np_ > 0:
                ocf_np_vals.append(f"{ocf/np_:.1f}x")
            else:
                ocf_np_vals.append("-")
        lines.append("| 经营现金流/净利润 | " + " | ".join(ocf_np_vals) + " |")

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
        Generate a structured analysis report stub with all extracted data.

        Sections:
        1. 企业概况 (manual fill)
        2. 核心财务指标 (auto-populated from metrics)
        3. 收入结构 (auto-populated if available)
        4. 竞争力分析/护城河 (prompt)
        5. 风险预警 (prompt)
        6. 总结 (prompt)
        """
        lines = [
            '# 企业财务分析报告（工具自动提取 + 待人工/LLM分析）',
            '',
            '---',
            '',
            '## 一、企业概况',
            '',
            '> *此部分需根据PDF中[业务]/[行业概览]/[历史、发展及公司架构]等章节人工填充。*',
            '',
            '| 项目 | 内容 |',
            '|------|------|',
            '| 公司全称 | *(待提取)* |',
            '| 上市地及代码 | *(待提取)* |',
            '| 核心业务 | *(待提取)* |',
            '| 资产模式 | *(重资产/轻资产 - 待判断)* |',
            '| 行业地位 | *(待提取)* |',
            '',
            '---',
            '',
            MarkdownOutput.format_metrics_summary(metrics),
            '',
            '---',
            '',
            MarkdownOutput.format_revenue_breakdown(metrics),
            '',
            '---',
            '',
            '## 三、竞争力分析（护城河研判）',
            '',
            '> *此部分需基于PDF中[我们的优势]/[行业概览]等章节人工/LLM分析。*',
            '',
            '| 维度 | 待评级 | 判断依据 |',
            '|------|--------|----------|',
            '| 规模与成本优势 | ★★★ | *(待填充)* |',
            '| 技术壁垒 | ★★★ | *(待填充)* |',
            '| 客户粘性 | ★★★ | *(待填充)* |',
            '| 特许权与牌照 | ★★★ | *(待填充)* |',
            '| 综合护城河 | ★★★ | *(待填充)* |',
            '',
            '### 盈利可持续性',
            '- **客户复购率**: *(待判断)*',
            '- **行业需求稳定性**: *(待判断)*',
            '- **竞争格局**: *(待判断)*',
            '- **资本投入依赖度 (CAPEX/OCF)**: *(见上表经营/投资现金流对比)*',
            '',
            '---',
            '',
            '## 四、风险预警',
            '',
            '> *此部分需基于PDF中[风险因素]章节及财务数据异常人工/LLM分析。*',
            '',
            '| 风险项 | 等级 | 说明 |',
            '|--------|------|------|',
            '| 盈利能力 | 🔴🟡🟢 | ROE/净利率是否过低 |',
            '| 偿债风险 | 🔴🟡🟢 | 流动比率/杠杆率 |',
            '| 行业周期 | 🔴🟡🟢 | 化工行业5-7年周期 |',
            '| 原材料波动 | 🔴🟡🟢 | LPG/原盐/煤炭价格 |',
            '| 贸易摩擦 | 🔴🟡🟢 | 反倾销调查等 |',
            '| ... | ... | ... |',
            '',
            '---',
            '',
            '## 五、总结',
            '',
            '> *综合上述分析，给出投资吸引力评级和关键判断。*',
            '',
            '| 维度 | 评级 |',
            '|------|------|',
            '| 业务竞争力 | ★★★ |',
            '| 财务健康度 | ★★★ |',
            '| 成长性 | ★★★ |',
            '| 综合投资吸引力 | ★★★ |',
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
