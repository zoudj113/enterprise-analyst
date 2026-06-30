"""
Chinese financial terminology keyword dictionary.

Organized by financial statement section type for page classification,
with an aggregated master list for "is this a financial page?" heuristics.
"""

import re

# ── Section-specific keyword dictionaries ──────────────────────────────

FINANCIAL_KEYWORDS = {
    "income_statement": [
        "綜合損益", "全面收益", "損益表", "經營業績", "經營利潤",
        "淨利潤", "淨虧損", "年內利潤", "年內虧損",
        "除稅前利潤", "除稅前虧損", "所得稅費用",
        "經調整淨利潤", "經調整", "股份支付",
        "毛利", "毛利率", "銷售成本",
        "收入", "其他收入", "其他收益", "其他費用",
        "銷售及分銷費用", "銷售及分銷", "行政費用",
        "研發費用", "財務費用", "財務成本",
        "金融資產減值", "信用減值",
        "母公司擁有人", "基本每股", "稀釋每股",
    ],
    "balance_sheet": [
        "財務狀況", "財務狀況表",
        "非流動資產", "流動資產", "資產總值", "總資產",
        "非流動負債", "流動負債", "負債總額",
        "權益總額", "資產淨額", "負債淨額", "資產虧絀",
        "現金及現金等價物", "銀行存款",
        "存貨", "貿易應收款項", "貿易及其他應收",
        "貿易應付款項", "貿易及其他應付", "應付票據",
        "物業、廠房及設備", "使用權資產",
        "無形資產", "商譽",
        "合約負債", "租賃負債",
        "遞延稅項資產", "遞延稅項負債",
        "預付款項", "其他應收款項",
        "以公允價值計量", "金融資產", "金融負債",
        "應付稅款", "計息銀行借款", "借款",
        "股本", "儲備", "保留盈利",
    ],
    "cash_flow": [
        "現金流量", "現金流量表",
        "經營活動所得", "經營活動現金", "經營現金流",
        "投資活動所得", "投資活動現金",
        "融資活動所得", "融資活動現金",
        "現金及現金等價物增加", "現金及現金等價物減少",
        "年初現金", "年末現金", "期末現金",
        "經營所得現金", "已付所得稅", "已收利息",
    ],
    "revenue_breakdown": [
        "收入結構", "按產品", "按渠道", "按地區", "按類別",
        "收入構成", "分類收入", "分部收入", "收入明細",
        "產品類別劃分", "銷售渠道劃分",
        "收入明細", "收入佔比", "各板塊", "業務板塊",
        "經銷渠道", "直營渠道", "經銷商", "分銷商",
        "化学", "化學", "化工", "新材料", "能源",
        "銷售模式", "下游", "產能", "產量", "銷量",
    ],
    "gross_margin": [
        "毛利", "毛利率", "分部毛利",
        "按產品類別劃分的毛利", "按渠道劃分的毛利",
    ],
    "cost_structure": [
        "銷售成本", "成本構成", "成本結構",
        "直接材料", "直接人工", "直接勞動",
        "授權費用", "特許權使用費",
        "生產成本", "製造費用",
        "折舊及攤銷", "折舊", "攤銷",
    ],
    "expenses": [
        "銷售及分銷", "銷售費用", "分銷費用",
        "行政費用", "管理費用",
        "研發費用", "研究及開發",
        "費用率", "費用佔比",
        "人工成本", "廣告及營銷", "運輸及物流",
        "租金費用", "辦公及差旅",
    ],
    "business_overview": [
        "主營業務", "業務概覽", "公司概況",
        "產品", "行業概覽", "市場規模",
        "商業模式", "價值鏈", "供應鏈",
        "競爭格局", "市場份額", "排名",
        "核心競爭力", "優勢", "戰略",
        "品牌", "IP", "知識產權",
        "產能", "生產基地", "一體化", "產業鏈",
        "氯鹼", "碳三碳四", "濕電子", "化工集團",
    ],
    "risk_factors": [
        "風險因素", "風險", "不確定性",
        "競爭", "法律法規", "監管",
        "依賴", "集中", "關鍵人員",
        "知識產權", "商譽減值",
    ],
    "equity_structure": [
        "股權", "股東", "持股", "控股股東",
        "股份激勵", "股權激勵", "股份支付",
        "優先股", "普通股",
        "創始人", "管理層",
        "首次公開發售", "上市",
    ],
}

# ── Aggregated master keyword list ─────────────────────────────────────

ALL_FINANCIAL_KEYWORDS = list(set(
    kw for kw_list in FINANCIAL_KEYWORDS.values() for kw in kw_list
))

# ── Number pattern for financial data page detection ───────────────────

NUMBER_PATTERN = re.compile(r'[\d,]+\.?\d*')

# Pages with more than this many digit characters are likely financial data pages
MIN_FINANCIAL_DIGIT_THRESHOLD = 20

# ── Year pattern for detecting fiscal years in the document ────────────

YEAR_PATTERN = re.compile(r'(?:19|20)\d{2}年')

# Pattern for identifying fiscal years from financial statement headings
# e.g., "截至2023年、2024年及2025年12月31日止年度"
FISCAL_YEAR_HEADING_PATTERN = re.compile(
    r'截至\s*((?:(?:19|20)\d{2}\s*年[、，,及]?\s*)+)\s*12\s*月\s*31\s*日\s*止\s*年\s*度'
)

# Pattern for year columns in table headers
# e.g., "2023年  2024年  2025年" appearing together on one line
YEAR_COLUMNS_PATTERN = re.compile(
    r'((?:(?:19|20)\d{2}\s*年\s*){2,})'
)
