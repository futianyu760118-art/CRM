"""端到端冒烟测试：线索 → 客户 → 商机 → 询价 → 核价 → 报价 → 审批 → PDF → 邮件 → K3。

用法（后端已启动）：
    python scripts/e2e_smoke.py
"""

from __future__ import annotations

import sys

import httpx

BASE = "http://127.0.0.1:8000/api/v1"

ACCOUNTS = {
    "admin": "admin123",
    "boss": "boss123",
    "manager": "manager123",
    "sales": "sales123",
    "pricing": "pricing123",
}


class Client:
    def __init__(self, username: str) -> None:
        self.username = username
        self.http = httpx.Client(base_url=BASE, timeout=30.0)
        self.token = ""

    def login(self) -> None:
        res = self.http.post("/auth/login", json={"username": self.username, "password": ACCOUNTS[self.username]})
        res.raise_for_status()
        self.token = res.json()["data"]["access_token"]
        self.http.headers["Authorization"] = f"Bearer {self.token}"

    def call(self, method: str, path: str, **kwargs):
        res = self.http.request(method, path, **kwargs)
        payload = res.json()
        if res.status_code >= 400 or payload.get("code") != 0:
            raise RuntimeError(f"{method} {path} -> {res.status_code} {payload}")
        return payload["data"]


def step(msg: str) -> None:
    print(f"  -> {msg}")


