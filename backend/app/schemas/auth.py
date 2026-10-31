"""认证相关 Schema。"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50, examples=["admin"])
    password: str = Field(min_length=1, max_length=128, examples=["admin123"])


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class MenuItem(BaseModel):
    code: str
    name: str
    path: str | None = None
    icon: str | None = None
    sort: int = 0


class MeOut(BaseModel):
    id: uuid.UUID
    username: str
    name: str
    email: str | None = None
    avatar: str | None = None
    is_superuser: bool
    roles: list[str]
    permissions: list[str]
    department_id: uuid.UUID | None = None
    department_name: str | None = None
    menus: list[MenuItem] = []
