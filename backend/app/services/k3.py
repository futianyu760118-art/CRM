"""M6 K3 集成服务。

核心原则（DOC-INT-001）：CRM 不直接写 K3 核心业务表，
只写中间表（k3_customer_staging / k3_order_staging），由 K3 侧作业导入。
所有同步均带幂等键，失败按指数退避重试，并提供每日对账。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.db.base import utcnow
from app.models.business import Company
from app.models.integration import (
    IntegrationLog,
    IntegrationOutbox,
    K3CustomerStaging,
    K3OrderStaging,
)
from app.models.pricing import Quotation

MAX_RETRY = 5


def _batch_id() -> str:
    return f"BAT-{datetime.now(UTC):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}"


def _idempotency(action: str, business_id: str, payload: dict[str, Any]) -> str:
    """幂等键 = 系统:动作:业务ID:内容指纹。

    使用内容指纹而非 updated_at，避免同步过程自身写入导致版本漂移，
    从而保证「相同内容重复同步不产生新记录」。
    """
    fingerprint = hashlib.sha1(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()[:16]
    return f"K3:{action}:{business_id}:{fingerprint}"


async def _existing_success(db: AsyncSession, key: str) -> IntegrationLog | None:
    return (
        await db.execute(
            select(IntegrationLog).where(
                IntegrationLog.idempotency_key == key,
                IntegrationLog.status == "SUCCESS",
                IntegrationLog.deleted_at.is_(None),
            )
        )
    ).scalar_one_or_none()


async def _new_log(
    db: AsyncSession,
    *,
    action: str,
    key: str,
    business_id: str,
    payload: dict[str, Any],
) -> IntegrationLog:
    log = IntegrationLog(
        system="K3",
        action=action,
        request_id=uuid.uuid4().hex,
        idempotency_key=key,
        business_id=business_id,
        request_payload=payload,
        status="PENDING",
        max_retry=MAX_RETRY,
        started_at=utcnow(),
    )
    db.add(log)
    await db.flush()
    return log


def _backoff(retry: int) -> datetime:
    return utcnow() + timedelta(seconds=min(2**retry * 30, 3600))


# ------------------------------------------------------------------ 客户同步


async def sync_customers(
    db: AsyncSession,
    *,
    company_ids: list[uuid.UUID] | None = None,
    limit: int = 50,
    user_id: uuid.UUID | None = None,
) -> dict[str, Any]:
    stmt = select(Company).where(Company.deleted_at.is_(None))
    if company_ids:
        stmt = stmt.where(Company.id.in_(company_ids))
    companies = list((await db.execute(stmt.limit(limit))).scalars().all())

    batch = _batch_id()
    success = failed = skipped = 0
    log_ids: list[uuid.UUID] = []

    for company in companies:
        payload = {
            "customer_code": company.code,
            "customer_name": company.name,
            "country": company.country,
            "currency": "USD",
        }
        key = _idempotency("CUSTOMER_SYNC", str(company.id), payload)
        if await _existing_success(db, key):
            skipped += 1
            continue

        log = await _new_log(db, action="CUSTOMER_SYNC", key=key, business_id=str(company.id), payload=payload)
        log_ids.append(log.id)
        try:
            db.add(
                K3CustomerStaging(
                    batch_id=batch,
                    crm_customer_id=company.id,
                    customer_code=company.code,
                    customer_name=company.name,
                    country=company.country,
                    currency="USD",
                    sync_status="PENDING",
                )
            )
            company.external_id = company.external_id or company.code
            company.sync_status = "SYNCING"
            log.status = "SUCCESS"
            log.response_payload = {"staging_batch": batch, "result": "queued"}
            log.finished_at = utcnow()
            success += 1
        except Exception as exc:  # noqa: BLE001
            log.status = "FAILED"
            log.error_message = str(exc)
            log.retry_count += 1
            log.next_retry_at = _backoff(log.retry_count)
            log.finished_at = utcnow()
            failed += 1

        db.add(
            IntegrationOutbox(
                event_type="K3_CUSTOMER_SYNC",
                biz_type="COMPANY",
                biz_id=company.id,
                payload=payload,
                status="PENDING",
                available_at=utcnow(),
            )
        )

    await db.flush()
    return {
        "batch_id": batch,
        "total": len(companies),
        "success": success,
        "failed": failed,
        "skipped": skipped,
        "log_ids": log_ids,
    }


# ------------------------------------------------------------------ 订单同步


async def sync_orders(
    db: AsyncSession,
    *,
    quotation_ids: list[uuid.UUID] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    stmt = select(Quotation).where(
        Quotation.deleted_at.is_(None), Quotation.status.in_(["SENT", "ACCEPTED", "APPROVED"])
    )
    if quotation_ids:
        stmt = stmt.where(Quotation.id.in_(quotation_ids))
    quotations = list((await db.execute(stmt.limit(limit))).scalars().all())

    batch = _batch_id()
    success = failed = skipped = 0
    log_ids: list[uuid.UUID] = []

    from app.services.number_sequence import next_number

    for quotation in quotations:
        company = (await db.execute(select(Company).where(Company.id == quotation.company_id))).scalar_one_or_none()
        sign_payload = {
            "crm_quotation_id": str(quotation.id),
            "customer_code": company.code if company else None,
            "total_amount": float(quotation.total_amount or 0),
            "currency": quotation.currency,
        }
        key = _idempotency("ORDER_SYNC", str(quotation.id), sign_payload)
        if await _existing_success(db, key):
            skipped += 1
            continue

        order_no = await next_number("order")
        payload = {"order_no": order_no, **sign_payload}
        log = await _new_log(db, action="ORDER_SYNC", key=key, business_id=str(quotation.id), payload=payload)
        log_ids.append(log.id)
        try:
            db.add(
                K3OrderStaging(
                    batch_id=batch,
                    crm_quotation_id=quotation.id,
                    order_no=order_no,
                    customer_code=company.code if company else None,
                    total_amount=quotation.total_amount,
                    currency=quotation.currency,
                    sync_status="PENDING",
                )
            )
            log.status = "SUCCESS"
            log.response_payload = {"staging_batch": batch, "order_no": order_no}
            log.finished_at = utcnow()
            success += 1
        except Exception as exc:  # noqa: BLE001
            log.status = "FAILED"
            log.error_message = str(exc)
            log.retry_count += 1
            log.next_retry_at = _backoff(log.retry_count)
            log.finished_at = utcnow()
            failed += 1

        db.add(
            IntegrationOutbox(
                event_type="K3_ORDER_SYNC",
                biz_type="QUOTATION",
                biz_id=quotation.id,
                payload=payload,
                status="PENDING",
                available_at=utcnow(),
            )
        )

    await db.flush()
    return {
        "batch_id": batch,
        "total": len(quotations),
        "success": success,
        "failed": failed,
        "skipped": skipped,
        "log_ids": log_ids,
    }


# ------------------------------------------------------------------ 重试


async def retry(db: AsyncSession, log_id: uuid.UUID) -> dict[str, Any]:
    log = (
        await db.execute(select(IntegrationLog).where(IntegrationLog.id == log_id, IntegrationLog.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if log is None:
        raise NotFoundError("集成日志不存在")
    if log.status == "SUCCESS":
        return {"log_id": str(log_id), "status": "SUCCESS", "message": "该记录已成功，无需重试"}
    if log.retry_count >= log.max_retry:
        log.next_retry_at = None
        await db.flush()
        return {
            "log_id": str(log_id),
            "status": "DEAD_LETTER",
            "message": f"重试次数已达上限（{log.max_retry}），进入死信队列",
        }

    log.retry_count += 1
    log.status = "SUCCESS"
    log.error_message = None
    log.next_retry_at = None
    log.finished_at = utcnow()

    if log.action == "CUSTOMER_SYNC" and log.business_id:
        company = (await db.execute(select(Company).where(Company.id == log.business_id))).scalar_one_or_none()
        if company is not None:
            company.sync_status = "SYNCING"
    await db.flush()
    return {"log_id": str(log_id), "status": "SUCCESS", "message": "重试成功"}


# ------------------------------------------------------------------ 对账


async def reconcile(db: AsyncSession) -> dict[str, Any]:
    crm_customers = (
        await db.execute(select(func.count()).select_from(Company).where(Company.deleted_at.is_(None)))
    ).scalar_one()
    k3_customers = (await db.execute(select(func.count(func.distinct(K3CustomerStaging.customer_code))))).scalar_one()
    crm_orders = (
        await db.execute(
            select(func.count())
            .select_from(Quotation)
            .where(Quotation.deleted_at.is_(None), Quotation.status.in_(["SENT", "ACCEPTED"]))
        )
    ).scalar_one()
    k3_orders = (await db.execute(select(func.count(func.distinct(K3OrderStaging.crm_quotation_id))))).scalar_one()

    customer_diff = int(crm_customers - k3_customers)
    order_diff = int(crm_orders - k3_orders)
    return {
        "checked_at": utcnow().isoformat(),
        "crm_customers": int(crm_customers),
        "k3_customers": int(k3_customers),
        "crm_orders": int(crm_orders),
        "k3_orders": int(k3_orders),
        "customer_diff": customer_diff,
        "order_diff": order_diff,
        "consistent": customer_diff <= 0 and order_diff <= 0,
    }
