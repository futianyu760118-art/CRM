"""SQLAlchemy 声明式基类与公共字段 Mixin（DOC-DEV-001 § 2.2）。"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, event, func, inspect, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class BaseModel(Base, UUIDPrimaryKeyMixin, TimestampMixin):
    """所有业务表的基类：id + created_at + updated_at + deleted_at。"""

    __abstract__ = True


class OwnerMixin:
    """业务归属：负责人 + 部门（DataScope 依据）。"""

    owner_id: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True, index=True)
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("department.id"), nullable=True, index=True
    )


class BusinessModel(BaseModel, OwnerMixin):
    __abstract__ = True


#: `revision` 自增的排除列：派生/同步/审计列，变化不代表业务内容变化
_REVISION_IGNORED_COLUMNS = frozenset(
    {"revision", "updated_at", "last_sync_at", "sync_status", "deleted_at", "tenant_id"}
)


def _bump_revision(mapper, connection, target) -> None:  # noqa: ANN001
    """AEOS Object.revision：仅业务字段真实变更时 +1（F3-A02）。

    幂等重放（同内容 setattr）不产生 UPDATE，也就不会触发本监听器；仅派生列变化
    （``sync_status``/``last_sync_at``/``deleted_at`` 等）同样不计数。
    """
    state = inspect(target)
    for attr in mapper.column_attrs:
        key = attr.key
        if key in _REVISION_IGNORED_COLUMNS:
            continue
        if state.attrs[key].history.has_changes():
            target.revision = (target.revision or 0) + 1
            return


class AeosObjectMixin:
    """AEOS V7.2.2 Object / Owner 契约列（PAND-330，架构 §4.1）。

    - Object 五字段：``tenant_id`` / ``revision`` + 派生的 object_type/object_id/source_system；
    - Owner 五字段：``fact_owner`` / ``processor`` / ``consumer`` / ``verifier``，
      ``record_owner`` 复用既有 ``OwnerMixin.owner_id``（不新增重复列）。
    """

    tenant_id: Mapped[str] = mapped_column(String(50), nullable=False, default="default", server_default="default")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    fact_owner: Mapped[str] = mapped_column(
        String(30), nullable=False, default="M05", server_default="M05", index=True
    )
    processor: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)
    consumer: Mapped[list[str]] = mapped_column(JSONB, nullable=False, default=list, server_default=text("'[]'::jsonb"))
    verifier: Mapped[uuid.UUID | None] = mapped_column(PGUUID(as_uuid=True), nullable=True)

    @classmethod
    def __declare_last__(cls) -> None:
        # 每个映射子类各挂一次 before_update：单实现点，且只在真正发出 UPDATE 时触发
        event.listen(cls, "before_update", _bump_revision)
