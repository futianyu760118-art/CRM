"""线索/客户查重（PAND-314 §3.2，LEAD-02 / LEAD-03）。

判定口径：
- 确定重复：名称去首尾空格、忽略大小写全等；邮箱去空格转小写全等；电话仅保留数字全等。
- 疑似重复：邮箱域名一致但名称不同（免费邮箱除外）；名称去法律后缀归一后一致。
- 空名称/空邮箱/空电话不参与匹配；软删不参与。

``check_lead_duplicates`` 同时扫描线索、客户与客户联系人（线索新建/改名）；
``check_company_duplicates`` 按 16-15 口径只扫描客户（线索转客户）。
两侧共用本文件的归一化函数，供前端「打开已有 / 仍然创建」弹层消费。
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import Activity, Company, Contact, Lead
from app.models.user import User

#: 候选上限（LEAD-02：>20 只回前 20）
CANDIDATE_LIMIT = 20

#: 免费邮箱域名不参与「同域名疑似重复」
FREE_MAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "yahoo.com",
    "yahoo.cn",
    "hotmail.com",
    "outlook.com",
    "live.com",
    "msn.com",
    "aol.com",
    "icloud.com",
    "qq.com",
    "163.com",
    "126.com",
    "yeah.net",
    "sina.com",
    "sina.cn",
    "sohu.com",
    "foxmail.com",
    "139.com",
    "aliyun.com",
    "protonmail.com",
}

#: 英文公司法律/组织后缀（归一化时剥离）
_LEGAL_SUFFIX_TOKENS = {
    "co",
    "company",
    "corp",
    "corporation",
    "inc",
    "incorporated",
    "ltd",
    "limited",
    "llc",
    "llp",
    "plc",
    "pte",
    "pty",
    "gmbh",
    "ag",
    "sa",
    "sas",
    "sarl",
    "srl",
    "bv",
    "nv",
    "oy",
    "ab",
    "as",
    "kg",
    "spa",
    "group",
    "holding",
    "holdings",
    "enterprise",
    "enterprises",
    "trading",
    "trade",
    "international",
    "industries",
    "industrial",
}

_CN_LEGAL_SUFFIX = re.compile(r"(股份有限公司|有限责任公司|有限公司|集团|公司)$")
_NON_NAME_CHARS = re.compile(r"[^0-9a-z一-鿿]+")
_NON_DIGITS = re.compile(r"[^0-9]+")


def normalize_name(value: str | None) -> str:
    """名称去首尾空白、合并内部空白、忽略大小写。"""
    return " ".join((value or "").split()).lower()


def normalize_email(value: str | None) -> str:
    return (value or "").strip().lower()


def normalize_phone(value: str | None) -> str:
    """电话仅保留数字；不足 6 位视为无效，避免短号误命中。"""
    digits = _NON_DIGITS.sub("", value or "")
    return digits if len(digits) >= 6 else ""


def email_domain(value: str | None) -> str:
    email = normalize_email(value)
    if "@" not in email:
        return ""
    return email.rsplit("@", 1)[1].strip()


def name_core(value: str | None) -> str:
    """剥离法律后缀后的名称核心（用于疑似重复）。"""
    text = (value or "").strip().lower()
    text = _CN_LEGAL_SUFFIX.sub("", text)
    text = _NON_NAME_CHARS.sub(" ", text)
    tokens = [t for t in text.split() if t not in _LEGAL_SUFFIX_TOKENS]
    return " ".join(tokens)


def is_same_name(left: str | None, right: str | None) -> bool:
    a, b = normalize_name(left), normalize_name(right)
    return bool(a) and a == b


def is_same_email(left: str | None, right: str | None) -> bool:
    a, b = normalize_email(left), normalize_email(right)
    return bool(a) and a == b


def is_same_phone(left: str | None, right: str | None) -> bool:
    a, b = normalize_phone(left), normalize_phone(right)
    return bool(a) and a == b


def is_same_name_core(left: str | None, right: str | None) -> bool:
    a, b = name_core(left), name_core(right)
    return len(a) >= 3 and a == b


def shares_email_domain(left: str | None, right: str | None) -> bool:
    a, b = email_domain(left), email_domain(right)
    return bool(a) and a == b and a not in FREE_MAIL_DOMAINS


def company_domain_hit(company: Company, email: str | None) -> bool:
    """客户英文名/官网包含来件邮箱域名（非免费邮箱）。"""
    domain = email_domain(email)
    if not domain or domain in FREE_MAIL_DOMAINS:
        return False
    text = f"{company.name_en or ''} {company.website or ''}".lower()
    return domain in text


def _like(value: str) -> str:
    """转义 LIKE 通配符，避免用户输入 %/_ 扩大匹配面。"""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _digits_expr(column: Any) -> Any:
    return func.regexp_replace(func.coalesce(column, ""), "[^0-9]", "", "g")


async def _owner_names(db: AsyncSession, owner_ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    clean = {i for i in owner_ids if i is not None}
    if not clean:
        return {}
    rows = (await db.execute(select(User.id, User.name).where(User.id.in_(clean)))).all()
    return {r[0]: r[1] for r in rows}


async def _last_followup_leads(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, datetime]:
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(Activity.biz_id, func.max(Activity.happened_at))
            .where(Activity.biz_type == "LEAD", Activity.biz_id.in_(ids), Activity.deleted_at.is_(None))
            .group_by(Activity.biz_id)
        )
    ).all()
    return {r[0]: r[1] for r in rows if r[0] and r[1]}


async def _last_followup_companies(db: AsyncSession, ids: set[uuid.UUID]) -> dict[uuid.UUID, datetime]:
    if not ids:
        return {}
    rows = (
        await db.execute(
            select(Activity.company_id, func.max(Activity.happened_at))
            .where(Activity.company_id.in_(ids), Activity.deleted_at.is_(None))
            .group_by(Activity.company_id)
        )
    ).all()
    return {r[0]: r[1] for r in rows if r[0] and r[1]}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _candidate(
    *,
    ref: str,
    kind: str,
    entity_id: uuid.UUID,
    name: str | None,
    owner_name: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    reason: str | None = None,
    company_id: uuid.UUID | None = None,
    company_name: str | None = None,
    last_followup_at: datetime | None = None,
) -> dict[str, Any]:
    return {
        "ref": ref,
        "kind": kind,
        "id": str(entity_id),
        "name": name,
        "owner_name": owner_name,
        "email": email,
        "phone": phone,
        "reason": reason,
        "company_id": str(company_id) if company_id else None,
        "company_name": company_name,
        "last_followup_at": _iso(last_followup_at),
    }


def _pack(definite: list[dict[str, Any]], suspected: list[dict[str, Any]], limit: int) -> dict[str, Any]:
    total = len(definite) + len(suspected)
    ordered = definite + suspected
    kept = ordered[:limit]
    return {
        "definite": [c for c in kept if c in definite],
        "suspected": [c for c in kept if c not in definite],
        "truncated": total > limit,
        "total": total,
    }


async def check_lead_duplicates(
    db: AsyncSession,
    *,
    name: str | None,
    email: str | None = None,
    phone: str | None = None,
    exclude_lead_id: uuid.UUID | None = None,
    limit: int = CANDIDATE_LIMIT,
) -> dict[str, Any]:
    """线索新建/改名查重，返回 ``{definite, suspected, truncated, total}``。"""
    norm_name = normalize_name(name)
    norm_email = normalize_email(email)
    digits = normalize_phone(phone)
    domain = email_domain(email)
    core = name_core(name)

    lead_conds = []
    if norm_name:
        lead_conds.append(func.lower(func.trim(Lead.name)) == norm_name)
    if norm_email:
        lead_conds.append(func.lower(Lead.email) == norm_email)
    if domain:
        lead_conds.append(Lead.email.ilike(f"%@{_like(domain)}", escape="\\"))
    if digits:
        lead_conds.append(_digits_expr(Lead.phone) == digits)
    if len(core) >= 3:
        lead_conds.append(func.lower(Lead.name).ilike(f"%{_like(core)}%", escape="\\"))

    leads: list[Lead] = []
    if lead_conds:
        stmt: Select = select(Lead).where(Lead.deleted_at.is_(None), or_(*lead_conds))
        if exclude_lead_id:
            stmt = stmt.where(Lead.id != exclude_lead_id)
        leads = list((await db.execute(stmt)).scalars().all())

    company_conds = []
    if norm_name:
        company_conds.append(func.lower(func.trim(Company.name)) == norm_name)
    if len(core) >= 3:
        company_conds.append(func.lower(Company.name).ilike(f"%{_like(core)}%", escape="\\"))
    if domain:
        company_conds.append(Company.name_en.ilike(f"%{_like(domain)}%", escape="\\"))
    companies: list[Company] = []
    if company_conds:
        companies = list(
            (await db.execute(select(Company).where(Company.deleted_at.is_(None), or_(*company_conds))))
            .scalars()
            .all()
        )

    contact_conds = []
    if norm_email:
        contact_conds.append(func.lower(Contact.email) == norm_email)
    if domain:
        contact_conds.append(Contact.email.ilike(f"%@{_like(domain)}", escape="\\"))
    if digits:
        contact_conds.append(_digits_expr(Contact.phone) == digits)
        contact_conds.append(_digits_expr(Contact.mobile) == digits)
    contacts: list[Contact] = []
    if contact_conds:
        contacts = list(
            (await db.execute(select(Contact).where(Contact.deleted_at.is_(None), or_(*contact_conds))))
            .scalars()
            .all()
        )

    owner_ids = {r.owner_id for r in leads if r.owner_id}
    owner_ids |= {c.owner_id for c in companies if c.owner_id}
    owner_ids |= {c.owner_id for c in contacts if c.owner_id}
    owner_names = await _owner_names(db, owner_ids)
    lead_followups = await _last_followup_leads(db, {r.id for r in leads})

    company_ids = {c.id for c in companies} | {c.company_id for c in contacts if c.company_id}
    company_map = {c.id: c for c in ((await _companies_by_ids(db, company_ids)) if company_ids else [])}
    company_followups = await _last_followup_companies(db, company_ids)

    definite: list[dict[str, Any]] = []
    suspected: list[dict[str, Any]] = []

    for row in leads:
        if (
            is_same_name(row.name, name)
            or (norm_email and is_same_email(row.email, email))
            or (digits and is_same_phone(row.phone, phone))
        ):
            definite.append(
                _candidate(
                    ref=row.lead_no,
                    kind="lead",
                    entity_id=row.id,
                    name=row.name,
                    owner_name=owner_names.get(row.owner_id),
                    email=row.email,
                    phone=row.phone,
                    reason="名称/邮箱/电话一致",
                    last_followup_at=lead_followups.get(row.id),
                )
            )
        elif shares_email_domain(row.email, email):
            suspected.append(
                _candidate(
                    ref=row.lead_no,
                    kind="lead",
                    entity_id=row.id,
                    name=row.name,
                    owner_name=owner_names.get(row.owner_id),
                    email=row.email,
                    phone=row.phone,
                    reason="邮箱域名一致",
                    last_followup_at=lead_followups.get(row.id),
                )
            )
        elif is_same_name_core(row.name, name):
            suspected.append(
                _candidate(
                    ref=row.lead_no,
                    kind="lead",
                    entity_id=row.id,
                    name=row.name,
                    owner_name=owner_names.get(row.owner_id),
                    email=row.email,
                    phone=row.phone,
                    reason="名称去除法律后缀后一致",
                    last_followup_at=lead_followups.get(row.id),
                )
            )

    for row in companies:
        if is_same_name(row.name, name):
            definite.append(
                _candidate(
                    ref=row.code,
                    kind="customer",
                    entity_id=row.id,
                    name=row.name,
                    owner_name=owner_names.get(row.owner_id),
                    company_id=row.id,
                    company_name=row.name,
                    reason="客户名称一致",
                    last_followup_at=company_followups.get(row.id),
                )
            )
        elif company_domain_hit(row, email):
            suspected.append(
                _candidate(
                    ref=row.code,
                    kind="customer",
                    entity_id=row.id,
                    name=row.name,
                    owner_name=owner_names.get(row.owner_id),
                    company_id=row.id,
                    company_name=row.name,
                    reason="邮箱域名一致",
                    last_followup_at=company_followups.get(row.id),
                )
            )
        elif is_same_name_core(row.name, name):
            suspected.append(
                _candidate(
                    ref=row.code,
                    kind="customer",
                    entity_id=row.id,
                    name=row.name,
                    owner_name=owner_names.get(row.owner_id),
                    company_id=row.id,
                    company_name=row.name,
                    reason="名称去除法律后缀后一致",
                    last_followup_at=company_followups.get(row.id),
                )
            )

    seen_contacts: set[uuid.UUID] = set()
    for row in contacts:
        company = company_map.get(row.company_id) if row.company_id else None
        same = (norm_email and is_same_email(row.email, email)) or (
            digits and (is_same_phone(row.phone, phone) or is_same_phone(row.mobile, phone))
        )
        reason = "联系人邮箱/电话一致" if same else "联系人邮箱域名一致"
        if not same and not shares_email_domain(row.email, email):
            continue
        if row.id in seen_contacts:
            continue
        seen_contacts.add(row.id)
        candidate = _candidate(
            ref=company.code if company else row.name,
            kind="contact",
            entity_id=row.id,
            name=row.name,
            owner_name=owner_names.get(row.owner_id),
            email=row.email,
            phone=row.phone or row.mobile,
            reason=reason,
            company_id=row.company_id,
            company_name=company.name if company else None,
            last_followup_at=company_followups.get(row.company_id) if row.company_id else None,
        )
        (definite if same else suspected).append(candidate)

    return _pack(definite, suspected, limit)


async def _companies_by_ids(db: AsyncSession, ids: set[uuid.UUID]) -> list[Company]:
    if not ids:
        return []
    return list((await db.execute(select(Company).where(Company.id.in_(ids)))).scalars().all())


async def check_company_duplicates(
    db: AsyncSession,
    *,
    name: str | None,
    tax_id: str | None = None,
    email: str | None = None,
    phone: str | None = None,
    mobile: str | None = None,
    limit: int = CANDIDATE_LIMIT,
) -> dict[str, Any]:
    """线索转客户查重（16-15 口径）：同名确定，税号/联系人电话/邮箱/邮箱域名疑似。"""
    norm_name = normalize_name(name)
    norm_tax = (tax_id or "").strip().lower()
    norm_email = normalize_email(email)
    digits = {d for d in (normalize_phone(phone), normalize_phone(mobile)) if d}
    domain = email_domain(email)
    core = name_core(name)

    company_conds = []
    if norm_name:
        company_conds.append(func.lower(func.trim(Company.name)) == norm_name)
    if norm_tax:
        company_conds.append(func.lower(Company.tax_id) == norm_tax)
    if len(core) >= 3:
        company_conds.append(func.lower(Company.name).ilike(f"%{_like(core)}%", escape="\\"))
    if domain:
        company_conds.append(Company.name_en.ilike(f"%{_like(domain)}%", escape="\\"))
    companies: list[Company] = []
    if company_conds:
        companies = list(
            (await db.execute(select(Company).where(Company.deleted_at.is_(None), or_(*company_conds))))
            .scalars()
            .all()
        )

    contact_conds = []
    if norm_email:
        contact_conds.append(func.lower(Contact.email) == norm_email)
    if domain:
        contact_conds.append(Contact.email.ilike(f"%@{_like(domain)}", escape="\\"))
    for value in digits:
        contact_conds.append(_digits_expr(Contact.phone) == value)
        contact_conds.append(_digits_expr(Contact.mobile) == value)
    contacts: list[Contact] = []
    if contact_conds:
        contacts = list(
            (await db.execute(select(Contact).where(Contact.deleted_at.is_(None), or_(*contact_conds))))
            .scalars()
            .all()
        )

    hit_ids = {c.company_id for c in contacts if c.company_id}
    extra_companies = await _companies_by_ids(db, hit_ids - {c.id for c in companies})
    company_map = {c.id: c for c in [*companies, *extra_companies]}

    owner_ids = {c.owner_id for c in companies if c.owner_id}
    owner_ids |= {c.owner_id for c in contacts if c.owner_id}
    owner_names = await _owner_names(db, owner_ids)
    followups = await _last_followup_companies(db, set(company_map))

    reasons: dict[uuid.UUID, list[str]] = {}
    definite_ids: set[uuid.UUID] = set()
    for row in companies:
        row_reasons: list[str] = []
        if is_same_name(row.name, name):
            definite_ids.add(row.id)
            row_reasons.append("客户名称一致")
        elif is_same_name_core(row.name, name):
            row_reasons.append("名称去除法律后缀后一致")
        if norm_tax and (row.tax_id or "").strip().lower() == norm_tax:
            row_reasons.append("税号一致")
        if company_domain_hit(row, email):
            row_reasons.append("邮箱域名一致")
        if row_reasons:
            reasons[row.id] = row_reasons

    for row in contacts:
        if row.company_id is None:
            continue
        row_reasons = reasons.setdefault(row.company_id, [])
        if norm_email and is_same_email(row.email, email):
            row_reasons.append("联系人邮箱一致")
        elif shares_email_domain(row.email, email):
            row_reasons.append("邮箱域名一致")
        if digits and any(is_same_phone(row.phone, value) or is_same_phone(row.mobile, value) for value in digits):
            row_reasons.append("联系人电话一致")

    definite: list[dict[str, Any]] = []
    suspected: list[dict[str, Any]] = []
    for company_id, row_reasons in reasons.items():
        company = company_map.get(company_id)
        if company is None:
            continue
        candidate = _candidate(
            ref=company.code,
            kind="customer",
            entity_id=company.id,
            name=company.name,
            owner_name=owner_names.get(company.owner_id),
            company_id=company.id,
            company_name=company.name,
            reason=" / ".join(dict.fromkeys(row_reasons)),
            last_followup_at=followups.get(company.id),
        )
        (definite if company_id in definite_ids else suspected).append(candidate)

    return _pack(definite, suspected, limit)


def merge_note(remark: str | None, note: str | None) -> str | None:
    """把「仍然创建」的查重说明追加到备注，保留人工填写内容。"""
    clean = (note or "").strip()
    if not clean:
        return remark
    suffix = f"（查重确认：{clean}）"
    base = (remark or "").strip()
    return f"{base}\n{suffix}".strip() if base else suffix


def _dedup_payload(result: dict[str, Any]) -> dict[str, Any]:
    return {"candidates": result}


__all__ = [
    "CANDIDATE_LIMIT",
    "check_company_duplicates",
    "check_lead_duplicates",
    "email_domain",
    "is_same_email",
    "is_same_name",
    "is_same_name_core",
    "is_same_phone",
    "merge_note",
    "name_core",
    "normalize_email",
    "normalize_name",
    "normalize_phone",
    "shares_email_domain",
]
