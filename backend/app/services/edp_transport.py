"""M02/EDP transport for AEOS.Event.V1 entity events.

Entity events do not go directly to EBMS. In HTTP mode the transport first
resolves/registers the source object in EDP Registry and then writes one event
to EDP /events/batch. EDP owns downstream delivery to FAC.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from hashlib import sha1
from pathlib import Path
from typing import Any

import httpx

from app.core.config import Settings
from app.core.config import settings as default_settings
from app.services.ebms_transport import DeliveryResult


def _edp_object_type(value: str) -> str:
    value = re.sub(r"(?<!^)(?=[A-Z])", "_", value).upper()
    return re.sub(r"[^A-Z0-9_]", "_", value)


@dataclass
class EdpEntityTransport:
    mode: str = field(default_factory=lambda: default_settings.EDP_DELIVERY_MODE)
    base_url: str = field(default_factory=lambda: default_settings.EDP_BASE_URL)
    api_key: str = field(default_factory=lambda: default_settings.EDP_API_KEY)
    spool_dir: str = field(default_factory=lambda: default_settings.EDP_SPOOL_DIR)
    timeout: float = field(default_factory=lambda: default_settings.EDP_TIMEOUT_SECONDS)

    @classmethod
    def from_settings(cls, cfg: Settings | None = None) -> EdpEntityTransport:
        cfg = cfg or default_settings
        return cls(
            mode=cfg.EDP_DELIVERY_MODE,
            base_url=cfg.EDP_BASE_URL,
            api_key=cfg.EDP_API_KEY,
            spool_dir=cfg.EDP_SPOOL_DIR,
            timeout=cfg.EDP_TIMEOUT_SECONDS,
        )

    def _headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["X-API-Key"] = self.api_key
        return headers

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
            return await self._deliver_http(
                contract,
                event_type=event_type,
                idempotency_key=idempotency_key,
            )
        if mode == "spool":
            return self._deliver_spool(
                contract,
                event_type=event_type,
                contract_id=contract_id,
                idempotency_key=idempotency_key,
            )
        if mode == "dry_run":
            return DeliveryResult(
                ok=True,
                mode="dry_run",
                target="M02/EDP",
                response={
                    "dry_run": True,
                    "contract_id": contract_id,
                    "event_type": event_type,
                },
            )
        return DeliveryResult(
            ok=False,
            mode=mode,
            target="M02/EDP",
            error=f"未知投递模式: {mode!r}",
        )

    async def _deliver_http(
        self,
        contract: dict[str, Any],
        *,
        event_type: str,
        idempotency_key: str,
    ) -> DeliveryResult:
        base = self.base_url.rstrip("/")
        if not base:
            return DeliveryResult(
                ok=False,
                mode="http",
                target="(unset)",
                error="EDP_BASE_URL 未配置",
            )
        if not self.api_key:
            return DeliveryResult(
                ok=False,
                mode="http",
                target=base,
                error="EDP_API_KEY 未配置",
            )

        object_type = _edp_object_type(str(contract.get("object_type") or "UNKNOWN"))
        source_id = str(contract.get("object_id") or "")
        if not source_id:
            return DeliveryResult(
                ok=False,
                mode="http",
                target=base,
                error="AEOS.Event.V1 object_id 为空",
            )

        registry_url = f"{base}/api/v1/objects"
        events_url = f"{base}/api/v1/events/batch"
        headers = self._headers()

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                lookup = await client.get(
                    registry_url,
                    params={
                        "object_type": object_type,
                        "source_system": "M05",
                        "source_id": source_id,
                        "limit": 1,
                    },
                    headers=headers,
                )
                if not (200 <= lookup.status_code < 300):
                    return self._http_failure(lookup, registry_url)

                lookup_body = self._json_body(lookup)
                items = lookup_body.get("items") if isinstance(lookup_body, dict) else None
                edp_object_id: str | None = None
                if isinstance(items, list) and items:
                    edp_object_id = str(items[0].get("object_id") or "")

                if not edp_object_id:
                    created = await client.post(
                        registry_url,
                        json={
                            "object_type": object_type,
                            "owner_domain": "sales",
                            "source_system": "M05",
                            "source_id": source_id,
                            "attributes": {
                                "aeos_contract_version": contract.get("contract_version"),
                                "event_type": event_type,
                            },
                        },
                        headers=headers,
                    )
                    if not (200 <= created.status_code < 300):
                        return self._http_failure(created, registry_url)
                    created_body = self._json_body(created)
                    edp_object_id = str(created_body.get("object_id") or "")

                if not edp_object_id:
                    return DeliveryResult(
                        ok=False,
                        mode="http",
                        target=registry_url,
                        error="EDP Registry 未返回 object_id",
                    )

                event_response = await client.post(
                    events_url,
                    json={
                        "events": [
                            {
                                "event_type": event_type,
                                "object_id": edp_object_id,
                                "source_system": "M05",
                                "occurred_at": contract.get("occurred_at"),
                                "actor_type": "SERVICE",
                                "actor_id": "M05",
                                "data": {"aeos_event": contract},
                            }
                        ]
                    },
                    headers={**headers, "Idempotency-Key": idempotency_key},
                )
        except httpx.HTTPError as exc:
            return DeliveryResult(
                ok=False,
                mode="http",
                target=base,
                error=f"{type(exc).__name__}: {exc}",
            )

        body = self._json_body(event_response)
        if 200 <= event_response.status_code < 300:
            rejected = int(body.get("rejected", 0)) if isinstance(body, dict) else 0
            if rejected == 0:
                return DeliveryResult(
                    ok=True,
                    mode="http",
                    target=events_url,
                    status_code=event_response.status_code,
                    response=body,
                )
            return DeliveryResult(
                ok=False,
                mode="http",
                target=events_url,
                status_code=event_response.status_code,
                response=body,
                error=f"EDP rejected={rejected}",
            )
        if event_response.status_code == 409:
            return DeliveryResult(
                ok=True,
                mode="http",
                target=events_url,
                status_code=409,
                response=body,
            )
        return self._http_failure(event_response, events_url)

    @staticmethod
    def _json_body(response: Any) -> dict[str, Any]:
        try:
            value = response.json()
            return value if isinstance(value, dict) else {"raw": value}
        except ValueError:
            return {"raw": str(getattr(response, "text", ""))[:500]}

    @classmethod
    def _http_failure(cls, response: Any, target: str) -> DeliveryResult:
        return DeliveryResult(
            ok=False,
            mode="http",
            target=target,
            status_code=int(response.status_code),
            response=cls._json_body(response),
            error=f"HTTP {response.status_code}",
        )

    def _deliver_spool(
        self,
        contract: dict[str, Any],
        *,
        event_type: str,
        contract_id: str,
        idempotency_key: str,
    ) -> DeliveryResult:
        fingerprint = sha1(idempotency_key.encode("utf-8")).hexdigest()[:12]
        safe_type = re.sub(r"[^A-Za-z0-9_-]", "_", event_type)
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "_", contract_id)
        path = Path(self.spool_dir) / safe_type / f"{safe_id}__{fingerprint}.json"
        payload = {
            "target": "M02/EDP",
            "idempotency_key": idempotency_key,
            "aeos_event": contract,
        }
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".json.tmp")
            tmp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            tmp.replace(path)
        except OSError as exc:
            return DeliveryResult(
                ok=False,
                mode="spool",
                target=str(path),
                error=f"{type(exc).__name__}: {exc}",
            )
        return DeliveryResult(
            ok=True,
            mode="spool",
            target=str(path),
            response={"spool_file": str(path), "contract_id": contract_id},
        )
