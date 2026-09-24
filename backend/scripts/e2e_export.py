"""导出功能冒烟测试：询价单 Excel / 报价单 Excel+PDF。"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000/api/v1"
OUT = r"C:\Users\75597\AppData\Local\Temp\opencode"


def login(client: httpx.Client, username: str, password: str) -> None:
    res = client.post("/auth/login", json={"username": username, "password": password})
    res.raise_for_status()
    token = res.json()["data"]["access_token"]
    client.headers["Authorization"] = f"Bearer {token}"


def main() -> int:
    with httpx.Client(base_url=BASE, timeout=120.0) as client:
        login(client, "admin", "admin123")

        # 1) 询价单 Excel
        inquiries = client.get("/inquiries", params={"page_size": 200}).json()["data"]
        imported = next((i for i in inquiries["items"] if i["inquiry_no"] == "JFX20260916-212"), None)
        target = imported or inquiries["items"][0]
        print(f"[1] 询价单 {target['inquiry_no']} (来源={target['source']})")
        res = client.get(f"/inquiries/{target['id']}/export-excel")
        res.raise_for_status()
        path = Path(OUT) / f"inquiry_{target['inquiry_no']}.xlsx"
        path.write_bytes(res.content)
        print(f"    Excel 导出 {len(res.content)} bytes -> {path}")

        # 2) 报价单
        quotations = client.get("/quotations", params={"page_size": 10}).json()["data"]
        if not quotations["items"]:
            print("[2] 无报价单，跳过")
            return 0
        q = quotations["items"][0]
        print(f"[2] 报价单 {q['quotation_no']} 客户={q['company_name']} 状态={q['status']}")

        pdf = client.post(f"/quotations/{q['id']}/generate-pdf").json()["data"]
        print(f"    PDF: {pdf['detail']} {pdf['size']} bytes")
        raw = client.get(f"/quotations/{q['id']}/pdf")
        raw.raise_for_status()
        (Path(OUT) / f"quotation_{q['quotation_no']}.pdf").write_bytes(raw.content)

        xls = client.get(f"/quotations/{q['id']}/export-excel")
        xls.raise_for_status()
        (Path(OUT) / f"quotation_{q['quotation_no']}.xlsx").write_bytes(xls.content)
        print(f"    Excel 导出 {len(xls.content)} bytes")

    print("\n[PASS] 导出冒烟通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
