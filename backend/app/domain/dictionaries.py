"""PAND-312 六模块改进：新增枚举字典（编码 ↔ 中文标签单一事实来源）。

PAND-314 架构决策 D1：枚举统一用 String 列 + 集中字典（不用 PG ENUM）。
开发A（PAND-315）建设本文件；开发B（PAND-316）的 ``doc_type/courier/currency``
也登记在这里，两侧不得各自硬编码。
"""

from __future__ import annotations

from collections.abc import Mapping

# ------------------------------------------------------------------ 线索（LEAD-01）
LEAD_LEVELS: dict[str, str] = {
    "A": "A级（高意向）",
    "B": "B级（中意向）",
    "C": "C级（低意向）",
}
LEAD_LEVEL_DEFAULT = "B"

# 渠道大类：与客户来源共用编码，标签按各自业务口径（AC Q2 默认合并）
LEAD_CHANNELS: dict[str, str] = {
    "EXHIBITION": "展会",
    "B2B": "B2B平台",
    "WEBSITE": "官网询盘",
    "REFERRAL": "客户推荐",
    "DIRECT": "自主开发",
    "AGENT": "代理商",
    "SOCIAL": "社媒",
    "OTHER": "其他",
}
LEAD_CHANNEL_DEFAULT = "OTHER"

# ------------------------------------------------------------------ 客户（CUST-01）
CUSTOMER_SOURCES: dict[str, str] = {
    "EXHIBITION": "展会",
    "YUNQUTONG": "云渠通",
    "WEBSITE": "官网",
    "DIRECT": "主动开发",
    "B2B": "B2B平台",
    "REFERRAL": "客户推荐",
    "AGENT": "代理商",
    "SOCIAL": "社媒",
    "OTHER": "其他",
}
CUSTOMER_SOURCE_DEFAULT = "OTHER"

CUSTOMER_TYPES: dict[str, str] = {
    "END_USER": "终端用户",
    "TRADER": "贸易商",
    "AGENT": "代理商",
    "DISTRIBUTOR": "分销商",
    "FACTORY": "生产工厂",
    "OTHER": "其他",
}
CUSTOMER_TYPE_DEFAULT = "OTHER"

PAYMENT_METHODS: dict[str, str] = {
    "TT": "T/T 电汇",
    "LC": "L/C 信用证",
    "DP": "D/P 付款交单",
    "DA": "D/A 承兑交单",
    "OA": "O/A 赊销",
    "WU": "西联汇款",
    "CASH": "现金",
    "OTHER": "其他",
}

# ------------------------------------------------------------------ 联系人（CONT-04）
CONTACT_RELATION_TYPES: dict[str, str] = {
    "DECISION_MAKER": "决策人",
    "PURCHASING": "采购对接人",
    "TECHNICAL": "技术对接人",
    "FINANCE": "财务对接人",
    "LOGISTICS": "物流对接人",
    "OTHER": "其他",
}
CONTACT_RELATION_DEFAULT = "OTHER"

# ------------------------------------------------------------------ 开发B 共用（PAND-316，先冻结）
PRODUCT_DOC_TYPES: dict[str, str] = {
    "SALES_MATERIAL": "销售资料",
    "SPEC_SHEET": "规格书",
    "TEST_REPORT": "测试报告",
    "CERTIFICATION": "认证文件",
}

CURRENCIES: dict[str, str] = {
    "USD": "美元",
    "CNY": "人民币",
    "EUR": "欧元",
    "JPY": "日元",
    "GBP": "英镑",
}
CURRENCY_DEFAULT = "USD"

COURIERS: dict[str, str] = {
    "SF": "顺丰",
    "JD": "京东物流",
    "ZTO": "中通",
    "YTO": "圆通",
    "YUNDA": "韵达",
    "STO": "申通",
    "EMS": "EMS",
    "DHL": "DHL",
    "FEDEX": "FedEx",
    "UPS": "UPS",
    "OTHER": "其他",
}


def values(options: Mapping[str, str]) -> list[str]:
    return list(options)


def label_of(options: Mapping[str, str], value: str | None) -> str | None:
    if value is None:
        return None
    return options.get(value)


def labels_text(options: Mapping[str, str]) -> str:
    """拼接枚举可选项文案，用于校验提示（如「仅可选 A级（高意向）/ B级（中意向）」）。"""
    return " / ".join(options.values())


def invalid_message(label: str, options: Mapping[str, str]) -> str:
    return f"{label}：仅可选 {labels_text(options)}"
