"""系统管理相关 Schema：用户、角色、权限、部门、字典、审计、功能开关。"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from app.schemas.common import ORMModel


# ------------------------------------------------------------------ 用户
class UserCreate(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    code: str | None = Field(default=None, max_length=20, description="业务员编号，如 HJ003（K3 职员编号）")
    password: str = Field(min_length=6, max_length=128)
    name: str = Field(min_length=1, max_length=100)
    email: str | None = None
    phone: str | None = None
    department_id: uuid.UUID | None = None
    role_ids: list[uuid.UUID] = Field(default_factory=list)
    is_superuser: bool = False
    status: str = "ACTIVE"


class UserUpdate(BaseModel):
    name: str | None = None
    code: str | None = None
    email: str | None = None
    phone: str | None = None
    department_id: uuid.UUID | None = None
    role_ids: list[uuid.UUID] | None = None
    status: str | None = None


class UserOut(ORMModel):
    id: uuid.UUID
    username: str
    code: str | None = None
    name: str
    email: str | None = None
    phone: str | None = None
    avatar: str | None = None
    department_id: uuid.UUID | None = None
    department_name: str | None = None
    is_superuser: bool
    status: str
    roles: list[str] = Field(default_factory=list)
    last_login_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


# ------------------------------------------------------------------ 角色
class RoleCreate(BaseModel):
    code: str = Field(min_length=2, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    permission_codes: list[str] = Field(default_factory=list)
    scope_type: str = "SELF"
    sort: int = 0


class RoleUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    permission_codes: list[str] | None = None
    scope_type: str | None = None
    status: str | None = None
    sort: int | None = None


class RoleOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    is_system: bool
    status: str
    sort: int
    permission_codes: list[str] = Field(default_factory=list)
    scope_type: str = "SELF"
    created_at: datetime


# ------------------------------------------------------------------ 权限
class PermissionOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    module: str
    type: str
    parent_id: uuid.UUID | None = None
    path: str | None = None
    icon: str | None = None
    sort: int
    status: str


# ------------------------------------------------------------------ 部门
class DepartmentCreate(BaseModel):
    code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=100)
    parent_id: uuid.UUID | None = None
    sort: int = 0
    status: str = "ACTIVE"
    remark: str | None = None


class DepartmentUpdate(BaseModel):
    name: str | None = None
    parent_id: uuid.UUID | None = None
    sort: int | None = None
    status: str | None = None
    remark: str | None = None


class DepartmentOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    parent_id: uuid.UUID | None = None
    sort: int
    status: str
    remark: str | None = None
    created_at: datetime


# ------------------------------------------------------------------ 字典
class DictionaryCreate(BaseModel):
    dict_type: str = Field(min_length=1, max_length=50)
    label: str
    value: str
    sort: int = 0
    enabled: bool = True
    remark: str | None = None


class DictionaryOut(ORMModel):
    id: uuid.UUID
    dict_type: str
    label: str
    value: str
    sort: int
    enabled: bool


# ------------------------------------------------------------------ 审计日志
class AuditLogOut(ORMModel):
    id: uuid.UUID
    username: str | None = None
    module: str
    action: str
    method: str
    path: str
    resource_id: str | None = None
    status_code: int
    success: bool
    duration_ms: int
    ip: str | None = None
    error_message: str | None = None
    request_id: str | None = None
    created_at: datetime


# ------------------------------------------------------------------ 功能开关
class FeatureFlagOut(ORMModel):
    id: uuid.UUID
    code: str
    name: str
    description: str | None = None
    enabled: bool
    extra: dict[str, Any] | None = None


class FeatureFlagUpdate(BaseModel):
    enabled: bool
