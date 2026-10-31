"""PAND-304 自检断言：R1–R4 口径落地的纯逻辑部分（无需数据库）。

1. R1 报价库证书等级取并集，24 条国标仍在值域内。
2. R2 客户身份以 customer_code 为准：占位名折叠、同名异码拆分、同码多行合并。
3. R3/R4 辅助逻辑：备注拼装、多行电话按 50 字符列宽拆分且原文不丢。

运行（纯逻辑，无需数据库）：
    python -m pytest tests/test_pand304_selfcheck.py -v
"""

from __future__ import annotations

from typing import Any

from app.domain.state_machine import QUOTE_LIBRARY_CERTIFICATE_LEVELS
from scripts.ebms_migrate_sales_center import (
    _customer_entities,
    _customer_remark,
    _split_phone,
)


def _row(index: int, **fields: Any) -> dict[str, Any]:
    return {"id": index, "updated_at": f"2026-01-{index:02d} 00:00:00", **fields}


def test_certificate_levels_cover_union() -> None:
    assert QUOTE_LIBRARY_CERTIFICATE_LEVELS == [
        "CE",
        "ROHS",
        "CCC",
        "UL",
        "ETL",
        "国标",
        "行标",
        "企标",
        "无证书",
    ]


def test_placeholder_name_falls_back_to_code() -> None:
    entities = _customer_entities([_row(1, name="/", customer_code="HJ003-1"), _row(2, name="/", customer_code="HJ003-2")])
    assert [(e["primary_code"], e["name"]) for e in entities] == [
        ("HJ003-1", "HJ003-1"),
        ("HJ003-2", "HJ003-2"),
    ]


def test_same_code_rows_collapse_to_one_customer() -> None:
    entities = _customer_entities(
        [_row(1, name="宁波多赛", customer_code="C1", phone="111"), _row(2, name="宁波多赛", customer_code="C1", phone="222")]
    )
    assert len(entities) == 1
    assert entities[0]["name"] == "宁波多赛"
    assert len(entities[0]["rows"]) == 2


def test_same_name_different_code_stays_split() -> None:
    # 联系人标识不同 → 即使同名也必须是两个客户（宁波多赛口径）
    entities = _customer_entities(
        [_row(1, name="宁波多赛", customer_code="C1", phone="111"), _row(2, name="宁波多赛", customer_code="C2", phone="222")]
    )
    assert sorted(e["primary_code"] for e in entities) == ["C1", "C2"]


def test_same_name_identical_contacts_merge() -> None:
    entities = _customer_entities(
        [_row(1, name="某客户", customer_code="C1", phone="111"), _row(2, name="某客户", customer_code="C2", phone="111")]
    )
    assert len(entities) == 1
    assert entities[0]["codes"] == ["C1", "C2"]


def test_customer_remark_keeps_sales_person_and_text() -> None:
    rows = [_row(1, sales_person="张三", remarks="重点关注"), _row(2, sales_person="李四", remarks="月结")]
    assert _customer_remark(rows) == "原销售员：张三\n原销售员：李四\n重点关注\n月结"


def test_split_phone_fits_column_and_keeps_original() -> None:
    raw = "Tel: +49(0)711-60 17 11 0\nFax: +49(0)711-60 17 11 11"
    phone, original = _split_phone(raw)
    assert phone == "Tel: +49(0)711-60 17 11 0"
    assert len(phone) <= 50
    assert original == raw


def test_short_phone_untouched() -> None:
    assert _split_phone("0571-89026601") == ("0571-89026601", None)
