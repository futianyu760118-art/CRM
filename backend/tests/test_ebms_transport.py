"""EBMS 投递传输层单测（http / spool / dry_run）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.services import ebms_transport
from app.services.ebms_transport import EbmsTransport

CONTRACT: dict[str, Any] = {
    "contract_version": "AEOS.Result.V1",
    "result_id": "RES-T-1",
    "source_system": "M05",
    "object_type": "BusinessMetric",
    "object_id": "order_amount",
    "period": {"start": "2026-09-01", "end": "2026-09-30"},
    "metric": {"code": "order_amount", "value": 10.0, "unit": "currency", "calculation_version": "V1"},
    "status": "VERIFIED",
    "evidence_ids": [],
    "trace_id": "TRACE-RES-T-1",
    "occurred_at": "2026-09-30T23:59:59+08:00",
}


class TestSpoolMode:
    async def test_writes_contract_file_under_event_type_dir(self, tmp_path: Path) -> None:
        transport = EbmsTransport(mode="spool", spool_dir=str(tmp_path))
        result = await transport.deliver(
            CONTRACT, event_type="AEOS_RESULT_V1", contract_id="RES-T-1", idempotency_key="k1"
        )
        assert result.ok and result.mode == "spool"
        written = list((tmp_path / "AEOS_RESULT_V1").glob("*.json"))
        assert len(written) == 1
        assert json.loads(written[0].read_text(encoding="utf-8")) == CONTRACT
        assert not list((tmp_path / "AEOS_RESULT_V1").glob("*.tmp"))

    async def test_same_idempotency_key_overwrites_single_file(self, tmp_path: Path) -> None:
        transport = EbmsTransport(mode="spool", spool_dir=str(tmp_path))
        for _ in range(3):
            result = await transport.deliver(
                CONTRACT, event_type="AEOS_RESULT_V1", contract_id="RES-T-1", idempotency_key="same-key"
            )
            assert result.ok
        assert len(list((tmp_path / "AEOS_RESULT_V1").glob("*.json"))) == 1

    async def test_contract_id_is_sanitized_for_filesystem(self, tmp_path: Path) -> None:
        transport = EbmsTransport(mode="spool", spool_dir=str(tmp_path))
        result = await transport.deliver(
            CONTRACT, event_type="AEOS_RESULT_V1", contract_id="RES/../evil", idempotency_key="k"
        )
        assert result.ok
        files = list((tmp_path / "AEOS_RESULT_V1").glob("*.json"))
        assert len(files) == 1
        # 路径穿越字符被替换，文件仍落在 spool 目录内
        assert files[0].parent == tmp_path / "AEOS_RESULT_V1"


class TestDryRunAndConfig:
    async def test_dry_run_reports_ok_without_side_effect(self, tmp_path: Path) -> None:
        transport = EbmsTransport(mode="dry_run", spool_dir=str(tmp_path))
        result = await transport.deliver(
            CONTRACT, event_type="AEOS_RESULT_V1", contract_id="RES-T-1", idempotency_key="k"
        )
        assert result.ok and result.mode == "dry_run"
        assert list(tmp_path.iterdir()) == []

    async def test_unknown_mode_fails(self) -> None:
        result = await EbmsTransport(mode="carrier-pigeon").deliver(
            CONTRACT, event_type="AEOS_RESULT_V1", contract_id="RES-T-1", idempotency_key="k"
        )
        assert not result.ok
        assert "未知投递模式" in (result.error or "")

    async def test_http_without_url_fails(self) -> None:
        result = await EbmsTransport(mode="http", ingest_url="").deliver(
            CONTRACT, event_type="AEOS_RESULT_V1", contract_id="RES-T-1", idempotency_key="k"
        )
        assert not result.ok
        assert "EBMS_INGEST_URL 未配置" in (result.error or "")

    def test_from_settings_reads_config(self) -> None:
        transport = EbmsTransport.from_settings()
        assert transport.mode in {"http", "spool", "dry_run"}


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any = None) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = "" if payload is None else json.dumps(payload)

    def json(self) -> Any:
        if self._payload is None:
            raise ValueError("not json")
        return self._payload


class _FakeClient:
    """替换 httpx.AsyncClient：按预设响应返回，并记录请求。"""

    response: _FakeResponse = _FakeResponse(200, {"ok": True})
    calls: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False

    async def post(self, url: str, json: Any = None, headers: dict[str, str] | None = None) -> _FakeResponse:
        type(self).calls.append({"url": url, "json": json, "headers": headers or {}})
        return type(self).response


class TestHttpMode:
    @pytest.fixture(autouse=True)
    def _patch_httpx(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _FakeClient.calls = []
        monkeypatch.setattr(ebms_transport.httpx, "AsyncClient", _FakeClient)

    async def test_2xx_is_delivered_with_contract_headers(self) -> None:
        _FakeClient.response = _FakeResponse(200, {"received": True})
        transport = EbmsTransport(mode="http", ingest_url="http://ebms.local/ingest", token="tok")
        result = await transport.deliver(
            CONTRACT, event_type="AEOS_RESULT_V1", contract_id="RES-T-1", idempotency_key="idem-1"
        )
        assert result.ok and result.status_code == 200
        sent = _FakeClient.calls[-1]
        assert sent["url"] == "http://ebms.local/ingest"
        assert sent["json"] == CONTRACT
        assert sent["headers"]["X-Idempotency-Key"] == "idem-1"
        assert sent["headers"]["X-Contract-Version"] == "AEOS.Result.V1"
        assert sent["headers"]["X-Event-Type"] == "AEOS_RESULT_V1"
        assert sent["headers"]["Authorization"] == "Bearer tok"

    async def test_409_is_treated_as_delivered(self) -> None:
        _FakeClient.response = _FakeResponse(409, {"message": "duplicate"})
        result = await EbmsTransport(mode="http", ingest_url="http://ebms.local/ingest").deliver(
            CONTRACT, event_type="AEOS_RESULT_V1", contract_id="RES-T-1", idempotency_key="idem-1"
        )
        assert result.ok and result.status_code == 409

    async def test_5xx_is_failure_with_receipt(self) -> None:
        _FakeClient.response = _FakeResponse(500, {"message": "boom"})
        result = await EbmsTransport(mode="http", ingest_url="http://ebms.local/ingest").deliver(
            CONTRACT, event_type="AEOS_RESULT_V1", contract_id="RES-T-1", idempotency_key="idem-1"
        )
        assert not result.ok
        assert result.status_code == 500
        assert result.error == "HTTP 500"
        assert result.response == {"message": "boom"}

    async def test_transport_error_is_reported_not_raised(self, monkeypatch: pytest.MonkeyPatch) -> None:
        class _BoomClient(_FakeClient):
            async def post(self, url: str, json: Any = None, headers: dict[str, str] | None = None) -> Any:
                raise ebms_transport.httpx.ConnectError("no route")

        monkeypatch.setattr(ebms_transport.httpx, "AsyncClient", _BoomClient)
        result = await EbmsTransport(mode="http", ingest_url="http://ebms.local/ingest").deliver(
            CONTRACT, event_type="AEOS_RESULT_V1", contract_id="RES-T-1", idempotency_key="idem-1"
        )
        assert not result.ok
        assert "ConnectError" in (result.error or "")
