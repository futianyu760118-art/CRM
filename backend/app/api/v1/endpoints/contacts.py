"""M2 联系人接口（通用 CRUD + 客户名补全）。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.api.crud import CrudConfig, build_crud_router
from app.models.business import Company, Contact
from app.schemas.business import ContactCreate, ContactOut, ContactUpdate
from app.services.query import name_map


async def _enrich(db: AsyncSession, rows: list[Any]) -> list[dict[str, Any]]:
    mapping = await name_map(db, Company, {r.company_id for r in rows if r.company_id})
    result = []
    for row in rows:
        data = ContactOut.model_validate(row).model_dump(mode="json")
        data["company_name"] = mapping.get(row.company_id)
        result.append(data)
    return result


router = build_crud_router(
    CrudConfig(
        model=Contact,
        prefix="/contacts",
        tag="M2-联系人",
        name="联系人",
        create_schema=ContactCreate,
        update_schema=ContactUpdate,
        out_schema=ContactOut,
        view_permission="contact:view",
        create_permission="contact:create",
        update_permission="contact:update",
        delete_permission="contact:delete",
        search_fields=("name", "email", "phone", "mobile"),
        filter_fields={"company_id": "company_id"},
        enrich=_enrich,
        description="联系人 CRUD，支持按客户过滤与关键词搜索",
    )
)
