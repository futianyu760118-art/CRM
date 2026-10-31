"""联系人-客户关联服务（一客多联系人 / 一人多客户，PAND-314 §2.3）。

``contact_company_link`` 承载「关系类型 + 主要联系人标记」；``contact.company_id``
与 ``contact.is_primary`` 保留为主公司冗余列，统一由本模块回写，其他端点不得直写。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import utcnow
from app.domain import dictionaries as dic
from app.models.business import Company, Contact, ContactCompanyLink


def contact_value(contact: Contact) -> str | None:
    """主要联系人展示值：手机 → WhatsApp → 微信 → 邮箱，首个非空。"""
    for value in (contact.mobile, contact.whatsapp, contact.wechat, contact.email):
        if value:
            return value
    return None


async def _active_link(
    db: AsyncSession, contact_id: uuid.UUID, company_id: uuid.UUID
) -> ContactCompanyLink | None:
    return (
        await db.execute(
            select(ContactCompanyLink).where(
                ContactCompanyLink.contact_id == contact_id,
                ContactCompanyLink.company_id == company_id,
                ContactCompanyLink.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def _get_or_create_link(
    db: AsyncSession,
    contact: Contact,
    company_id: uuid.UUID,
    relation_type: str,
) -> ContactCompanyLink:
    link = await _active_link(db, contact.id, company_id)
    if link is not None:
        link.relation_type = relation_type
        return link
    # 软删行仍占用 (contact_id, company_id) 唯一键，复用并复活
    stale = (
        await db.execute(
            select(ContactCompanyLink).where(
                ContactCompanyLink.contact_id == contact.id,
                ContactCompanyLink.company_id == company_id,
            )
        )
    ).scalar_one_or_none()
    if stale is not None:
        stale.deleted_at = None
        stale.relation_type = relation_type
        stale.is_primary = False
        return stale
    link = ContactCompanyLink(
        contact_id=contact.id,
        company_id=company_id,
        relation_type=relation_type,
        is_primary=False,
        owner_id=contact.owner_id,
        department_id=contact.department_id,
    )
    db.add(link)
    return link


async def attach_company(
    db: AsyncSession,
    contact: Contact,
    company_id: uuid.UUID,
    relation_type: str = dic.CONTACT_RELATION_DEFAULT,
    is_primary: bool = False,
) -> ContactCompanyLink:
    """为联系人新增/更新某客户关联；主档无主公司时回填。"""
    link = await _get_or_create_link(db, contact, company_id, relation_type)
    if contact.company_id is None:
        contact.company_id = company_id
    if is_primary:
        await set_primary(db, contact, company_id)
    await db.flush()
    return link


async def set_primary(db: AsyncSession, contact: Contact, company_id: uuid.UUID) -> None:
    """设该客户的主要联系人，旧主自动取消（含主档冗余列）。"""
    await db.execute(
        update(ContactCompanyLink)
        .where(
            ContactCompanyLink.company_id == company_id,
            ContactCompanyLink.deleted_at.is_(None),
            ContactCompanyLink.is_primary.is_(True),
            ContactCompanyLink.contact_id != contact.id,
        )
        .values(is_primary=False, updated_at=utcnow())
    )
    await db.execute(
        update(Contact)
        .where(
            Contact.company_id == company_id,
            Contact.deleted_at.is_(None),
            Contact.id != contact.id,
            Contact.is_primary.is_(True),
        )
        .values(is_primary=False, updated_at=utcnow())
    )
    link = await _get_or_create_link(db, contact, company_id, dic.CONTACT_RELATION_DEFAULT)
    link.is_primary = True
    contact.company_id = company_id
    contact.is_primary = True
    await db.flush()


async def detach_company(db: AsyncSession, contact: Contact, company_id: uuid.UUID) -> None:
    """仅解除某客户关联，主档与其他客户关联保留。"""
    link = await _active_link(db, contact.id, company_id)
    if link is None:
        return
    link.deleted_at = utcnow()
    link.is_primary = False
    if contact.company_id == company_id:
        replacement = (
            await db.execute(
                select(ContactCompanyLink)
                .where(
                    ContactCompanyLink.contact_id == contact.id,
                    ContactCompanyLink.deleted_at.is_(None),
                    ContactCompanyLink.company_id != company_id,
                )
                .order_by(ContactCompanyLink.is_primary.desc(), ContactCompanyLink.created_at.asc())
            )
        ).scalars().first()
        contact.company_id = replacement.company_id if replacement else None
        contact.is_primary = bool(replacement and replacement.is_primary)


async def contact_companies_map(
    db: AsyncSession, contacts: list[Contact]
) -> dict[uuid.UUID, list[dict[str, Any]]]:
    """批量取联系人 → 关联客户列表（含关系类型）。"""
    ids = [c.id for c in contacts]
    result: dict[uuid.UUID, list[dict[str, Any]]] = {c.id: [] for c in contacts}
    if not ids:
        return result
    rows = (
        await db.execute(
            select(ContactCompanyLink, Company)
            .join(Company, Company.id == ContactCompanyLink.company_id)
            .where(
                ContactCompanyLink.contact_id.in_(ids),
                ContactCompanyLink.deleted_at.is_(None),
                Company.deleted_at.is_(None),
            )
            .order_by(ContactCompanyLink.is_primary.desc(), Company.name.asc())
        )
    ).all()
    for link, company in rows:
        result[link.contact_id].append(
            {
                "company_id": company.id,
                "company_code": company.code,
                "company_name": company.name,
                "relation_type": link.relation_type,
                "relation_label": dic.label_of(dic.CONTACT_RELATION_TYPES, link.relation_type)
                or link.relation_type,
                "is_primary": link.is_primary,
            }
        )
    # 迁移未覆盖的存量数据：无 link 时按主档列兜底
    legacy_ids = {c.company_id for c in contacts if c.company_id and not result[c.id]}
    if legacy_ids:
        companies = {
            c.id: c
            for c in (
                await db.execute(
                    select(Company).where(Company.id.in_(legacy_ids), Company.deleted_at.is_(None))
                )
            )
            .scalars()
            .all()
        }
        for contact in contacts:
            if not result[contact.id] and contact.company_id in companies:
                company = companies[contact.company_id]
                result[contact.id].append(
                    {
                        "company_id": company.id,
                        "company_code": company.code,
                        "company_name": company.name,
                        "relation_type": dic.CONTACT_RELATION_DEFAULT,
                        "relation_label": dic.CONTACT_RELATION_TYPES[dic.CONTACT_RELATION_DEFAULT],
                        "is_primary": contact.is_primary,
                    }
                )
    return result


async def company_contacts(db: AsyncSession, company_id: uuid.UUID) -> list[dict[str, Any]]:
    """某客户下的联系人（经 link 表，含关系类型），存量按主档兜底。"""
    rows = (
        await db.execute(
            select(ContactCompanyLink, Contact)
            .join(Contact, Contact.id == ContactCompanyLink.contact_id)
            .where(
                ContactCompanyLink.company_id == company_id,
                ContactCompanyLink.deleted_at.is_(None),
                Contact.deleted_at.is_(None),
            )
            .order_by(ContactCompanyLink.is_primary.desc(), Contact.created_at.asc())
        )
    ).all()
    linked_ids = {contact.id for _, contact in rows}
    items: list[dict[str, Any]] = []
    for link, contact in rows:
        items.append(_contact_item(contact, link.relation_type, link.is_primary, link.id))
    legacy_conds = [Contact.company_id == company_id, Contact.deleted_at.is_(None)]
    if linked_ids:
        legacy_conds.append(Contact.id.notin_(linked_ids))
    legacy = (await db.execute(select(Contact).where(*legacy_conds))).scalars().all()
    for contact in legacy:
        items.append(
            _contact_item(contact, dic.CONTACT_RELATION_DEFAULT, contact.is_primary, contact.id)
        )
    items.sort(key=lambda item: (not item["is_primary"], item["created_at"] or ""))
    return items


def _contact_item(
    contact: Contact,
    relation_type: str,
    is_primary: bool,
    link_id: uuid.UUID,
) -> dict[str, Any]:
    return {
        "id": str(contact.id),
        "link_id": str(link_id),
        "name": contact.name,
        "position": contact.position,
        "email": contact.email,
        "phone": contact.phone,
        "mobile": contact.mobile,
        "wechat": contact.wechat,
        "whatsapp": contact.whatsapp,
        "relation_type": relation_type,
        "relation_label": dic.label_of(dic.CONTACT_RELATION_TYPES, relation_type) or relation_type,
        "is_primary": is_primary,
        "contact_value": contact_value(contact),
        "created_at": _iso(contact.created_at),
    }


async def primary_contact_map(
    db: AsyncSession, company_ids: set[uuid.UUID]
) -> dict[uuid.UUID, dict[str, Any]]:
    """批量取客户主要联系人 ``{company_id: {name, contact_value}}``。"""
    clean = {i for i in company_ids if i is not None}
    if not clean:
        return {}
    result: dict[uuid.UUID, dict[str, Any]] = {}
    rows = (
        await db.execute(
            select(ContactCompanyLink.company_id, Contact)
            .join(Contact, Contact.id == ContactCompanyLink.contact_id)
            .where(
                ContactCompanyLink.company_id.in_(clean),
                ContactCompanyLink.is_primary.is_(True),
                ContactCompanyLink.deleted_at.is_(None),
                Contact.deleted_at.is_(None),
            )
        )
    ).all()
    for company_id, contact in rows:
        result[company_id] = {"name": contact.name, "contact_value": contact_value(contact)}
    missing = clean - set(result)
    if missing:
        legacy = (
            await db.execute(
                select(Contact.company_id, Contact).where(
                    Contact.company_id.in_(missing),
                    Contact.is_primary.is_(True),
                    Contact.deleted_at.is_(None),
                )
            )
        ).all()
        for company_id, contact in legacy:
            result.setdefault(company_id, {"name": contact.name, "contact_value": contact_value(contact)})
    return result


async def company_contact_counts(db: AsyncSession, company_ids: set[uuid.UUID]) -> dict[uuid.UUID, int]:
    """批量统计每客户联系人数量（link 表 ∪ 主档列，去重）。"""
    clean = {i for i in company_ids if i is not None}
    if not clean:
        return {}
    seen: dict[uuid.UUID, set[uuid.UUID]] = {cid: set() for cid in clean}
    linked_pairs = (
        await db.execute(
            select(ContactCompanyLink.company_id, ContactCompanyLink.contact_id)
            .join(Contact, Contact.id == ContactCompanyLink.contact_id)
            .where(
                ContactCompanyLink.company_id.in_(clean),
                ContactCompanyLink.deleted_at.is_(None),
                Contact.deleted_at.is_(None),
            )
        )
    ).all()
    for company_id, contact_id in linked_pairs:
        seen.setdefault(company_id, set()).add(contact_id)
    legacy = (
        await db.execute(
            select(Contact.company_id, Contact.id).where(
                Contact.company_id.in_(clean), Contact.deleted_at.is_(None)
            )
        )
    ).all()
    for company_id, contact_id in legacy:
        seen.setdefault(company_id, set()).add(contact_id)
    return {company_id: len(ids) for company_id, ids in seen.items() if ids}


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


__all__ = [
    "attach_company",
    "company_contact_counts",
    "company_contacts",
    "contact_companies_map",
    "contact_value",
    "detach_company",
    "primary_contact_map",
    "set_primary",
]
