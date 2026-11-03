"""PAND-325 返工自检：R1 电话国家码归一 / R2 样品流转日期关系 / R3 休眠 180 天边界。

覆盖验收边界：
1. ``+86`` / ``0086`` / 裸 ``86`` 前缀与无前缀号码判重一致，且位数不足不误剥离（LEAD-03 / LEAD-02 / CONT-04）。
2. 寄出日期缺省回填当天、未来寄出日拒绝；反馈日期缺省回填当天、早于寄出日拒绝（SAMP-02）。
3. 休眠分组严格大于 180 天：恰好 180 天 / 179 天为活跃，181 天为休眠（CUST-02）。

运行（纯逻辑，无需数据库）：
    python -m pytest tests/test_pand325_selfcheck.py -v
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.api.v1.endpoints.samples import resolve_feedback_date, resolve_send_date
from app.core.exceptions import ApiError
from app.models.business import Company, Contact
from app.services import dedup
from app.services.customer_group import (
    GROUP_ACTIVE,
    GROUP_DORMANT,
    classify,
    dormant_condition,
)

TODAY = date(2026, 11, 3)
NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)
MOBILE = "13800000000"


# ------------------------------------------------------------------ R1 电话国家码
@pytest.mark.parametrize(
    "value",
    [
        "+86 138-0000-0000",
        "+86-138-0000-0000",
        "0086 138 0000 0000",
        "008613800000000",
        "86 13800000000",
        MOBILE,
    ],
)
def test_normalize_phone_strips_china_country_code(value: str) -> None:
    assert dedup.normalize_phone(value) == MOBILE


def test_plus86_and_bare_phone_are_same_person() -> None:
    assert dedup.is_same_phone("+86 138-0000-0000", MOBILE) is True
    assert dedup.is_same_phone("0086 138-0000-0000", MOBILE) is True
    assert dedup.is_same_phone("86 138-0000-0000", MOBILE) is True


def test_country_code_not_stripped_without_enough_national_digits() -> None:
    # 11 位、恰好以 86 开头但不足「86 + 10 位」门限，按原号码参与判重
    assert dedup.normalize_phone("86123456789") == "86123456789"
    # 0086 后不足 10 位同样不剥离
    assert dedup.normalize_phone("0086 138") == "0086138"
    # 短号仍视为无效
    assert dedup.normalize_phone("86 12") == ""


def test_sql_digits_expr_mirrors_country_code_normalization() -> None:
    sql = str(
        select(dedup._digits_expr(Contact.phone)).compile(compile_kwargs={"literal_binds": True})
    )
    assert "regexp_replace" in sql
    # 与 normalize_phone 同口径：按位数门限剥离开头的 0086 / 86
    assert "0086" in sql and "'86'" in sql
    assert "substr" in sql


# ------------------------------------------------------------------ R2 样品日期
def test_send_date_defaults_to_today() -> None:
    assert resolve_send_date(None, None, TODAY) == TODAY


def test_future_send_date_rejected() -> None:
    with pytest.raises(ApiError) as info:
        resolve_send_date(TODAY + timedelta(days=1), None, TODAY)
    assert "寄出日期：不得晚于今天" in info.value.message
    assert TODAY.isoformat() in info.value.message


def test_send_date_accepts_today_and_past() -> None:
    assert resolve_send_date(TODAY, None, TODAY) == TODAY
    assert resolve_send_date(None, TODAY - timedelta(days=3), TODAY) == TODAY - timedelta(days=3)


def test_feedback_date_defaults_to_today() -> None:
    assert resolve_feedback_date(None, None, TODAY - timedelta(days=2), TODAY) == TODAY


def test_feedback_earlier_than_send_date_rejected() -> None:
    sent_on = TODAY - timedelta(days=2)
    with pytest.raises(ApiError) as info:
        resolve_feedback_date(sent_on - timedelta(days=1), None, sent_on, TODAY)
    assert "反馈日期：不得早于寄出日期" in info.value.message
    assert sent_on.isoformat() in info.value.message


def test_feedback_date_same_day_as_send_date_allowed() -> None:
    sent_on = TODAY - timedelta(days=2)
    assert resolve_feedback_date(sent_on, None, sent_on, TODAY) == sent_on
    assert resolve_feedback_date(None, None, None, TODAY) == TODAY  # 无寄出日时不校验下限


# ------------------------------------------------------------------ R3 休眠边界
@pytest.mark.parametrize(
    ("days", "expected"),
    [(179, GROUP_ACTIVE), (180, GROUP_ACTIVE), (181, GROUP_DORMANT)],
)
def test_dormant_boundary_by_last_followup(days: int, expected: str) -> None:
    created = NOW - timedelta(days=400)
    group, _ = classify(created, None, NOW - timedelta(days=days), False, NOW)
    assert group == expected


@pytest.mark.parametrize(
    ("days", "expected"),
    [(180, GROUP_ACTIVE), (181, GROUP_DORMANT)],
)
def test_dormant_boundary_without_followup(days: int, expected: str) -> None:
    group, _ = classify(NOW - timedelta(days=days), None, None, False, NOW)
    assert group == expected


def test_dormant_sql_uses_strict_less_than() -> None:
    sql = str(dormant_condition(Company, NOW))
    assert "<=" not in sql
    assert "<" in sql
