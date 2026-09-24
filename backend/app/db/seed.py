"""初始化数据：权限、角色、部门、管理员、功能开关、字典、编号规则。

用法：
    python -m app.db.seed            # 仅写入种子数据（表需已存在）
    python -m app.db.seed --create   # 先建表再写种子数据（开发快捷方式）
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

from sqlalchemy import delete, select

from app.core.permissions import PERMISSIONS, ROLE_TEMPLATES
from app.core.security import hash_password
from app.db.base import Base
from app.db.session import async_session_factory, engine
from app.models import (
    Activity,
    Company,
    Contact,
    DataScope,
    Department,
    Dictionary,
    EmailAccount,
    FeatureFlag,
    Lead,
    NumberSequence,
    Opportunity,
    Permission,
    PricingRule,
    Product,
    Role,
    RolePermission,
    Sku,
    SystemConfig,
    Task,
    User,
    UserRole,
)
from app.models.support import NumberSequence as Seq
from app.services import company_code

DEFAULT_DEPARTMENTS: list[dict[str, Any]] = [
    {"code": "HQ", "name": "总部", "parent": None, "sort": 1},
    {"code": "SALES", "name": "外贸销售部", "parent": "HQ", "sort": 10},
    {"code": "SALES-1", "name": "销售一组", "parent": "SALES", "sort": 11},
    {"code": "SALES-2", "name": "销售二组", "parent": "SALES", "sort": 12},
    {"code": "PRICING", "name": "核价部", "parent": "HQ", "sort": 20},
    {"code": "FINANCE", "name": "财务部", "parent": "HQ", "sort": 30},
    {"code": "IT", "name": "信息技术部", "parent": "HQ", "sort": 40},
]

DEFAULT_FLAGS: list[tuple[str, str, str, bool]] = [
    ("module.lead", "线索模块", "M2", False),
    ("module.customer", "客户中心", "M2", False),
    ("module.opportunity", "商机模块", "M3", False),
    ("module.inquiry", "询价模块", "M3", False),
    ("module.pricing", "核价模块", "M4", False),
    ("module.quotation", "报价模块", "M4", False),
    ("module.quotation.pdf", "报价PDF生成", "M4", False),
    ("module.approval", "审批流", "M4", False),
    ("module.email", "邮件收发", "M5", False),
    ("module.email.imap", "IMAP 自动接收", "M5", False),
    ("module.k3", "K3 集成", "M6", False),
    ("module.k3.write", "K3 写入同步", "M6", False),
    ("integration.twenty", "Twenty CRM 集成", "可选", False),
]

DEFAULT_DICTIONARIES: list[tuple[str, str, str, int]] = [
    ("customer_level", "A类客户", "A", 1),
    ("customer_level", "B类客户", "B", 2),
    ("customer_level", "C类客户", "C", 3),
    ("customer_level", "D类客户", "D", 4),
    ("customer_source", "展会", "EXHIBITION", 1),
    ("customer_source", "云渠通", "YUNQUTONG", 2),
    ("customer_source", "官网", "WEBSITE", 3),
    ("customer_source", "主动开发", "OUTBOUND", 4),
    ("customer_status", "正常", "ACTIVE", 1),
    ("customer_status", "停用", "INACTIVE", 2),
    ("customer_status", "黑名单", "BLACKLIST", 3),
    ("currency", "美元", "USD", 1),
    ("currency", "人民币", "CNY", 2),
    ("currency", "欧元", "EUR", 3),
    ("incoterm", "FOB", "FOB", 1),
    ("incoterm", "CIF", "CIF", 2),
    ("incoterm", "EXW", "EXW", 3),
    ("lead_status", "待分配", "NEW", 1),
    ("lead_status", "已分配", "ASSIGNED", 2),
    ("lead_status", "已转化", "CONVERTED", 3),
    ("lead_status", "无效", "INVALID", 4),
]

DEFAULT_CONFIGS: list[tuple[str, str, str, str]] = [
    ("company.name", "示例外贸有限公司", "general", "公司名称（用于报价单抬头）"),
    (
        "company.address",
        "浙江省宁波市XX工业园区XX路XX号",
        "general",
        "公司地址（报价单 Add 行）",
    ),
    ("company.contact", "Email:sales@example.com  Website:www.example.com", "general", "联系方式（报价单抬头）"),
    ("quotation.valid_days", "30", "quotation", "报价单默认有效期（天）"),
    ("quotation.default_currency", "RMB", "quotation", "报价单默认币种"),
    ("pricing.default_margin", "0.25", "pricing", "核价默认目标利润率"),
]

DEFAULT_SEQUENCES: list[tuple[str, str, str, str]] = [
    ("opportunity", "商机编号", "{YYYYMM}-{0000}", "MONTH"),
    ("inquiry", "询价编号", "{YYYYMM}-{0000}", "MONTH"),
    ("quotation", "报价编号", "{YYYYMM}-{0000}", "MONTH"),
    ("order", "订单编号", "{YYYYMM}-{0000}", "MONTH"),
    ("company", "客户编码", "{0000}", "NEVER"),
]

DEFAULT_USERS: list[tuple[str, str, str, str, bool, str]] = [
    ("admin", "admin123", "系统管理员", "admin", True, "HJ001"),
    ("boss", "boss123", "总经理", "boss", False, "HJ002"),
    ("manager", "manager123", "销售主管", "manager", False, "HJ003"),
    ("pricing", "pricing123", "核价员李四", "pricing", False, "HJ004"),
    ("sales", "sales123", "业务员张三", "sales", False, "HJ005"),
]


async def _create_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("[seed] 表结构已创建")


async def seed() -> None:
    async with async_session_factory() as db:
        # ---------- 权限 ----------
        existing = {p.code: p for p in (await db.execute(select(Permission))).scalars().all()}
        for item in PERMISSIONS:
            if item["code"] in existing:
                continue
            db.add(
                Permission(
                    code=item["code"],
                    name=item["name"],
                    module=item["code"].split(":")[0],
                    type=item.get("type", "MENU"),
                    path=item.get("path"),
                    icon=item.get("icon"),
                    sort=item.get("sort", 0),
                )
            )
        await db.flush()
        perm_map = {p.code: p for p in (await db.execute(select(Permission))).scalars().all()}
        print(f"[seed] 权限点 {len(perm_map)} 个")

        # ---------- 部门 ----------
        dept_map: dict[str, Department] = {d.code: d for d in (await db.execute(select(Department))).scalars().all()}
        for d in DEFAULT_DEPARTMENTS:
            if d["code"] in dept_map:
                continue
            parent = dept_map.get(d["parent"]) if d["parent"] else None
            dept = Department(code=d["code"], name=d["name"], sort=d["sort"], parent_id=parent.id if parent else None)
            db.add(dept)
            await db.flush()
            dept_map[d["code"]] = dept
        print(f"[seed] 部门 {len(dept_map)} 个")

        # ---------- 角色 + 权限 + 数据范围 ----------
        for code, tpl in ROLE_TEMPLATES.items():
            role = (await db.execute(select(Role).where(Role.code == code))).scalar_one_or_none()
            if role is None:
                role = Role(
                    code=code,
                    name=tpl["name"],
                    description=tpl["description"],
                    is_system=True,
                    sort=0,
                )
                db.add(role)
                await db.flush()
            await db.execute(delete(RolePermission).where(RolePermission.role_id == role.id))
            if "*" in tpl["permissions"]:
                targets = list(perm_map.values())
            else:
                targets = [perm_map[c] for c in tpl["permissions"] if c in perm_map]
            for perm in targets:
                db.add(RolePermission(role_id=role.id, permission_id=perm.id))

            scope = (await db.execute(select(DataScope).where(DataScope.role_id == role.id))).scalar_one_or_none()
            if scope is None:
                db.add(DataScope(role_id=role.id, scope_type=tpl["scope_type"], department_ids=[]))
            else:
                scope.scope_type = tpl["scope_type"]
        print(f"[seed] 角色 {len(ROLE_TEMPLATES)} 个")

        # ---------- 用户 ----------
        role_map = {r.code: r for r in (await db.execute(select(Role))).scalars().all()}
        for username, password, name, role_code, is_super, user_code in DEFAULT_USERS:
            user = (await db.execute(select(User).where(User.username == username))).scalar_one_or_none()
            if user is not None:
                continue
            dept_code = "IT" if is_super else ("PRICING" if role_code == "pricing" else "SALES")
            user = User(
                username=username,
                code=user_code,
                password_hash=hash_password(password),
                name=name,
                email=f"{username}@example.com",
                department_id=dept_map[dept_code].id,
                is_superuser=is_super,
            )
            db.add(user)
            await db.flush()
            if role_code in role_map:
                db.add(UserRole(user_id=user.id, role_id=role_map[role_code].id))
        print(f"[seed] 用户 {len(DEFAULT_USERS)} 个（默认密码见 README）")

        # ---------- 功能开关 ----------
        flag_codes = {f.code for f in (await db.execute(select(FeatureFlag))).scalars().all()}
        for code, name, milestone, enabled in DEFAULT_FLAGS:
            if code in flag_codes:
                continue
            db.add(
                FeatureFlag(
                    code=code,
                    name=name,
                    description=f"里程碑 {milestone}",
                    enabled=enabled,
                    extra={"milestone": milestone},
                )
            )
        print(f"[seed] 功能开关 {len(DEFAULT_FLAGS)} 个")

        # ---------- 字典 ----------
        if not (await db.execute(select(Dictionary.id).limit(1))).scalar_one_or_none():
            for dict_type, label, value, sort in DEFAULT_DICTIONARIES:
                db.add(Dictionary(dict_type=dict_type, label=label, value=value, sort=sort))
        print(f"[seed] 字典 {len(DEFAULT_DICTIONARIES)} 项")

        # ---------- 系统配置 ----------
        for key, value, group, desc in DEFAULT_CONFIGS:
            if (await db.execute(select(SystemConfig.id).where(SystemConfig.key == key))).scalar_one_or_none():
                continue
            db.add(SystemConfig(key=key, value=value, group=group, description=desc))

        # ---------- 编号规则 ----------
        seq_keys = {s.key for s in (await db.execute(select(Seq))).scalars().all()}
        for key, name, pattern, period in DEFAULT_SEQUENCES:
            if key in seq_keys:
                continue
            db.add(NumberSequence(key=key, name=name, pattern=pattern, reset_period=period))

        await db.commit()

    await seed_master_data()
    print("[seed] 完成")


# ------------------------------------------------------------------ 主数据 / 演示数据

DEFAULT_PRODUCTS: list[dict[str, Any]] = [
    {
        "code": "P-1001",
        "name": "不锈钢保温杯",
        "name_en": "Stainless Steel Vacuum Flask",
        "category": "饮具",
        "unit": "PCS",
        "skus": [
            {"code": "P-1001-500", "spec": "500ml / 304 双层真空", "price": 3.5, "cost": 2.6},
            {"code": "P-1001-750", "spec": "750ml / 304 双层真空", "price": 4.2, "cost": 3.1},
        ],
    },
    {
        "code": "P-2001",
        "name": "硅胶厨房套装",
        "name_en": "Silicone Kitchen Utensil Set",
        "category": "厨具",
        "unit": "SET",
        "skus": [
            {"code": "P-2001-12", "spec": "12 件套 / 食品级硅胶", "price": 6.8, "cost": 4.9},
        ],
    },
    {
        "code": "P-3001",
        "name": "折叠户外椅",
        "name_en": "Folding Camping Chair",
        "category": "户外",
        "unit": "PCS",
        "skus": [
            {"code": "P-3001-AL", "spec": "铝合金 / 承重 120kg", "price": 12.5, "cost": 9.2},
        ],
    },
]

DEFAULT_PRICING_RULES: list[dict[str, Any]] = [
    {
        "code": "RULE-A-CUSTOMER",
        "name": "A 类客户 +2% 利润率",
        "conditions": {"customer_level": "A"},
        "actions": {"margin_delta": 0.02},
        "priority": 100,
    },
    {
        "code": "RULE-BULK",
        "name": "大单（≥5000）让利 3%",
        "conditions": {"quantity": {"gte": 5000}},
        "actions": {"margin_delta": -0.03},
        "priority": 90,
    },
    {
        "code": "RULE-EU",
        "name": "欧洲市场系数 1.05",
        "conditions": {"country": {"in": ["Germany", "France", "Italy", "Spain", "Netherlands"]}},
        "actions": {"price_multiplier": 1.05},
        "priority": 80,
    },
]

DEMO_EMAIL_ACCOUNT = {
    "name": "演示邮箱（模拟收发）",
    "email": "sales@example.com",
    "display_name": "外贸销售部",
    "smtp_host": "demo",
    "imap_host": "demo",
    "is_default": True,
}

DEMO_LEADS: list[dict[str, Any]] = [
    {
        "name": "Nordic Home AB",
        "contact_name": "Erik Lund",
        "email": "erik@nordichome.se",
        "country": "Sweden",
        "source": "EXHIBITION",
        "industry": "家居",
    },
    {
        "name": "Alpine Trading GmbH",
        "contact_name": "Julia Weber",
        "email": "julia@alpine-trading.de",
        "country": "Germany",
        "source": "WEBSITE",
        "industry": "贸易",
    },
    {
        "name": "Sunrise Import Co.",
        "contact_name": "Mike Chen",
        "email": "mike@sunriseimport.com",
        "country": "USA",
        "source": "OUTBOUND",
        "industry": "进口商",
    },
]

DEMO_COMPANIES: list[dict[str, Any]] = [
    {
        "name": "Blue Ocean Trading Ltd.",
        "name_en": "Blue Ocean Trading Ltd.",
        "country": "United Kingdom",
        "industry": "贸易",
        "customer_level": "A",
        "source": "EXHIBITION",
        "website": "www.blueocean-trading.co.uk",
        "contacts": [
            {
                "name": "David Smith",
                "position": "Purchasing Manager",
                "email": "david@blueocean-trading.co.uk",
                "is_primary": True,
            },
            {"name": "Emma Brown", "position": "Assistant", "email": "emma@blueocean-trading.co.uk"},
        ],
    },
    {
        "name": "Rhein Handel GmbH",
        "name_en": "Rhein Handel GmbH",
        "country": "Germany",
        "industry": "批发零售",
        "customer_level": "B",
        "source": "YUNQUTONG",
        "website": "www.rhein-handel.de",
        "contacts": [
            {"name": "Lukas Meyer", "position": "Buyer", "email": "lukas@rhein-handel.de", "is_primary": True},
        ],
    },
]


async def seed_master_data() -> None:
    """产品 / 核价规则 / 邮件账号 / 演示业务数据（幂等）。"""
    async with async_session_factory() as db:
        # 产品 + SKU
        if not (await db.execute(select(Product.id).limit(1))).scalar_one_or_none():
            for item in DEFAULT_PRODUCTS:
                product = Product(
                    code=item["code"],
                    name=item["name"],
                    name_en=item.get("name_en"),
                    category=item.get("category"),
                    unit=item.get("unit", "PCS"),
                )
                db.add(product)
                await db.flush()
                for sku in item["skus"]:
                    db.add(
                        Sku(
                            product_id=product.id,
                            code=sku["code"],
                            spec=sku["spec"],
                            unit=item.get("unit", "PCS"),
                            price=sku["price"],
                            cost=sku["cost"],
                        )
                    )
            print(f"[seed] 产品 {len(DEFAULT_PRODUCTS)} 个（含 SKU）")

        # 核价规则
        if not (await db.execute(select(PricingRule.id).limit(1))).scalar_one_or_none():
            for rule in DEFAULT_PRICING_RULES:
                db.add(
                    PricingRule(
                        code=rule["code"],
                        name=rule["name"],
                        conditions=rule["conditions"],
                        actions=rule["actions"],
                        priority=rule["priority"],
                    )
                )
            print(f"[seed] 核价规则 {len(DEFAULT_PRICING_RULES)} 条")

        # 邮件账号
        if not (await db.execute(select(EmailAccount.id).limit(1))).scalar_one_or_none():
            db.add(EmailAccount(**DEMO_EMAIL_ACCOUNT))
            print("[seed] 邮件账号 1 个（模拟模式）")

        # 线索
        sales = (await db.execute(select(User).where(User.username == "sales"))).scalar_one_or_none()
        dept = (await db.execute(select(Department).where(Department.code == "SALES"))).scalar_one_or_none()

        if sales is not None and not (await db.execute(select(Lead.id).limit(1))).scalar_one_or_none():
            for idx, item in enumerate(DEMO_LEADS, start=1):
                db.add(
                    Lead(
                        lead_no=f"LEAD-202601-{idx:04d}",
                        name=item["name"],
                        contact_name=item.get("contact_name"),
                        email=item.get("email"),
                        country=item.get("country"),
                        industry=item.get("industry"),
                        source=item.get("source", "EXHIBITION"),
                        owner_id=sales.id,
                        department_id=dept.id if dept else None,
                    )
                )
            print(f"[seed] 线索 {len(DEMO_LEADS)} 条")

        # 客户 + 联系人 + 商机 + 跟进 + 任务
        if sales is not None and not (await db.execute(select(Company.id).limit(1))).scalar_one_or_none():
            for idx, item in enumerate(DEMO_COMPANIES, start=1):
                code, owner_seq, global_seq = await company_code.next_company_code(sales)
                company = Company(
                    code=code,
                    owner_seq=owner_seq,
                    global_seq=global_seq,
                    name=item["name"],
                    name_en=item.get("name_en"),
                    country=item.get("country"),
                    currency=item.get("currency", "USD"),
                    industry=item.get("industry"),
                    customer_level=item.get("customer_level"),
                    source=item.get("source"),
                    website=item.get("website"),
                    owner_id=sales.id,
                    department_id=dept.id if dept else None,
                    sync_status="PENDING",
                )
                db.add(company)
                await db.flush()
                await company_code.ensure_primary_code(db, company)
                await company_code.add_currency_code(db, company, company.currency)
                for contact in item["contacts"]:
                    db.add(
                        Contact(
                            company_id=company.id,
                            name=contact["name"],
                            position=contact.get("position"),
                            email=contact.get("email"),
                            is_primary=contact.get("is_primary", False),
                            owner_id=sales.id,
                            department_id=dept.id if dept else None,
                        )
                    )
                opportunity = Opportunity(
                    opportunity_no=f"OPP-202601-{idx:04d}",
                    company_id=company.id,
                    name=f"{item['name']} - 保温杯采购项目",
                    stage="QUALIFIED",
                    estimated_amount=45000 + idx * 5000,
                    currency="USD",
                    product_category="饮具",
                    quantity=10000 + idx * 1000,
                    requirement="客户需要 304 不锈钢双层真空杯，定制 LOGO，FOB 宁波",
                    owner_id=sales.id,
                    department_id=dept.id if dept else None,
                )
                db.add(opportunity)
                await db.flush()
                db.add(
                    Activity(
                        biz_type="OPPORTUNITY",
                        biz_id=opportunity.id,
                        company_id=company.id,
                        opportunity_id=opportunity.id,
                        type="EMAIL",
                        content="发送产品目录与报价区间，客户表示需要样品确认质量。",
                        owner_id=sales.id,
                        department_id=dept.id if dept else None,
                    )
                )
                db.add(
                    Task(
                        title=f"跟进 {item['name']} 样品需求",
                        content="整理样品清单并确认快递费用",
                        biz_type="OPPORTUNITY",
                        biz_id=opportunity.id,
                        assignee_id=sales.id,
                        priority="HIGH",
                        owner_id=sales.id,
                        department_id=dept.id if dept else None,
                    )
                )
            print(f"[seed] 客户 {len(DEMO_COMPANIES)} 个（含联系人/商机/跟进/任务）")

        await db.commit()


async def main() -> None:
    if "--create" in sys.argv:
        await _create_tables()
    await seed()
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
