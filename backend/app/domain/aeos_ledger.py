"""AEOS 事件台账（PAND-330，F1-A05 / F11-A01）。

单一事实源：L1 同步事件（13 个小写点号事件）与 L2 业务事件（18 个 PascalCase 事件）
在同一台账登记，以 ``channel`` 列区分通道，不得混用。
"""

from __future__ import annotations

from dataclasses import dataclass

L1_CHANNEL = "L1"
L2_CHANNEL = "L2"


@dataclass(frozen=True)
class EventLedgerEntry:
    event_type: str
    channel: str
    object_type: str | None
    description: str


#: L1 同步事件（与冻结 schema/契约 §4.1 逐字一致）：6 实体 × {upserted, deleted} + dictionary.upserted
L1_EVENT_TYPES: tuple[str, ...] = (
    "customer.upserted",
    "customer.deleted",
    "inquiry.upserted",
    "inquiry.deleted",
    "quote_library.upserted",
    "quote_library.deleted",
    "order.upserted",
    "order.deleted",
    "sample.upserted",
    "sample.deleted",
    "feedback.upserted",
    "feedback.deleted",
    "dictionary.upserted",
)

#: L2 业务事件（F11-A01 初始 18 项，PascalCase）
L2_EVENT_TYPES: tuple[str, ...] = (
    "LeadCreated",
    "LeadAssigned",
    "LeadConverted",
    "CustomerCreated",
    "OpportunityCreated",
    "OpportunityStageChanged",
    "InquiryCreated",
    "InquirySubmitted",
    "QuoteCreated",
    "QuoteSubmitted",
    "QuoteApproved",
    "QuoteRejected",
    "CommercialOrderRequested",
    "CommercialOrderConfirmed",
    "SalesActionCreated",
    "SalesResultSubmitted",
    "SalesResultVerified",
    "EvidenceSubmitted",
)

_L2_OBJECTS: dict[str, str] = {
    "LeadCreated": "Lead",
    "LeadAssigned": "Lead",
    "LeadConverted": "Lead",
    "CustomerCreated": "Customer",
    "OpportunityCreated": "Opportunity",
    "OpportunityStageChanged": "Opportunity",
    "InquiryCreated": "Inquiry",
    "InquirySubmitted": "Inquiry",
    "QuoteCreated": "Quotation",
    "QuoteSubmitted": "Quotation",
    "QuoteApproved": "Quotation",
    "QuoteRejected": "Quotation",
    "CommercialOrderRequested": "CommercialOrder",
    "CommercialOrderConfirmed": "CommercialOrder",
    "SalesActionCreated": "SalesAction",
    "SalesResultSubmitted": "SalesResult",
    "SalesResultVerified": "SalesResult",
    "EvidenceSubmitted": "Evidence",
}

EVENT_LEDGER: dict[str, EventLedgerEntry] = {
    **{
        event_type: EventLedgerEntry(event_type, L1_CHANNEL, None, "L1 实体同步事件")
        for event_type in L1_EVENT_TYPES
    },
    **{
        event_type: EventLedgerEntry(event_type, L2_CHANNEL, _L2_OBJECTS[event_type], "L2 业务事件")
        for event_type in L2_EVENT_TYPES
    },
}


def is_registered(event_type: str, channel: str | None = None) -> bool:
    entry = EVENT_LEDGER.get(event_type)
    if entry is None:
        return False
    return channel is None or entry.channel == channel


def channel_of(event_type: str) -> str | None:
    entry = EVENT_LEDGER.get(event_type)
    return entry.channel if entry else None
