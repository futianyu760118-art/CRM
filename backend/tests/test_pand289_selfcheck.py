"""PAND-289 开发B 口径回调返工 自检断言（实际 vs 期望）。

覆盖三项签批口径（PAND-285 默认项，纯函数非 DB 断言，无需测试库）：

- 16-06 交付逾期判定 = B：``promised_date`` 为主、``sla_days``（默认 7）仅作无交期兜底。
- 16-09 订单状态映射 = B：同名映射 ``completed→completed``、``closed→closed``。
- 16-15 客户查重 = B：名称精确匹配 + 税号/电话任一命中即「疑似」人工确认。

运行：

    python -m pytest tests/test_pand289_selfcheck.py -v
"""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, date, datetime

from app.api.v1.endpoints import companies as companies_api
from app.domain.state_machine import EXTERNAL_ORDER_STATUS_MAP
from app.models.business import Company, Contact
from app.schemas.ebms import PilotExceptionIn
from app.services import ebms
from app.services.ebms_ingest import _map_payload

AS_OF = datetime(2026, 10, 17, 12, 0, tzinfo=UTC)


def _mk(name: str, code: str, tax_id: str | None = None) -> Company:
    c = Company(code=code, name=name, tax_id=tax_id)
    c.id = uuid.uuid4()
    return c


# ---------------------------------------------------------------- 16-06 交付逾期判定 = B


class TestDeliveryOverdueBasis:
    def test_default_sla_is_7(self) -> None:
        assert ebms.DEFAULT_DELIVERY_SLA_DAYS == 7
        assert inspect.signature(ebms.emit_delivery_overdue).parameters["sla_days"].default == 7
        assert PilotExceptionIn().sla_days == 7

    def test_promised_date_is_primary(self) -> None:
        assert ebms._overdue_days(date(2026, 10, 10), None, AS_OF, 7) == (7, "promised_date")

    def test_promised_date_ignores_sla_when_present(self) -> None:
        # created_at 很新（不超 sla），但承诺交期已过 → 仍按交期逾期
        assert ebms._overdue_days(date(2026, 10, 16), AS_OF, AS_OF, 7) == (1, "promised_date")

    def test_promised_date_today_not_overdue(self) -> None:
        assert ebms._overdue_days(date(2026, 10, 17), None, AS_OF, 7) is None

    def test_promised_date_future_not_overdue(self) -> None:
        assert ebms._overdue_days(date(2026, 10, 20), None, AS_OF, 7) is None

    def test_falls_back_to_sla_when_no_promised_date(self) -> None:
        created = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)  # 距 as_of 16 天 → 16-7=9
        assert ebms._overdue_days(None, created, AS_OF, 7) == (9, "sla")

    def test_within_sla_not_overdue(self) -> None:
        created = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)  # 距 as_of 2 天 < 7
        assert ebms._overdue_days(None, created, AS_OF, 7) is None

    def test_no_inputs_not_overdue(self) -> None:
        assert ebms._overdue_days(None, None, AS_OF, 7) is None

    def test_naive_created_at_treated_as_utc(self) -> None:
        assert ebms._overdue_days(None, datetime(2026, 10, 1, 12, 0), AS_OF, 7) == (9, "sla")


# ---------------------------------------------------------------- 16-09 订单状态映射 = B


class TestOrderStatusMapping:
    def test_external_order_status_map_is_same_name(self) -> None:
        assert EXTERNAL_ORDER_STATUS_MAP == {"completed": "completed", "closed": "closed"}

    def test_ingest_maps_order_status_via_frozen_contract(self) -> None:
        assert _map_payload("Order", {"status": "completed"})["status"] == "completed"
        assert _map_payload("Order", {"status": "closed"})["status"] == "closed"

    def test_ingest_passes_through_undeclared_status(self) -> None:
        assert _map_payload("Order", {"status": "shipped"})["status"] == "shipped"


# ---------------------------------------------------------------- 16-15 客户查重 = B


class TestCustomerDedup:
    def test_exact_name_match_case_insensitive(self) -> None:
        c1 = _mk("Acme Corp", "C1")
        c2 = _mk(" acme corp ", "C2")
        groups = companies_api._detect_duplicates([c1, c2], [])
        names = [g for g in groups if g["kind"] == "name"]
        assert len(names) == 1
        assert names[0]["suspected"] is False
        assert {c.code for c in names[0]["companies"]} == {"C1", "C2"}

    def test_single_company_no_group(self) -> None:
        assert companies_api._detect_duplicates([_mk("Solo", "C1")], []) == []

    def test_tax_id_hit_is_suspected(self) -> None:
        c1 = _mk("A", "C1", tax_id="91330200MA")
        c2 = _mk("B", "C2", tax_id="91330200MA")
        groups = companies_api._detect_duplicates([c1, c2], [])
        taxes = [g for g in groups if g["kind"] == "tax_id"]
        assert len(taxes) == 1
        assert taxes[0]["suspected"] is True
        assert {c.code for c in taxes[0]["companies"]} == {"C1", "C2"}

    def test_contact_phone_or_mobile_hit_is_suspected(self) -> None:
        c1 = _mk("A", "C1")
        c2 = _mk("B", "C2")
        ct1 = Contact(company_id=c1.id, name="甲", phone="13800000000")
        ct2 = Contact(company_id=c2.id, name="乙", mobile="13800000000")
        groups = companies_api._detect_duplicates([c1, c2], [ct1, ct2])
        phones = [g for g in groups if g["kind"] == "phone"]
        assert len(phones) == 1
        assert phones[0]["suspected"] is True
        assert {c.code for c in phones[0]["companies"]} == {"C1", "C2"}
