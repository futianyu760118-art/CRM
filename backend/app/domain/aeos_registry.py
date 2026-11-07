"""AEOS 对象 / 命名 / 系统台账（PAND-330，F3-A03 / F4 / F6-A03 / F6-A05）。

代码级单一事实源，不落 DB 表（架构 §4.1）。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SystemRegistryEntry:
    module_id: str
    system_code: str
    system_name: str
    system_name_en: str


@dataclass(frozen=True)
class ObjectRegistryEntry:
    entity: str  # PascalCase 实体名
    table: str  # snake_case 表名
    l1_object_type: str | None
    fact_owner: str
    owner_fields: bool  # 是否适用 Owner 五字段
    note: str = ""


#: 系统台账（F6-A03 四字段）
SYSTEMS: dict[str, SystemRegistryEntry] = {
    "M05": SystemRegistryEntry("M05", "CRM", "销售自治中心", "Sales Autonomous Center"),
}

#: 对象 / 命名台账（F6-A05：覆盖 F3-A03 全部关键对象）
OBJECTS: dict[str, ObjectRegistryEntry] = {
    "Lead": ObjectRegistryEntry("Lead", "lead", None, "M05", True),
    "Customer": ObjectRegistryEntry("Customer", "company", "Customer", "M05", True),
    "Contact": ObjectRegistryEntry("Contact", "contact", None, "M05", True),
    "Opportunity": ObjectRegistryEntry("Opportunity", "opportunity", None, "M05", True),
    "Inquiry": ObjectRegistryEntry("Inquiry", "inquiry", "Inquiry", "M05", True),
    "Quotation": ObjectRegistryEntry("Quotation", "quotation", None, "M05", True),
    "CommercialOrder": ObjectRegistryEntry(
        "CommercialOrder", "sales_order", "Order", "M05", True, "L1 object_type 冻结为 Order"
    ),
    "QuoteLibrary": ObjectRegistryEntry("QuoteLibrary", "quote_library", "QuoteLibrary", "M05", True),
    "Sample": ObjectRegistryEntry("Sample", "sample", "Sample", "M05", True),
    "Feedback": ObjectRegistryEntry("Feedback", "feedback", "Feedback", "M05", True),
    "Verification": ObjectRegistryEntry(
        "Verification", "verification", None, "M05", False, "验证责任人由 verifier 字段承载"
    ),
    "SalesResult": ObjectRegistryEntry(
        "SalesResult", "sales_result", None, "M05", True, "F5 验证闭环，L2 Event.V2 承载"
    ),
    "Product": ObjectRegistryEntry("Product", "product", None, "M04", False, "引用型对象"),
    "Sku": ObjectRegistryEntry("Sku", "sku", None, "M04", False, "引用型对象"),
    "Dictionary": ObjectRegistryEntry("Dictionary", "dictionary", "Dictionary", "EBMS", False, "过程/字典对象"),
    "SalesActivity": ObjectRegistryEntry(
        "SalesActivity", "activity", None, "M05", False, "命名冲突待确认（架构 R6）"
    ),
    "SalesException": ObjectRegistryEntry("SalesException", "", None, "M05", False, "待建（登记，不迁移）"),
    "SalesDecisionRef": ObjectRegistryEntry("SalesDecisionRef", "", None, "M05", False, "待建（登记，不迁移）"),
    "SalesEvidenceRef": ObjectRegistryEntry("SalesEvidenceRef", "", None, "M05", False, "待建（登记，不迁移）"),
    "SalesEvent": ObjectRegistryEntry("SalesEvent", "", None, "M05", False, "待建（登记，不迁移）"),
}

#: 不适用 fact_owner/owner_id 的过程对象（F4-A04）
PROCESS_OBJECTS: frozenset[str] = frozenset(
    {"IntegrationOutbox", "IntegrationLog", "AuditLog", "SyncConflict", "InquiryStatusLog"}
)


def object_type_of(entity: str) -> str | None:
    entry = OBJECTS.get(entity)
    return entry.l1_object_type if entry else None


def fact_owner_of(entity: str) -> str | None:
    entry = OBJECTS.get(entity)
    return entry.fact_owner if entry else None


def objects_with_owner_fields() -> tuple[str, ...]:
    return tuple(name for name, entry in OBJECTS.items() if entry.owner_fields)
