"""产品资料与标准报价领域逻辑（PAND-316 PROD-01/02/03）。

纯函数部分（版本号、区间、状态）供接口与自检共用；``recompute_current``
是唯一需要数据库的写操作，负责重算「当前有效」标记。
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business import ProductDocument, StandardQuote

DOC_MAX_BYTES = 50 * 1024 * 1024
ALLOWED_EXTENSIONS: tuple[str, ...] = (
    "pdf",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "ppt",
    "pptx",
    "jpg",
    "jpeg",
    "png",
    "zip",
)

VERSION_PATTERN = re.compile(r"^v\d+(?:\.\d+){0,2}$")
VERSION_MAX_LENGTH = 20

QUOTE_ACTIVE = "ACTIVE"
QUOTE_DISABLED = "DISABLED"
QUOTE_LABELS: dict[str, str] = {
    "ACTIVE": "生效中",
    "EXPIRED": "已过期",
    "PENDING": "未生效",
    "DISABLED": "已停用",
}


# ------------------------------------------------------------------ 版本号（PROD-02）
def validate_version(version_no: str | None) -> str:
    """返回归一后的版本号；格式非法时抛出中文原因。"""
    value = (version_no or "").strip()
    if not value:
        raise ValueError("不能为空")
    if len(value) > VERSION_MAX_LENGTH:
        raise ValueError(f"最多 {VERSION_MAX_LENGTH} 字")
    if not VERSION_PATTERN.fullmatch(value):
        raise ValueError("格式应为 v1 或 v1.0 或 v1.2.3")
    return value


def version_key(version_no: str) -> tuple[int, ...]:
    """数字段比较，避免 ``v1.10`` 被字符串判为小于 ``v1.9``。"""
    body = version_no[1:] if version_no.startswith("v") else version_no
    return tuple(int(part) for part in body.split(".") if part.isdigit())


def next_version_no(existing: Iterable[str]) -> str:
    """同类型最新版本整数位 +1（v1.0 -> v2；无历史 -> v1）。"""
    keys = [version_key(v) for v in existing if v]
    if not keys:
        return "v1"
    return f"v{max(key[0] for key in keys) + 1}"


# ------------------------------------------------------------------ 文件（PROD-01）
def file_extension(filename: str | None) -> str:
    name = (filename or "").strip()
    if "." not in name:
        return ""
    return name.rsplit(".", 1)[1].lower()


def validate_upload(filename: str | None, size: int) -> str:
    """校验格式与大小，返回扩展名；非法时抛出中文原因。"""
    ext = file_extension(filename)
    if ext not in ALLOWED_EXTENSIONS:
        allowed = "、".join(ALLOWED_EXTENSIONS)
        raise ValueError(f"不支持的格式（允许 {allowed}）")
    if size > DOC_MAX_BYTES:
        raise ValueError("单文件不能超过 50MB")
    if size <= 0:
        raise ValueError("文件内容为空")
    return ext


# ------------------------------------------------------------------ 标准报价（PROD-03）
def normalize_price(value: float | Decimal | None) -> Decimal:
    try:
        price = Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValueError("格式不正确（应为数字）") from None
    if price <= 0:
        raise ValueError("必须大于 0")
    if price.as_tuple().exponent < -4:
        raise ValueError("最多 4 位小数")
    return price


def interval_overlaps(a_from: int, a_to: int | None, b_from: int, b_to: int | None) -> bool:
    """区间口径 [起, 止)，止为空表示无上限。"""
    a_hi = a_to if a_to is not None else float("inf")
    b_hi = b_to if b_to is not None else float("inf")
    return a_from < b_hi and b_from < a_hi


def find_overlap(
    existing: Iterable[StandardQuote], qty_from: int, qty_to: int | None
) -> StandardQuote | None:
    for quote in existing:
        if quote.status == QUOTE_DISABLED:
            continue
        if interval_overlaps(qty_from, qty_to, quote.qty_from, quote.qty_to):
            return quote
    return None


def interval_text(qty_from: int, qty_to: int | None) -> str:
    upper = qty_to if qty_to is not None else "∞"
    return f"[{qty_from}, {upper})"


def quote_status(status: str, valid_from: date, valid_to: date, today: date) -> str:
    if status == QUOTE_DISABLED:
        return "DISABLED"
    if valid_to < today:
        return "EXPIRED"
    if valid_from > today:
        return "PENDING"
    return "ACTIVE"


def quote_status_label(status: str, valid_from: date, valid_to: date, today: date) -> str:
    return QUOTE_LABELS[quote_status(status, valid_from, valid_to, today)]


def default_plan_date(today: date) -> date:
    return today + timedelta(days=7)


# ------------------------------------------------------------------ 当前有效重算
async def recompute_current(db: AsyncSession, product_id: uuid.UUID, doc_type: str) -> None:
    """同产品同类型下版本号最高的一份置为当前有效，其余置历史。"""
    rows = (
        (
            await db.execute(
                select(ProductDocument).where(
                    ProductDocument.product_id == product_id,
                    ProductDocument.doc_type == doc_type,
                    ProductDocument.deleted_at.is_(None),
                )
            )
        )
        .scalars()
        .all()
    )
    if not rows:
        return
    top = max(rows, key=lambda r: version_key(r.version_no))
    for row in rows:
        row.is_current = row.id == top.id
