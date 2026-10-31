"""通用 Schema：分页、排序。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Literal

from fastapi import Query
from pydantic import BaseModel, ConfigDict


class PageParams(BaseModel):
    page: int = 1
    page_size: int = 20
    sort: str = "created_at"
    order: Literal["asc", "desc"] = "desc"


def page_params(
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=200)] = 20,
    sort: Annotated[str, Query(max_length=50)] = "created_at",
    order: Annotated[Literal["asc", "desc"], Query()] = "desc",
) -> PageParams:
    return PageParams(page=page, page_size=page_size, sort=sort, order=order)


PageDep = Annotated[PageParams, Query()]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class IdMixin(BaseModel):
    id: uuid.UUID


class TimestampOut(ORMModel):
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