def main() -> int:
    sales = Client("sales")
    pricing = Client("pricing")
    manager = Client("manager")
    boss = Client("boss")
    admin = Client("admin")
    for client in (sales, pricing, manager, boss, admin):
        client.login()
    step("5 个角色登录成功")

    # 1. 线索 -> 客户
    lead = sales.call(
        "POST",
        "/leads",
        json={
            "name": "E2E Test Import Co.",
            "contact_name": "Tom Tester",
            "email": "tom@e2e-test-import.com",
            "country": "USA",
            "source": "EXHIBITION",
        },
    )
    step(f"线索创建 {lead['lead_no']}")

    converted = sales.call("POST", f"/leads/{lead['id']}/convert", json={"customer_level": "A"})
    company_id = converted["company_id"]
    contact_id = converted.get("contact_id")
    step(f"线索转客户 {converted['company_code']}")

    # 2. 商机
    opp = sales.call(
        "POST",
        "/opportunities",
        json={
            "name": "E2E 保温杯项目",
            "company_id": company_id,
            "primary_contact_id": contact_id,
            "estimated_amount": 120000,
            "currency": "USD",
            "product_category": "饮具",
            "quantity": 20000,
            "requirement": "304 不锈钢保温杯 500ml，定制 LOGO",
        },
    )
    step(f"商机创建 {opp['opportunity_no']} stage={opp['stage']}")

    opp = sales.call(
        "PATCH",
        f"/opportunities/{opp['id']}/stage",
        json={"stage": "QUALIFIED", "requirement": "304 保温杯", "estimated_amount": 120000},
    )
    opp = sales.call(
        "PATCH",
        f"/opportunities/{opp['id']}/stage",
        json={"stage": "REQUIREMENT", "product_category": "饮具", "quantity": 20000},
    )
    step(f"商机阶段流转 -> {opp['stage']}")

    products = sales.call("GET", "/products")
    product = products["items"][0]
    sku = product["skus"][0]

    # 3. 询价
    inquiry = sales.call(
        "POST",
        "/inquiries",
        json={
            "company_id": company_id,
            "contact_id": contact_id,
            "opportunity_id": opp["id"],
            "currency": "USD",
            "requirement_text": "20000 pcs stainless steel vacuum flask, custom logo",
            "target_price": 3.2,
            "trade_terms": "FOB Ningbo",
            "items": [
                {
                    "product_id": product["id"],
                    "sku_id": sku["id"],
                    "product_name": product["name"],
                    "spec": sku["spec"],
                    "quantity": 20000,
                    "unit": "PCS",
                    "target_price": 3.2,
                }
            ],
        },
    )
    step(f"询价单创建 {inquiry['inquiry_no']} status={inquiry['status']}")

    inquiry = sales.call("POST", f"/inquiries/{inquiry['id']}/submit")
    step(f"询价提交 status={inquiry['status']}")

    # 4. 核价（含规则引擎）
    calc = sales.call(
        "POST",
        "/pricing/calc",
        json={
            "material_cost": 42000,
            "labor_cost": 7000,
            "packaging_cost": 2400,
            "freight_cost": 1600,
            "tooling_cost": 800,
            "other_cost": 1000,
            "target_margin": 0.22,
            "quantity": 20000,
        },
    )
    step(
        f"核价试算 成本={calc['total_cost']} 单位成本={calc['unit_cost']} "
        f"底价={calc['floor_price']} 建议价={calc['suggested_price']}"
    )

    record = pricing.call(
        "POST",
        "/pricing",
        json={
            "inquiry_id": inquiry["id"],
            "currency": "USD",
            "target_margin": 0.22,
            "costs": {
                "material_cost": 42000,
                "labor_cost": 7000,
                "packaging_cost": 2400,
                "freight_cost": 1600,
                "tooling_cost": 800,
                "other_cost": 1000,
            },
        },
    )
    step(f"核价记录 V{record['version']} 建议价={record['suggested_price']}")

    record = pricing.call("POST", f"/pricing/{record['id']}/submit")
    step(f"核价提交 status={record['status']}")

    pending = manager.call("GET", "/approvals?scope=mine")
    approval_id = pending["items"][0]["id"]
    manager.call("POST", f"/approvals/{approval_id}/approve", json={"comment": "成本合理"})
    pending = boss.call("GET", "/approvals?scope=mine")
    if pending["items"]:
        boss.call("POST", f"/approvals/{pending['items'][0]['id']}/approve", json={"comment": "同意"})
        step("核价审批：主管 + 老板 双级通过")
    else:
        step("核价审批：单级通过")

    pricing_versions = sales.call("GET", f"/inquiries/{inquiry['id']}/pricing-versions")
    approved = [v for v in pricing_versions if v["status"] == "APPROVED"]
    if not approved:
        raise RuntimeError("核价未审批通过")
    step(f"核价版本 {len(pricing_versions)} 个，最新状态 {pricing_versions[0]['status']}")

    # 5. 报价
    quotation = sales.call(
        "POST",
        "/quotations/from-pricing",
        json={"pricing_id": record["id"], "incoterm": "FOB Ningbo", "valid_days": 30},
    )
    step(f"报价单生成 {quotation['quotation_no']} 总额={quotation['total_amount']}")

    quotation = sales.call("POST", f"/quotations/{quotation['id']}/submit")
    step(f"报价提交 status={quotation['status']}")

    for role, client in (("manager", manager), ("boss", boss)):
        pending = client.call("GET", "/approvals?scope=mine")
        target = [p for p in pending["items"] if p["biz_type"] == "QUOTATION"]
        if target:
            client.call("POST", f"/approvals/{target[0]['id']}/approve", json={"comment": f"{role} 同意"})
            step(f"报价审批：{role} 通过")

    quotation = sales.call("GET", f"/quotations/{quotation['id']}")
    step(f"报价最终状态 {quotation['status']}")

    # 6. PDF + 邮件
    pdf = sales.call("POST", f"/quotations/{quotation['id']}/generate-pdf")
    step(f"PDF 生成引擎={pdf['detail']} 大小={pdf['size']} bytes")

    mail = sales.call(
        "POST",
        f"/quotations/{quotation['id']}/send-email",
        params={"to_addrs": "tom@e2e-test-import.com"},
    )
    step(f"报价邮件 {mail['send_status']} -> {mail['to']}")

    # 7. 邮件自动关联
    injected = sales.call("POST", "/emails/inject-inbound", params={"from_addr": "tom@e2e-test-import.com"})
    step(f"收件注入 自动关联={injected['auto_matched']} 匹配方式={injected['match_type']}")
    mail_list = sales.call("GET", "/emails?page=1&page_size=5")
    step(f"邮件列表共 {mail_list['total']} 封")

    # 8. K3 同步
    sync_c = admin.call("POST", "/integrations/k3/customer/sync", json={"limit": 20})
    step(f"K3 客户同步 成功={sync_c['success']} 跳过={sync_c['skipped']} 失败={sync_c['failed']}")
    sync_o = admin.call("POST", "/integrations/k3/order/sync", json={"limit": 20})
    step(f"K3 订单同步 成功={sync_o['success']} 跳过={sync_o['skipped']}")
    again = admin.call("POST", "/integrations/k3/customer/sync", json={"limit": 20})
    step(f"K3 幂等重跑 跳过={again['skipped']}（应等于上一步同步数）")
    rec = admin.call("POST", "/integrations/k3/reconcile")
    step(f"对账 客户差异={rec['customer_diff']} 订单差异={rec['order_diff']}")

    # 9. 数据范围 / 权限
    sales_scope = sales.call("GET", "/customers?page=1&page_size=1")
    admin_scope = admin.call("GET", "/customers?page=1&page_size=1")
    step(f"数据范围：业务员可见客户 {sales_scope['total']} 个 / 管理员可见 {admin_scope['total']} 个")

    audit = admin.call("GET", "/audit-logs?page=1&page_size=1")
    step(f"审计日志累计 {audit['total']} 条")

    print("\n[PASS] 端到端全链路通过")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"\n[FAIL] {exc}")
        sys.exit(1)
