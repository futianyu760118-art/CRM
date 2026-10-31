"""PAND-315 自检断言：客户域（线索/客户/联系人）纯逻辑部分。

覆盖：
1. 字典值域与默认值（LEAD-01 / CUST-01 / CONT-04）。
2. 查重归一化：名称/邮箱/电话/法律后缀/免费邮箱域名（LEAD-02）。
3. 客户新/活跃/休眠分类口径与互斥性（CUST-02）。
4. 校验错误中文化：字段中文名 + 可读原因 + JSON 可序列化（D2）。
5. 主要联系人取值优先级（CONT-03）。
6. 线索转客户来源映射与查重说明拼装。

运行（纯逻辑，无需数据库）：
    python -m pytest tests/test_pand315_selfcheck.py -v
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.api.v1.endpoints.leads import _lead_source
from app.core.exceptions import localize_validation_errors
from app.domain import dictionaries as dic
from app.models.business import Company, Contact, Lead
from app.schemas.business import CompanyCreate, ContactCreate, LeadCreate
from app.services import dedup
from app.services.contact_link import contact_value
from app.services.customer_group import (
    GROUP_ACTIVE,
    GROUP_DORMANT,
    GROUP_NEW,
    active_condition,
    classify,
    dormant_condition,
    new_condition,
)

NOW = datetime(2026, 10, 31, tzinfo=UTC)


# ------------------------------------------------------------------ 字典
def test_dictionary_defaults_in_value_domain() -> None:
    assert dic.LEAD_LEVEL_DEFAULT in dic.LEAD_LEVELS
    assert dic.LEAD_CHANNEL_DEFAULT in dic.LEAD_CHANNELS
    assert dic.CUSTOMER_SOURCE_DEFAULT in dic.CUSTOMER_SOURCES
    assert dic.CUSTOMER_TYPE_DEFAULT in dic.CUSTOMER_TYPES
    assert dic.CONTACT_RELATION_DEFAULT in dic.CONTACT_RELATION_TYPES


def test_dictionary_codes_and_labels_are_stable() -> None:
    assert dic.LEAD_LEVELS == {"A": "A级（高意向）", "B": "B级（中意向）", "C": "C级（低意向）"}
    assert dic.CUSTOMER_SOURCES["YUNQUTONG"] == "云渠通"
    assert dic.PAYMENT_METHODS["TT"] == "T/T 电汇"
    assert dic.CONTACT_RELATION_TYPES["DECISION_MAKER"] == "决策人"
    assert set(dic.CONTACT_RELATION_TYPES) == {
        "DECISION_MAKER",
        "PURCHASING",
        "TECHNICAL",
        "FINANCE",
        "LOGISTICS",
        "OTHER",
    }


# ------------------------------------------------------------------ 查重
def test_normalize_name_email_phone() -> None:
    assert dedup.normalize_name("  Ningbo   Dosa  ") == "ningbo dosa"
    assert dedup.normalize_email("  Sales@Example.COM ") == "sales@example.com"
    assert dedup.normalize_phone("+86 138-0013-8000") == "8613800138000"
    assert dedup.normalize_phone("123") == ""  # 短号不参与匹配


def test_name_core_strips_legal_suffixes() -> None:
    assert dedup.name_core("Ningbo Dosa Co., Ltd.") == "ningbo dosa"
    assert dedup.name_core("宁波多赛有限公司") == "宁波多赛"
    assert dedup.is_same_name_core("Ningbo Dosa Co., Ltd.", "Ningbo Dosa Trading Co.") is True
    assert dedup.is_same_name_core("AB Ltd", "AB Co") is False  # 核心长度 <3 不判定


def test_email_domain_excludes_free_mail() -> None:
    assert dedup.email_domain("buyer@acme-industries.com") == "acme-industries.com"
    assert dedup.shares_email_domain("a@acme-industries.com", "b@acme-industries.com") is True
    assert dedup.shares_email_domain("a@gmail.com", "b@gmail.com") is False


def test_duplicate_candidates_truncate_to_20() -> None:
    definite = [
        {"ref": f"LD-{i}", "kind": "lead", "name": f"n{i}"} for i in range(5)
    ]
    suspected = [
        {"ref": f"C{i}", "kind": "customer", "name": f"c{i}"} for i in range(20)
    ]
    packed = dedup._pack(definite, suspected, 20)
    assert packed["total"] == 25
    assert packed["truncated"] is True
    assert len(packed["definite"]) + len(packed["suspected"]) == 20
    assert len(packed["definite"]) == 5


def test_merge_note_keeps_manual_remark() -> None:
    assert dedup.merge_note("原备注", "确认非重复") == "原备注\n（查重确认：确认非重复）"
    assert dedup.merge_note(None, "确认非重复") == "（查重确认：确认非重复）"
    assert dedup.merge_note("原备注", "  ") == "原备注"


# ------------------------------------------------------------------ 客户分类
def test_classify_new_customer() -> None:
    group, reason = classify(NOW - timedelta(days=10), None, None, False, NOW)
    assert group == GROUP_NEW
    assert "90 天" in reason


def test_classify_new_requires_no_closed_order() -> None:
    group, _ = classify(NOW - timedelta(days=10), None, NOW - timedelta(days=1), True, NOW)
    assert group == GROUP_ACTIVE


def test_classify_dormant_by_customer_status() -> None:
    group, reason = classify(NOW - timedelta(days=400), "未合作休眠客户", NOW - timedelta(days=2), False, NOW)
    assert group == GROUP_DORMANT
    assert "未合作休眠客户" in reason


def test_classify_dormant_by_stale_followup() -> None:
    group, reason = classify(NOW - timedelta(days=400), None, NOW - timedelta(days=200), False, NOW)
    assert group == GROUP_DORMANT
    assert "200 天前" in reason


def test_classify_dormant_without_followup() -> None:
    group, reason = classify(NOW - timedelta(days=200), None, None, False, NOW)
    assert group == GROUP_DORMANT
    assert "无跟进记录" in reason


def test_classify_active_with_recent_followup() -> None:
    group, _ = classify(NOW - timedelta(days=400), None, NOW - timedelta(days=30), False, NOW)
    assert group == GROUP_ACTIVE


def test_group_conditions_are_mutually_exclusive_sql() -> None:
    new_sql = str(new_condition(Company, NOW))
    dormant_sql = str(dormant_condition(Company, NOW))
    active_sql = str(active_condition(Company, NOW))
    assert "company.created_at >=" in new_sql and "sales_order.status IN" in new_sql
    assert "NOT (" in dormant_sql and "activity" in dormant_sql
    assert "NOT (" in active_sql


def test_every_customer_lands_in_exactly_one_group() -> None:
    cases = [
        (NOW - timedelta(days=1), None, None, False),
        (NOW - timedelta(days=100), None, NOW - timedelta(days=1), False),
        (NOW - timedelta(days=200), None, None, False),
        (NOW - timedelta(days=30), None, None, True),
    ]
    groups = [classify(*case, NOW)[0] for case in cases]
    assert all(g in {GROUP_NEW, GROUP_ACTIVE, GROUP_DORMANT} for g in groups)
    assert len(groups) == len(cases)


# ------------------------------------------------------------------ 校验中文化
def _localized(exc: ValidationError) -> tuple[str, list[dict]]:
    return localize_validation_errors(exc.errors())


def test_missing_field_message_uses_chinese_label() -> None:
    with pytest.raises(ValidationError) as info:
        LeadCreate()  # type: ignore[call-arg]
    message, details = _localized(info.value)
    assert "名称：不能为空" in message
    assert all("msg" not in d for d in details)
    json.dumps(details)  # ctx.error 已转字符串


def test_too_long_message() -> None:
    with pytest.raises(ValidationError) as info:
        LeadCreate(name="x" * 201)
    message, _ = _localized(info.value)
    assert "名称：最多 200 字" in message


def test_enum_error_message_lists_chinese_options() -> None:
    with pytest.raises(ValidationError) as info:
        LeadCreate(name="测试", lead_level="Z")
    message, _ = _localized(info.value)
    assert "线索等级：" in message
    assert "A级（高意向）" in message
    assert "Z" not in message


def test_website_requires_http_prefix() -> None:
    with pytest.raises(ValidationError) as info:
        CompanyCreate(name="客户", website="www.example.com")
    message, _ = _localized(info.value)
    assert "官网：请输入以 http:// 或 https:// 开头的网址" in message
    assert CompanyCreate(name="客户", website="https://example.com").website == "https://example.com"


def test_whatsapp_format() -> None:
    assert ContactCreate(name="张三", whatsapp="+86 138-0013-8000").whatsapp == "+86 138-0013-8000"
    with pytest.raises(ValidationError) as info:
        ContactCreate(name="张三", whatsapp="abc")
    message, _ = _localized(info.value)
    assert "WhatsApp：仅可包含数字、空格、+ 和 -" in message


def test_defaults_for_new_lead_and_customer() -> None:
    lead = LeadCreate(name="测试线索")
    assert lead.lead_level == "B"
    assert lead.channel == "OTHER"
    company = CompanyCreate(name="测试客户")
    assert company.source == "OTHER"
    assert company.customer_type == "OTHER"


# ------------------------------------------------------------------ 主要联系人
def test_contact_value_priority() -> None:
    contact = Contact(name="张三", mobile="13800000000", whatsapp="+8613900000000", wechat="wx", email="a@b.com")
    assert contact_value(contact) == "13800000000"
    contact.mobile = None
    assert contact_value(contact) == "+8613900000000"
    contact.whatsapp = None
    assert contact_value(contact) == "wx"
    contact.wechat = None
    assert contact_value(contact) == "a@b.com"
    contact.email = None
    assert contact_value(contact) is None


# ------------------------------------------------------------------ 转客户映射
def test_lead_source_prefers_channel_then_source() -> None:
    lead = Lead(name="客户", source="EXHIBITION", channel="B2B")
    assert _lead_source(lead) == "B2B"
    lead.channel = "UNKNOWN"
    assert _lead_source(lead) == "EXHIBITION"
    lead.source = "UNKNOWN"
    assert _lead_source(lead) == "OTHER"
    lead.channel = None
    assert _lead_source(lead) == "OTHER"
