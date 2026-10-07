"""EBMS 契约投递传输层。

CRM 只向 EBMS 投递 AEOS 契约，不直写 EBMS 库（红线）。投递通道可切换：

- ``http``     ：POST 到 EBMS 摄入端点（生产/跨机联调）。
- ``spool``    ：落地本地 spool 目录，EBMS 侧流水线轮询消费；EBMS 未就绪时的端到端联调通道。
- ``dry_run``  ：只做校验与记录，不产生外部副作用。

三种模式返回统一的 `DeliveryResult`，投递结果始终回写 `IntegrationLog`，保证可对账。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.core.config import settings as default_settings

logger = logging.getLogger("app.integration.ebms")


@dataclass(frozen=True)
class DeliveryResult:
    """一次投递的结果（成功/失败 + 回执或错误）。"""

    ok: bool
    mode: str
    target: str
    status_code: int | None = None
    response: dict[str, Any] | None = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "mode": self.mode,
            "target": self.target,
            "status_code": self.status_code,
            "response": self.response,
            "error": self.error,
        }


@dataclass
class EbmsTransport:
    """按配置模式投递单个契约。"""

    mode: str = field(default_factory=lambda: default_settings.EBMS_DELIVERY_MODE)
    ingest_url: str = field(default_factory=lambda: default_settings.EBMS_INGEST_URL)
    token: str = field(default_factory=lambda: default_settings.EBMS_INGEST_TOKEN)
    spool_dir: str = field(default_factory=lambda: default_settings.EBMS_SPOOL_DIR)
    timeout: float = field(default_factory=lambda: default_settings.EBMS_TIMEOUT_SECONDS)

    @classmethod
    def from_settings(cls, cfg: Settings | None = None) -> EbmsTransport:
        cfg = cfg or default_settings
        return cls(
            mode=cfg.EBMS_DELIVERY_MODE,
            ingest_url=cfg.EBMS_INGEST_URL,
            token=cfg.EBMS_INGEST_TOKEN,
            spool_dir=cfg.EBMS_SPOOL_DIR,
            timeout=cfg.EBMS_TIMEOUT_SECONDS,
        )

    def _spool_path(self, event_type: str, contract_id: str, idempotency_key: str) -> Path:
        """按 事件类型/契约ID 归档，文件名含幂等指纹 → 重复投递覆盖同一文件。"""
        from hashlib import sha1

        fingerprint = sha1(idempotency_key.encode("utf-8")).hexdigest()[:12]
        safe_type = "".join(c if c.isalnum() or c in "-_" else "_" for c in event_type)
        safe_id = "".join(c if c.isalnum() or c in "-_" else "_" for c in contract_id)
        return Path(self.spool_dir) / safe_type / f"{safe_id}__{fingerprint}.json"

    async def deliver(
        self,
        contract: dict[str, Any],
        *,
        event_type: str,
        contract_id: str,
        idempotency_key: str,
    ) -> DeliveryResult:
        mode = (self.mode or "dry_run").strip().lower()
        if mode == "http":
            return await self._deliver_http(contract, event_type=event_type, idempotency_key=idempotency_key)
        if mode == "spool":
            return self._deliver_spool(
                contract, event_type=event_type, contract_id=contract_id, idempotency_key=idempotency_key
            )
        if mode == "dry_run":
            return DeliveryResult(
                ok=True,
                mode="dry_run",
                target="(none)",
                response={"dry_run": True, "contract_id": contract_id, "event_type": event_type},
            )
        return DeliveryResult(ok=False, mode=mode, target="(none)", error=f"未知投递模式: {mode!r}")

    async def _deliver_http(self, contract: dict[str, Any], *, event_type: str, idempotency_key: str) -> DeliveryResult:
        if not self.ingest_url:
            return DeliveryResult(ok=False, mode="http", target="(unset)", error="EBMS_INGEST_URL 未配置")

        headers = {
            "Content-Type": "application/json",
            "X-Contract-Version": str(contract.get("contract_version", "")),
            "X-Event-Type": event_type,
            "X-Idempotency-Key": idempotency_key,
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(self.ingest_url, json=contract, headers=headers)
        except httpx.HTTPError as exc:
            return DeliveryResult(ok=False, mode="http", target=self.ingest_url, error=f"{type(exc).__name__}: {exc}")

        body: dict[str, Any] | None
        try:
            parsed = resp.json()
            body = parsed if isinstance(parsed, dict) else {"raw": parsed}
        except ValueError:
            body = {"raw": resp.text[:500]}

        # 2xx 视为投递成功；409 表示 EBMS 已按幂等键收过同一契约，等价成功。
        if 200 <= resp.status_code < 300 or resp.status_code == 409:
            return DeliveryResult(
                ok=True, mode="http", target=self.ingest_url, status_code=resp.status_code, response=body
            )
        return DeliveryResult(
            ok=False,
            mode="http",
            target=self.ingest_url,
            status_code=resp.status_code,
            response=body,
            error=f"HTTP {resp.status_code}",
        )

    def _deliver_spool(
        self,
        contract: dict[str, Any],
        *,
        event_type: str,
        contract_id: str,
        idempotency_key: str,
    ) -> DeliveryResult:
        path = self._spool_path(event_type, contract_id, idempotency_key)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(contract, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
            tmp.replace(path)  # 原子落盘，避免 EBMS 侧读到半截文件
        except OSError as exc:
            return DeliveryResult(ok=False, mode="spool", target=str(path), error=f"{type(exc).__name__}: {exc}")
        return DeliveryResult(
            ok=True,
            mode="spool",
            target=str(path),
            response={"spool_file": str(path), "contract_id": contract_id, "event_type": event_type},
        )
