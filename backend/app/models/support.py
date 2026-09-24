"""支撑表：编号规则、功能开关、字典、系统配置。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import BaseModel


class NumberSequence(BaseModel):
    """编号规则：OPP-{YYYYMM}-{0001}，并发安全。"""

    __tablename__ = "number_sequence"

    key: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    pattern: Mapped[str] = mapped_column(String(100), default="{YYYYMM}-{0000}", nullable=False)
    reset_period: Mapped[str] = mapped_column(String(20), default="MONTH", nullable=False)
    current_value: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class FeatureFlag(BaseModel):
    __tablename__ = "feature_flag"

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    extra: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class Dictionary(BaseModel):
    """数据字典（枚举值统一用 varchar + 字典表）。"""

    __tablename__ = "dictionary"

    dict_type: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    label: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[str] = mapped_column(String(100), nullable=False)
    sort: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    remark: Mapped[str | None] = mapped_column(Text, nullable=True)


class SystemConfig(BaseModel):
    __tablename__ = "system_config"

    key: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    value: Mapped[str | None] = mapped_column(Text, nullable=True)
    group: Mapped[str] = mapped_column(String(50), default="general", nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)
