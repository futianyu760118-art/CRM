"""M02/EDP entity event transport tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.services import edp_transport
from app.services.edp_transport import EdpEntityTransport


EVENT_CONTRACT: dict[str, Any] = {
    "contract_version": "AEOS.Event.V1",
    "event_id": "EVT-M05-001",
    "event_type": "inquiry.upserted",
    "source_system": "M05",
    "object_type": "Inquiry",
    "object_id": "INQ-2026-0088",
    "operation": "UPSERT",
    "occurred_at": "2026-11-18T08:00:00+00:00",
    "trace_id": "TRACE-INQ-0088",
    "payload": {
        "serial_number": "INQ-2026-0088",
        "status": "SUBMITTED",
        "items": [{"internal_model": "WL6000", "quantity": "8000"}],
    },
    "idempotency_key": "M02:inquiry.upserted:INQ-2026-0088:test",
}


class _FakeResponse:
    def __init__(self, status_code: int, payload: Any) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self) -> Any:
        return self._payload


class _FakeClient:
    get_responses: list[_FakeResponse] = []
    post_responses: list[_FakeResponse] = []
    calls: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *args: Any) -> bool:
        return False

    async def get(
        self,
        url: str,
        params: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> _FakeResponse:
        type(self).calls.append(
            {"method": "GET", "url": url, "params": params, "headers": headers or {}}
        )
        return type(self).get_responses.pop(0)

    async def post(
        self,
        url: str,
        json: Any = None,
        headers: dict[str, str] | None = None,
    ) -> _FakeResponse:
        type(self).calls.append(
            {"method": "POST", "url": url, "json": json, "headers": headers or {}}
        )
        return type(self).post_responses.pop(0)


@pytest.fixture(autouse=True)
def _patch_httpx(monkeypatch: pytest.MonkeyPatch) -> None:
    _FakeClient.calls = []
    _FakeClient.get_responses = []
    _FakeClient.post_responses = []
    monkeypatch.setattr(edp_transport.httpx, "AsyncClient", _FakeClient)


async def test_existing_registry_object_is_reused_for_event_batch() -> None:
    _FakeClient.get_responses = [
        _FakeResponse(
            200,
            {
                "items": [
                    {
                        "object_id": "11111111-1111-1111-1111-111111111111",
                        "source_id": "INQ-2026-0088",
                    }
                ],
                "next_cursor": None,
            },
        )
    ]
    _FakeClient.post_responses = [
        _FakeResponse(200, {"accepted": 1, "duplicated": 0, "rejected": 0})
    ]

    result = await EdpEntityTransport(
        mode="http",
        base_url="http://edp.local",
        api_key="key-1",
    ).deliver(
        EVENT_CONTRACT,
        event_type="inquiry.upserted",
        contract_id="EVT-M05-001",
        idempotency_key="M02:idem-1",
    )

    assert result.ok
    assert [c["method"] for c in _FakeClient.calls] == ["GET", "POST"]
    lookup = _FakeClient.calls[0]
    assert lookup["params"]["object_type"] == "INQUIRY"
    assert lookup["params"]["source_system"] == "M05"
    assert lookup["params"]["source_id"] == "INQ-2026-0088"
    assert lookup["headers"]["X-API-Key"] == "key-1"

    event = _FakeClient.calls[1]
    item = event["json"]["events"][0]
    assert item["object_id"] == "11111111-1111-1111-1111-111111111111"
    assert item["source_system"] == "M05"
    assert item["data"]["aeos_event"] == EVENT_CONTRACT
    assert event["headers"]["Idempotency-Key"] == "M02:idem-1"


async def test_missing_registry_object_is_created_before_event() -> None:
    _FakeClient.get_responses = [_FakeResponse(200, {"items": [], "next_cursor": None})]
    _FakeClient.post_responses = [
        _FakeResponse(
            201,
            {
                "object_id": "22222222-2222-2222-2222-222222222222",
                "revision": 1,
                "status": "ACTIVE",
                "created_at": "2026-11-18T08:00:00Z",
            },
        ),
        _FakeResponse(200, {"accepted": 1, "duplicated": 0, "rejected": 0}),
    ]

    result = await EdpEntityTransport(
        mode="http",
        base_url="http://edp.local",
        api_key="key-1",
    ).deliver(
        EVENT_CONTRACT,
        event_type="inquiry.upserted",
        contract_id="EVT-M05-001",
        idempotency_key="M02:idem-2",
    )

    assert result.ok
    assert [c["method"] for c in _FakeClient.calls] == ["GET", "POST", "POST"]
    register = _FakeClient.calls[1]
    assert register["url"].endswith("/api/v1/objects")
    assert register["json"]["object_type"] == "INQUIRY"
    assert register["json"]["owner_domain"] == "sales"
    assert register["json"]["source_id"] == "INQ-2026-0088"


async def test_edp_rejection_is_delivery_failure() -> None:
    _FakeClient.get_responses = [
        _FakeResponse(
            200,
            {
                "items": [
                    {"object_id": "11111111-1111-1111-1111-111111111111"}
                ]
            },
        )
    ]
    _FakeClient.post_responses = [
        _FakeResponse(
            200,
            {
                "accepted": 0,
                "duplicated": 0,
                "rejected": 1,
                "errors": [{"index": 0, "message": "bad event"}],
            },
        )
    ]
    result = await EdpEntityTransport(
        mode="http",
        base_url="http://edp.local",
        api_key="key-1",
    ).deliver(
        EVENT_CONTRACT,
        event_type="inquiry.upserted",
        contract_id="EVT-M05-001",
        idempotency_key="M02:idem-3",
    )
    assert not result.ok
    assert result.error == "EDP rejected=1"


async def test_http_requires_edp_url_and_api_key() -> None:
    missing_url = await EdpEntityTransport(mode="http", base_url="", api_key="key").deliver(
        EVENT_CONTRACT,
        event_type="inquiry.upserted",
        contract_id="EVT-M05-001",
        idempotency_key="M02:x",
    )
    assert not missing_url.ok
    assert "EDP_BASE_URL" in (missing_url.error or "")

    missing_key = await EdpEntityTransport(
        mode="http", base_url="http://edp.local", api_key=""
    ).deliver(
        EVENT_CONTRACT,
        event_type="inquiry.upserted",
        contract_id="EVT-M05-001",
        idempotency_key="M02:x",
    )
    assert not missing_key.ok
    assert "EDP_API_KEY" in (missing_key.error or "")


async def test_spool_mode_writes_m02_wrapper(tmp_path: Path) -> None:
    result = await EdpEntityTransport(
        mode="spool",
        spool_dir=str(tmp_path),
    ).deliver(
        EVENT_CONTRACT,
        event_type="inquiry.upserted",
        contract_id="EVT-M05-001",
        idempotency_key="M02:idem-spool",
    )
    assert result.ok
    files = list((tmp_path / "inquiry_upserted").glob("*.json"))
    assert len(files) == 1
    body = json.loads(files[0].read_text(encoding="utf-8"))
    assert body["target"] == "M02/EDP"
    assert body["aeos_event"] == EVENT_CONTRACT
