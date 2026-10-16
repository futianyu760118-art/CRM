"""EBMS 集成通道（AEOS 契约投递）。

红线（本模块严格遵守）：
- 不直写 EBMS 库：只经 `IntegrationOutbox` 落库 + `EbmsTransport` 对外投递契约。
- 不新增 CRM 业务内容：复用既有 `integration_outbox` / `integration_log`，读取既有
  `quotation` 数据，不新增业务表、不改业务状态机。

投递语义（仿 M6 K3 模式，并修正其可复现问题）：
- 本地消息表 `IntegrationOutbox` 与业务事务同库写入，Worker/端点异步投递。
- 幂等键 = ``EBMS:{action}:{契约ID}:{内容指纹}``。指纹覆盖契约除 `occurred_at`
  （易变时钟）外的全部字段 → 「同内容重复投递」被跳过，「数值/严重度变化」产生新投递。
- 失败按指数退避重试，超过 `EBMS_MAX_RETRY` 转 `DEAD_LETTER`，全过程写 `IntegrationLog` 供对账。
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import UTC, date, datetime, time, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.contracts.aeos import (
    ContractValidationError,
    build_exception_contract,
    build_result_contract,
    to_wire,
    validate_contract,
)
from app.core.config import settings
from app.core.error_codes import ErrCode
from app.core.exceptions import ApiError, NotFoundError
from app.db.base import utcnow
from app.models.integration import IntegrationLog, IntegrationOutbox
from app.models.pricing import Quotation
from app.services.ebms_transport import DeliveryResult, EbmsTransport

# 契约源系统：CRM = M05 销售自治（EBMS/docs/AEOS_V7.2_DATA_OWNERSHIP_V1.md）
SOURCE_SYSTEM = "M05"

EVENT_RESULT = "AEOS_RESULT_V1"
EVENT_EXCEPTION = "AEOS_EXCEPTION_V1"
ACTION_RESULT = "RESULT_DELIVER"
ACTION_EXCEPTION = "EXCEPTION_DELIVER"

_EVENT_ACTION: dict[str, str] = {
    EVENT_RESULT: ACTION_RESULT,
    EVENT_EXCEPTION: ACTION_EXCEPTION,
}

OUTBOX_PENDING = "PENDING"
OUTBOX_DONE = "DONE"
OUTBOX_FAILED = "FAILED"

LOG_PENDING = "PENDING"
LOG_SUCCESS = "SUCCESS"
LOG_FAILED = "FAILED"
LOG_DEAD_LETTER = "DEAD_LETTER"

#: 中国标准时间固定 +08:00（无夏令时，等价 Asia/Shanghai，且免 tzdata 依赖）
CN_TZ = timezone(timedelta(hours=8))

#: 试点 A 计入「经营结果」的报价状态（CRM 对销售订单商务状态的 Owner 边界）
ORDER_STATUS_FOR_METRIC = "ACCEPTED"
#: 指标口径：code -> (unit, calculation_version)
METRIC_SPECS: dict[str, tuple[str, str]] = {
    "order_count": ("count", "M05-ORDER-COUNT-V1"),
    "order_amount": ("currency", "M05-ORDER-AMOUNT-V1"),
    "avg_order_amount": ("currency", "M05-AVG-ORDER-AMOUNT-V1"),
}

#: 试点 B 视为「在途订单」的报价状态
IN_FLIGHT_ORDER_STATUSES: tuple[str, ...] = ("APPROVED", "SENT", "ACCEPTED")
#: 逾期天数 -> severity（自高到低匹配）
SEVERITY_THRESHOLDS: tuple[tuple[int, str], ...] = ((30, "critical"), (14, "high"), (7, "medium"), (0, "low"))
REASON_DELIVERY_OVERDUE = "DELIVERY_OVERDUE"


def cn_now() -> datetime:
    """当前时间（+08:00，秒级）。"""
    return datetime.now(CN_TZ).replace(microsecond=0)


def _order_timestamp() -> Any:
    """订单业务时间：成交审批 > 发给客户 > 建单，取首个可用时间（SQL 侧 coalesce）。"""
    return func.coalesce(Quotation.approved_at, Quotation.sent_at, Quotation.created_at)


def _fingerprint(contract: dict[str, Any]) -> str:
    """内容指纹：排除易变时钟字段 `occurred_at`，其余字段参与。"""
    stable = {k: v for k, v in contract.items() if k != "occurred_at"}
    return hashlib.sha1(
        json.dumps(stable, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()[:16]


def _idempotency(action: str, contract_id: str, contract: dict[str, Any]) -> str:
    return f"EBMS:{action}:{contract_id}:{_fingerprint(contract)}"


def _backoff(retry: int) -> datetime:
    return utcnow() + timedelta(seconds=min(2**retry * 30, 3600))


def _batch_id() -> str:
    return f"EBMS-{datetime.now(UTC):%Y%m%d%H%M%S}-{uuid.uuid4().hex[:6]}"


async def _latest_log(db: AsyncSession, key: str) -> IntegrationLog | None:
    """取该幂等键最近一条日志（K3 的 `scalar_one_or_none` 在重试产生多行时会抛错，此处规避）。"""
    return (
        await db.execute(
            select(IntegrationLog)
            .where(IntegrationLog.idempotency_key == key, IntegrationLog.deleted_at.is_(None))
            .order_by(IntegrationLog.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _outbox_for_key(db: AsyncSession, key: str) -> IntegrationOutbox | None:
    return (
        await db.execute(
            select(IntegrationOutbox)
            .where(
                IntegrationOutbox.idempotency_key == key,
                IntegrationOutbox.deleted_at.is_(None),
            )
            .order_by(IntegrationOutbox.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


async def _enqueue(
    db: AsyncSession,
    *,
    contract: Any,
    event_type: str,
    biz_type: str,
    biz_id: uuid.UUID,
) -> tuple[IntegrationOutbox | None, IntegrationLog | None, bool]:
    """事务内写入 Outbox + Log，返回 (outbox, log, created)。

    created=False 表示同内容契约已在队列中或已投递成功，本次不重复入队。
    仅当上次尝试已失败（FAILED / DEAD_LETTER）时才重新武装同一条 Outbox 行。
    """
    action = _EVENT_ACTION[event_type]
    wire = to_wire(contract)
    contract_id = contract.contract_id
    key = _idempotency(action, contract_id, wire)

    existing = await _latest_log(db, key)
    if existing is not None and existing.status in (LOG_PENDING, LOG_SUCCESS):
        return None, existing, False

    if existing is None:
        log = _new_log(db, action=action, key=key, contract_id=contract_id, wire=wire)
    else:
        # 失败/死信后的重新入队：复用同一行，避免幂等键下堆积重复行
        log = existing
        log.status = LOG_PENDING
        log.error_message = None
        log.next_retry_at = None
        log.started_at = utcnow()
        log.finished_at = None
        log.request_payload = wire

    outbox = await _outbox_for_key(db, key)
    if outbox is not None and outbox.status != OUTBOX_DONE:
        outbox.payload = wire
        outbox.status = OUTBOX_PENDING
        outbox.retry_count = 0
        outbox.available_at = utcnow()
        outbox.processed_at = None
    else:
        outbox = IntegrationOutbox(
            event_type=event_type,
            biz_type=biz_type,
            biz_id=biz_id,
            idempotency_key=key,
            payload=wire,
            status=OUTBOX_PENDING,
            available_at=utcnow(),
        )
        db.add(outbox)

    await db.flush()
    return outbox, log, True


def _new_log(db: AsyncSession, *, action: str, key: str, contract_id: str, wire: dict[str, Any]) -> IntegrationLog:
    log = IntegrationLog(
        system="EBMS",
        action=action,
        request_id=uuid.uuid4().hex,
        idempotency_key=key,
        business_id=contract_id,
        request_payload=wire,
        status=LOG_PENDING,
        max_retry=settings.EBMS_MAX_RETRY,
        started_at=utcnow(),
    )
    db.add(log)
    return log


# ------------------------------------------------------------------ 试点 A：销售/订单经营结果


async def emit_sales_result(
    db: AsyncSession,
    *,
    period_start: date,
    period_end: date,
    metric_code: str = "order_amount",
    currency: str = "RMB",
    limit: int = 500,
) -> dict[str, Any]:
    """把 CRM 侧销售/订单经营结果构造成 `AEOS.Result.V1` 并入库投递队列。

    口径说明：
    - 统计区间为 `[period_start 00:00, period_end+1d 00:00)` 半开区间，避免边界重复计入。
    - 仅按同币种聚合，**不做汇率折算** —— 避免在 CRM 内重复定义 M09 财经口径（红线 4）。
    - `evidence_ids` 记录全部计入的报价单 ID，满足「专业指标必须记录 calculation_version 与 evidence_ids」。
    """
    if metric_code not in METRIC_SPECS:
        raise ApiError(ErrCode.PARAM_ERROR, f"未知指标: {metric_code}，允许: {sorted(METRIC_SPECS)}")
    if period_end < period_start:
        raise ApiError(ErrCode.PARAM_ERROR, "period_end 不得早于 period_start")

    unit, calculation_version = METRIC_SPECS[metric_code]
    start_dt = datetime.combine(period_start, time.min, tzinfo=UTC)
    end_dt = datetime.combine(period_end + timedelta(days=1), time.min, tzinfo=UTC)
    order_ts = _order_timestamp()

    rows = (
        await db.execute(
            select(Quotation.id, Quotation.total_amount)
            .where(
                Quotation.deleted_at.is_(None),
                Quotation.status == ORDER_STATUS_FOR_METRIC,
                Quotation.currency == currency,
                order_ts >= start_dt,
                order_ts < end_dt,
            )
            .order_by(order_ts)
            .limit(limit)
        )
    ).all()

    evidence_ids = [str(r[0]) for r in rows]
    order_count = len(rows)
    total_amount = sum(float(r[1] or 0) for r in rows)

    if metric_code == "order_count":
        value = float(order_count)
    elif metric_code == "avg_order_amount":
        value = round(total_amount / order_count, 4) if order_count else 0.0
    else:
        value = round(total_amount, 4)

    result_id = f"RES-{SOURCE_SYSTEM}-{metric_code.upper()}-{period_start:%Y%m%d}-{period_end:%Y%m%d}-{currency}"
    contract = build_result_contract(
        result_id=result_id,
        source_system=SOURCE_SYSTEM,
        object_type="BusinessMetric",
        object_id=metric_code,
        period_start=period_start,
        period_end=period_end,
        metric_code=metric_code,
        metric_value=value,
        metric_unit=unit,
        calculation_version=calculation_version,
        evidence_ids=evidence_ids,
        trace_id=f"TRACE-{result_id}",
        occurred_at=datetime.combine(period_end, time(23, 59, 59), tzinfo=CN_TZ),
        extra={"currency": currency, "order_count": order_count},
    )

    anchor = rows[0][0] if rows else uuid.uuid4()
    _, log, created = await _enqueue(
        db, contract=contract, event_type=EVENT_RESULT, biz_type="QUOTATION", biz_id=anchor
    )
    await db.flush()

    return {
        "batch_id": _batch_id(),
        "contract_version": contract.contract_version,
        "contract_id": contract.contract_id,
        "event_type": EVENT_RESULT,
        "metric_code": metric_code,
        "metric_value": value,
        "unit": unit,
        "currency": currency,
        "order_count": order_count,
        "evidence_count": len(evidence_ids),
        "created": created,
        "skipped": not created,
        "log_id": str(log.id) if log else None,
        "idempotency_key": log.idempotency_key if log else None,
    }


# ------------------------------------------------------------------ 试点 B：订单交付逾期异常


def _severity_for(days_overdue: int) -> str:
    for threshold, level in SEVERITY_THRESHOLDS:
        if days_overdue >= threshold:
            return level
    return SEVERITY_THRESHOLDS[-1][1]


async def emit_delivery_overdue(
    db: AsyncSession,
    *,
    sla_days: int = 30,
    as_of: datetime | None = None,
    statuses: tuple[str, ...] | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    """把在途订单的交付逾期构造成 `AEOS.Exception.V1` 并入库投递队列。

    口径与边界（重要）：
    - EBMS `AEOS_V7.2_DATA_OWNERSHIP_V1.md` 将 Delivery Order / Schedule 的 Owner 定为
      **M06 交付自治**；CRM 仅拥有 Sales Order 商务状态。CRM 无交付事实数据，因此本试点
      以**显式、可调**的 SLA 代理口径判定逾期：`业务时间 + sla_days < as_of` 即视为逾期。
    - 该判据是联调期的代理规则，不代表交付事实；待 M06 正式 Delivery 数据接入后应改由 M06 产出。
    - `object_type` 取 `SalesOrder`（CRM 实际拥有的对象），而非基线样例的 `DeliveryOrder`。
    """
    if sla_days < 0:
        raise ApiError(ErrCode.PARAM_ERROR, "sla_days 不得为负")

    as_of = as_of or cn_now()
    if as_of.tzinfo is None:
        as_of = as_of.replace(tzinfo=CN_TZ)
    statuses = statuses or IN_FLIGHT_ORDER_STATUSES
    deadline = as_of - timedelta(days=sla_days)
    order_ts = _order_timestamp()

    rows = (
        await db.execute(
            select(Quotation.id, Quotation.quotation_no, order_ts)
            .where(
                Quotation.deleted_at.is_(None),
                Quotation.status.in_(statuses),
                order_ts < deadline,
            )
            .order_by(order_ts)
            .limit(limit)
        )
    ).all()

    emitted: list[dict[str, Any]] = []
    created_count = 0
    for qid, quotation_no, ts in rows:
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        days_overdue = max((as_of - ts).days - sla_days, 1)
        contract = build_exception_contract(
            exception_id=f"EXC-{SOURCE_SYSTEM}-{quotation_no}",
            source_system=SOURCE_SYSTEM,
            object_type="SalesOrder",
            object_id=quotation_no,
            severity=_severity_for(days_overdue),
            reason_code=REASON_DELIVERY_OVERDUE,
            evidence_ids=[str(qid)],
            trace_id=f"TRACE-EXC-{SOURCE_SYSTEM}-{quotation_no}",
            occurred_at=cn_now(),
            extra={"days_overdue": days_overdue, "sla_days": sla_days, "deadline": deadline.isoformat()},
        )
        _, log, created = await _enqueue(
            db, contract=contract, event_type=EVENT_EXCEPTION, biz_type="QUOTATION", biz_id=qid
        )
        created_count += int(created)
        emitted.append(
            {
                "contract_id": contract.contract_id,
                "object_id": quotation_no,
                "severity": contract.severity,
                "days_overdue": days_overdue,
                "created": created,
                "log_id": str(log.id) if log else None,
            }
        )

    await db.flush()
    return {
        "batch_id": _batch_id(),
        "event_type": EVENT_EXCEPTION,
        "reason_code": REASON_DELIVERY_OVERDUE,
        "sla_days": sla_days,
        "as_of": as_of.isoformat(),
        "total": len(rows),
        "created": created_count,
        "skipped": len(rows) - created_count,
        "emitted": emitted,
    }


# ------------------------------------------------------------------ 投递


async def _mark_outbox(row: IntegrationOutbox, *, status: str, retry: int | None = None) -> None:
    row.status = status
    if retry is not None:
        row.retry_count = retry
    if status == OUTBOX_DONE:
        row.processed_at = utcnow()


async def _deliver_one(db: AsyncSession, row: IntegrationOutbox, transport: EbmsTransport) -> str:
    """投递单条 Outbox，返回结果标签：delivered/skipped/failed/dead_letter。"""
    action = _EVENT_ACTION.get(row.event_type)
    payload = dict(row.payload or {})
    if action is None:
        await _mark_outbox(row, status=OUTBOX_FAILED)
        return "failed"

    try:
        contract = validate_contract(payload)
    except ContractValidationError:
        # 契约不合规属确定性错误，重试无意义 → 直接终态（正常路径下 enqueue 已校验，此处仅防御）
        await _mark_outbox(row, status=OUTBOX_FAILED)
        return "dead_letter"

    wire = to_wire(contract)
    key = row.idempotency_key or _idempotency(action, contract.contract_id, wire)
    log = await _latest_log(db, key)
    if log is None:
        log = _new_log(db, action=action, key=key, contract_id=contract.contract_id, wire=wire)

    if log.status == LOG_SUCCESS:
        await _mark_outbox(row, status=OUTBOX_DONE)
        return "skipped"

    result: DeliveryResult = await transport.deliver(
        wire, event_type=row.event_type, contract_id=contract.contract_id, idempotency_key=key
    )
    log.response_payload = result.to_dict()
    log.finished_at = utcnow()

    if result.ok:
        log.status = LOG_SUCCESS
        log.error_message = None
        log.next_retry_at = None
        await _mark_outbox(row, status=OUTBOX_DONE)
        return "delivered"

    log.retry_count += 1
    log.error_message = result.error
    if log.retry_count >= log.max_retry:
        log.status = LOG_DEAD_LETTER
        log.next_retry_at = None
        await _mark_outbox(row, status=OUTBOX_FAILED, retry=log.retry_count)
        return "dead_letter"

    log.status = LOG_FAILED
    log.next_retry_at = _backoff(log.retry_count)
    await _mark_outbox(row, status=OUTBOX_PENDING, retry=log.retry_count)
    row.available_at = log.next_retry_at
    return "failed"


async def deliver_pending(
    db: AsyncSession, *, limit: int = 50, transport: EbmsTransport | None = None
) -> dict[str, Any]:
    """投递所有到期未处理的 EBMS Outbox（Worker / 联调端点入口）。"""
    transport = transport or EbmsTransport.from_settings()
    now = utcnow()
    rows = list(
        (
            await db.execute(
                select(IntegrationOutbox)
                .where(
                    IntegrationOutbox.deleted_at.is_(None),
                    IntegrationOutbox.event_type.in_(tuple(_EVENT_ACTION)),
                    IntegrationOutbox.status == OUTBOX_PENDING,
                    or_(IntegrationOutbox.available_at.is_(None), IntegrationOutbox.available_at <= now),
                )
                .order_by(IntegrationOutbox.created_at)
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )

    tally = {"delivered": 0, "skipped": 0, "failed": 0, "dead_letter": 0}
    for row in rows:
        tally[await _deliver_one(db, row, transport)] += 1
    await db.flush()

    return {
        "mode": transport.mode,
        "picked": len(rows),
        **tally,
    }


async def retry(db: AsyncSession, log_id: uuid.UUID, *, transport: EbmsTransport | None = None) -> dict[str, Any]:
    """按日志重投契约（真正重新投递，而非仅改状态）。"""
    log = (
        await db.execute(select(IntegrationLog).where(IntegrationLog.id == log_id, IntegrationLog.deleted_at.is_(None)))
    ).scalar_one_or_none()
    if log is None:
        raise NotFoundError("集成日志不存在")
    if log.status == LOG_SUCCESS:
        return {"log_id": str(log_id), "status": LOG_SUCCESS, "message": "该记录已成功，无需重试"}
    if log.retry_count >= log.max_retry:
        log.status = LOG_DEAD_LETTER
        log.next_retry_at = None
        await db.flush()
        return {
            "log_id": str(log_id),
            "status": LOG_DEAD_LETTER,
            "message": f"重试次数已达上限（{log.max_retry}），进入死信队列",
        }

    transport = transport or EbmsTransport.from_settings()
    payload = dict(log.request_payload or {})
    try:
        contract = validate_contract(payload)
    except ContractValidationError as exc:
        log.status = LOG_DEAD_LETTER
        log.error_message = f"契约校验失败: {exc.message}"
        log.finished_at = utcnow()
        await db.flush()
        return {"log_id": str(log_id), "status": LOG_DEAD_LETTER, "message": log.error_message}

    wire = to_wire(contract)
    key = log.idempotency_key or _idempotency(log.action, contract.contract_id, wire)
    result = await transport.deliver(
        wire, event_type=_event_of(log.action), contract_id=contract.contract_id, idempotency_key=key
    )
    log.retry_count += 1
    log.response_payload = result.to_dict()
    log.finished_at = utcnow()

    if result.ok:
        log.status = LOG_SUCCESS
        log.error_message = None
        log.next_retry_at = None
    else:
        log.error_message = result.error
        if log.retry_count >= log.max_retry:
            log.status = LOG_DEAD_LETTER
            log.next_retry_at = None
        else:
            log.status = LOG_FAILED
            log.next_retry_at = _backoff(log.retry_count)

    # 同步 Outbox 状态，保持两表一致可对账（按幂等键精确定位）
    outbox = await _outbox_for_key(db, key) if log.idempotency_key else None
    if outbox is not None:
        if result.ok:
            await _mark_outbox(outbox, status=OUTBOX_DONE, retry=log.retry_count)
        elif log.status == LOG_DEAD_LETTER:
            await _mark_outbox(outbox, status=OUTBOX_FAILED, retry=log.retry_count)
        else:
            await _mark_outbox(outbox, status=OUTBOX_PENDING, retry=log.retry_count)
            outbox.available_at = log.next_retry_at

    await db.flush()
    return {
        "log_id": str(log_id),
        "status": log.status,
        "retry_count": log.retry_count,
        "mode": transport.mode,
        "message": "重投成功" if result.ok else (result.error or "重投失败"),
    }


def _event_of(action: str) -> str:
    for event, act in _EVENT_ACTION.items():
        if act == action:
            return event
    return action


# ------------------------------------------------------------------ 对账


async def _count_outbox(db: AsyncSession, event_type: str, status: str | None = None) -> int:
    stmt = (
        select(func.count())
        .select_from(IntegrationOutbox)
        .where(IntegrationOutbox.deleted_at.is_(None), IntegrationOutbox.event_type == event_type)
    )
    if status:
        stmt = stmt.where(IntegrationOutbox.status == status)
    return int((await db.execute(stmt)).scalar_one())


async def _count_log(db: AsyncSession, action: str, status: str | None = None) -> int:
    stmt = (
        select(func.count())
        .select_from(IntegrationLog)
        .where(IntegrationLog.deleted_at.is_(None), IntegrationLog.action == action)
    )
    if status:
        stmt = stmt.where(IntegrationLog.status == status)
    return int((await db.execute(stmt)).scalar_one())


async def reconcile(db: AsyncSession) -> dict[str, Any]:
    """对账：产出（Outbox） vs 投递成功（Log），并按状态给出积压/失败量。"""
    result = {
        "produced": await _count_outbox(db, EVENT_RESULT),
        "delivered": await _count_log(db, ACTION_RESULT, LOG_SUCCESS),
        "pending": await _count_outbox(db, EVENT_RESULT, OUTBOX_PENDING),
        "failed": await _count_outbox(db, EVENT_RESULT, OUTBOX_FAILED),
    }
    exception = {
        "produced": await _count_outbox(db, EVENT_EXCEPTION),
        "delivered": await _count_log(db, ACTION_EXCEPTION, LOG_SUCCESS),
        "pending": await _count_outbox(db, EVENT_EXCEPTION, OUTBOX_PENDING),
        "failed": await _count_outbox(db, EVENT_EXCEPTION, OUTBOX_FAILED),
    }
    dead_letter = (
        await db.execute(
            select(func.count())
            .select_from(IntegrationLog)
            .where(
                IntegrationLog.deleted_at.is_(None),
                IntegrationLog.system == "EBMS",
                IntegrationLog.status == LOG_DEAD_LETTER,
            )
        )
    ).scalar_one()

    return {
        "checked_at": cn_now().isoformat(),
        "mode": settings.EBMS_DELIVERY_MODE,
        "result": result,
        "exception": exception,
        "dead_letter": int(dead_letter),
        "consistent": result["pending"] == 0
        and exception["pending"] == 0
        and result["failed"] == 0
        and exception["failed"] == 0,
    }
